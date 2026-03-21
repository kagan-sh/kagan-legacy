import asyncio
import builtins
import contextlib
import re
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, cast

from loguru import logger
from sqlalchemy import Engine, and_, desc, or_
from sqlmodel import select

from kagan.core._db_helpers import _add_and_refresh, _db_async
from kagan.core.enums import SessionEventType, TaskStatus
from kagan.core.models import SessionEvent

LIVE_STREAM_QUEUE_MAX_SIZE = 512
GLOBAL_STREAM_QUEUE_MAX_SIZE = 512
BOARD_STREAM_QUEUE_MAX_SIZE = 256

# Secret scrubbing — compiled at module level for performance.
_SECRET_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"AKIA[A-Z0-9]{16}"),  # AWS access key IDs
    re.compile(r"ghp_[a-zA-Z0-9]{36}"),  # GitHub personal access tokens
    re.compile(r"ghu_[a-zA-Z0-9]{36}"),  # GitHub user tokens
    re.compile(r"sk-[a-zA-Z0-9]{20,}"),  # OpenAI API keys
    re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH )?PRIVATE KEY-----"),  # Private key blocks
    re.compile(r"Bearer [a-zA-Z0-9._\-]{20,}"),  # Bearer tokens
]
_SENSITIVE_KEYS: frozenset[str] = frozenset(
    {"password", "secret", "token", "api_key", "apikey", "authorization"}
)


def _scrub_secrets(payload: dict) -> dict:
    """Deep-copy payload replacing secrets with [REDACTED]. Never mutates input."""

    def _scrub_value(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                k: "[REDACTED]" if k.lower() in _SENSITIVE_KEYS else _scrub_value(v)
                for k, v in value.items()
            }
        if isinstance(value, list):
            return [_scrub_value(item) for item in value]
        if isinstance(value, str):
            result = value
            for pattern in _SECRET_PATTERNS:
                result = pattern.sub("[REDACTED]", result)
            if result != value:
                logger.debug("Scrubbing secret from event payload")
            return result
        return value

    return _scrub_value(payload)


_NON_CRITICAL_EVENT_TYPES: frozenset[SessionEventType] = frozenset(
    {
        SessionEventType.AGENT_STATUS,
        SessionEventType.TOOL_CALL_UPDATE,
        SessionEventType.PLAN_UPDATE,
    }
)


class _BoundedEventQueue[T]:
    def __init__(self, *, maxsize: int) -> None:
        self._maxsize = maxsize
        self._pending: deque[T] = deque()
        self._not_empty = asyncio.Event()

    @property
    def pending(self) -> deque[T]:
        return self._pending

    def put_nowait(self, item: T) -> None:
        if len(self._pending) >= self._maxsize:
            raise asyncio.QueueFull
        self._pending.append(item)
        self._not_empty.set()

    def force_put_nowait(self, item: T) -> None:
        self._pending.append(item)
        self._not_empty.set()

    def get_nowait(self) -> T:
        if not self._pending:
            raise asyncio.QueueEmpty
        item = self._pending.popleft()
        if not self._pending:
            self._not_empty.clear()
        return item

    async def get(self) -> T:
        while not self._pending:
            await self._not_empty.wait()
        return self.get_nowait()

    def empty(self) -> bool:
        return not self._pending


@dataclass(slots=True)
class BoardEvent:
    task_id: str
    kind: str
    title: str | None = None
    status: str | None = None
    from_status: str | None = None
    to_status: str | None = None


