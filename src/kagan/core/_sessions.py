import asyncio
import os
import signal
import sys
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any, cast

from loguru import logger
from sqlalchemy import Engine
from sqlmodel import desc, select

from kagan.core import git
from kagan.core._agent import (
    get_backend,
    spawn_agent,
    spawn_agent_via_acp,
    unregister_spawned_process,
)
from kagan.core._db import default_db_path
from kagan.core._db_helpers import _add_and_refresh, _db_async, _db_sync, _utc_now
from kagan.core._events import Events
from kagan.core._launchers import get_launcher
from kagan.core._prompts import PROMPT_TASK_KEY, build_persona_section, get_persona_prompt
from kagan.core.enums import SessionEventType, SessionStatus, TaskStatus, WorkMode
from kagan.core.errors import (
    AgentError,
    ConfigurationError,
    PreflightError,
    SessionError,
    WorktreeError,
)
from kagan.core.models import Repository, Session, Setting, Task, Worktree


def _terminate_process(pid: int) -> None:
    """Terminate a process cross-platform."""
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
    """Check if a process exists cross-platform."""
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


def _build_auto_run_prompt(
    task: Task,
    *,
    custom_instructions: str | None = None,
    persona_prompt: str | None = None,
) -> str:
    description = (task.description or "").strip()
    lines = [
        f"Task: {task.title}",
        "",
    ]
    if description:
        lines.extend(["Description:", description, ""])

    criteria = [item.strip() for item in task.acceptance_criteria if item and item.strip()]
    if criteria:
        lines.append("Acceptance Criteria (EVERY item must pass):")
        lines.extend(f"- {item}" for item in criteria)
        lines.append("")
        lines.extend(
            [
                "EXPECTED OUTCOME:",
                "All acceptance criteria above are satisfied. Tests pass. No regressions.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "EXPECTED OUTCOME:",
                "Task completed as described. Code compiles and tests pass.",
                "Note: this task has no acceptance criteria — it will require manual human review.",
                "",
            ]
        )

    lines.extend(
        [
            "MUST DO:",
            "- Commit ALL changes before signaling completion.",
            "- Run the project's test/lint commands if they exist.",
            "- Write a clear commit message explaining WHY, not just what.",
            "",
            "After changing files, run:",
            "git add -A",
            (
                'git -c user.name="'
                f"{git.KAGAN_AGENT_NAME}"
                '" -c user.email="'
                f"{git.KAGAN_AGENT_EMAIL}"
                '" -c commit.gpgsign=false '
                'commit -m "feat: explain why this change was needed"'
            ),
            "",
            "MUST NOT DO:",
            "- Do NOT modify files outside the scope of this task.",
            "- Do NOT delete or skip existing tests to make the build pass.",
            "- Do NOT suppress type errors or linter warnings.",
            "- Do NOT leave uncommitted changes.",
            "",
            "Only signal completion after committing.",
            "If blocked, explain the reason and signal blocked.",
        ]
    )
    base = "\n".join(lines).strip()
    if persona_prompt and persona_prompt.strip():
        base = f"{build_persona_section(persona_prompt)}\n\n{base}"
    if custom_instructions and custom_instructions.strip():
        return f"## Custom Instructions\n\n{custom_instructions.strip()}\n\n{base}"
    return base


def _build_pair_startup_prompt(task: Task) -> str:
    description = (task.description or "").strip()
    criteria = [item.strip() for item in task.acceptance_criteria if item and item.strip()]

    lines = [
        f"PAIR Task: {task.id} — {task.title}",
        "",
        "You are in a Kagan task worktree.",
        "Read `.kagan/start_prompt.md` and follow it as the execution contract.",
        "",
        "Execution Rules:",
        "- Start with a brief plan (3-5 bullets), then implement.",
        "- Use available MCP tools to inspect task/session state and record progress.",
        "- Keep the user updated with concise progress and verification results.",
        "- Commit changes with a clear WHY-focused message before claiming completion.",
        "- Self-check against acceptance criteria, then report ready for REVIEW.",
        "",
    ]
    if description:
        lines.extend(["Description:", description, ""])
    if criteria:
        lines.append("Acceptance criteria:")
        lines.extend(f"- {item}" for item in criteria)
        lines.append("")
    lines.append(
        "Start now: propose a brief plan, then implement, verify, commit, and report for review."
    )
    return "\n".join(lines).strip() + "\n"


