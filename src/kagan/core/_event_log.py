"""Append-only frame store for chat and task event streams.

Mirrors the ``snapshot → ready → live`` resume pattern from vibe-kanban's
``MsgStore::history_plus_stream``.  Each ``(session_id, kind)`` pair has an
independent, monotonically-increasing ``seq`` counter so SSE clients can use
``Last-Event-ID`` to resume without replaying already-seen frames.

Public API
----------
- ``EntryIndexProvider`` — atomic seq counter per ``(session_id, kind)``.
- ``EventLog``           — append/history/subscribe on top of the DB table.
- ``FrameRow``           — lightweight DTO returned from history/subscribe.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections import deque
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

from loguru import logger
from sqlalchemy import Engine, func
from sqlmodel import select

from kagan.core._db_helpers import _add_and_refresh, _db_async, _db_sync
from kagan.core.errors import KaganError
from kagan.core.models import EventLogEntry

_LIVE_QUEUE_MAX = 512

# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class EventLogError(KaganError):
    """Raised for EventLog-specific errors."""


def _parse_entry_idx_from_patch_path(path: object) -> int | None:
    """Return entry index ``N`` from ``/entries/N`` or ``/entries/N/...``."""
    if not isinstance(path, str) or not path.startswith("/entries/"):
        return None
    rest = path[len("/entries/") :]
    head, _, _tail = rest.partition("/")
    if head.isdigit():
        return int(head)
    return None


def _infer_row_idx_from_frame(frame: dict[str, Any]) -> int | None:
    """Derive the logical entry idx for a patch row when the frame carries it."""
    op = frame.get("op")
    if op == "create":
        val = frame.get("value")
        if isinstance(val, dict):
            vi = val.get("idx")
            if isinstance(vi, int):
                return vi
        return None
    if op in ("append", "finalize"):
        return _parse_entry_idx_from_patch_path(frame.get("path"))
    return None


# ---------------------------------------------------------------------------
# FrameRow — lightweight DTO
# ---------------------------------------------------------------------------


@dataclass(slots=True, frozen=True)
class FrameRow:
    """Immutable view of a single event_log row."""

    seq: int
    idx: int
    ts: datetime
    frame: dict[str, Any]


# ---------------------------------------------------------------------------
# EntryIndexProvider — atomic counter seeded from DB max(idx)
# ---------------------------------------------------------------------------


class EntryIndexProvider:
    """Per-(session_id, kind) monotonic counter.

    The counter seeds from the database so restarts never reuse logical entry
    indices.  For JSON patch frames with ``op == "create"``, we take
    ``max(idx)`` over those rows only (conversation entry indices).  Rows
    without a create op (legacy tests or pre-patch data) fall back to
    ``max(idx)`` across all rows.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._counters: dict[tuple[str, str], int] = {}

    def _lock(self, session_id: str, kind: str) -> asyncio.Lock:
        key = (session_id, kind)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _seed_from_db(self, session_id: str, kind: str) -> int:
        """Next idx to assign: ``max(create-entry idx)+1``, else ``max(idx)+1``."""

        def _query(s) -> int:
            op_col = EventLogEntry.frame["op"].as_string()
            stmt_create = select(func.max(EventLogEntry.idx)).where(
                EventLogEntry.session_id == session_id,
                EventLogEntry.kind == kind,
                op_col == "create",
            )
            m_create = s.exec(stmt_create).one()

            stmt_all = select(func.max(EventLogEntry.idx)).where(
                EventLogEntry.session_id == session_id,
                EventLogEntry.kind == kind,
            )
            m_all = s.exec(stmt_all).one()

            if m_create is not None:
                return m_create + 1
            if m_all is not None:
                return m_all + 1
            return 0

        return _db_sync(self._engine, _query)

    async def ensure_at_least(self, session_id: str, kind: str, floor_next: int) -> None:
        """Ensure the next ``next()`` value is at least ``floor_next``."""
        key = (session_id, kind)
        async with self._lock(session_id, kind):
            if key not in self._counters:
                seed = await asyncio.to_thread(self._seed_from_db, session_id, kind)
                self._counters[key] = seed
            if self._counters[key] < floor_next:
                self._counters[key] = floor_next

    async def next(self, session_id: str, kind: str) -> int:
        """Return the next idx for the given ``(session_id, kind)`` pair.

        The first call seeds from the DB; subsequent calls increment in-process.
        """
        key = (session_id, kind)
        async with self._lock(session_id, kind):
            if key not in self._counters:
                seed = await asyncio.to_thread(self._seed_from_db, session_id, kind)
                self._counters[key] = seed
                logger.debug(
                    "EntryIndexProvider seeded ({}, {}) → idx={}",
                    session_id,
                    kind,
                    seed,
                )
            val = self._counters[key]
            self._counters[key] += 1
            return val


