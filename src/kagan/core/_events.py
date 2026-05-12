import asyncio
import builtins
import contextlib
import json
import re
from collections import deque
from collections.abc import AsyncIterator
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from loguru import logger
from pydantic import BaseModel
from sqlalchemy import Engine, and_, desc, or_
from sqlmodel import select

from kagan.core._db_helpers import _add_and_refresh, _db_async, _sa_col
from kagan.core.enums import TaskStatus
from kagan.core.models import SessionEvent

if TYPE_CHECKING:
    from kagan.core._event_log import EventLog

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


_NON_CRITICAL_EVENT_TYPES: frozenset[str] = frozenset(
    {
        "agent_status",
        "tool_call_update",
        "plan_update",
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


# ── Module-level functions (canonical API) ─────────────────────────


def _parse_cursor_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed.astimezone(UTC).replace(tzinfo=None)


async def emit_event(
    engine: Engine,
    signals: dict[str, asyncio.Event],
    task_id: str,
    event_type: str,
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
        await _db_async(engine, lambda s: _add_and_refresh(s, event))
    if task_id not in signals:
        signals[task_id] = asyncio.Event()
    signal = signals[task_id]
    signal.set()
    return event


async def list_events(
    engine: Engine,
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
        stmt = stmt.order_by(_sa_col(SessionEvent.created_at)).offset(offset).limit(limit)
        return list(s.exec(stmt).all())

    return await _db_async(engine, _query)


async def list_events_recent(
    engine: Engine,
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

    cutoff = _parse_cursor_timestamp(before) if before is not None else None

    def _query(s):
        stmt = select(SessionEvent).where(SessionEvent.task_id == task_id)
        if session_id is not None:
            stmt = stmt.where(SessionEvent.session_id == session_id)
        if cutoff is not None:
            if before_id:
                stmt = stmt.where(
                    or_(
                        _sa_col(SessionEvent.created_at) < cutoff,
                        and_(
                            _sa_col(SessionEvent.created_at) == cutoff,
                            _sa_col(SessionEvent.id) < before_id,
                        ),
                    )
                )
            else:
                stmt = stmt.where(_sa_col(SessionEvent.created_at) < cutoff)
        stmt = stmt.order_by(
            desc(_sa_col(SessionEvent.created_at)),
            desc(_sa_col(SessionEvent.id)),
        ).limit(bounded)
        return list(s.exec(stmt).all())

    recent = await _db_async(engine, _query)
    recent.reverse()
    return recent


async def list_events_before(
    engine: Engine,
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

    cutoff = _parse_cursor_timestamp(before)

    def _query(s):
        stmt = select(SessionEvent).where(SessionEvent.task_id == task_id)
        if before_id:
            stmt = stmt.where(
                or_(
                    _sa_col(SessionEvent.created_at) < cutoff,
                    and_(
                        _sa_col(SessionEvent.created_at) == cutoff,
                        _sa_col(SessionEvent.id) < before_id,
                    ),
                )
            )
        else:
            stmt = stmt.where(_sa_col(SessionEvent.created_at) < cutoff)
        if session_id is not None:
            stmt = stmt.where(SessionEvent.session_id == session_id)
        stmt = stmt.order_by(
            desc(_sa_col(SessionEvent.created_at)),
            desc(_sa_col(SessionEvent.id)),
        ).limit(bounded)
        return list(s.exec(stmt).all())

    recent = await _db_async(engine, _query)
    recent.reverse()
    return recent


async def list_events_after(
    engine: Engine,
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

    cutoff = _parse_cursor_timestamp(after_ts)

    def _query(s):
        stmt = select(SessionEvent).where(
            SessionEvent.task_id == task_id,
            or_(
                _sa_col(SessionEvent.created_at) > cutoff,
                and_(
                    _sa_col(SessionEvent.created_at) == cutoff,
                    _sa_col(SessionEvent.id) > after_id,
                ),
            ),
        )
        if session_id is not None:
            stmt = stmt.where(SessionEvent.session_id == session_id)
        stmt = stmt.order_by(
            _sa_col(SessionEvent.created_at),
            _sa_col(SessionEvent.id),
        ).limit(bounded)
        return list(s.exec(stmt).all())

    return await _db_async(engine, _query)


async def latest_event(
    engine: Engine,
    task_id: str,
    *,
    event_type: str | None = None,
) -> SessionEvent | None:
    def op(s) -> SessionEvent | None:
        stmt = select(SessionEvent).where(SessionEvent.task_id == task_id)
        if event_type is not None:
            stmt = stmt.where(SessionEvent.event_type == event_type)
        stmt = stmt.order_by(desc(_sa_col(SessionEvent.created_at)))
        return s.exec(stmt).first()

    return await _db_async(engine, op)


# ── Class (manages live queues + streaming, delegates DB ops) ──────


class Events:
    def __init__(
        self,
        engine: Engine,
        signals: dict[str, asyncio.Event],
        *,
        event_log: "EventLog | None" = None,
    ) -> None:
        self._engine = engine
        self._signals = signals
        self._event_log: EventLog | None = event_log
        self._live_queues: dict[str, list[_BoundedEventQueue[SessionEvent]]] = {}
        self._global_live_queues: list[_BoundedEventQueue[SessionEvent]] = []
        self._board_live_queues: list[_BoundedEventQueue[BoardEvent]] = []
        # Settlement-rule tracking: maps session_id to outstanding AgentEnd
        # subscriber count + idle event.  Decremented when each subscriber
        # acknowledges the AgentEnd event (via ``notify_agent_end_handled``).
        self._agent_end_pending: dict[str, int] = {}
        self._agent_end_idle: dict[str, asyncio.Event] = {}
        # Per-session tracking of the running assistant entry idx in the EventLog.
        # Populated by notify_agent_spawn(); used by emit() to route append/finalize frames.
        self._running_assistant_idx: dict[str, int] = {}

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
        if event_type == "agent_status":
            return (event_type, event.task_id, event.session_id)
        if event_type == "plan_update":
            return (event_type, event.task_id, event.session_id)
        if event_type == "tool_call_update":
            payload = event.payload if isinstance(event.payload, dict) else {}
            tool_call_id = payload.get("tool_call_id") or payload.get("id")
            return (event_type, event.task_id, str(tool_call_id) if tool_call_id else None)
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
        return _parse_cursor_timestamp(value)

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
        et = event.event_type
        if et in {"agent_completed", "agent_failed"}:
            return True
        if et != "task_status_changed":
            return False
        payload = event.payload if isinstance(event.payload, dict) else {}
        next_status = str(payload.get("to") or "").upper()
        return next_status != TaskStatus.IN_PROGRESS.value

    # ── EventLog dual-write helpers ────────────────────────────────────────────

    async def notify_agent_spawn(self, session_id: str) -> None:
        """Create the initial assistant entry frame for a newly spawned agent session.

        Must be called once per session after the session row is created and before
        the ACP callback is registered.  Stores the assigned idx for subsequent
        append/finalize frame routing.

        Frame semantics: create op, role="assistant", text="", finalized=False.
        The FrameRow.idx field stores the same logical index as the resolved
        path; the path placeholder is rewritten after append once idx is known.
        """
        if self._event_log is None:
            return
        from datetime import UTC, datetime

        ts = datetime.now(UTC).replace(tzinfo=None)
        # Append a placeholder frame; the idx is returned by append_with_idx.
        frame: dict[str, Any] = {
            "type": "patch",
            "op": "create",
            "path": "/entries/{idx}",  # placeholder — idx unknown until after append
            "value": {
                "role": "assistant",
                "text": "",
                "finalized": False,
                "ts": ts.isoformat(),
            },
        }
        _seq, actual_idx = await self._event_log.append_with_idx(session_id, "task", frame)
        # Record the assigned idx so subsequent append/finalize frames can target it.
        self._running_assistant_idx[session_id] = actual_idx
        logger.debug("EventLog: agent spawn create frame session={} idx={}", session_id, actual_idx)

    async def _append_task_frame(self, session_id: str, frame: dict[str, Any]) -> None:
        """Append a frame to the EventLog for a task session, suppressing errors."""
        if self._event_log is None or not session_id:
            return
        try:
            await self._event_log.append(session_id, "task", frame)
        except Exception:
            logger.exception(
                "EventLog.append failed for session={} frame_op={}", session_id, frame.get("op")
            )

    async def _emit_task_frame_for_event(
        self,
        event_type: str,
        payload: dict[str, Any],
        session_id: str | None,
    ) -> None:
        """Dual-write a task EventLog frame for a lifecycle SessionEvent.

        Maps event_type → frame op per the W3 frame semantics:
          - output_chunk         → append frame on the running assistant idx
          - agent_completed      → finalize frame (no reason)
          - agent_failed         → finalize frame (reason="agent_failed")
          - task_status_changed  → system create frame (text=JSON payload)
        Other event types are silently ignored (not framed).
        """
        if self._event_log is None or session_id is None:
            return

        from datetime import UTC, datetime

        ts = datetime.now(UTC).replace(tzinfo=None)

        if event_type == "output_chunk":
            # Append agent stdout chunk to the running assistant entry.
            running_idx = self._running_assistant_idx.get(session_id)
            if running_idx is None:
                logger.debug(
                    "EventLog: output_chunk for session={} but no running assistant idx", session_id
                )
                return
            chunk_text: str = ""
            if isinstance(payload, dict):
                chunk_text = str(payload.get("text") or payload.get("chunk") or "")
            frame: dict[str, Any] = {
                "type": "patch",
                "op": "append",
                "path": f"/entries/{running_idx}/text",
                "value": chunk_text,
            }
            await self._append_task_frame(session_id, frame)

        elif event_type == "agent_completed":
            running_idx = self._running_assistant_idx.get(session_id)
            if running_idx is not None:
                frame = {
                    "type": "patch",
                    "op": "finalize",
                    "path": f"/entries/{running_idx}",
                    "value": None,
                    "reason": None,
                }
                await self._append_task_frame(session_id, frame)
                self._running_assistant_idx.pop(session_id, None)

        elif event_type == "agent_failed":
            running_idx = self._running_assistant_idx.get(session_id)
            if running_idx is not None:
                frame = {
                    "type": "patch",
                    "op": "finalize",
                    "path": f"/entries/{running_idx}",
                    "value": None,
                    "reason": "agent_failed",
                }
                await self._append_task_frame(session_id, frame)
                self._running_assistant_idx.pop(session_id, None)

        elif event_type == "task_status_changed":
            status_text = json.dumps(
                {
                    "event": "status",
                    "from": payload.get("from"),
                    "to": payload.get("to"),
                    "ts": ts.isoformat(),
                }
            )
            frame = {
                "type": "patch",
                "op": "create",
                "path": "/entries/{idx}",
                "value": {
                    "role": "system",
                    "text": status_text,
                    "finalized": True,
                    "ts": ts.isoformat(),
                },
            }
            await self._append_task_frame(session_id, frame)

    async def emit(
        self,
        task_id: str,
        event_type: str,
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
        if event_type == "task_status_changed":
            self.publish_board(
                BoardEvent(
                    task_id=task_id,
                    kind="status_changed",
                    from_status=str(payload.get("from") or ""),
                    to_status=str(payload.get("to") or ""),
                )
            )
        elif event_type == "auto_review_started":
            self.publish_board(BoardEvent(task_id=task_id, kind="auto_review_started"))
        # Write a frame to the EventLog for task lifecycle events.
        await self._emit_task_frame_for_event(event_type, scrubbed_payload, session_id)
        return event

    async def emit_typed(
        self,
        task_id: str,
        agent_event: BaseModel,
        *,
        session_id: str | None = None,
        persist: bool = True,
    ) -> SessionEvent:
        """Emit a typed Pydantic agent-event variant.

        The variant's ``kind`` field becomes ``event_type`` in the DB row.
        The full ``model_dump(mode="json")`` is stored in ``payload``
        (the ``kind`` field is included so the row is self-describing).

        Payload secrets are scrubbed before persistence.
        """
        raw_payload: dict[str, Any] = agent_event.model_dump(mode="json")
        kind: str = raw_payload.get("kind", "unknown")
        scrubbed_payload = _scrub_secrets(raw_payload)
        event = SessionEvent(
            task_id=task_id,
            session_id=session_id,
            event_type=kind,  # type: ignore[arg-type] — kind is a str, DB accepts str
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
        if kind == "task_status_changed":
            self.publish_board(
                BoardEvent(
                    task_id=task_id,
                    kind="status_changed",
                    from_status=str(scrubbed_payload.get("from_status") or ""),
                    to_status=str(scrubbed_payload.get("to_status") or ""),
                )
            )
        elif kind == "auto_review_started":
            self.publish_board(BoardEvent(task_id=task_id, kind="auto_review_started"))
        # Write a frame to the EventLog for task lifecycle events.
        await self._emit_task_frame_for_event(kind, scrubbed_payload, session_id)
        return event

    def publish_board(self, event: BoardEvent) -> None:
        for queue in self._board_live_queues:
            self._enqueue_board_event(queue, event)

    # ── Settlement rule ────────────────────────────────────────────────────────

    def register_agent_end_subscriber(self, session_id: str, count: int = 1) -> None:
        """Register ``count`` subscribers that must acknowledge AgentEnd before idle.

        Call once per subscriber (e.g. the session manager's completion handler)
        before the agent session starts so the counter is ready when the event fires.
        """
        self._agent_end_pending[session_id] = self._agent_end_pending.get(session_id, 0) + count
        if session_id not in self._agent_end_idle:
            self._agent_end_idle[session_id] = asyncio.Event()

    def notify_agent_end_handled(self, session_id: str) -> None:
        """Decrement the outstanding AgentEnd subscriber count for a session.

        When the count reaches zero the idle event fires and ``wait_idle``
        unblocks.  Safe to call from sync context (no I/O).
        """
        remaining = max(0, self._agent_end_pending.get(session_id, 0) - 1)
        self._agent_end_pending[session_id] = remaining
        if remaining == 0:
            idle = self._agent_end_idle.get(session_id)
            if idle is not None:
                idle.set()

    async def wait_idle(self, session_id: str, *, timeout: float | None = None) -> bool:
        """Wait until all AgentEnd subscribers for ``session_id`` have acknowledged.

        Returns ``True`` if idle was reached, ``False`` if ``timeout`` expired.
        If no subscribers were registered the method returns immediately with ``True``.
        """
        idle = self._agent_end_idle.get(session_id)
        if idle is None or self._agent_end_pending.get(session_id, 0) == 0:
            return True
        if timeout is None:
            await idle.wait()
            return True
        try:
            await asyncio.wait_for(idle.wait(), timeout=timeout)
            return True
        except TimeoutError:
            return False

    async def list_all(self, *, offset: int = 0, limit: int = 20) -> list[SessionEvent]:
        return await _db_async(
            self._engine,
            lambda s: list(
                s.exec(
                    select(SessionEvent)
                    .order_by(_sa_col(SessionEvent.created_at))
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
        return await list_events(
            self._engine, task_id, offset=offset, limit=limit, session_id=session_id
        )

    async def list_recent(
        self,
        task_id: str,
        *,
        limit: int = 50,
        before: str | None = None,
        before_id: str | None = None,
        session_id: str | None = None,
    ) -> builtins.list[SessionEvent]:
        return await list_events_recent(
            self._engine,
            task_id,
            limit=limit,
            before=before,
            before_id=before_id,
            session_id=session_id,
        )

    async def list_before(
        self,
        task_id: str,
        *,
        before: str,
        before_id: str | None = None,
        limit: int = 50,
        session_id: str | None = None,
    ) -> builtins.list[SessionEvent]:
        return await list_events_before(
            self._engine,
            task_id,
            before=before,
            before_id=before_id,
            limit=limit,
            session_id=session_id,
        )

    async def list_after(
        self,
        task_id: str,
        *,
        after_ts: str,
        after_id: str,
        limit: int = 50,
        session_id: str | None = None,
    ) -> builtins.list[SessionEvent]:
        return await list_events_after(
            self._engine,
            task_id,
            after_ts=after_ts,
            after_id=after_id,
            limit=limit,
            session_id=session_id,
        )

    async def latest(
        self,
        task_id: str,
        *,
        event_type: str | None = None,
    ) -> SessionEvent | None:
        return await latest_event(self._engine, task_id, event_type=event_type)

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


__all__ = [
    "BoardEvent",
    "Events",
    "emit_event",
    "latest_event",
    "list_events",
    "list_events_after",
    "list_events_before",
    "list_events_recent",
]