class Sessions:
    def __init__(
        self,
        engine: Engine,
        events: Events,
        *,
        get_task: Callable[[str], Awaitable[Task]],
        set_status: Callable[[str, TaskStatus], Task],
        db_path: Path | None = None,
    ) -> None:
        self._engine = engine
        self._events = events
        self._get_task = get_task
        self._set_status = set_status
        self._db_path: Path | None = db_path

    async def _ref_strategy(self) -> str:
        """Read the configured branch-ref resolution strategy from settings."""
        settings = await _db_async(
            self._engine,
            lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
        )
        value = settings.get("worktree_base_ref_strategy", "local_if_ahead")
        if value in {"local", "remote", "local_if_ahead"}:
            return value
        return "local_if_ahead"

    async def _prepare_session(
        self,
        task_id: str,
        *,
        mode: WorkMode,
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
            raise SessionError(
                None, f"Task {task_id!r} has no workspace. Call workspace.provision() first."
            )

        # Rebase onto latest base branch before starting (local_if_ahead policy)
        await self._rebase_if_enabled(task_id)

        session_obj = Session(
            task_id=task_id,
            mode=mode,
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

        return task, ws, session_obj

    async def run(self, task_id: str, *, agent_backend: str, persona: str | None = None):
        task, ws, session_obj = await self._prepare_session(
            task_id,
            mode=WorkMode.AUTO,
            agent_backend=agent_backend,
            persona=persona,
        )

        custom_task_prompt: str | None = None
        settings_dict = await _db_async(
            self._engine,
            lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
        )
        raw_custom = settings_dict.get(PROMPT_TASK_KEY, "").strip()
        if raw_custom:
            custom_task_prompt = raw_custom
        persona_prompt: str | None = None
        if persona:
            persona_prompt = get_persona_prompt(persona, settings_dict)
        prompt = _build_auto_run_prompt(
            task,
            custom_instructions=custom_task_prompt,
            persona_prompt=persona_prompt,
        )
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
        logger.info("Agent session started for task={}", task_id)
        return session_obj

    async def pair(
        self,
        task_id: str,
        *,
        agent_backend: str,
        launcher: str,
        ide: str | None = None,
        persona: str | None = None,
    ):
        task, ws, session_obj = await self._prepare_session(
            task_id,
            mode=WorkMode.PAIR,
            agent_backend=agent_backend,
            persona=persona,
            launcher=launcher,
        )

        launch_fn = get_launcher(launcher)
        db_path_str = str(self._db_path or default_db_path())
        backend_entry = get_backend(agent_backend)
        backend_executable = backend_entry.get("executable")
        if not backend_executable:
            raise AgentError(f"agent backend {agent_backend!r} has no executable configured")
        startup_prompt = _build_pair_startup_prompt(task)
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
        logger.info("PAIR session launched for task={}", task_id)
        return session_obj

    async def finish_pair(self, task_id: str) -> dict[str, Any]:
        task = await self._get_task(task_id)
        if task.execution_mode is not WorkMode.PAIR:
            raise PreflightError("PAIR finish is only valid for tasks in PAIR execution mode.")

        ws = await _db_async(
            self._engine,
            lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
        )
        if ws is None:
            raise SessionError(
                None, f"Task {task_id!r} has no workspace. Call workspace.provision() first."
            )

        latest_pair_session = await _db_async(
            self._engine,
            lambda s: s.exec(
                select(Session)
                .where(Session.task_id == task_id, Session.mode == WorkMode.PAIR)
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
        commit_message = f"chore: finalize pair session changes ({short_id})"

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
                    session_id=latest_pair_session.id if latest_pair_session is not None else None,
                )
            if latest_pair_session is not None:
                await asyncio.to_thread(self._complete_session, latest_pair_session.id)
            return {
                "task_id": task_id,
                "status": TaskStatus.REVIEW.value,
                "ready_for_review": True,
                "pending_changes": False,
                "base_branch": base_branch,
            }

        if latest_pair_session is not None:
            if pending_before or pending_after:
                await asyncio.to_thread(self._fail_session, latest_pair_session.id)
            else:
                await asyncio.to_thread(self._complete_session, latest_pair_session.id)

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
            await asyncio.to_thread(self._set_status, task_id, TaskStatus.BACKLOG)
            await self._events.emit(
                task_id,
                SessionEventType.TASK_STATUS_CHANGED,
                {"from": TaskStatus.IN_PROGRESS.value, "to": TaskStatus.BACKLOG.value},
                session_id=active.id if active is not None else None,
            )
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

        async def on_update(_acp_session_id: str, update: Any) -> None:
            result = map_acp_update_to_event(update)
            if result is not None:
                event_type, payload = result
                await self._events.emit(task_id, event_type, payload, session_id=session_id)

        return on_update

    async def _evaluate_review_readiness(
        self,
        *,
        task_id: str,
        worktree: Path,
        base_branch: str,
        commit_message: str,
        strategy: str = "local_if_ahead",
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

        has_commits = False
        try:
            has_commits = await git.has_commits_since(worktree, base_branch, strategy=strategy)
        except WorktreeError as exc:
            logger.debug("Commit check failed for task={}: {}", task_id, exc)

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
            commit_message=f"chore: finalize auto run changes ({short_id})",
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
        exc = task.exception() if not task.cancelled() else None
        if exc is not None:
            logger.error("ACP session failed for task={}: {}", task_id, exc)
            await asyncio.to_thread(self._fail_session, session_id)
            await self._events.emit(
                task_id,
                SessionEventType.AGENT_FAILED,
                {"error": str(exc)},
                session_id=session_id,
            )
        else:
            await asyncio.to_thread(self._complete_session, session_id)
            db_task = await self._get_task(task_id)
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
            await self._events.emit(
                task_id,
                SessionEventType.AGENT_COMPLETED,
                {},
                session_id=session_id,
            )

    async def _monitor_detached(self, pid: int, task_id: str, session_id: str) -> None:
        while True:
            await asyncio.sleep(2.0)
            try:
                if not _process_exists(pid):
                    raise ProcessLookupError(pid)
            except ProcessLookupError:
                await asyncio.to_thread(self._complete_session, session_id)
                task = await self._get_task(task_id)
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
                await self._events.emit(
                    task_id,
                    SessionEventType.AGENT_COMPLETED,
                    {},
                    session_id=session_id,
                )
                logger.info("Detached agent exited, session={} task={}", session_id, task_id)
                return
            except PermissionError:
                continue

    async def _rebase_if_enabled(self, task_id: str) -> None:
        """Rebase worktree onto latest base branch before starting task.

        This implements the local_if_ahead policy: when a user switches branches
        and starts a task, the worktree is automatically rebased onto the latest
        version of the current branch.
        """

        settings = await _db_async(
            self._engine,
            lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
        )
        # Check if auto-rebase is enabled (default: True for local_if_ahead policy)
        strategy = settings.get("worktree_base_ref_strategy", "local_if_ahead")
        if strategy != "local_if_ahead":
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


__all__ = ["Sessions"]
