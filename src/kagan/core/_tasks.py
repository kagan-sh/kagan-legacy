import asyncio
import builtins
import contextlib
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from loguru import logger
from sqlalchemy import Engine, desc
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from kagan.core._db_helpers import (
    _add_and_refresh,
    _db_async,
    _db_sync,
    _delete_task_children,
    _utc_now,
)
from kagan.core._events import BoardEvent, Events
from kagan.core._security import scan_text_for_injection
from kagan.core._sessions import DetachResult, Sessions
from kagan.core._transitions import validate_move
from kagan.core._utils import utc_iso
from kagan.core.enums import Priority, SessionEventType, SessionStatus, TaskStatus
from kagan.core.errors import KaganError, NotFoundError, SessionError
from kagan.core.models import AuditEntry, Project, Session, SessionEvent, Task, TaskNote, Worktree

if TYPE_CHECKING:
    from kagan.core.client import KaganCore


_UNSET: Final[object] = object()


class Tasks:
    def __init__(
        self,
        engine: Engine,
        signals: dict[str, asyncio.Event],
        *,
        client: "KaganCore | None" = None,
        db_path: Path | None = None,
    ) -> None:
        self._engine = engine
        self._active_project_id: str | None = None
        self._client = client
        self._db_path = db_path
        self.events = Events(
            engine,
            signals,
            event_bus=client.event_bus if client is not None else None,
        )
        self.sessions = Sessions(
            engine,
            self.events,
            get_task=self.get,
            set_status=self._set_status,
            ensure_workspace=self._ensure_workspace,
            db_path=db_path,
        )

    @staticmethod
    def _serialize_value(value: object) -> object:
        return value.value if isinstance(value, Enum) else value

    @staticmethod
    def _record_task_audit(
        session: Any,
        *,
        action: str,
        task_id: str,
        detail: dict[str, object] | None = None,
    ) -> None:
        session.add(
            AuditEntry(
                action=action,
                entity_type="task",
                entity_id=task_id,
                detail=detail or {},
            )
        )

    def _require_project(self) -> str:
        if self._active_project_id is None:
            raise SessionError(None, "No active project. Call client.projects.set_active() first.")
        return self._active_project_id

    async def _ensure_workspace(self, task_id: str) -> Worktree:
        if self._client is None:
            raise SessionError(None, "Workspace provisioning requires a KaganCore client.")
        return await self._client.worktrees.create(task_id)

    async def run(
        self,
        task_id: str,
        *,
        agent_backend: str,
        launcher: str | None = None,
        ide: str | None = None,
        persona: str | None = None,
    ):
        return await self.sessions.run(
            task_id,
            agent_backend=agent_backend,
            launcher=launcher,
            ide=ide,
            persona=persona,
        )

    async def cancel(self, task_id: str) -> None:
        await self.sessions.cancel(task_id)

    async def detach(self, task_id: str) -> DetachResult:
        return await self.sessions.detach(task_id)

    async def create(
        self,
        title: str,
        *,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        base_branch: str | None = None,
        acceptance_criteria: list[str] | None = None,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> Task:
        project_id = self._require_project()

        for field_name, text in [("title", title), ("description", description)]:
            if text:
                result = scan_text_for_injection(text)
                if result["risk_level"] != "SAFE":
                    logger.warning(
                        "Potential injection detected in task {}: {}",
                        field_name,
                        result["findings"],
                    )

        project_exists = await _db_async(
            self._engine,
            lambda s: s.get(Project, project_id) is not None,
        )
        if not project_exists:
            self._clear_stale_active_project(project_id)
            raise NotFoundError("Project", project_id)

        task = Task(
            project_id=project_id,
            title=title,
            description=description,
            priority=priority,
            base_branch=base_branch,
            acceptance_criteria=acceptance_criteria or [],
            agent_backend=agent_backend,
            launcher=launcher,
        )

        def op(s):
            try:
                s.add(task)
                s.add(AuditEntry(action="task.create", entity_type="task", entity_id=task.id))
                s.commit()
                s.refresh(task)
                logger.debug("Task created id={}", task.id)
                return task
            except IntegrityError as exc:
                s.rollback()
                if "FOREIGN KEY constraint failed" in str(exc.orig):
                    self._clear_stale_active_project(project_id)
                    raise NotFoundError("Project", project_id) from exc
                raise

        created = await _db_async(self._engine, op)
        self.events.publish_board(
            BoardEvent(
                task_id=created.id,
                kind="created",
                title=created.title,
                status=created.status.value,
            )
        )
        return created

    def _clear_stale_active_project(self, project_id: str) -> None:
        if self._active_project_id != project_id:
            return
        self._active_project_id = None
        if self._client is not None and self._client.active_project_id == project_id:
            self._client.active_project_id = None
        logger.warning("Cleared stale active project id={}", project_id)

    async def get(self, task_id: str) -> Task:
        task = await _db_async(self._engine, lambda s: s.get(Task, task_id))
        if task is None:
            raise NotFoundError("Task", task_id)
        return task

    async def list(
        self,
        *,
        status: TaskStatus | None = None,
    ) -> list[Task]:
        project_id = self._require_project()
        stmt = select(Task).where(Task.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        return await _db_async(self._engine, lambda s: list(s.exec(stmt).all()))

    async def update(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: Priority | None = None,
        base_branch: str | None = None,
        acceptance_criteria: builtins.list[str] | None = None,
        agent_backend: str | None = None,
        launcher: str | None | object = _UNSET,
    ) -> Task:
        task = await self.get(task_id)
        updates = {
            "title": title,
            "description": description,
            "priority": priority,
            "base_branch": base_branch,
            "acceptance_criteria": acceptance_criteria,
            "agent_backend": agent_backend,
            "launcher": launcher,
        }
        changed_fields: dict[str, object] = {}

        def op(s):
            db_task = s.get(Task, task.id)
            if db_task is None:
                raise NotFoundError("Task", task.id)
            for field, value in updates.items():
                if value is _UNSET:
                    continue
                if field == "launcher":
                    db_task.launcher = value if isinstance(value, str) else None
                    changed_fields["launcher"] = self._serialize_value(
                        value if isinstance(value, str) else None
                    )
                    continue
                if value is not None:
                    setattr(db_task, field, value)
                    changed_fields[field] = self._serialize_value(value)
            db_task.updated_at = _utc_now()
            if changed_fields:
                self._record_task_audit(
                    s,
                    action="task.update",
                    task_id=task.id,
                    detail={"fields": dict(changed_fields)},
                )
            s.add(db_task)
            s.commit()
            s.refresh(db_task)
            return db_task

        updated = await _db_async(self._engine, op)
        self.events.publish_board(
            BoardEvent(
                task_id=updated.id,
                kind="updated",
                title=updated.title,
                status=updated.status.value,
            )
        )
        return updated

    async def set_status(self, task_id: str, status: TaskStatus) -> Task:
        task = await self.get(task_id)
        validate_move(task.status, status)
        moved = await asyncio.to_thread(self._set_status, task_id, status)
        await self.events.emit(
            task_id,
            SessionEventType.TASK_STATUS_CHANGED,
            {"from": task.status.value, "to": status.value},
        )
        return moved

    def _set_status(self, task_id: str, status: TaskStatus) -> Task:
        def op(s):
            task = s.get(Task, task_id)
            if task is None:
                raise NotFoundError("Task", task_id)
            from_status = task.status
            task.status = status
            if status is not TaskStatus.DONE:
                task.review_approved = False
            task.updated_at = _utc_now()
            self._record_task_audit(
                s,
                action="task.status_change",
                task_id=task_id,
                detail={"from": from_status.value, "to": status.value},
            )
            s.add(task)
            s.commit()
            s.refresh(task)
            logger.info("Task {} moved to {}", task_id, status.value)
            return task

        return _db_sync(self._engine, op)

    async def delete(self, task_id: str) -> None:
        task = await self.get(task_id)
        if self._client is None:
            raise SessionError(None, "Task operations are not attached to a client instance.")
        with contextlib.suppress(KaganError, OSError, RuntimeError):
            await self.sessions.cancel(task_id)
        self.events.publish_board(
            BoardEvent(
                task_id=task_id,
                kind="deleted",
                title=task.title,
                status=task.status.value,
            )
        )
        await self._client.worktrees.cleanup(task_id)

        def op(s):
            _delete_task_children(s, task_id)
            task = s.get(Task, task_id)
            if task:
                self._record_task_audit(
                    s,
                    action="task.delete",
                    task_id=task_id,
                    detail={"status": task.status.value, "title": task.title},
                )
                s.delete(task)

        await _db_async(self._engine, op, commit=True)

    async def search(self, query: str) -> builtins.list[Task]:
        project_id = self._require_project()
        q = query.lower()
        tasks = await _db_async(
            self._engine,
            lambda s: list(s.exec(select(Task).where(Task.project_id == project_id)).all()),
        )
        return [t for t in tasks if q in t.title.lower() or q in t.description.lower()]

    async def build_context(self, task_id: str) -> dict:
        task = await self.get(task_id)
        events = await self.events.list(task_id, limit=10)
        ws = await _db_async(
            self._engine,
            lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
        )
        return {"task": task, "workspace": ws, "recent_events": events}

    async def runtime_summaries(self, task_ids: builtins.list[str]) -> dict[str, dict[str, Any]]:
        task_ids = list(dict.fromkeys(task_ids))
        if not task_ids:
            return {}

        running_statuses = {SessionStatus.PENDING, SessionStatus.RUNNING}

        def op(s):
            worktrees = {
                worktree.task_id
                for worktree in s.exec(
                    select(Worktree).where(cast("Any", Worktree.task_id).in_(task_ids))
                ).all()
            }

            latest_events: dict[str, str] = {}
            for event in s.exec(
                select(SessionEvent)
                .where(cast("Any", SessionEvent.task_id).in_(task_ids))
                .order_by(desc(cast("Any", SessionEvent.created_at)))
            ).all():
                latest_events.setdefault(event.task_id, utc_iso(event.created_at) or "")

            active_sessions: dict[str, dict[str, Any]] = {}
            for session in s.exec(
                select(Session)
                .where(cast("Any", Session.task_id).in_(task_ids))
                .order_by(desc(cast("Any", Session.started_at)))
            ).all():
                if session.status not in running_statuses or session.task_id in active_sessions:
                    continue
                active_sessions[session.task_id] = {
                    "id": session.id,
                    "status": session.status.value,
                    "launcher": session.launcher,
                    "agent_backend": session.agent_backend,
                    "started_at": utc_iso(session.started_at) or "",
                    "context_window_used": session.context_window_used,
                    "context_window_size": session.context_window_size,
                    "cost_amount": session.cost_amount,
                    "cost_currency": session.cost_currency,
                }

            return {
                task_id: {
                    "has_workspace": task_id in worktrees,
                    "last_event_at": latest_events.get(task_id),
                    "active_session": active_sessions.get(task_id),
                }
                for task_id in task_ids
            }

        return await _db_async(self._engine, op)

    async def runtime_summary(self, task_id: str) -> dict[str, Any]:
        return (await self.runtime_summaries([task_id])).get(
            task_id,
            {"has_workspace": False, "last_event_at": None, "active_session": None},
        )

    async def counts(self, *, project_id: str | None = None) -> dict[TaskStatus, int]:
        pid = project_id or self._require_project()
        tasks = await _db_async(
            self._engine,
            lambda s: list(s.exec(select(Task).where(Task.project_id == pid)).all()),
        )
        result: dict[TaskStatus, int] = {s: 0 for s in TaskStatus}
        for task in tasks:
            result[task.status] = result.get(task.status, 0) + 1
        return result

    async def wait_for_completion(
        self,
        task_id: str,
        *,
        timeout: float | None,
        wait_for_status: set[TaskStatus] | None = None,
    ) -> tuple[Task, bool]:
        loop = asyncio.get_running_loop()
        initial = await self.get(task_id)
        targets = wait_for_status or set()

        if targets and initial.status in targets:
            return initial, False

        deadline = None if timeout is None else loop.time() + max(0.0, timeout)
        stream = self.events.stream(task_id)

        while True:
            if deadline is not None and deadline - loop.time() <= 0:
                latest = await self.get(task_id)
                return latest, True

            latest = await self.get(task_id)
            if targets:
                if latest.status in targets:
                    return latest, False
            elif latest.status != initial.status:
                return latest, False

            try:
                wait_window = (
                    5.0 if deadline is None else min(max(0.0, deadline - loop.time()), 5.0)
                )
                event = await asyncio.wait_for(anext(stream), timeout=wait_window)
            except StopAsyncIteration:
                latest = await self.get(task_id)
                if targets:
                    return latest, latest.status not in targets
                return latest, latest.status == initial.status
            except TimeoutError:
                continue

            if event.event_type is not SessionEventType.TASK_STATUS_CHANGED:
                continue

            latest = await self.get(task_id)
            if targets:
                if latest.status in targets:
                    return latest, False
                continue

            if latest.status != initial.status:
                return latest, False

    async def add_note(self, task_id: str, content: str) -> TaskNote:
        await self.get(task_id)
        note = TaskNote(task_id=task_id, content=content)
        return await _db_async(self._engine, lambda s: _add_and_refresh(s, note))

    async def list_notes(self, task_id: str) -> builtins.list[TaskNote]:
        stmt = (
            select(TaskNote)
            .where(TaskNote.task_id == task_id)
            .order_by(cast("Any", TaskNote.created_at))
        )
        return await _db_async(self._engine, lambda s: list(s.exec(stmt).all()))

    async def list_project_learnings(self, project_id: str) -> builtins.list[str]:
        """Return up to 20 unique [LEARNING]-prefixed notes across all tasks in a project.

        Notes are ordered newest-first and deduplicated by content after stripping the prefix.
        Only notes whose content starts with "[LEARNING]" are included.
        """
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
        notes: builtins.list[TaskNote] = await _db_async(
            self._engine, lambda s: list(s.exec(stmt).all())
        )
        seen: set[str] = set()
        result: builtins.list[str] = []
        for note in notes:
            text = note.content.removeprefix("[LEARNING]").strip()
            if text and text not in seen:
                seen.add(text)
                result.append(text)
                if len(result) >= 20:
                    break
        return result


__all__ = ["Tasks"]