# ---------------------------------------------------------------------------
# _SeqProvider — in-process seq counter (separate from idx)
# ---------------------------------------------------------------------------


class _SeqProvider:
    """Monotonic seq counter per (session_id, kind), backed by DB max(seq)."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._locks: dict[tuple[str, str], asyncio.Lock] = {}
        self._counters: dict[tuple[str, str], int] = {}

    def _lock(self, session_id: str, kind: str) -> asyncio.Lock:
        key = (session_id, kind)
        if key not in self._locks:
            self._locks[key] = asyncio.Lock()
        return self._locks[key]

    def _seed_from_db(self, session_id: str, kind: str) -> int:
        def _query(s) -> int | None:
            stmt = select(func.max(EventLogEntry.seq)).where(
                EventLogEntry.session_id == session_id,
                EventLogEntry.kind == kind,
            )
            return s.exec(stmt).one()

        result = _db_sync(self._engine, _query)
        return (result + 1) if result is not None else 0

    async def next(self, session_id: str, kind: str) -> int:
        key = (session_id, kind)
        async with self._lock(session_id, kind):
            if key not in self._counters:
                seed = await asyncio.to_thread(self._seed_from_db, session_id, kind)
                self._counters[key] = seed
            val = self._counters[key]
            self._counters[key] += 1
            return val


# ---------------------------------------------------------------------------
# _BoundedQueue — minimal async queue for live-tail subscribers
# ---------------------------------------------------------------------------


class _BoundedQueue:
    def __init__(self) -> None:
        self._items: deque[FrameRow] = deque()
        self._ready = asyncio.Event()

    def put(self, row: FrameRow) -> None:
        if len(self._items) >= _LIVE_QUEUE_MAX:
            logger.warning(
                "EventLog live queue full — dropping oldest frame (seq={})",
                self._items[0].seq,
            )
            self._items.popleft()
        self._items.append(row)
        self._ready.set()

    async def get(self) -> FrameRow:
        while not self._items:
            await self._ready.wait()
        item = self._items.popleft()
        if not self._items:
            self._ready.clear()
        return item


# ---------------------------------------------------------------------------
# EventLog
# ---------------------------------------------------------------------------


class EventLog:
    """Append-only frame store.

    Each ``(session_id, kind)`` pair gets independent, monotonically-increasing
    ``seq`` and ``idx`` values.  Live subscribers are notified in-process via
    a queue; backlog is replayed from the DB.
    """

    def __init__(self, engine: Engine) -> None:
        self._engine = engine
        self._seq = _SeqProvider(engine)
        self._idx = EntryIndexProvider(engine)
        # Per-(session_id, kind) list of live subscriber queues
        self._subs: dict[tuple[str, str], list[_BoundedQueue]] = {}

    async def append(
        self,
        session_id: str,
        kind: Literal["chat", "task"],
        frame: dict[str, Any],
        *,
        row_idx: int | None = None,
    ) -> int:
        """Persist a frame and return its assigned ``seq``.

        The ``seq`` is monotonically increasing within ``(session_id, kind)``.
        """
        _seq, _idx = await self._append_internal(session_id, kind, frame, row_idx=row_idx)
        return _seq

    async def append_with_idx(
        self,
        session_id: str,
        kind: Literal["chat", "task"],
        frame: dict[str, Any],
        *,
        row_idx: int | None = None,
    ) -> tuple[int, int]:
        """Persist a frame and return ``(seq, idx)``.

        The ``seq`` is monotonically increasing within ``(session_id, kind)``.
        The ``idx`` is the stable entry index embedded in the frame path.
        """
        return await self._append_internal(session_id, kind, frame, row_idx=row_idx)

    async def _append_internal(
        self,
        session_id: str,
        kind: Literal["chat", "task"],
        frame: dict[str, Any],
        *,
        row_idx: int | None = None,
    ) -> tuple[int, int]:
        seq = await self._seq.next(session_id, kind)
        resolved = row_idx if row_idx is not None else _infer_row_idx_from_frame(frame)
        if resolved is not None:
            idx = resolved
            await self._idx.ensure_at_least(session_id, kind, resolved + 1)
        else:
            idx = await self._idx.next(session_id, kind)
        ts = datetime.now(UTC).replace(tzinfo=None)

        entry = EventLogEntry(
            session_id=session_id,
            kind=kind,
            seq=seq,
            idx=idx,
            ts=ts,
            frame=frame,
        )
        await _db_async(self._engine, lambda s: _add_and_refresh(s, entry))

        row = FrameRow(seq=seq, idx=idx, ts=ts, frame=frame)
        key = (session_id, kind)
        for queue in list(self._subs.get(key, [])):
            queue.put(row)

        logger.debug("EventLog.append session={} kind={} seq={} idx={}", session_id, kind, seq, idx)
        return seq, idx

    async def history(
        self,
        session_id: str,
        kind: str,
        from_seq: int = 0,
        limit: int | None = None,
    ) -> list[FrameRow]:
        """Return frames in ascending ``seq`` order.

        Parameters
        ----------
        from_seq:
            Skip frames with ``seq < from_seq``.
        limit:
            Cap the result set.
        """

        def _query(s) -> list[FrameRow]:
            stmt = (
                select(EventLogEntry)
                .where(
                    EventLogEntry.session_id == session_id,
                    EventLogEntry.kind == kind,
                    EventLogEntry.seq >= from_seq,
                )
                .order_by(EventLogEntry.seq)
            )
            if limit is not None:
                stmt = stmt.limit(limit)
            rows = list(s.exec(stmt).all())
            return [FrameRow(seq=r.seq, idx=r.idx, ts=r.ts, frame=r.frame or {}) for r in rows]

        return await _db_async(self._engine, _query)

    async def subscribe(
        self,
        session_id: str,
        kind: str,
        from_seq: int = 0,
        *,
        queue_registered: asyncio.Event | None = None,
    ) -> AsyncIterator[FrameRow]:
        """Yield backlog from ``from_seq``, then live tail.

        The backlog is replayed from the DB before the live queue is
        registered, so no frames are missed between the two phases.

        queue_registered
            When set, ``.set()`` is invoked immediately before the first
            ``await`` on the live queue (after backlog + catch-up). Tests can
            ``await queue_registered.wait()`` before appending live frames so
            they never race registration.
        """
        # Phase 1 — replay backlog
        backlog = await self.history(session_id, kind, from_seq=from_seq)
        max_yielded = from_seq - 1
        for row in backlog:
            yield row
            if row.seq > max_yielded:
                max_yielded = row.seq

        # Phase 2 — live tail
        queue = _BoundedQueue()
        key = (session_id, kind)
        subs = self._subs.setdefault(key, [])
        subs.append(queue)

        # The window between backlog end and queue registration can miss frames.
        # Catch up any frames that arrived between the DB read and queue attach.
        catchup_seq = max_yielded + 1
        catchup = await self.history(session_id, kind, from_seq=catchup_seq)
        for row in catchup:
            yield row
            if row.seq > max_yielded:
                max_yielded = row.seq

        if queue_registered is not None:
            queue_registered.set()

        try:
            while True:
                row = await queue.get()
                # Skip frames we already yielded in backlog or catch-up passes
                if row.seq <= max_yielded:
                    continue
                yield row
                max_yielded = row.seq
        finally:
            with contextlib.suppress(ValueError):
                subs.remove(queue)
            if not subs:
                self._subs.pop(key, None)


__all__ = [
    "EntryIndexProvider",
    "EventLog",
    "EventLogError",
    "FrameRow",
]
