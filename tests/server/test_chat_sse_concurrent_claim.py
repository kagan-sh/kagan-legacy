"""Regression test for the Greptile P1 SSE concurrent-turn race.

Pre-fix, ``_sse_stream`` performed in this order:

1. Pre-flight ``turn_status`` check (advisory only).
2. ``engine.push_user`` — persists a user row.
3. ``_broadcast`` CHAT_USER_MESSAGE + CHAT_TURN_STARTED.
4. ``engine.stream_assistant`` — only here did ``_claim_slot`` actually
   raise ``TurnInProgressError`` if another turn was in flight.

Between (1) and (4) there are four ``await`` points. A concurrent request on
the same session could pass the pre-flight check, persist a user row,
broadcast frames, then trip ``TurnInProgressError`` at ``stream_assistant``.

Post-fix the route claims the slot synchronously via
``ChatEngine.try_claim_turn`` BEFORE any side effects, so the second request
emits CHAT_ERROR and closes cleanly without orphaning a user row.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
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


def _frames(chunks: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for chunk in chunks:
        for line in chunk.splitlines():
            if line.startswith("data: "):
                out.append(json.loads(line[len("data: ") :]))
    return out


async def test_concurrent_sse_streams_claim_atomically(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Two concurrent /stream requests for the same session: only the first
    persists a user row; the second emits CHAT_ERROR and closes cleanly.
    """
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()

        started = asyncio.Event()
        suspending = SuspendingFactory(first_chunk="partial", started=started)
        # The route builds a per-request SpawnPerTurnACPFactory; replace it
        # with the suspending factory so the first turn parks in flight and
        # the second request races against it.
        monkeypatch.setattr(
            _chat_routes,
            "SpawnPerTurnACPFactory",
            lambda **_kwargs: suspending,
        )

        session = await core.chat_sessions.create(source="web", label="t")
        session_dict = await get_chat_session(core, session.id)
        assert session_dict is not None

        ctx = SimpleNamespace(client=core)

        first_stream = _chat_routes._sse_stream(
            ctx,
            session.id,
            session_dict,
            text="first",
            backend="claude-code",
            attachments=None,
        )
        second_stream = _chat_routes._sse_stream(
            ctx,
            session.id,
            dict(session_dict),
            text="second",
            backend="claude-code",
            attachments=None,
        )

        first_consumer = asyncio.create_task(_drain_sse(first_stream))
        # Wait until the first turn is actually parked (slot claimed and
        # the suspending factory has emitted its chunk) — ensures the second
        # request races against an in-flight turn, not the empty state.
        await asyncio.wait_for(started.wait(), timeout=5.0)

        # The second stream must emit CHAT_ERROR and close cleanly without
        # persisting a user row or broadcasting CHAT_USER_MESSAGE /
        # CHAT_TURN_STARTED frames.
        second_chunks = await asyncio.wait_for(_drain_sse(second_stream), timeout=5.0)
        second_frames = _frames(second_chunks)

        assert len(second_frames) == 1, (
            f"Second /stream should emit exactly one CHAT_ERROR; got {second_frames}"
        )
        assert second_frames[0]["t"] == "CHAT_ERROR"
        assert "in progress" in second_frames[0]["error"].lower()

        # Cancel the first turn so the consumer drains.
        await core.chat.cancel(session.id)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(first_consumer, timeout=5.0)

        # Exactly ONE user row should be persisted (from the first request).
        history = await core.chat.history(session.id)
        user_rows = [m for m in history if m.role == "user"]
        assert len(user_rows) == 1, (
            f"Concurrent /stream must NOT orphan user rows; saw {len(user_rows)}"
        )
        assert user_rows[0].content == "first"
    finally:
        core.close()


async def test_pre_stream_failure_releases_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If anything between try_claim_turn and entering stream_assistant
    raises (settings.get / resolve_repo_path / yield), the slot must be
    released so a subsequent /stream request does not 409 forever.

    Greptile P1: the original ``pre_stream_ok`` guard only covered
    ``push_user``; the gap between push_user and stream_assistant included
    two more awaits + two yields where a slot leak was possible.
    """
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()

        session = await core.chat_sessions.create(source="web", label="t")
        session_dict = await get_chat_session(core, session.id)
        assert session_dict is not None

        ctx = SimpleNamespace(client=core)

        # Force settings.get() to raise — simulates a flaky read between
        # try_claim_turn and stream_assistant entry.
        async def _boom(*_args: Any, **_kwargs: Any) -> dict[str, str]:
            raise RuntimeError("simulated settings failure")

        monkeypatch.setattr(core.settings, "get", _boom)

        stream = _chat_routes._sse_stream(
            ctx,
            session.id,
            session_dict,
            text="first",
            backend="claude-code",
            attachments=None,
        )

        # Drain the generator — exception must propagate via the route's
        # except branch but the slot must be released by the finally.
        chunks = await _drain_sse(stream)
        # The CHAT_USER_MESSAGE + CHAT_TURN_STARTED frames go out before the
        # settings.get() call, then CHAT_ERROR fires when the exception is
        # caught.
        frames = _frames(chunks)
        kinds = [f["t"] for f in frames]
        assert "CHAT_ERROR" in kinds

        # Slot must be free: a follow-up turn_status should report inactive.
        status = core.chat.turn_status(session.id)
        assert not status.active, (
            "Slot leaked after pre-stream failure — engine._states still has "
            "the sentinel."
        )
    finally:
        core.close()


async def test_client_disconnect_mid_stream_releases_slot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Starlette throws CancelledError at the active yield when the SSE
    client drops. Pre-fix the disconnect branch returned without calling
    engine.detach, leaving the sentinel in engine._states until Python's
    async-gen finalizer eventually fired. Every subsequent /stream for the
    same session 409'd in the meantime.

    Greptile P1.
    """
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()

        started = asyncio.Event()
        suspending = SuspendingFactory(first_chunk="partial", started=started)
        monkeypatch.setattr(
            _chat_routes,
            "SpawnPerTurnACPFactory",
            lambda **_kwargs: suspending,
        )

        session = await core.chat_sessions.create(source="web", label="t")
        session_dict = await get_chat_session(core, session.id)
        assert session_dict is not None

        ctx = SimpleNamespace(client=core)

        stream = _chat_routes._sse_stream(
            ctx,
            session.id,
            session_dict,
            text="first",
            backend="claude-code",
            attachments=None,
        )

        # Drive the stream until it parks on the suspending factory, then
        # simulate a Starlette client disconnect by cancelling the consumer
        # task — Starlette throws CancelledError at the active yield, which
        # propagates into _sse_stream's except branch. The branch should run
        # engine.detach so the slot is freed.
        consumer = asyncio.create_task(_drain_sse(stream))
        await asyncio.wait_for(started.wait(), timeout=5.0)
        consumer.cancel()
        with contextlib.suppress(asyncio.CancelledError, asyncio.TimeoutError):
            await asyncio.wait_for(consumer, timeout=2.0)

        # Slot must be free: a follow-up /stream must not 409.
        await asyncio.sleep(0)  # let any pending awaits flush
        status = core.chat.turn_status(session.id)
        assert not status.active, (
            "Slot leaked on client disconnect — engine._states still has "
            "the sentinel after aclose()."
        )
    finally:
        core.close()
