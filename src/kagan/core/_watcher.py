"""DBWatcher -- polling-based task board change tracker."""

import asyncio
import contextlib
from collections import deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from sqlalchemy.exc import SQLAlchemyError

from kagan.core._events import BoardEvent
from kagan.core.errors import NotFoundError
from kagan.core.models import Task

if TYPE_CHECKING:
    from kagan.core.client import KaganCore


@dataclass(frozen=True, slots=True)
class _TaskState:
    title: str
    status: str


class DBWatcher:
    _POLL_INTERVAL_MIN: float = 0.5
    _POLL_INTERVAL_MAX: float = 2.0
    _POLL_BACKOFF_FACTOR: float = 1.5
    _MAX_PENDING_CONTEXT_LINES: int = 200

    def __init__(self, core: "KaganCore") -> None:
        self._core = core
        self._initialized = False
        self._active_project_id: str | None = None
        self._snapshot: dict[str, _TaskState] = {}
        self._pending: deque[str] = deque()
        self._dropped_pending_count = 0
        self._poll_interval = self._POLL_INTERVAL_MIN
        self._subscription_task: asyncio.Task[None] | None = None
        self._poll_task: asyncio.Task[None] | None = None
        self._change_event = asyncio.Event()

    async def initialize(self) -> None:
        self._active_project_id = self._core.active_project_id
        self._snapshot = await self._take_snapshot()
        self._poll_interval = self._POLL_INTERVAL_MIN
        self._initialized = True

    async def subscribe(self) -> None:
        if not self._initialized:
            await self.initialize()
        if self._subscription_task is None or self._subscription_task.done():
            self._subscription_task = asyncio.create_task(
                self._consume_events(),
                name="db-watcher-subscribe",
            )
        if self._poll_task is None or self._poll_task.done():
            self._poll_task = asyncio.create_task(
                self._poll_db_loop(),
                name="db-watcher-poll",
            )

    async def poll(self) -> bool:
        if not self._change_event.is_set():
            return False
        self._change_event.clear()
        return True

    async def wait_for_change(self) -> None:
        await self._change_event.wait()
        self._change_event.clear()

    async def close(self) -> None:
        for task in (self._subscription_task, self._poll_task):
            if task is None:
                continue
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task
        self._subscription_task = None
        self._poll_task = None

    def drain_context(self) -> str | None:
        if not self._pending and self._dropped_pending_count == 0:
            return None
        header = "[Context Update \u2014 board changes since your last message]"
        lines: list[str] = [header]
        if self._dropped_pending_count:
            noun = "update" if self._dropped_pending_count == 1 else "updates"
            lines.append(f"[{self._dropped_pending_count} older board {noun} omitted]")
        lines.extend(self._pending)
        block = "\n".join(lines)
        self._pending.clear()
        self._dropped_pending_count = 0
        return block

    async def _take_snapshot(self) -> dict[str, _TaskState]:
        tasks = await self._core.tasks.list()
        return {t.id: _TaskState(t.title, t.status.value) for t in tasks}

    async def _consume_events(self) -> None:
        async for event in self._core.tasks.events.stream_board():
            await self._handle_event(event)

    async def _poll_db_loop(self) -> None:
        while True:
            await asyncio.sleep(self._poll_interval)
            try:
                current = await self._take_snapshot()
            except (OSError, SQLAlchemyError):
                self._poll_interval = min(
                    self._poll_interval * self._POLL_BACKOFF_FACTOR,
                    self._POLL_INTERVAL_MAX,
                )
                continue
            changed = self._diff_snapshot(current)
            if changed:
                self._poll_interval = self._POLL_INTERVAL_MIN
                continue
            self._poll_interval = min(
                self._poll_interval * self._POLL_BACKOFF_FACTOR,
                self._POLL_INTERVAL_MAX,
            )

    def _detect_created(
        self, current: dict[str, _TaskState], old_ids: set[str], new_ids: set[str]
    ) -> bool:
        changed = False
        for task_id in new_ids - old_ids:
            state = current[task_id]
            self._snapshot[task_id] = state
            self._record(f"Task '{state.title}' ({task_id}) created [{state.status}]")
            changed = True
        return changed

    def _detect_deleted(self, old_ids: set[str], new_ids: set[str]) -> bool:
        changed = False
        for task_id in old_ids - new_ids:
            state = self._snapshot.pop(task_id)
            self._record(f"Task '{state.title}' ({task_id}) deleted")
            changed = True
        return changed

    def _detect_modified(
        self, current: dict[str, _TaskState], old_ids: set[str], new_ids: set[str]
    ) -> bool:
        changed = False
        for task_id in old_ids & new_ids:
            old = self._snapshot[task_id]
            new = current[task_id]
            if old.status != new.status:
                self._snapshot[task_id] = new
                self._record(
                    f"Task '{new.title}' ({task_id}) moved {old.status} \u2192 {new.status}"
                )
                changed = True
            elif old.title != new.title:
                self._snapshot[task_id] = new
                self._record(f"Task '{new.title}' ({task_id}) updated")
                changed = True
        return changed

    def _diff_snapshot(self, current: dict[str, _TaskState]) -> bool:
        old_ids = set(self._snapshot)
        new_ids = set(current)

        changed = self._detect_created(current, old_ids, new_ids)
        changed = self._detect_deleted(old_ids, new_ids) or changed
        changed = self._detect_modified(current, old_ids, new_ids) or changed

        return changed

    async def _handle_event(self, event: BoardEvent) -> None:
        if event.kind == "created":
            task = await self._resolve_if_relevant(event.task_id)
            if task is None:
                return
            title = event.title or task.title
            status = event.status or task.status.value
            self._snapshot[event.task_id] = _TaskState(
                title,
                status,
            )
            self._record(f"Task '{title}' ({event.task_id}) created [{status}]")
            return

        if event.kind == "updated":
            task = await self._resolve_if_relevant(event.task_id)
            if task is None:
                return
            title = event.title or task.title
            status = event.status or task.status.value
            self._snapshot[event.task_id] = _TaskState(
                title,
                status,
            )
            self._record(f"Task '{title}' ({event.task_id}) updated")
            return

        if event.kind == "deleted":
            snap = self._snapshot.pop(event.task_id, None)
            if snap is None:
                return
            title = event.title or snap.title
            self._record(f"Task '{title}' ({event.task_id}) deleted")
            return

        if event.kind in ("session_started", "session_ended", "auto_review_started"):
            # Session lifecycle events don't change task fields tracked in
            # _TaskState, but the kanban board still needs a reload so that
            # cards reflect the active-session / running indicator.
            if event.task_id in self._snapshot or await self._resolve_if_relevant(event.task_id):
                self._change_event.set()
            return

        if event.kind != "status_changed":
            return

        task = await self._resolve_if_relevant(event.task_id)
        if task is None:
            return
        snap = self._snapshot.get(event.task_id)
        title = task.title if snap is None else snap.title
        prev_status = event.from_status or (snap.status if snap is not None else task.status.value)
        new_status = event.to_status or task.status.value
        self._snapshot[event.task_id] = _TaskState(
            title,
            new_status,
        )
        self._record(f"Task '{title}' ({event.task_id}) moved {prev_status} \u2192 {new_status}")

    async def _resolve_if_relevant(self, task_id: str) -> Task | None:
        if task_id in self._snapshot:
            try:
                return await self._core.tasks.get(task_id)
            except NotFoundError:
                return None
        try:
            task = await self._core.tasks.get(task_id)
        except NotFoundError:
            return None
        if task.project_id != self._active_project_id:
            return None
        return task

    def _record(self, line: str) -> None:
        if len(self._pending) >= self._MAX_PENDING_CONTEXT_LINES:
            self._pending.popleft()
            self._dropped_pending_count += 1
        self._pending.append(line)
        self._poll_interval = self._POLL_INTERVAL_MIN
        self._change_event.set()


__all__ = ["DBWatcher"]
