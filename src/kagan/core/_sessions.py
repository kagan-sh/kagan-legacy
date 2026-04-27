import asyncio
import contextlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import Any

from acp.schema import ToolCallStart, UsageUpdate
from loguru import logger
from sqlalchemy import Engine
from sqlmodel import desc, select

from kagan.core._agent import (
    BackendCapability,
    get_backend_spec,
    resolve_default_agent_backend,
    spawn_agent,
    spawn_agent_via_acp,
    unregister_spawned_process,
)
from kagan.core._agent_monitor import (
    evaluate_review_readiness,
    rebase_if_enabled,
    ref_strategy,
    resolve_post_agent_status,
)
from kagan.core._analytics import emit_telemetry
from kagan.core._compaction import ContextCompactor
from kagan.core._db import default_db_path
from kagan.core._db_helpers import (
    _add_and_refresh,
    _col,
    _db_async,
    _db_sync,
    _setting_enabled,
    _utc_now,
)
from kagan.core._events import BoardEvent, Events
from kagan.core._hooks import HookAction, HookContext, HookEvent, HookRunner
from kagan.core._launchers import get_launcher
from kagan.core._prompts import (
    build_persona_section,
    get_persona_prompt,
    resolve_review_prompt,
    resolve_task_prompt,
)
from kagan.core._session_helpers import (
    DetachResult,
    agent_timeout_seconds,
    build_attached_startup_prompt,
    classify_agent_error,
    is_shutdown_runtime_error,
    process_exists,
    terminate_process,
)
from kagan.core.enums import (
    AgentRole,
    SessionEventType,
    SessionStatus,
    TaskStatus,
)
from kagan.core.errors import (
    AgentError,
    ConfigurationError,
    SessionError,
    WorktreeError,
)
from kagan.core.models import (
    AcceptanceCriterion,
    Project,
    Repository,
    ReviewVerdict,
    Session,
    SessionEvent,
    Setting,
    Task,
    TaskNote,
    Worktree,
)

# ---------------------------------------------------------------------------
# Module-level query functions
# ---------------------------------------------------------------------------


async def fetch_project_learnings(engine: Engine, project_id: str) -> list[str]:
    """Return up to 20 unique [LEARNING]-prefixed notes for a project (newest first)."""
    stmt = (
        select(TaskNote)
        .where(_col(TaskNote.task_id).in_(select(Task.id).where(Task.project_id == project_id)))
        .where(_col(TaskNote.content).like("[LEARNING]%"))
        .order_by(desc(_col(TaskNote.created_at)))
        .limit(30)
    )
    notes: list[TaskNote] = await _db_async(engine, lambda s: list(s.exec(stmt).all()))
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


async def get_latest_session(engine: Engine, task_id: str) -> Session | None:
    return await _db_async(
        engine,
        lambda s: s.exec(
            select(Session)
            .where(Session.task_id == task_id)
            .order_by(desc(_col(Session.started_at)))
        ).first(),
    )


async def list_active_sessions(engine: Engine) -> list[Session]:
    return await _db_async(
        engine,
        lambda s: list(
            s.exec(
                select(Session).where(
                    (Session.status == SessionStatus.PENDING)
                    | (Session.status == SessionStatus.RUNNING)
                )
            ).all()
        ),
    )


async def resolve_session_binding(engine: Engine, session_id: str) -> tuple[str | None, str | None]:
    def op(s) -> tuple[str | None, str | None]:
        bound = s.get(Session, session_id)
        if bound is None:
            return None, None
        task = s.get(Task, bound.task_id)
        return bound.task_id, (task.project_id if task is not None else None)

    return await _db_async(engine, op)


async def list_task_sessions(engine: Engine, task_id: str) -> list[Session]:
    return await _db_async(
        engine,
        lambda s: list(
            s.exec(
                select(Session).where(Session.task_id == task_id).order_by(_col(Session.started_at))
            ).all()
        ),
    )


async def get_latest_task_session(engine: Engine, task_id: str) -> Session | None:
    return await _db_async(
        engine,
        lambda s: s.exec(
            select(Session)
            .where(Session.task_id == task_id)
            .order_by(desc(_col(Session.started_at)))
        ).first(),
    )


async def has_active_session(engine: Engine, task_id: str) -> bool:
    active_session = await _db_async(
        engine,
        lambda s: s.exec(
            select(Session).where(
                Session.task_id == task_id,
                _col(Session.status).in_([SessionStatus.PENDING, SessionStatus.RUNNING]),
            )
        ).first(),
    )
    return active_session is not None


