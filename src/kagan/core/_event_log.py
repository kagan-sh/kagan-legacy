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

    The counter is seeded from ``max(idx)`` the first time a new
    ``EventLog`` instance appends to a given ``(session_id, kind)`` pair,
    so restarts never reuse idx values.
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
        """Read ``max(idx)`` from the DB for this (session, kind) pair."""

        def _query(s) -> int | None:
            stmt = select(func.max(EventLogEntry.idx)).where(
                EventLogEntry.session_id == session_id,
                EventLogEntry.kind == kind,
            )
            return s.exec(stmt).one()

        result = _db_sync(self._engine, _query)
        return (result + 1) if result is not None else 0

    async def next(self, session_id: str, kind: str) -> int:
        """Return the next idx for the given ``(session_id, kind)`` pair.

        The first call seeds from ``max(idx)`` in the DB; subsequent calls
        increment in-process.
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
    ) -> int:
        """Persist a frame and return its assigned ``seq``.

        The ``seq`` is monotonically increasing within ``(session_id, kind)``.
        """
        _seq, _idx = await self._append_internal(session_id, kind, frame)
        return _seq

    async def append_with_idx(
        self,
        session_id: str,
        kind: Literal["chat", "task"],
        frame: dict[str, Any],
    ) -> tuple[int, int]:
        """Persist a frame and return ``(seq, idx)``.

        The ``seq`` is monotonically increasing within ``(session_id, kind)``.
        The ``idx`` is the stable entry index embedded in the frame path.
        """
        return await self._append_internal(session_id, kind, frame)

    async def _append_internal(
        self,
        session_id: str,
        kind: Literal["chat", "task"],
        frame: dict[str, Any],
    ) -> tuple[int, int]:
        seq = await self._seq.next(session_id, kind)
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
    ) -> AsyncIterator[FrameRow]:
        """Yield backlog from ``from_seq``, then live tail.

        The backlog is replayed from the DB before the live queue is
        registered, so no frames are missed between the two phases.
        """
        # Phase 1 — replay backlog
        backlog = await self.history(session_id, kind, from_seq=from_seq)
        for row in backlog:
            yield row

        # Phase 2 — live tail
        queue = _BoundedQueue()
        key = (session_id, kind)
        subs = self._subs.setdefault(key, [])
        subs.append(queue)

        # The window between backlog end and queue registration can miss frames.
        # Catch up any frames that arrived between the DB read and queue attach.
        catchup_seq = (backlog[-1].seq + 1) if backlog else from_seq
        catchup = await self.history(session_id, kind, from_seq=catchup_seq)
        for row in catchup:
            # Deduplicate against anything already queued
            yield row

        try:
            while True:
                row = await queue.get()
                # Skip frames we already yielded in the catch-up pass
                if row.seq < catchup_seq + len(catchup):
                    continue
                yield row
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
