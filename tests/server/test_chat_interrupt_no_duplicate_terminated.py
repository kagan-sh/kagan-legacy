"""Regression test for the Greptile P2 duplicate CHAT_TURN_TERMINATED frame.

Pre-fix, calling ``/interrupt`` while a ``/stream`` consumer was active
broadcast ``CHAT_TURN_TERMINATED`` twice:

1. Once from the ``/interrupt`` handler itself (an unconditional
   ``_broadcast`` after ``engine.cancel``).
2. Once from ``_sse_stream`` mapping the engine's ``TurnCancelled`` event
   into a SSE frame and broadcasting it.

This test drives a real ``ChatEngine`` with a ``SuspendingFactory``, taps
the ``/watch`` fanout via a queue, and asserts ``CHAT_TURN_TERMINATED`` is
seen exactly once.
"""

from __future__ import annotations

import asyncio
import contextlib
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from kagan.cli.chat.sessions import get_chat_session
from kagan.core import KaganCore
from kagan.server import _chat_routes
from tests.helpers.chat_engine import SuspendingFactory

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.smoke]


async def _drain_sse(stream: Any) -> list[str]:
    chunks: list[str] = []
    async for chunk in stream:
        chunks.append(chunk)
    return chunks


async def _interrupt_via_engine(core: KaganCore, session_id: str) -> None:
    """Emulate the body of the ``/interrupt`` route handler.

    Mirrors ``chat_interrupt`` in ``_chat_routes`` but unwrapped so the test
    does not need a Starlette request/response cycle. Any divergence from the
    handler's logic would mask the regression we're guarding against.
    """
    result = await core.chat.cancel(session_id, reason="user")
    if not result.was_running:
        _chat_routes._broadcast(session_id, {"t": "CHAT_TURN_TERMINATED", "reason": "user"})


async def test_interrupt_during_active_stream_emits_terminated_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When a ``/stream`` consumer is active, ``/interrupt`` MUST NOT
    broadcast its own CHAT_TURN_TERMINATED — the engine's TurnCancelled
    already propagates via ``_sse_stream``.
    """
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()

        started = asyncio.Event()
        suspending = SuspendingFactory(first_chunk="partial", started=started)
        # The route builds a per-request SpawnPerTurnACPFactory; replace it
        # with our suspending factory so the turn parks in flight.
        monkeypatch.setattr(
            _chat_routes,
            "SpawnPerTurnACPFactory",
            lambda **_kwargs: suspending,
        )

        session = await core.chat_sessions.create(source="web", label="t")
        session_dict = await get_chat_session(core, session.id)
        assert session_dict is not None

        # Subscribe to the /watch fanout with a queue so we can count frames.
        watch_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _chat_routes._chat_subscribers[session.id].append(watch_queue)

        ctx = SimpleNamespace(client=core)
        sse_stream = _chat_routes._sse_stream(
            ctx,
            session.id,
            session_dict,
            text="hello",
            backend="claude-code",
            attachments=None,
        )

        consumer = asyncio.create_task(_drain_sse(sse_stream))
        try:
            await asyncio.wait_for(started.wait(), timeout=5.0)
            # Let the partial chunk surface through the queue.
            await asyncio.sleep(0.05)

            await _interrupt_via_engine(core, session.id)

            await asyncio.wait_for(consumer, timeout=5.0)
        finally:
            with contextlib.suppress(Exception):
                _chat_routes._chat_subscribers[session.id].remove(watch_queue)

        # Drain the watch queue and count CHAT_TURN_TERMINATED frames.
        terminated_count = 0
        while not watch_queue.empty():
            event = watch_queue.get_nowait()
            if event.get("t") == "CHAT_TURN_TERMINATED":
                terminated_count += 1

        assert terminated_count == 1, (
            f"CHAT_TURN_TERMINATED should fire exactly once; saw {terminated_count}"
        )
    finally:
        core.close()


async def test_interrupt_with_no_active_turn_still_broadcasts_once(
    tmp_path: Path,
) -> None:
    """When no ``/stream`` consumer is active, ``/interrupt`` falls back to
    broadcasting CHAT_TURN_TERMINATED itself so /watch-only subscribers see
    the cancel signal.
    """
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()
        session = await core.chat_sessions.create(source="web", label="t")

        watch_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _chat_routes._chat_subscribers[session.id].append(watch_queue)
        try:
            await _interrupt_via_engine(core, session.id)
        finally:
            _chat_routes._chat_subscribers[session.id].remove(watch_queue)

        terminated_count = 0
        while not watch_queue.empty():
            event = watch_queue.get_nowait()
            if event.get("t") == "CHAT_TURN_TERMINATED":
                terminated_count += 1
        assert terminated_count == 1, (
            "When no turn is in flight /interrupt MUST broadcast "
            f"CHAT_TURN_TERMINATED exactly once; saw {terminated_count}"
        )
    finally:
        core.close()
