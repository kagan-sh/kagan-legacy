import asyncio
import contextlib
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, cast

from sqlalchemy import Engine, desc
from sqlmodel import select

from kagan.core._db_helpers import _add_and_refresh, _db_async
from kagan.core.enums import SessionEventType, SessionStatus
from kagan.core.models import Session, SessionEvent

LIVE_STREAM_QUEUE_MAX_SIZE = 512
GLOBAL_STREAM_QUEUE_MAX_SIZE = 512
BOARD_STREAM_QUEUE_MAX_SIZE = 256

_NON_CRITICAL_EVENT_TYPES: frozenset[SessionEventType] = frozenset(
    {
        SessionEventType.OUTPUT_CHUNK,
        SessionEventType.AGENT_STATUS,
        SessionEventType.TOOL_CALL_UPDATE,
        SessionEventType.PLAN_UPDATE,
    }
)


@dataclass(slots=True)
class BoardEvent:
    task_id: str
    kind: str
    title: str | None = None
    status: str | None = None
    from_status: str | None = None
    to_status: str | None = None


class Events:
    """Event operations for a task — emit, list, stream."""

    def __init__(self, engine: Engine, signals: dict[str, asyncio.Event]) -> None:
        self._engine = engine
        self._signals = signals
        self._live_queues: dict[str, list[asyncio.Queue[SessionEvent]]] = {}
        self._global_live_queues: list[asyncio.Queue[SessionEvent]] = []
        self._board_live_queues: list[asyncio.Queue[BoardEvent]] = []

    def _signal_for(self, task_id: str) -> asyncio.Event:
        if task_id not in self._signals:
            self._signals[task_id] = asyncio.Event()
        return self._signals[task_id]

    @staticmethod
    def _session_event_key_for_coalesce(event: SessionEvent) -> tuple[str, str, str | None] | None:
        event_type = event.event_type
        if event_type is SessionEventType.AGENT_STATUS:
            return (event_type.value, event.task_id, event.session_id)
        if event_type is SessionEventType.PLAN_UPDATE:
            return (event_type.value, event.task_id, event.session_id)
        if event_type is SessionEventType.TOOL_CALL_UPDATE:
            payload = event.payload if isinstance(event.payload, dict) else {}
            tool_call_id = payload.get("tool_call_id") or payload.get("id")
            return (event_type.value, event.task_id, str(tool_call_id) if tool_call_id else None)
        return None

    @staticmethod
    def _board_event_key_for_coalesce(event: BoardEvent) -> tuple[str, str]:
        return (event.task_id, event.kind)

    def _coalesce_or_drop_non_critical_event(
        self,
        queue: asyncio.Queue[SessionEvent],
        event: SessionEvent,
    ) -> bool:
        key = self._session_event_key_for_coalesce(event)
        if key is None:
            return False
        any_queue = cast("Any", queue)
        pending = cast("Any", any_queue._queue)
        for idx in range(len(pending) - 1, -1, -1):
            existing = pending[idx]
            if self._session_event_key_for_coalesce(existing) == key:
                pending[idx] = event
                return True
        return False

    def _drop_oldest_non_critical_event(self, queue: asyncio.Queue[SessionEvent]) -> bool:
        any_queue = cast("Any", queue)
        pending = cast("Any", any_queue._queue)
        for idx, existing in enumerate(pending):
            if existing.event_type in _NON_CRITICAL_EVENT_TYPES:
                del pending[idx]
                return True
        return False

    def _enqueue_session_event(
        self, queue: asyncio.Queue[SessionEvent], event: SessionEvent
    ) -> None:
        try:
            queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        if event.event_type in _NON_CRITICAL_EVENT_TYPES:
            self._coalesce_or_drop_non_critical_event(queue, event)
            return

        if not self._drop_oldest_non_critical_event(queue):
            any_queue = cast("Any", queue)
            pending = cast("Any", any_queue._queue)
            if pending:
                pending.popleft()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(event)

    def _enqueue_board_event(self, queue: asyncio.Queue[BoardEvent], event: BoardEvent) -> None:
        try:
            queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        key = self._board_event_key_for_coalesce(event)
        any_queue = cast("Any", queue)
        pending = cast("Any", any_queue._queue)
        for idx in range(len(pending) - 1, -1, -1):
            if self._board_event_key_for_coalesce(pending[idx]) == key:
                pending[idx] = event
                return

        if pending:
            pending.popleft()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(event)

    async def emit(
        self,
        task_id: str,
        event_type: SessionEventType,
        payload: dict,
        *,
        session_id: str | None = None,
    ) -> SessionEvent:
        event = SessionEvent(
            task_id=task_id,
            session_id=session_id,
            event_type=event_type,
            payload=payload,
        )
        await _db_async(self._engine, lambda s: _add_and_refresh(s, event))
        self._signal_for(task_id).set()
        for queue in self._live_queues.get(task_id, []):
            self._enqueue_session_event(queue, event)
        for queue in self._global_live_queues:
            self._enqueue_session_event(queue, event)
        if event_type is SessionEventType.TASK_STATUS_CHANGED:
            self.publish_board(
                BoardEvent(
                    task_id=task_id,
                    kind="status_changed",
                    from_status=str(payload.get("from") or ""),
                    to_status=str(payload.get("to") or ""),
                )
            )
        return event

    def publish_board(self, event: BoardEvent) -> None:
        for queue in self._board_live_queues:
            self._enqueue_board_event(queue, event)

    async def list_all(self, *, offset: int = 0, limit: int = 20) -> list[SessionEvent]:
        return await _db_async(
            self._engine,
            lambda s: list(
                s.exec(
                    select(SessionEvent)
                    .order_by(cast("Any", SessionEvent.created_at))
                    .offset(offset)
                    .limit(limit)
                ).all()
            ),
        )

    async def list(
        self,
        task_id: str,
        *,
        offset: int = 0,
        limit: int = 20,
    ) -> list[SessionEvent]:
        return await _db_async(
            self._engine,
            lambda s: list(
                s.exec(
                    select(SessionEvent)
                    .where(SessionEvent.task_id == task_id)
                    .order_by(cast("Any", SessionEvent.created_at))
                    .offset(offset)
                    .limit(limit)
                ).all()
            ),
        )

    async def latest(
        self,
        task_id: str,
        *,
        event_type: SessionEventType | None = None,
    ) -> SessionEvent | None:
        def op(s) -> SessionEvent | None:
            stmt = select(SessionEvent).where(SessionEvent.task_id == task_id)
            if event_type is not None:
                stmt = stmt.where(SessionEvent.event_type == event_type)
            stmt = stmt.order_by(desc(cast("Any", SessionEvent.created_at)))
            return s.exec(stmt).first()

        return await _db_async(self._engine, op)

    async def stream(self, task_id: str) -> AsyncIterator[SessionEvent]:
        offset = 0
        batch = await self.list(task_id, offset=offset, limit=50)
        for event in batch:
            yield event
        offset += len(batch)
        while len(batch) == 50:
            batch = await self.list(task_id, offset=offset, limit=50)
            for event in batch:
                yield event
            offset += len(batch)

        queue: asyncio.Queue[SessionEvent] = asyncio.Queue(maxsize=LIVE_STREAM_QUEUE_MAX_SIZE)
        queues = self._live_queues.setdefault(task_id, [])
        queues.append(queue)
        try:
            while True:
                try:
                    event = await asyncio.wait_for(queue.get(), timeout=5.0)
                    yield event
                except TimeoutError:
                    has_active = await _db_async(
                        self._engine,
                        lambda s: (
                            s.exec(
                                select(Session).where(
                                    Session.task_id == task_id,
                                    cast("Any", Session.status).in_(
                                        [SessionStatus.PENDING, SessionStatus.RUNNING]
                                    ),
                                )
                            ).first()
                            is not None
                        ),
                    )
                    if not has_active:
                        return
        finally:
            queues = self._live_queues.get(task_id, [])
            with contextlib.suppress(ValueError):
                queues.remove(queue)
            if not queues:
                self._live_queues.pop(task_id, None)

    async def stream_all(self, *, replay: bool = True) -> AsyncIterator[SessionEvent]:
        if replay:
            offset = 0
            batch = await self.list_all(offset=offset, limit=50)
            for event in batch:
                yield event
            offset += len(batch)
            while len(batch) == 50:
                batch = await self.list_all(offset=offset, limit=50)
                for event in batch:
                    yield event
                offset += len(batch)

        queue: asyncio.Queue[SessionEvent] = asyncio.Queue(maxsize=GLOBAL_STREAM_QUEUE_MAX_SIZE)
        self._global_live_queues.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            with contextlib.suppress(ValueError):
                self._global_live_queues.remove(queue)

    async def stream_board(self) -> AsyncIterator[BoardEvent]:
        queue: asyncio.Queue[BoardEvent] = asyncio.Queue(maxsize=BOARD_STREAM_QUEUE_MAX_SIZE)
        self._board_live_queues.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            with contextlib.suppress(ValueError):
                self._board_live_queues.remove(queue)


__all__ = ["BoardEvent", "Events"]
