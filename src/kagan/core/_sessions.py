import asyncio
import contextlib
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, TypedDict, cast

from acp.schema import ToolCallStart
from loguru import logger
from sqlalchemy import Engine
from sqlmodel import desc, select

from kagan.core import git
from kagan.core._agent import (
    get_backend,
    resolve_default_agent_backend,
    spawn_agent,
    spawn_agent_via_acp,
    unregister_spawned_process,
)
from kagan.core._db import default_db_path
from kagan.core._db_helpers import _add_and_refresh, _db_async, _db_sync, _setting_enabled, _utc_now
from kagan.core._events import BoardEvent, Events
from kagan.core._launchers import get_launcher
from kagan.core._prompts import (
    build_persona_section,
    get_persona_prompt,
    resolve_review_prompt,
    resolve_task_prompt,
)
from kagan.core._repetition_guard import RepetitionGuard
from kagan.core.enums import (
    BranchRefStrategy,
    SessionEventType,
    SessionStatus,
    TaskStatus,
)
from kagan.core.errors import (
    AgentError,
    AgentRateLimitError,
    AgentRepetitionError,
    AgentTimeoutError,
    ConfigurationError,
    SessionError,
    WorktreeError,
)
from kagan.core.models import Repository, Session, SessionEvent, Setting, Task, TaskNote, Worktree


class DetachResult(TypedDict):
    task_id: str
    status: str
    ready_for_review: bool
    pending_changes: bool
    base_branch: str


def _terminate_process(pid: int) -> None:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        PROCESS_TERMINATE = 0x0001
        handle = kernel32.OpenProcess(PROCESS_TERMINATE, False, pid)
        if handle:
            kernel32.TerminateProcess(handle, 1)
            kernel32.CloseHandle(handle)
    else:
        os.kill(pid, signal.SIGTERM)


