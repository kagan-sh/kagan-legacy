import asyncio
import builtins
import contextlib
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING, Any, Final

from loguru import logger
from sqlalchemy import Engine, desc
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from kagan.core._db_helpers import (
    _add_and_refresh,
    _col,
    _db_async,
    _db_sync,
    _utc_now,
)
from kagan.core._events import BoardEvent, Events, list_events
from kagan.core._security import scan_text_for_injection
from kagan.core._session_helpers import DetachResult
from kagan.core._sessions import Sessions, fetch_project_learnings
from kagan.core._task_classification import classify_task
from kagan.core._transitions import validate_move
from kagan.core._utils import utc_iso
from kagan.core.enums import Priority, SessionEventType, SessionStatus, TaskStatus
from kagan.core.errors import KaganError, NotFoundError, SessionError
from kagan.core.models import (
    AcceptanceCriterion,
    AuditEntry,
    Project,
    Repository,
    Session,
    SessionEvent,
    Task,
    TaskNote,
    Worktree,
)

if TYPE_CHECKING:
    from kagan.core.client import KaganCore


_UNSET: Final[object] = object()


# ── Helpers (module-level) ───────────────────────────────────────────


def _serialize_value(value: object) -> object:
    return value.value if isinstance(value, Enum) else value


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


async def backfill_task_types(engine: Engine) -> int:
    """Backfill task_type for all tasks without classification.

    Classifies all unclassified tasks using classify_task() based on their
    title and description. Returns the count of tasks updated.
    """

    def op(s) -> int:
        unclassified = list(s.exec(select(Task).where(Task.task_type.is_(None))).all())
        updated_count = 0
        for task in unclassified:
            task_type = classify_task(task.title, task.description)
            task.task_type = task_type.value
            s.add(task)
            updated_count += 1
        if updated_count > 0:
            s.commit()
        logger.info("Backfilled task_type for {} tasks", updated_count)
        return updated_count

    return await _db_async(engine, op)


