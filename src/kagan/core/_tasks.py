import asyncio
import builtins
import contextlib
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final, cast

from loguru import logger
from sqlalchemy import Engine
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
from kagan.core._sessions import Sessions
from kagan.core._transitions import validate_move
from kagan.core.enums import Priority, SessionEventType, TaskStatus, WorkMode
from kagan.core.errors import KaganError, NotFoundError, SessionError
from kagan.core.models import AuditEntry, Project, Task, TaskNote, Worktree

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
        self.events = Events(engine, signals)
        self.sessions = Sessions(
            engine,
            self.events,
            get_task=self.get,
            set_status=self._set_status,
            db_path=db_path,
        )

    def _require_project(self) -> str:
        if self._active_project_id is None:
            raise SessionError(None, "No active project. Call client.projects.set_active() first.")
        return self._active_project_id

    async def run(self, task_id: str, *, agent_backend: str, persona: str | None = None):
        return await self.sessions.run(task_id, agent_backend=agent_backend, persona=persona)

    async def pair(
        self,
        task_id: str,
        *,
        agent_backend: str,
        launcher: str,
        ide: str | None = None,
        persona: str | None = None,
    ):
        return await self.sessions.pair(
            task_id,
            agent_backend=agent_backend,
            launcher=launcher,
            ide=ide,
            persona=persona,
        )

    async def cancel(self, task_id: str) -> None:
        await self.sessions.cancel(task_id)

    async def end_pairing(self, task_id: str) -> dict[str, Any]:
        return await self.sessions.finish_pair(task_id)

    async def create(
        self,
        title: str,
        *,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        execution_mode: WorkMode = WorkMode.PAIR,
        base_branch: str | None = None,
        acceptance_criteria: list[str] | None = None,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> Task:
        project_id = self._require_project()

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
            execution_mode=execution_mode,
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
        execution_mode: WorkMode | None = None,
    ) -> list[Task]:
        project_id = self._require_project()
        stmt = select(Task).where(Task.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if execution_mode is not None:
            stmt = stmt.where(Task.execution_mode == execution_mode)
        return await _db_async(self._engine, lambda s: list(s.exec(stmt).all()))

    async def update(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: Priority | None = None,
        execution_mode: WorkMode | None = None,
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
            "execution_mode": execution_mode,
            "base_branch": base_branch,
            "acceptance_criteria": acceptance_criteria,
            "agent_backend": agent_backend,
            "launcher": launcher,
        }

        def op(s):
            db_task = s.get(Task, task.id)
            if db_task is None:
                raise NotFoundError("Task", task.id)
            for field, value in updates.items():
                if value is _UNSET:
                    continue
                if field == "launcher":
                    db_task.launcher = value if isinstance(value, str) else None
                    continue
                if value is not None:
                    setattr(db_task, field, value)
            db_task.updated_at = _utc_now()
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
            task.status = status
            if status is not TaskStatus.DONE:
                task.review_approved = False
            task.updated_at = _utc_now()
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


__all__ = ["Tasks"]