def _process_exists(pid: int) -> bool:
    if sys.platform == "win32":
        import ctypes

        kernel32 = ctypes.windll.kernel32
        SYNCHRONIZE = 0x00100000
        handle = kernel32.OpenProcess(SYNCHRONIZE, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    else:
        try:
            os.kill(pid, 0)
            return True
        except ProcessLookupError:
            return False


def _is_shutdown_runtime_error(exc: RuntimeError) -> bool:
    message = str(exc)
    return "Executor shutdown has been called" in message or "Event loop is closed" in message


def _build_attached_startup_prompt(task: Task) -> str:
    description = (task.description or "").strip()
    criteria = [item.strip() for item in task.acceptance_criteria if item and item.strip()]

    lines = [
        f"# Interactive Task: {task.id} — {task.title}",
        "",
        "Act as a Senior Developer collaborating on this implementation.",
        "",
        "## Task Overview",
        f"**Title:** {task.title}",
        "",
    ]
    if description:
        lines.extend([f"**Description:** {description}", ""])
    if criteria:
        lines.append("## Acceptance Criteria")
        lines.extend(f"- {item}" for item in criteria)
        lines.append("")
    lines.extend(
        [
            "## Important Rules",
            "- You are in a git worktree, NOT the main repository",
            "- Only modify files within this worktree",
            "- COMMIT all changes before finishing (semantic commits: feat:, fix:, docs:, etc.)",
            "- When complete: commit your work, then call `run_update` with action `detach`",
            "- Your tools are available via the connected MCP server (WORKER role)",
            "",
            "## Coordination Workflow",
            "",
            "Before implementing:",
            "1. Call `task_list` to check for parallel IN_PROGRESS tasks",
            "2. Review concurrent tasks to avoid overlapping file modifications",
            "3. Call `task_events` on related completed tasks to learn from prior work",
            "",
            "## Completion",
            "",
            "1. Implement and verify against acceptance criteria",
            "2. Commit with clear WHY-focused message",
            "3. Call `run_update` with action `detach` to signal completion",
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _classify_agent_error(exc: BaseException) -> str:
    """Return a classification string for AGENT_FAILED payloads."""
    if isinstance(exc, AgentRepetitionError):
        return "repetition"
    if isinstance(exc, AgentTimeoutError):
        return "timeout"
    if isinstance(exc, AgentRateLimitError):
        return "rate_limit"
    msg = str(exc).lower()
    if "rate limit" in msg or "rate_limit" in msg or "429" in msg:
        return "rate_limit"
    if "timeout" in msg or "timed out" in msg:
        return "timeout"
    return "unknown"


class Sessions:
    def __init__(
        self,
        engine: Engine,
        events: Events,
        *,
        get_task: Callable[[str], Awaitable[Task]],
        set_status: Callable[[str, TaskStatus], Task],
        ensure_workspace: Callable[[str], Awaitable[Worktree]],
        db_path: Path | None = None,
    ) -> None:
        self._engine = engine
        self._events = events
        self._get_task = get_task
        self._set_status = set_status
        self._ensure_workspace = ensure_workspace
        self._db_path: Path | None = db_path

    async def _fetch_project_learnings(self, project_id: str) -> list[str]:
        """Return up to 20 unique [LEARNING]-prefixed notes for a project (newest first)."""
        stmt = (
            select(TaskNote)
            .where(
                cast("Any", TaskNote.task_id).in_(
                    select(Task.id).where(Task.project_id == project_id)
                )
            )
            .where(cast("Any", TaskNote.content).like("[LEARNING]%"))
            .order_by(desc(cast("Any", TaskNote.created_at)))
            .limit(30)
        )
        notes: list[TaskNote] = await _db_async(self._engine, lambda s: list(s.exec(stmt).all()))
        seen: set[str] = set()
        result: list[str] = []
        for note in notes:
            text = note.content.removeprefix("[LEARNING]").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
                if len(result) >= 20:
                    break
        return result

    async def get_latest(self, task_id: str) -> Session | None:
        return await _db_async(
            self._engine,
            lambda s: s.exec(
                select(Session)
                .where(Session.task_id == task_id)
                .order_by(desc(cast("Any", Session.started_at)))
            ).first(),
        )

    async def list_active(self) -> list[Session]:
        return await _db_async(
            self._engine,
            lambda s: list(
                s.exec(
                    select(Session).where(
                        (Session.status == SessionStatus.PENDING)
                        | (Session.status == SessionStatus.RUNNING)
                    )
                ).all()
            ),
        )

    async def resolve_binding(self, session_id: str) -> tuple[str | None, str | None]:
        def op(s) -> tuple[str | None, str | None]:
            bound = s.get(Session, session_id)
            if bound is None:
                return None, None
            task = s.get(Task, bound.task_id)
            return bound.task_id, (task.project_id if task is not None else None)

        return await _db_async(self._engine, op)

    async def _ref_strategy(self) -> BranchRefStrategy:
        """Read the configured branch-ref resolution strategy from settings."""
        settings = await _db_async(
            self._engine,
            lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
        )
        value = settings.get("worktree_base_ref_strategy", "local_if_ahead")
        try:
            return BranchRefStrategy(value)
        except ValueError:
            return BranchRefStrategy.LOCAL_IF_AHEAD

    async def list_for_task(self, task_id: str) -> list[Session]:
        return await _db_async(
            self._engine,
            lambda s: list(
                s.exec(
                    select(Session)
                    .where(Session.task_id == task_id)
                    .order_by(cast("Any", Session.started_at))
                ).all()
            ),
        )

    async def get_latest_for_task(self, task_id: str) -> Session | None:
        return await _db_async(
            self._engine,
            lambda s: s.exec(
                select(Session)
                .where(Session.task_id == task_id)
                .order_by(desc(cast("Any", Session.started_at)))
            ).first(),
        )

    async def has_active(self, task_id: str) -> bool:
        active_session = await _db_async(
            self._engine,
            lambda s: s.exec(
                select(Session).where(
                    Session.task_id == task_id,
                    cast("Any", Session.status).in_([SessionStatus.PENDING, SessionStatus.RUNNING]),
                )
            ).first(),
        )
        return active_session is not None

    async def active_session_summaries(self, task_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not task_ids:
            return {}

        sessions = await _db_async(
            self._engine,
            lambda s: list(
                s.exec(
                    select(Session)
                    .where(cast("Any", Session.task_id).in_(task_ids))
                    .order_by(desc(cast("Any", Session.started_at)))
                ).all()
            ),
        )

        summaries: dict[str, dict[str, Any]] = {}
        active_statuses = {SessionStatus.PENDING, SessionStatus.RUNNING}
        for session in sessions:
            existing = summaries.get(session.task_id)
            is_active = session.status in active_statuses

            if existing is None:
                summaries[session.task_id] = {
                    "has_history": True,
                    "has_active": is_active,
                    "active_launcher": session.launcher if is_active else None,
                    "latest_launcher": session.launcher,
                }
                continue

            active_launcher = existing.get("active_launcher")
            if active_launcher is None and is_active:
                active_launcher = session.launcher

            summaries[session.task_id] = {
                "has_history": True,
                "has_active": bool(existing.get("has_active")) or is_active,
                "active_launcher": active_launcher,
                "latest_launcher": existing.get("latest_launcher"),
            }

        return summaries

    async def _prepare_session(
        self,
        task_id: str,
        *,
        agent_backend: str,
        persona: str | None = None,
        launcher: str | None = None,
    ) -> tuple[Task, Worktree, Session]:
        task = await self._get_task(task_id)
        ws = await _db_async(
            self._engine,
            lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
        )
        if ws is None:
            ws = await self._ensure_workspace(task_id)
        else:
            # Rebase existing worktrees against current base branch
            await self._rebase_if_enabled(task_id)

        session_obj = Session(
            task_id=task_id,
            agent_backend=agent_backend,
            launcher=launcher,
            persona=persona,
        )
        session_obj = await _db_async(self._engine, lambda s: _add_and_refresh(s, session_obj))

        if task.status == TaskStatus.BACKLOG:
            await asyncio.to_thread(self._set_status, task_id, TaskStatus.IN_PROGRESS)
            await self._events.emit(
                task_id,
                SessionEventType.TASK_STATUS_CHANGED,
                {"from": TaskStatus.BACKLOG.value, "to": TaskStatus.IN_PROGRESS.value},
                session_id=session_obj.id,
            )
        else:
            # No status change, but board still needs to know about the new
            # active session so cards reflect the running state immediately.
            self._events.publish_board(BoardEvent(task_id=task_id, kind="session_started"))

        return task, ws, session_obj

    async def run(
        self,
        task_id: str,
        *,
        agent_backend: str,
        launcher: str | None = None,
        ide: str | None = None,
        persona: str | None = None,
    ):
        task, ws, session_obj = await self._prepare_session(
            task_id,
            agent_backend=agent_backend,
            persona=persona,
            launcher=launcher,
        )

        if launcher is None:
            settings_dict = await _db_async(
                self._engine,
                lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
            )

            project_path = Path(ws.worktree_path)
            if task.status is TaskStatus.REVIEW:
                prompt = resolve_review_prompt(task_id, settings_dict, project_path)
            else:
                learnings = await self._fetch_project_learnings(task.project_id)
                prompt = resolve_task_prompt(task, settings_dict, project_path, learnings=learnings)

            persona_prompt: str | None = None
            if persona:
                persona_prompt = get_persona_prompt(persona, settings_dict)
                if persona_prompt and persona_prompt.strip():
                    prompt = f"{build_persona_section(persona_prompt)}\n\n{prompt}"
            db_path_str = str(self._db_path or default_db_path())
            entry = get_backend(agent_backend)

            if entry.get("supports_acp"):
                pid, reader_task = await spawn_agent_via_acp(
                    agent_backend,
                    Path(ws.worktree_path),
                    prompt,
                    session_id=session_obj.id,
                    task_id=task_id,
                    db_path=db_path_str,
                    project_id=task.project_id,
                    on_session_update=self._make_acp_callback(task_id, session_obj.id),
                )
                await asyncio.to_thread(self._update_session_pid, session_obj.id, pid)
                reader_task.add_done_callback(
                    lambda t: asyncio.create_task(self._handle_acp_done(t, task_id, session_obj.id))
                )
            else:
                pid = await spawn_agent(
                    agent_backend,
                    Path(ws.worktree_path),
                    prompt,
                    session_id=session_obj.id,
                    task_id=task_id,
                    db_path=db_path_str,
                    project_id=task.project_id,
                )
                await asyncio.to_thread(self._update_session_pid, session_obj.id, pid)
                asyncio.create_task(
                    self._monitor_detached(pid, task_id, session_obj.id),
                    name=f"agent-monitor:{task_id}",
                )
            logger.info("Detached session started for task={}", task_id)
            return session_obj

        launch_fn = get_launcher(launcher or "")
        db_path_str = str(self._db_path or default_db_path())
        backend_entry = get_backend(agent_backend)
        backend_executable = backend_entry.get("executable")
        if not backend_executable:
            raise AgentError(f"agent backend {agent_backend!r} has no executable configured")
        startup_prompt = _build_attached_startup_prompt(task)
        agent_cmd = str(backend_executable)
        launch_kwargs: dict[str, Any] = {
            "worktree_path": Path(ws.worktree_path),
            "session_id": session_obj.id,
            "agent_cmd": agent_cmd,
            "agent_backend": agent_backend,
            "db_path": db_path_str,
            "startup_prompt": startup_prompt,
        }
        if ide is not None:
            launch_kwargs["ide"] = ide
        await launch_fn(**launch_kwargs)
        await asyncio.to_thread(self._mark_session_running, session_obj.id)
        logger.info("Interactive session launched for task={}", task_id)
        return session_obj

    async def detach(self, task_id: str) -> DetachResult:
        task = await self._get_task(task_id)

        ws = await _db_async(
            self._engine,
            lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
        )
        if ws is None:
            raise SessionError(
                None, f"Task {task_id!r} has no workspace. Call workspace.provision() first."
            )

        latest_attached_session = await _db_async(
            self._engine,
            lambda s: s.exec(
                select(Session)
                .where(Session.task_id == task_id, cast("Any", Session.launcher).is_not(None))
                .order_by(desc(cast("Any", Session.started_at)))
            ).first(),
        )

        worktree = Path(ws.worktree_path)
        if not worktree.exists():
            raise ConfigurationError(
                f"Workspace path for task {task_id!r} does not exist",
                str(worktree),
            )

        repo = await _db_async(
            self._engine,
            lambda s, repo_id=ws.repo_id: s.get(Repository, repo_id),
        )
        base_branch = task.base_branch or (repo.default_branch if repo else "main")
        short_id = task_id[:8]
        commit_message = f"chore: finalize attached session changes ({short_id})"

        strategy = await self._ref_strategy()
        ready_for_review, pending_before, pending_after = await self._evaluate_review_readiness(
            task_id=task_id,
            worktree=worktree,
            base_branch=base_branch,
            commit_message=commit_message,
            strategy=strategy,
        )

        if ready_for_review:
            if task.status != TaskStatus.REVIEW:
                await asyncio.to_thread(self._set_status, task_id, TaskStatus.REVIEW)
                await self._events.emit(
                    task_id,
                    SessionEventType.TASK_STATUS_CHANGED,
                    {"from": task.status.value, "to": TaskStatus.REVIEW.value},
                    session_id=(
                        latest_attached_session.id if latest_attached_session is not None else None
                    ),
                )
            if latest_attached_session is not None:
                await asyncio.to_thread(self._complete_session, latest_attached_session.id)
            return {
                "task_id": task_id,
                "status": TaskStatus.REVIEW.value,
                "ready_for_review": True,
                "pending_changes": False,
                "base_branch": base_branch,
            }

        if latest_attached_session is not None:
            if pending_before or pending_after:
                await asyncio.to_thread(self._fail_session, latest_attached_session.id)
            else:
                await asyncio.to_thread(self._complete_session, latest_attached_session.id)

        current = await self._get_task(task_id)
        return {
            "task_id": task_id,
            "status": current.status.value,
            "ready_for_review": False,
            "pending_changes": pending_after,
            "base_branch": base_branch,
        }

    async def cancel(self, task_id: str) -> None:
        active = await _db_async(
            self._engine,
            lambda s: s.exec(
                select(Session).where(
                    Session.task_id == task_id,
                    cast("Any", Session.status).in_([SessionStatus.PENDING, SessionStatus.RUNNING]),
                )
            ).first(),
        )
        if active and active.pid:
            try:
                _terminate_process(active.pid)
            except ProcessLookupError:
                pass  # Process already exited
            except PermissionError:
                logger.warning(
                    "Cannot kill agent pid={} (permission denied). "
                    "Process may need manual cleanup.",
                    active.pid,
                )
        if active:
            await unregister_spawned_process(active.id)

            def cancel_op(s):
                obj = s.get(Session, active.id)
                if obj:
                    obj.status = SessionStatus.CANCELLED
                    obj.ended_at = _utc_now()
                    s.add(obj)

            await _db_async(self._engine, cancel_op, commit=True)

        task = await self._get_task(task_id)
        if task.status == TaskStatus.IN_PROGRESS:
            # Check if the agent made useful progress before being cancelled;
            # if the worktree has commits, move to REVIEW instead of BACKLOG.
            next_status = await self._resolve_post_agent_status(task_id)
            if next_status == task.status:
                next_status = TaskStatus.BACKLOG
            await asyncio.to_thread(self._set_status, task_id, next_status)
            await self._events.emit(
                task_id,
                SessionEventType.TASK_STATUS_CHANGED,
                {"from": TaskStatus.IN_PROGRESS.value, "to": next_status.value},
                session_id=active.id if active is not None else None,
            )
        else:
            # No status transition, but board cards need to clear active_session.
            self._events.publish_board(BoardEvent(task_id=task_id, kind="session_ended"))
        logger.info("Cancelled session for task={}", task_id)

    def _update_session_pid(self, session_id: str, pid: int) -> None:
        def op(s):
            obj = s.get(Session, session_id)
            if obj:
                obj.pid = pid
                obj.status = SessionStatus.RUNNING
                s.add(obj)

        _db_sync(self._engine, op, commit=True)

    def _mark_session_running(self, session_id: str) -> None:
        def op(s):
            obj = s.get(Session, session_id)
            if obj and obj.status == SessionStatus.PENDING:
                obj.status = SessionStatus.RUNNING
                s.add(obj)

        _db_sync(self._engine, op, commit=True)

    def _complete_session(self, session_id: str) -> None:
        def op(s):
            obj = s.get(Session, session_id)
            if obj and obj.status in {SessionStatus.PENDING, SessionStatus.RUNNING}:
                obj.status = SessionStatus.COMPLETED
                obj.ended_at = _utc_now()

                # Populate context window fields from the latest UsageUpdate event
                usage_event = s.exec(
                    select(SessionEvent)
                    .where(
                        SessionEvent.session_id == session_id,
                        SessionEvent.event_type == SessionEventType.AGENT_STATUS,
                    )
                    .order_by(desc(SessionEvent.created_at))
                ).first()
                if usage_event and isinstance(usage_event.payload, dict):
                    usage = usage_event.payload.get("usage")
                    if isinstance(usage, dict):
                        obj.context_window_used = usage.get("used")
                        obj.context_window_size = usage.get("size")
                        obj.cost_amount = usage.get("cost")
                        obj.cost_currency = usage.get("cost_currency")

                s.add(obj)

        _db_sync(self._engine, op, commit=True)

    def _fail_session(self, session_id: str) -> None:
        def op(s):
            obj = s.get(Session, session_id)
            if obj and obj.status in {SessionStatus.PENDING, SessionStatus.RUNNING}:
                obj.status = SessionStatus.FAILED
                obj.ended_at = _utc_now()
                s.add(obj)

        _db_sync(self._engine, op, commit=True)

    def _make_acp_callback(self, task_id: str, session_id: str):
        from kagan.core._acp import map_acp_update_to_event

        guard = RepetitionGuard()

        async def on_update(_acp_session_id: str, update: Any) -> None:
            # Check for repetitive tool calls before processing
            if isinstance(update, ToolCallStart):
                tool_name = getattr(update, "name", None) or getattr(update, "title", "unknown")
                arguments = getattr(update, "raw_input", None)
                if guard.check(tool_name, arguments):
                    logger.warning(
                        "Repetitive tool calls detected for task={} session={}; cancelling",
                        task_id,
                        session_id,
                    )
                    # Emit AGENT_FAILED before cancel so subscribers see the
                    # error event before the terminal TASK_STATUS_CHANGED.
                    await self._events.emit(
                        task_id,
                        SessionEventType.AGENT_FAILED,
                        {
                            "error": "Agent detected in tool-call loop; session cancelled",
                            "error_class": "repetition",
                        },
                        session_id=session_id,
                    )
                    await self.cancel(task_id)
                    return

            result = map_acp_update_to_event(update)
            if result is not None:
                event_type, payload = result
                await self._events.emit(
                    task_id,
                    event_type,
                    payload,
                    session_id=session_id,
                    persist=event_type is not SessionEventType.OUTPUT_CHUNK,
                )

        return on_update

    async def _evaluate_review_readiness(
        self,
        *,
        task_id: str,
        worktree: Path,
        base_branch: str,
        commit_message: str,
        strategy: BranchRefStrategy = BranchRefStrategy.LOCAL_IF_AHEAD,
    ) -> tuple[bool, bool, bool]:
        pending_before = False
        pending_after = False

        try:
            pending_before = await git.has_pending_changes(worktree)
        except WorktreeError as exc:
            logger.warning("Pending-change check failed for task={}: {}", task_id, exc)
            return False, True, True

        if pending_before:
            try:
                await git.commit_all(worktree, commit_message)
                logger.info("Auto-committed pending changes for task={}", task_id)
            except WorktreeError as exc:
                logger.warning("Auto-commit failed for task={}: {}", task_id, exc)

        try:
            pending_after = await git.has_pending_changes(worktree)
        except WorktreeError as exc:
            logger.warning("Post-commit pending check failed for task={}: {}", task_id, exc)
            pending_after = True

        has_commits = True
        try:
            has_commits = await git.has_commits_since(worktree, base_branch, strategy=strategy)
        except WorktreeError as exc:
            logger.warning(
                "Commit check failed for task={}, assuming commits exist: {}", task_id, exc,
            )

        ready_for_review = has_commits and not pending_after
        return ready_for_review, pending_before, pending_after

    async def _resolve_post_agent_status(self, task_id: str) -> TaskStatus:
        ws = await _db_async(
            self._engine,
            lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
        )
        if ws is None:
            logger.debug("No workspace for task={}, falling back to BACKLOG", task_id)
            return TaskStatus.BACKLOG

        worktree = Path(ws.worktree_path)
        if not worktree.exists():
            logger.debug("Worktree missing for task={}, falling back to BACKLOG", task_id)
            return TaskStatus.BACKLOG

        repo = await _db_async(
            self._engine,
            lambda s, repo_id=ws.repo_id: s.get(Repository, repo_id),
        )
        base_branch = (await self._get_task(task_id)).base_branch or (
            repo.default_branch if repo else "main"
        )

        short_id = task_id[:8]
        strategy = await self._ref_strategy()
        ready_for_review, pending_before, pending_after = await self._evaluate_review_readiness(
            task_id=task_id,
            worktree=worktree,
            base_branch=base_branch,
            commit_message=f"chore: finalize detached run changes ({short_id})",
            strategy=strategy,
        )
        if ready_for_review:
            return TaskStatus.REVIEW

        if pending_before or pending_after:
            logger.info("Pending changes remain for task={}, staying IN_PROGRESS", task_id)
            return TaskStatus.IN_PROGRESS

        logger.info("No commits found for task={}, moving to BACKLOG", task_id)
        return TaskStatus.BACKLOG

    async def _handle_acp_done(self, task: asyncio.Task, task_id: str, session_id: str) -> None:
        try:
            exc = task.exception() if not task.cancelled() else None
            if exc is not None:
                logger.error("ACP session failed for task={}: {}", task_id, exc)
                await asyncio.to_thread(self._fail_session, session_id)
                await self._events.emit(
                    task_id,
                    SessionEventType.AGENT_FAILED,
                    {"error": str(exc), "error_class": _classify_agent_error(exc)},
                    session_id=session_id,
                )
                # No status transition — notify board so cards clear active_session.
                self._events.publish_board(BoardEvent(task_id=task_id, kind="session_ended"))
            else:
                await asyncio.to_thread(self._complete_session, session_id)
                db_task = await self._get_task(task_id)

                # Retry with success check: if task has a success_command, verify it
                if await self._should_retry(db_task, session_id):
                    return

                transitioned_to_review = False
                if db_task.status == TaskStatus.IN_PROGRESS:
                    next_status = await self._resolve_post_agent_status(task_id)
                    if next_status != db_task.status:
                        await asyncio.to_thread(self._set_status, task_id, next_status)
                        await self._events.emit(
                            task_id,
                            SessionEventType.TASK_STATUS_CHANGED,
                            {"from": TaskStatus.IN_PROGRESS.value, "to": next_status.value},
                            session_id=session_id,
                        )
                        transitioned_to_review = next_status == TaskStatus.REVIEW
                await self._events.emit(
                    task_id,
                    SessionEventType.AGENT_COMPLETED,
                    {},
                    session_id=session_id,
                )
                if not transitioned_to_review:
                    # Board cards need to clear active_session even without
                    # a status transition (e.g. agent completed with no commits).
                    self._events.publish_board(BoardEvent(task_id=task_id, kind="session_ended"))
                if transitioned_to_review:
                    await self._maybe_auto_review(task_id)
        except RuntimeError as exc:
            if _is_shutdown_runtime_error(exc):
                logger.debug(
                    "Skipping ACP completion handling during shutdown for task={} session={}: {}",
                    task_id,
                    session_id,
                    exc,
                )
                return
            raise

    async def _should_retry(self, task: Task, session_id: str) -> bool:
        """Run the task's success_command and retry if it fails. Returns True if retrying."""
        if not task.success_command:
            return False
        if task.max_retries <= 0:
            return False

        # Get current attempt count
        session = await _db_async(self._engine, lambda s: s.get(Session, session_id))
        if session is None:
            return False
        current_attempt = session.attempt

        # Run success_command in the task worktree
        ws = await _db_async(
            self._engine,
            lambda s: s.exec(select(Worktree).where(Worktree.task_id == task.id)).first(),
        )
        cwd = Path(ws.worktree_path) if ws else None
        proc: asyncio.subprocess.Process | None = None
        try:
            proc = await asyncio.create_subprocess_shell(
                task.success_command,
                cwd=cwd,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                _, _stderr = await asyncio.wait_for(proc.communicate(), timeout=60.0)
            except TimeoutError:
                proc.kill()
                await proc.wait()
                raise
            exit_code = proc.returncode
        except (TimeoutError, OSError) as exc:
            logger.warning("Success command failed for task={}: {}", task.id, exc)
            if proc is not None:
                with contextlib.suppress(ProcessLookupError, PermissionError):
                    proc.kill()
                    await proc.wait()
            exit_code = 1

        if exit_code == 0:
            return False

        # Check if we can retry
        if current_attempt >= task.max_retries:
            logger.info(
                "Success check failed for task={} (attempt {}/{}), no more retries",
                task.id,
                current_attempt,
                task.max_retries,
            )
            return False

        logger.info(
            "Success check failed for task={} (attempt {}/{}), retrying",
            task.id,
            current_attempt,
            task.max_retries,
        )

        # Move task back to BACKLOG for retry
        await asyncio.to_thread(self._set_status, task.id, TaskStatus.BACKLOG)
        await self._events.emit(
            task.id,
            SessionEventType.TASK_STATUS_CHANGED,
            {"from": TaskStatus.IN_PROGRESS.value, "to": TaskStatus.BACKLOG.value},
            session_id=session_id,
        )

        # Re-run with incremented attempt
        settings_dict = await _db_async(
            self._engine,
            lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
        )
        backend = task.agent_backend or resolve_default_agent_backend(settings_dict)
        new_session = await self.run(task.id, agent_backend=backend, persona=session.persona)

        # Update the attempt counter on the new session
        def set_attempt(s):
            obj = s.get(Session, new_session.id)
            if obj:
                obj.attempt = current_attempt + 1
                s.add(obj)

        await _db_async(self._engine, set_attempt, commit=True)
        return True

    async def _monitor_detached(self, pid: int, task_id: str, session_id: str) -> None:
        while True:
            await asyncio.sleep(2.0)
            try:
                if not _process_exists(pid):
                    raise ProcessLookupError(pid)
            except ProcessLookupError:
                await unregister_spawned_process(session_id)
                await asyncio.to_thread(self._complete_session, session_id)
                task = await self._get_task(task_id)
                transitioned_to_review = False
                if task.status == TaskStatus.IN_PROGRESS:
                    next_status = await self._resolve_post_agent_status(task_id)
                    if next_status != task.status:
                        await asyncio.to_thread(self._set_status, task_id, next_status)
                        await self._events.emit(
                            task_id,
                            SessionEventType.TASK_STATUS_CHANGED,
                            {"from": TaskStatus.IN_PROGRESS.value, "to": next_status.value},
                            session_id=session_id,
                        )
                        transitioned_to_review = next_status == TaskStatus.REVIEW
                await self._events.emit(
                    task_id,
                    SessionEventType.AGENT_COMPLETED,
                    {},
                    session_id=session_id,
                )
                if not transitioned_to_review:
                    self._events.publish_board(BoardEvent(task_id=task_id, kind="session_ended"))
                if transitioned_to_review:
                    await self._maybe_auto_review(task_id)
                logger.info("Detached agent exited, session={} task={}", session_id, task_id)
                return
            except PermissionError:
                continue

    async def _maybe_auto_review(self, task_id: str) -> None:
        settings = await _db_async(
            self._engine,
            lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
        )
        if not _setting_enabled(settings, "auto_review", default=True):
            return

        task = await self._get_task(task_id)
        criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
        if not criteria:
            logger.info("Skipping auto-review for task={}: no acceptance criteria", task_id)
            return

        # Clear stale verdicts before starting fresh review
        def clear_verdicts(s) -> None:
            db_task = s.get(Task, task_id)
            if db_task is not None:
                db_task.review_verdicts = []
                db_task.updated_at = _utc_now()
                s.add(db_task)

        await _db_async(self._engine, clear_verdicts, commit=True)

        backend = task.agent_backend or resolve_default_agent_backend(settings)

        await self._events.emit(
            task_id,
            SessionEventType.AUTO_REVIEW_STARTED,
            {"agent_backend": backend},
        )

        try:
            await self.run(task_id, agent_backend=backend)
            logger.info("Auto-review launched for task={}", task_id)
        except (AgentError, SessionError, ConfigurationError, WorktreeError, OSError) as exc:
            logger.warning("Auto-review failed for task={}: {}", task_id, exc)
            await self._events.emit(
                task_id,
                SessionEventType.AGENT_FAILED,
                {"error": f"Auto-review failed: {exc}"},
            )

    async def _rebase_if_enabled(self, task_id: str) -> None:
        settings = await _db_async(
            self._engine,
            lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
        )
        # Check if auto-rebase is enabled (default: True for local_if_ahead policy)
        raw_strategy = settings.get("worktree_base_ref_strategy", "local_if_ahead")
        try:
            strategy = BranchRefStrategy(raw_strategy)
        except ValueError:
            strategy = BranchRefStrategy.LOCAL_IF_AHEAD
        if strategy != BranchRefStrategy.LOCAL_IF_AHEAD:
            return

        ws = await _db_async(
            self._engine,
            lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
        )
        if ws is None:
            return

        task = await self._get_task(task_id)
        repo = await _db_async(
            self._engine,
            lambda s, repo_id=ws.repo_id: s.get(Repository, repo_id),
        )
        target_branch = task.base_branch or (repo.default_branch if repo else "main")

        try:
            await git.rebase(ws.worktree_path, target_branch=target_branch)
            logger.debug("Rebased task={} onto latest {}", task_id, target_branch)
        except WorktreeError as exc:
            # Log but don't fail - let the agent handle conflicts if they occur
            logger.warning("Rebase failed for task={}: {}", task_id, exc)
            await self._events.emit(
                task_id,
                SessionEventType.PLAN_UPDATE,
                {
                    "op": "rebase",
                    "status": "failed",
                    "target_branch": target_branch,
                    "error": str(exc),
                },
            )


__all__ = ["DetachResult", "Sessions"]