async def active_session_summaries(
    engine: Engine, task_ids: list[str]
) -> dict[str, dict[str, Any]]:
    if not task_ids:
        return {}

    sessions = await _db_async(
        engine,
        lambda s: list(
            s.exec(
                select(Session)
                .where(_col(Session.task_id).in_(task_ids))
                .order_by(desc(_col(Session.started_at)))
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


def _infer_agent_role(task_status: TaskStatus) -> AgentRole:
    """Infer agent role based on task status context.

    Maps task status to agent role:
    - REVIEW → reviewer (agent is reviewing/approving)
    - IN_PROGRESS → worker (agent is executing/working on the task)
    - Others → worker (default)
    """
    if task_status == TaskStatus.REVIEW:
        return AgentRole.REVIEWER
    return AgentRole.WORKER


async def backfill_agent_roles(engine: Engine) -> int:
    """Backfill agent_role for all sessions without role assignment.

    Infers agent_role for all unassigned sessions based on the associated
    task's status. Returns the count of sessions updated.
    """

    def op(s) -> int:
        unassigned = list(s.exec(select(Session).where(Session.agent_role.is_(None))).all())
        updated_count = 0
        for session in unassigned:
            task = s.get(Task, session.task_id)
            if task is None:
                continue
            role = _infer_agent_role(task.status)
            session.agent_role = role.value
            s.add(session)
            updated_count += 1
        if updated_count > 0:
            s.commit()
        logger.info("Backfilled agent_role for {} sessions", updated_count)
        return updated_count

    return await _db_async(engine, op)


# ---------------------------------------------------------------------------
# Module-level sync DB helpers
# ---------------------------------------------------------------------------


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

    # -- Query delegates (one-liner wrappers) --------------------------------

    async def _fetch_project_learnings(self, project_id: str) -> list[str]:
        return await fetch_project_learnings(self._engine, project_id)

    async def get_latest(self, task_id: str) -> Session | None:
        return await get_latest_session(self._engine, task_id)

    async def list_active(self) -> list[Session]:
        return await list_active_sessions(self._engine)

    async def resolve_binding(self, session_id: str) -> tuple[str | None, str | None]:
        return await resolve_session_binding(self._engine, session_id)

    async def list_for_task(self, task_id: str) -> list[Session]:
        return await list_task_sessions(self._engine, task_id)

    async def get_latest_for_task(self, task_id: str) -> Session | None:
        return await get_latest_task_session(self._engine, task_id)

    async def has_active(self, task_id: str) -> bool:
        return await has_active_session(self._engine, task_id)

    async def active_session_summaries(self, task_ids: list[str]) -> dict[str, dict[str, Any]]:
        return await active_session_summaries(self._engine, task_ids)

    # -- Sync DB helper delegates -------------------------------------------

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

    # -- Orchestration methods (kept on class) ------------------------------

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
            await rebase_if_enabled(task_id, self._engine, self._get_task, self._events)

        # Infer agent role based on task status
        agent_role = _infer_agent_role(task.status)

        session_obj = Session(
            task_id=task_id,
            agent_backend=agent_backend,
            launcher=launcher,
            persona=persona,
            agent_role=agent_role.value,
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
                task_criteria_texts = await _db_async(
                    self._engine,
                    lambda s: [
                        c.text
                        for c in s.exec(
                            select(AcceptanceCriterion).where(
                                AcceptanceCriterion.task_id == task_id
                            )
                        ).all()
                    ],
                )
                prompt = resolve_task_prompt(
                    task,
                    settings_dict,
                    project_path,
                    learnings=learnings,
                    criteria_texts=task_criteria_texts,
                )

            persona_prompt: str | None = None
            if persona:
                persona_prompt = get_persona_prompt(persona, settings_dict)
            if persona_prompt and persona_prompt.strip():
                prompt = f"{build_persona_section(persona_prompt)}\n\n{prompt}"
            db_path_str = str(self._db_path or default_db_path())
            backend_spec = get_backend_spec(agent_backend)

            if backend_spec.has_capability(BackendCapability.ACP_STREAMING):
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
                _raw_timeout = settings_dict.get("agent_timeout_seconds")
                _timeout = agent_timeout_seconds(_raw_timeout)
                pid = await spawn_agent(
                    agent_backend,
                    Path(ws.worktree_path),
                    prompt,
                    session_id=session_obj.id,
                    task_id=task_id,
                    db_path=db_path_str,
                    project_id=task.project_id,
                    timeout_seconds=_timeout,
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
        backend_spec = get_backend_spec(agent_backend)
        criteria_texts = await _db_async(
            self._engine,
            lambda s: [
                c.text
                for c in s.exec(
                    select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task_id)
                ).all()
            ],
        )
        startup_prompt = build_attached_startup_prompt(task, criteria_texts)
        agent_cmd = backend_spec.executable
        launch_kwargs: dict[str, Any] = {
            "worktree_path": Path(ws.worktree_path),
            "session_id": session_obj.id,
            "agent_cmd": agent_cmd,
            "agent_backend": agent_backend,
            "db_path": db_path_str,
            "startup_prompt": startup_prompt,
            "task_id": task_id,
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
                .where(Session.task_id == task_id, _col(Session.launcher).is_not(None))
                .order_by(desc(_col(Session.started_at)))
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

        strategy = await ref_strategy(self._engine)
        ready_for_review, pending_before, pending_after = await evaluate_review_readiness(
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
                    _col(Session.status).in_([SessionStatus.PENDING, SessionStatus.RUNNING]),
                )
            ).first(),
        )
        if active and active.pid:
            try:
                terminate_process(active.pid)
            except ProcessLookupError:
                pass  # Process already exited
            except PermissionError:
                logger.warning(
                    "Cannot kill agent pid={} (permission denied). "
                    "Process may need manual cleanup.",
                    active.pid,
                )
        if active:
            unregister_spawned_process(active.id)

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
            next_status = await resolve_post_agent_status(task_id, self._engine, self._get_task)
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

    def _make_acp_callback(self, task_id: str, session_id: str):
        from kagan.core._acp import map_acp_update_to_event

        runner = HookRunner().default_hooks()
        compactor = ContextCompactor()

        async def on_update(_acp_session_id: str, update: Any) -> None:
            # Fire PRE_TOOL hooks before processing tool call starts
            if isinstance(update, ToolCallStart):
                tool_name = getattr(update, "name", None) or getattr(update, "title", "unknown")
                arguments = getattr(update, "raw_input", None)
                hook_ctx = HookContext(
                    task_id=task_id,
                    session_id=session_id,
                    event=HookEvent.PRE_TOOL,
                    tool_name=tool_name,
                    tool_arguments=arguments,
                )
                hook_result = runner.fire(hook_ctx)
                if hook_result.action == HookAction.CANCEL_SESSION:
                    logger.warning(
                        "Hook blocked tool call for task={} session={}; cancelling",
                        task_id,
                        session_id,
                    )
                    # Emit HOOK_BLOCKED before cancel so subscribers see the
                    # event before the terminal TASK_STATUS_CHANGED.
                    await self._events.emit(
                        task_id,
                        SessionEventType.HOOK_BLOCKED,
                        {
                            "error": hook_result.message or "Hook blocked session",
                            "tool_name": tool_name,
                        },
                        session_id=session_id,
                    )
                    await self.cancel(task_id)
                    return

            if isinstance(update, UsageUpdate):
                used = getattr(update, "used", 0) or 0
                size = getattr(update, "size", 0) or 0
                if compactor.update_usage(used, size):
                    compactor.record_compaction()
                    await self._events.emit(
                        task_id,
                        SessionEventType.COMPACTION_TRIGGERED,
                        {
                            "context_window_used": used,
                            "context_window_size": size,
                            "usage_ratio": compactor.usage_ratio,
                            "compaction_count": compactor.compaction_count,
                        },
                        session_id=session_id,
                    )

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

    async def _handle_acp_done(self, task: asyncio.Task, task_id: str, session_id: str) -> None:
        try:
            exc = task.exception() if not task.cancelled() else None
            if exc is not None:
                logger.error("ACP session failed for task={}: {}", task_id, exc)
                await asyncio.to_thread(self._fail_session, session_id)
                await self._events.emit(
                    task_id,
                    SessionEventType.AGENT_FAILED,
                    {"error": str(exc), "error_class": classify_agent_error(exc)},
                    session_id=session_id,
                )
                await asyncio.to_thread(self._set_status, task_id, TaskStatus.BACKLOG)
                # Notify board so cards clear active_session.
                self._events.publish_board(BoardEvent(task_id=task_id, kind="session_ended"))
            else:
                await asyncio.to_thread(self._complete_session, session_id)
                db_task = await self._get_task(task_id)
                completed_session = await _db_async(
                    self._engine, lambda s: s.get(Session, session_id)
                )
                session_backend = (
                    completed_session.agent_backend if completed_session is not None else ""
                )

                # Emit first_session_success telemetry if this is the very first completion
                await self._maybe_emit_first_session_success(session_id, session_backend)

                # Retry with success check: if task has a success_command, verify it
                if await self._should_retry(db_task, session_id):
                    return

                transitioned_to_review = False
                if db_task.status == TaskStatus.IN_PROGRESS:
                    next_status = await resolve_post_agent_status(
                        task_id, self._engine, self._get_task
                    )
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
            if is_shutdown_runtime_error(exc):
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
        if not task.success_command or not task.success_command.strip():
            return False
        if task.max_retries <= 0:
            return False

        # Get current attempt count
        session = await _db_async(self._engine, lambda s: s.get(Session, session_id))
        if session is None:
            return False
        current_attempt = session.attempt

        # success_command is authored as a shell command, so preserve shell
        # operators such as &&, pipes, redirects, and quoted expansions.
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
                if not process_exists(pid):
                    raise ProcessLookupError(pid)
            except ProcessLookupError:
                unregister_spawned_process(session_id)
                await asyncio.to_thread(self._complete_session, session_id)
                task = await self._get_task(task_id)
                detached_session = await _db_async(
                    self._engine, lambda s: s.get(Session, session_id)
                )
                detached_backend = (
                    detached_session.agent_backend if detached_session is not None else ""
                )
                await self._maybe_emit_first_session_success(session_id, detached_backend)
                transitioned_to_review = False
                if task.status == TaskStatus.IN_PROGRESS:
                    next_status = await resolve_post_agent_status(
                        task_id, self._engine, self._get_task
                    )
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

    async def _maybe_emit_first_session_success(self, session_id: str, agent_backend: str) -> None:
        """Emit FIRST_SESSION_SUCCESS telemetry once when no prior completed sessions exist."""
        from datetime import UTC, datetime

        try:

            def _check_and_get_install_time(s):
                """Return install_at if this is the first completed session, else None."""
                prior = s.exec(
                    select(Session).where(
                        Session.status == SessionStatus.COMPLETED,
                        Session.id != session_id,
                    )
                ).first()
                if prior is not None:
                    return None
                earliest_project = s.exec(select(Project).order_by(Project.created_at)).first()
                return earliest_project.created_at if earliest_project is not None else None

            install_at = await _db_async(self._engine, _check_and_get_install_time)
            if install_at is None:
                return

            now = datetime.now(UTC)
            # install_at may be naive (no tzinfo); normalize to UTC for comparison
            if install_at.tzinfo is None:
                install_at = install_at.replace(tzinfo=UTC)
            seconds_since_install = (now - install_at).total_seconds()

            await emit_telemetry(
                self._engine,
                "FIRST_SESSION_SUCCESS",
                {
                    "backend": agent_backend,
                    "seconds_since_install": round(seconds_since_install, 1),
                },
            )
            logger.info(
                "Emitted first_session_success telemetry: backend={} seconds={}",
                agent_backend,
                round(seconds_since_install, 1),
            )
        except Exception:
            # Telemetry is best-effort; never disrupt the session lifecycle
            logger.opt(exception=True).debug("Failed to emit first_session_success telemetry")

    async def _maybe_auto_review(self, task_id: str) -> None:
        settings = await _db_async(
            self._engine,
            lambda s: {row.key: row.value for row in s.exec(select(Setting)).all()},
        )
        if not _setting_enabled(settings, "auto_review", default=True):
            return

        task = await self._get_task(task_id)

        # Load criteria from the new table
        criteria = await _db_async(
            self._engine,
            lambda s: [
                c.text.strip()
                for c in s.exec(
                    select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task_id)
                ).all()
                if c.text.strip()
            ],
        )
        if not criteria:
            logger.info("Skipping auto-review for task={}: no acceptance criteria", task_id)
            return

        # Clear stale verdicts before starting fresh review
        def clear_verdicts(s) -> None:
            crit_rows = list(
                s.exec(
                    select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task_id)
                ).all()
            )
            criterion_ids = {c.id for c in crit_rows}
            if criterion_ids:
                verdict_rows = list(
                    s.exec(
                        select(ReviewVerdict).where(
                            ReviewVerdict.criterion_id.in_(criterion_ids)  # type: ignore[attr-defined]
                        )
                    ).all()
                )
                for v in verdict_rows:
                    s.delete(v)
            db_task = s.get(Task, task_id)
            if db_task is not None:
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


__all__ = [
    "DetachResult",
    "Sessions",
    "active_session_summaries",
    "fetch_project_learnings",
    "get_latest_session",
    "get_latest_task_session",
    "has_active_session",
    "list_active_sessions",
    "list_task_sessions",
    "resolve_session_binding",
]