# ── Tasks class ─────────────────────────────────────────────────────


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
        )
        self.sessions = Sessions(
            engine,
            self.events,
            get_task=self.get,
            set_status=self._set_status,
            ensure_workspace=self._ensure_workspace,
            db_path=db_path,
        )

    def _require_project(self) -> str:
        if self._active_project_id is None:
            raise SessionError(None, "No active project. Call client.projects.set_active() first.")
        return self._active_project_id

    def _clear_stale_active_project(self, project_id: str) -> None:
        if self._active_project_id != project_id:
            return
        self._active_project_id = None
        if self._client is not None and self._client.active_project_id == project_id:
            self._client.active_project_id = None
        logger.warning("Cleared stale active project id={}", project_id)

    async def _ensure_workspace(self, task_id: str) -> Worktree:
        if self._client is None:
            raise SessionError(None, "Workspace provisioning requires a KaganCore client.")
        return await self._client.worktrees.create(task_id)

    # ── Orchestration methods (keep on class — need instance state) ──

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

    # ── Core task operations ───────────────────────────────────────────

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
        repo_id: str | None = None,
    ) -> Task:
        active_project_id = self._require_project()

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
            lambda s: s.get(Project, active_project_id) is not None,
        )
        if not project_exists:
            self._clear_stale_active_project(active_project_id)
            raise NotFoundError("Project", active_project_id)

        if repo_id is not None:

            def _check_repo(s: Any) -> bool:
                repo = s.get(Repository, repo_id)
                return repo is not None and repo.project_id == active_project_id

            repo_ok = await _db_async(self._engine, _check_repo)
            if not repo_ok:
                raise NotFoundError("Repository", repo_id)

        task = Task(
            project_id=active_project_id,
            title=title,
            description=description,
            priority=priority,
            base_branch=base_branch,
            agent_backend=agent_backend,
            launcher=launcher,
            repo_id=repo_id,
        )
        # Classify task for analytics
        task_type = classify_task(title, description)
        task.task_type = task_type.value
        criteria_texts = acceptance_criteria or []

        def op(s):
            try:
                s.add(task)
                s.add(AuditEntry(action="task.create", entity_type="task", entity_id=task.id))
                s.flush()
                # Create AcceptanceCriterion rows
                for ordinal, text in enumerate(criteria_texts):
                    if text and str(text).strip():
                        s.add(
                            AcceptanceCriterion(
                                task_id=task.id,
                                ordinal=ordinal,
                                text=str(text).strip()[:500],
                            )
                        )
                s.commit()
                s.refresh(task)
                # Eagerly load the criteria relationship while the session is open
                _ = list(task.criteria)
                logger.debug("Task created id={} type={}", task.id, task.task_type)
                return task
            except IntegrityError as exc:
                s.rollback()
                if "FOREIGN KEY constraint failed" in str(exc.orig):
                    self._clear_stale_active_project(active_project_id)
                    raise NotFoundError("Project", active_project_id) from exc
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

    async def get(self, task_id: str) -> Task:
        def _get_with_criteria(s) -> Task | None:
            t = s.get(Task, task_id)
            if t is not None:
                _ = list(t.criteria)  # Eagerly load criteria while session is open
            return t

        task = await _db_async(self._engine, _get_with_criteria)
        if task is None:
            raise NotFoundError("Task", task_id)
        return task

    async def list(
        self,
        *,
        status: TaskStatus | None = None,
        repo_id: str | None = None,
    ) -> list[Task]:
        project_id = self._require_project()
        stmt = select(Task).where(Task.project_id == project_id)
        if status is not None:
            stmt = stmt.where(Task.status == status)
        if repo_id is not None:
            stmt = stmt.where(Task.repo_id == repo_id)

        def _list_with_criteria(s) -> list[Task]:
            tasks = list(s.exec(stmt).all())
            for t in tasks:
                _ = list(t.criteria)  # Eagerly load criteria while session is open
            return tasks

        return await _db_async(self._engine, _list_with_criteria)

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
        repo_id: str | None | object = _UNSET,
    ) -> Task:
        task = await self.get(task_id)
        scalar_updates = {
            "title": title,
            "description": description,
            "priority": priority,
            "base_branch": base_branch,
            "agent_backend": agent_backend,
            "launcher": launcher,
            "repo_id": repo_id,
        }
        changed_fields: dict[str, object] = {}
        # Re-classify if title or description changes
        should_reclassify = title is not None or description is not None

        def op(s):
            db_task = s.get(Task, task.id)
            if db_task is None:
                raise NotFoundError("Task", task.id)
            for field, value in scalar_updates.items():
                if value is _UNSET:
                    continue
                if field == "launcher":
                    db_task.launcher = value if isinstance(value, str) else None
                    changed_fields["launcher"] = _serialize_value(
                        value if isinstance(value, str) else None
                    )
                    continue
                if field == "repo_id":
                    db_task.repo_id = value if isinstance(value, str) else None
                    changed_fields["repo_id"] = _serialize_value(
                        value if isinstance(value, str) else None
                    )
                    continue
                if value is not None:
                    setattr(db_task, field, value)
                    changed_fields[field] = _serialize_value(value)

            # Update acceptance_criteria rows if provided
            if acceptance_criteria is not None:
                # Delete existing criteria rows then re-insert
                existing = list(
                    s.exec(
                        select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task.id)
                    ).all()
                )
                for crit in existing:
                    s.delete(crit)
                s.flush()
                for ordinal, text in enumerate(acceptance_criteria):
                    if text and str(text).strip():
                        s.add(
                            AcceptanceCriterion(
                                task_id=task.id,
                                ordinal=ordinal,
                                text=str(text).strip()[:500],
                            )
                        )
                changed_fields["acceptance_criteria"] = acceptance_criteria

            # Re-classify task if title or description changed
            if should_reclassify:
                new_title = title if title is not None else db_task.title
                new_desc = description if description is not None else db_task.description
                new_type = classify_task(new_title, new_desc)
                if db_task.task_type != new_type.value:
                    db_task.task_type = new_type.value
                    changed_fields["task_type"] = new_type.value

            db_task.updated_at = _utc_now()
            if changed_fields:
                _record_task_audit(
                    s,
                    action="task.update",
                    task_id=task.id,
                    detail={"fields": dict(changed_fields)},
                )
            s.add(db_task)
            s.commit()
            s.refresh(db_task)
            _ = list(db_task.criteria)  # Eagerly load criteria while session is open
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
        """Sync version of status change, used as a callback by Sessions."""

        def op(s):
            task = s.get(Task, task_id)
            if task is None:
                raise NotFoundError("Task", task_id)
            from_status = task.status
            task.status = status
            task.updated_at = _utc_now()
            _record_task_audit(
                s,
                action="task.status_change",
                task_id=task_id,
                detail={"from": from_status.value, "to": status.value},
            )
            s.add(task)
            s.commit()
            s.refresh(task)
            _ = list(task.criteria)  # Eagerly load criteria while session is open
            logger.info("Task {} moved to {}", task_id, status.value)
            return task

        return _db_sync(self._engine, op)

    async def delete(self, task_id: str) -> None:
        if self._client is None:
            raise SessionError(None, "Task operations are not attached to a client instance.")
        task = await self.get(task_id)
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
            db_task = s.get(Task, task_id)
            if db_task:
                _record_task_audit(
                    s,
                    action="task.delete",
                    task_id=task_id,
                    detail={"status": db_task.status.value, "title": db_task.title},
                )
                # CASCADE delete handles all child rows (sessions, worktrees,
                # task_events, notes, acceptance_criteria, review_verdicts)
                s.delete(db_task)

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
        events = await list_events(self._engine, task_id, limit=10)
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
                    select(Worktree).where(_col(Worktree.task_id).in_(task_ids))
                ).all()
            }

            latest_events: dict[str, str] = {}
            for event in s.exec(
                select(SessionEvent)
                .where(_col(SessionEvent.task_id).in_(task_ids))
                .order_by(desc(_col(SessionEvent.created_at)))
            ).all():
                latest_events.setdefault(event.task_id, utc_iso(event.created_at) or "")

            active_sessions: dict[str, dict[str, Any]] = {}
            for session in s.exec(
                select(Session)
                .where(_col(Session.task_id).in_(task_ids))
                .order_by(desc(_col(Session.started_at)))
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
                tid: {
                    "has_workspace": tid in worktrees,
                    "last_event_at": latest_events.get(tid),
                    "active_session": active_sessions.get(tid),
                }
                for tid in task_ids
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

    async def add_note(self, task_id: str, content: str) -> TaskNote:
        await self.get(task_id)
        note = TaskNote(task_id=task_id, content=content)
        return await _db_async(self._engine, lambda s: _add_and_refresh(s, note))

    async def list_notes(self, task_id: str) -> builtins.list[TaskNote]:
        stmt = (
            select(TaskNote).where(TaskNote.task_id == task_id).order_by(_col(TaskNote.created_at))
        )
        return await _db_async(self._engine, lambda s: list(s.exec(stmt).all()))

    async def delete_note(self, task_id: str, note_id: str) -> bool:
        """Delete a TaskNote by id. Returns True if found and deleted, False if not found."""

        def op(s) -> bool:
            note = s.get(TaskNote, note_id)
            if note is None or note.task_id != task_id:
                return False
            s.delete(note)
            return True

        return await _db_async(self._engine, op, commit=True)

    async def list_project_learnings(self, project_id: str) -> builtins.list[str]:
        """Return up to 20 unique [LEARNING]-prefixed notes across all tasks in a project.

        Notes are ordered newest-first and deduplicated by content after stripping the prefix.
        Only notes whose content starts with "[LEARNING]" are included.
        """
        return await fetch_project_learnings(self._engine, project_id)


__all__ = [
    "Tasks",
]