class Events:
    def __init__(self, engine: Engine, signals: dict[str, asyncio.Event]) -> None:
        self._engine = engine
        self._signals = signals
        self._live_queues: dict[str, list[_BoundedEventQueue[SessionEvent]]] = {}
        self._global_live_queues: list[_BoundedEventQueue[SessionEvent]] = []
        self._board_live_queues: list[_BoundedEventQueue[BoardEvent]] = []

    def _signal_for(self, task_id: str) -> asyncio.Event:
        if task_id not in self._signals:
            self._signals[task_id] = asyncio.Event()
        return self._signals[task_id]

    def _prune_signal_if_idle(self, task_id: str) -> None:
        if self._live_queues.get(task_id):
            return
        self._signals.pop(task_id, None)

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
        queue: _BoundedEventQueue[SessionEvent],
        event: SessionEvent,
    ) -> bool:
        key = self._session_event_key_for_coalesce(event)
        if key is None:
            return False
        pending = queue.pending
        for idx in range(len(pending) - 1, -1, -1):
            existing = pending[idx]
            if self._session_event_key_for_coalesce(existing) == key:
                pending[idx] = event
                return True
        return False

    def _drop_oldest_non_critical_event(self, queue: _BoundedEventQueue[SessionEvent]) -> bool:
        pending = queue.pending
        for idx, existing in enumerate(pending):
            if (
                existing.event_type in _NON_CRITICAL_EVENT_TYPES
                and not self._is_terminal_live_event(existing)
            ):
                del pending[idx]
                return True
        return False

    def _drop_oldest_non_terminal_event(self, queue: _BoundedEventQueue[SessionEvent]) -> bool:
        pending = queue.pending
        for idx, existing in enumerate(pending):
            if not self._is_terminal_live_event(existing):
                del pending[idx]
                return True
        return False

    def _enqueue_session_event(
        self, queue: _BoundedEventQueue[SessionEvent], event: SessionEvent
    ) -> None:
        try:
            queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        if event.event_type in _NON_CRITICAL_EVENT_TYPES:
            if self._coalesce_or_drop_non_critical_event(queue, event):
                return

        if not self._drop_oldest_non_critical_event(queue):
            if self._drop_oldest_non_terminal_event(queue):
                logger.warning(
                    "Live event queue reached capacity; dropping oldest non-terminal event "
                    "to preserve terminal delivery"
                )
            else:
                logger.warning(
                    "Live event queue contains only terminal events; temporarily exceeding "
                    "capacity to avoid dropping terminal event"
                )
                queue.force_put_nowait(event)
                return
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(event)

    @staticmethod
    def _parse_cursor_timestamp(value: str) -> datetime:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        return parsed.astimezone(UTC).replace(tzinfo=None)

    def _enqueue_board_event(
        self, queue: _BoundedEventQueue[BoardEvent], event: BoardEvent
    ) -> None:
        try:
            queue.put_nowait(event)
            return
        except asyncio.QueueFull:
            pass

        key = self._board_event_key_for_coalesce(event)
        pending = queue.pending
        for idx in range(len(pending) - 1, -1, -1):
            if self._board_event_key_for_coalesce(pending[idx]) == key:
                pending[idx] = event
                return

        if pending:
            pending.popleft()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(event)

    @staticmethod
    def _is_terminal_live_event(event: SessionEvent) -> bool:
        if event.event_type in {SessionEventType.AGENT_COMPLETED, SessionEventType.AGENT_FAILED}:
            return True
        if event.event_type is not SessionEventType.TASK_STATUS_CHANGED:
            return False
        payload = event.payload if isinstance(event.payload, dict) else {}
        next_status = str(payload.get("to") or "").upper()
        return next_status != TaskStatus.IN_PROGRESS.value

    async def emit(
        self,
        task_id: str,
        event_type: SessionEventType,
        payload: dict,
        *,
        session_id: str | None = None,
        persist: bool = True,
    ) -> SessionEvent:
        scrubbed_payload = _scrub_secrets(payload)
        event = SessionEvent(
            task_id=task_id,
            session_id=session_id,
            event_type=event_type,
            payload=scrubbed_payload,
        )
        if persist:
            await _db_async(self._engine, lambda s: _add_and_refresh(s, event))
        signal = self._signal_for(task_id)
        signal.set()
        for queue in self._live_queues.get(task_id, []):
            self._enqueue_session_event(queue, event)
        for queue in self._global_live_queues:
            self._enqueue_session_event(queue, event)
        self._prune_signal_if_idle(task_id)
        if event_type is SessionEventType.TASK_STATUS_CHANGED:
            self.publish_board(
                BoardEvent(
                    task_id=task_id,
                    kind="status_changed",
                    from_status=str(payload.get("from") or ""),
                    to_status=str(payload.get("to") or ""),
                )
            )
        elif event_type is SessionEventType.AUTO_REVIEW_STARTED:
            self.publish_board(BoardEvent(task_id=task_id, kind="auto_review_started"))
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
        session_id: str | None = None,
    ) -> list[SessionEvent]:
        def _query(s):
            stmt = select(SessionEvent).where(SessionEvent.task_id == task_id)
            if session_id is not None:
                stmt = stmt.where(SessionEvent.session_id == session_id)
            stmt = stmt.order_by(cast("Any", SessionEvent.created_at)).offset(offset).limit(limit)
            return list(s.exec(stmt).all())

        return await _db_async(self._engine, _query)

    async def list_recent(
        self,
        task_id: str,
        *,
        limit: int = 50,
        before: str | None = None,
        before_id: str | None = None,
        session_id: str | None = None,
    ) -> builtins.list[SessionEvent]:
        bounded = max(limit, 0)
        if bounded == 0:
            return []

        cutoff = self._parse_cursor_timestamp(before) if before is not None else None

        def _query(s):
            stmt = select(SessionEvent).where(SessionEvent.task_id == task_id)
            if session_id is not None:
                stmt = stmt.where(SessionEvent.session_id == session_id)
            if cutoff is not None:
                if before_id:
                    stmt = stmt.where(
                        or_(
                            cast("Any", SessionEvent.created_at) < cutoff,
                            and_(
                                cast("Any", SessionEvent.created_at) == cutoff,
                                cast("Any", SessionEvent.id) < before_id,
                            ),
                        )
                    )
                else:
                    stmt = stmt.where(cast("Any", SessionEvent.created_at) < cutoff)
            stmt = stmt.order_by(
                desc(cast("Any", SessionEvent.created_at)),
                desc(cast("Any", SessionEvent.id)),
            ).limit(bounded)
            return list(s.exec(stmt).all())

        recent = await _db_async(self._engine, _query)
        recent.reverse()
        return recent

    async def list_before(
        self,
        task_id: str,
        *,
        before: str,
        before_id: str | None = None,
        limit: int = 50,
        session_id: str | None = None,
    ) -> builtins.list[SessionEvent]:
        bounded = max(limit, 0)
        if bounded == 0:
            return []

        cutoff = self._parse_cursor_timestamp(before)

        def _query(s):
            stmt = select(SessionEvent).where(SessionEvent.task_id == task_id)
            if before_id:
                stmt = stmt.where(
                    or_(
                        cast("Any", SessionEvent.created_at) < cutoff,
                        and_(
                            cast("Any", SessionEvent.created_at) == cutoff,
                            cast("Any", SessionEvent.id) < before_id,
                        ),
                    )
                )
            else:
                stmt = stmt.where(cast("Any", SessionEvent.created_at) < cutoff)
            if session_id is not None:
                stmt = stmt.where(SessionEvent.session_id == session_id)
            stmt = stmt.order_by(
                desc(cast("Any", SessionEvent.created_at)),
                desc(cast("Any", SessionEvent.id)),
            ).limit(bounded)
            return list(s.exec(stmt).all())

        recent = await _db_async(self._engine, _query)
        recent.reverse()
        return recent

    async def list_after(
        self,
        task_id: str,
        *,
        after_ts: str,
        after_id: str,
        limit: int = 50,
        session_id: str | None = None,
    ) -> builtins.list[SessionEvent]:
        bounded = max(limit, 0)
        if bounded == 0:
            return []

        cutoff = self._parse_cursor_timestamp(after_ts)

        def _query(s):
            stmt = select(SessionEvent).where(
                SessionEvent.task_id == task_id,
                or_(
                    cast("Any", SessionEvent.created_at) > cutoff,
                    and_(
                        cast("Any", SessionEvent.created_at) == cutoff,
                        cast("Any", SessionEvent.id) > after_id,
                    ),
                ),
            )
            if session_id is not None:
                stmt = stmt.where(SessionEvent.session_id == session_id)
            stmt = stmt.order_by(
                cast("Any", SessionEvent.created_at),
                cast("Any", SessionEvent.id),
            ).limit(bounded)
            return list(s.exec(stmt).all())

        return await _db_async(self._engine, _query)

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

    async def stream(
        self,
        task_id: str,
        *,
        replay: bool = True,
        replay_limit: int | None = None,
    ) -> AsyncIterator[SessionEvent]:
        if replay:
            if replay_limit is None:
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
            elif replay_limit > 0:
                for event in await self.list_recent(task_id, limit=replay_limit):
                    yield event

        queue = _BoundedEventQueue[SessionEvent](maxsize=LIVE_STREAM_QUEUE_MAX_SIZE)
        queues = self._live_queues.setdefault(task_id, [])
        queues.append(queue)
        should_close_when_idle = False
        try:
            while True:
                if should_close_when_idle and queue.empty():
                    return
                event = await queue.get()
                yield event
                if self._is_terminal_live_event(event):
                    should_close_when_idle = True
        finally:
            queues = self._live_queues.get(task_id, [])
            with contextlib.suppress(ValueError):
                queues.remove(queue)
            if not queues:
                self._live_queues.pop(task_id, None)
                self._prune_signal_if_idle(task_id)

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

        queue = _BoundedEventQueue[SessionEvent](maxsize=GLOBAL_STREAM_QUEUE_MAX_SIZE)
        self._global_live_queues.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            with contextlib.suppress(ValueError):
                self._global_live_queues.remove(queue)

    async def stream_board(self) -> AsyncIterator[BoardEvent]:
        queue = _BoundedEventQueue[BoardEvent](maxsize=BOARD_STREAM_QUEUE_MAX_SIZE)
        self._board_live_queues.append(queue)
        try:
            while True:
                event = await queue.get()
                yield event
        finally:
            with contextlib.suppress(ValueError):
                self._board_live_queues.remove(queue)


__all__ = ["BoardEvent", "Events"]
