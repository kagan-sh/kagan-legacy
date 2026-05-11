"""Unit tests for kagan.core._event_log.

TDD-first spec: all tests written before implementation.
Real SQLite DB via event_log fixtures — no mocks.
"""

from __future__ import annotations

import asyncio

import pytest

from kagan.core._event_log import EventLog, FrameRow

pytestmark = [pytest.mark.unit]

pytest_plugins = ["tests.helpers.event_log"]


# ---------------------------------------------------------------------------
# append
# ---------------------------------------------------------------------------


async def test_append_assigns_monotonic_seq_per_session(
    event_log: EventLog,
    session_id: str,
) -> None:
    """seq is assigned monotonically-increasing integers within one (session, kind)."""
    s1 = await event_log.append(session_id, "chat", {"text": "a"})
    s2 = await event_log.append(session_id, "chat", {"text": "b"})
    s3 = await event_log.append(session_id, "chat", {"text": "c"})

    assert s1 == 0
    assert s2 == 1
    assert s3 == 2


async def test_append_assigns_independent_seqs_per_kind(
    event_log: EventLog,
    session_id: str,
) -> None:
    """chat and task seqs are independent counters — both start at 0."""
    chat_seq = await event_log.append(session_id, "chat", {"text": "hello"})
    task_seq = await event_log.append(session_id, "task", {"op": "start"})

    assert chat_seq == 0
    assert task_seq == 0


# ---------------------------------------------------------------------------
# history
# ---------------------------------------------------------------------------


async def test_history_returns_frames_in_seq_order(
    event_log: EventLog,
    session_id: str,
) -> None:
    """history() returns FrameRows sorted ascending by seq."""
    for i in range(5):
        await event_log.append(session_id, "chat", {"i": i})

    rows = await event_log.history(session_id, "chat")
    assert len(rows) == 5
    seqs = [r.seq for r in rows]
    assert seqs == sorted(seqs)
    assert seqs == list(range(5))


async def test_history_from_seq_skips_lower_seqs(
    event_log: EventLog,
    session_id: str,
) -> None:
    """history(from_seq=N) returns only rows with seq >= N."""
    for i in range(6):
        await event_log.append(session_id, "chat", {"i": i})

    rows = await event_log.history(session_id, "chat", from_seq=3)
    assert len(rows) == 3
    assert [r.seq for r in rows] == [3, 4, 5]


async def test_history_limit_caps_rows(
    event_log: EventLog,
    session_id: str,
) -> None:
    """history(limit=N) returns at most N rows."""
    for i in range(10):
        await event_log.append(session_id, "chat", {"i": i})

    rows = await event_log.history(session_id, "chat", limit=4)
    assert len(rows) == 4
    assert [r.seq for r in rows] == [0, 1, 2, 3]


# ---------------------------------------------------------------------------
# subscribe
# ---------------------------------------------------------------------------


async def test_subscribe_yields_snapshot_then_live(
    event_log: EventLog,
    session_id: str,
) -> None:
    """subscribe() yields backlog frames first, then frames appended while live."""
    # Write two frames before subscribing (backlog)
    await event_log.append(session_id, "chat", {"phase": "backlog", "i": 0})
    await event_log.append(session_id, "chat", {"phase": "backlog", "i": 1})

    collected: list[FrameRow] = []

    async def _consume() -> None:
        async for row in event_log.subscribe(session_id, "chat"):
            collected.append(row)
            if len(collected) >= 4:
                break

    # Start consumer; it will block waiting for live frames after backlog
    task = asyncio.create_task(_consume())

    # Let consumer drain the backlog
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Emit two live frames
    await event_log.append(session_id, "chat", {"phase": "live", "i": 2})
    await event_log.append(session_id, "chat", {"phase": "live", "i": 3})

    await asyncio.wait_for(task, timeout=3.0)

    assert len(collected) == 4
    assert collected[0].frame["phase"] == "backlog"
    assert collected[1].frame["phase"] == "backlog"
    assert collected[2].frame["phase"] == "live"
    assert collected[3].frame["phase"] == "live"
    assert [r.seq for r in collected] == [0, 1, 2, 3]


async def test_subscribe_with_from_seq_skips_seen(
    event_log: EventLog,
    session_id: str,
) -> None:
    """subscribe(from_seq=N) skips backlog frames with seq < N."""
    for i in range(5):
        await event_log.append(session_id, "task", {"i": i})

    collected: list[FrameRow] = []

    async def _consume() -> None:
        async for row in event_log.subscribe(session_id, "task", from_seq=3):
            collected.append(row)
            if len(collected) >= 2:
                break

    task = asyncio.create_task(_consume())
    await asyncio.wait_for(task, timeout=3.0)

    assert len(collected) == 2
    assert [r.seq for r in collected] == [3, 4]


# ---------------------------------------------------------------------------
# EntryIndexProvider — restart recovery
# ---------------------------------------------------------------------------


async def test_index_provider_recovers_max_idx_after_restart(
    event_log_engine,
    session_id: str,
) -> None:
    """A new EventLog seeded from an existing DB continues idx from max+1."""
    log1 = EventLog(event_log_engine)
    for i in range(3):
        await log1.append(session_id, "chat", {"i": i})

    # Confirm idx 0,1,2 stored
    rows1 = await log1.history(session_id, "chat")
    assert [r.idx for r in rows1] == [0, 1, 2]

    # Create fresh EventLog on same engine (simulates restart)
    log2 = EventLog(event_log_engine)
    seq = await log2.append(session_id, "chat", {"i": 3})

    rows2 = await log2.history(session_id, "chat")
    # idx should continue from 3, not restart at 0
    assert rows2[seq].idx == 3


# ---------------------------------------------------------------------------
# Concurrent appends
# ---------------------------------------------------------------------------


async def test_concurrent_appends_keep_seq_unique(
    event_log: EventLog,
    session_id: str,
) -> None:
    """Concurrent appends must not produce duplicate seq values."""
    n = 20
    tasks = [asyncio.create_task(event_log.append(session_id, "chat", {"n": i})) for i in range(n)]
    seqs = list(await asyncio.gather(*tasks))

    # All seq values must be unique
    assert len(set(seqs)) == n
    # All values must be in range [0, n)
    assert set(seqs) == set(range(n))


# ---------------------------------------------------------------------------
# Two subscribers
# ---------------------------------------------------------------------------


async def test_subscribe_two_clients_see_identical_frames(
    event_log: EventLog,
    session_id: str,
) -> None:
    """Two concurrent subscribers see the same sequence of frames."""
    # Pre-load one backlog frame
    await event_log.append(session_id, "chat", {"slot": 0})

    client_a: list[FrameRow] = []
    client_b: list[FrameRow] = []

    target = 3  # backlog(1) + live(2)

    async def _consumer(sink: list[FrameRow]) -> None:
        async for row in event_log.subscribe(session_id, "chat"):
            sink.append(row)
            if len(sink) >= target:
                break

    task_a = asyncio.create_task(_consumer(client_a))
    task_b = asyncio.create_task(_consumer(client_b))

    # Let both consumers drain backlog
    await asyncio.sleep(0)
    await asyncio.sleep(0)

    # Emit two live frames
    await event_log.append(session_id, "chat", {"slot": 1})
    await event_log.append(session_id, "chat", {"slot": 2})

    await asyncio.wait_for(asyncio.gather(task_a, task_b), timeout=5.0)

    assert len(client_a) == target
    assert len(client_b) == target
    assert [r.seq for r in client_a] == [r.seq for r in client_b]
    assert [r.frame for r in client_a] == [r.frame for r in client_b]
