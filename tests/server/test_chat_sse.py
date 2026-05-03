"""Wire-contract tests for the chat SSE transport layer.

Covers:
- ChatEvent → SSE frame mapping (absorbs test_chat_sse_mapping.py)
- /watch fanout broadcast to watch subscribers
- /interrupt emits CHAT_TURN_TERMINATED exactly once
- Concurrent /stream emits CHAT_ERROR without orphaning a user row

These tests drive the real ``_sse_stream`` generator and ``_broadcast``
function directly (transport seam), with ``SpawnPerTurnACPFactory`` replaced
by scripted/suspending helpers.  No HTTP stack needed.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from kagan.core.chat.events import (
    AssistantChunk,
    AssistantMessagePersisted,
    ToolCallProgress,
    ToolCallStart,
    TurnCancelled,
    TurnDone,
    TurnError,
    TurnStarted,
    UsageUpdate,
)
from kagan.server._chat_routes import _chat_event_to_sse_frame

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.smoke]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# 1. ChatEvent → SSE frame mapping
# ---------------------------------------------------------------------------


def test_chat_event_to_sse_frame_mapping() -> None:
    """Every ChatEvent variant maps to its documented wire shape."""
    assert _chat_event_to_sse_frame(AssistantChunk(text="hi")) == {
        "t": "CHAT_CHUNK",
        "content": "hi",
    }
    assert _chat_event_to_sse_frame(AssistantChunk(text="thinking", thought=True)) == {
        "t": "CHAT_CHUNK",
        "content": "thinking",
        "thought": True,
    }
    assert _chat_event_to_sse_frame(ToolCallStart(tool_id="abc", title="Read")) == {
        "t": "CHAT_TOOL_START",
        "tool": "Read",
    }
    assert _chat_event_to_sse_frame(ToolCallProgress(tool_id="abc", status="completed")) == {
        "t": "CHAT_TOOL_PROGRESS",
        "tool": "abc",
        "status": "completed",
    }
    assert _chat_event_to_sse_frame(
        AssistantMessagePersisted(message_id=42, content="done", terminated=False)
    ) == {"t": "CHAT_ASSISTANT_MESSAGE", "message_id": 42, "content": "done", "terminated": False}
    assert _chat_event_to_sse_frame(TurnDone(full_response="ok")) == {
        "t": "CHAT_DONE",
        "full_response": "ok",
    }
    assert _chat_event_to_sse_frame(TurnError(message="boom")) == {
        "t": "CHAT_ERROR",
        "error": "boom",
    }
    assert _chat_event_to_sse_frame(TurnCancelled(reason="user")) == {
        "t": "CHAT_TURN_TERMINATED",
        "reason": "user",
    }
    # TurnStarted and UsageUpdate have no inline SSE analogue.
    assert _chat_event_to_sse_frame(TurnStarted(at=datetime.now(UTC))) is None
    assert _chat_event_to_sse_frame(UsageUpdate(used=10, size=100)) is None


# ---------------------------------------------------------------------------
# 2. /watch fanout
# ---------------------------------------------------------------------------


async def test_sse_stream_broadcasts_to_watch_subscribers(tmp_path: "Path") -> None:
    """Events yielded by _sse_stream are also pushed to /watch subscribers."""
    from kagan.core import KaganCore
    from kagan.server import _chat_routes
    from tests.helpers.chat_engine import ScriptedFactory

    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()
        scripted = ScriptedFactory(chunks=["hello"])

        from kagan.cli.chat._session_picker import chat_session_to_legacy_dict as _to_dict

        session = await core.chat_sessions.create(source="web", label="t")
        pair = await core.chat_sessions.get_with_history(session.id)
        assert pair is not None
        session_dict = _to_dict(*pair)

        watch_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _chat_routes._chat_subscribers[session.id].append(watch_queue)

        ctx = SimpleNamespace(client=core)
        with _patched_factory(_chat_routes, scripted):
            chunks = await asyncio.wait_for(
                _drain_sse(
                    _chat_routes._sse_stream(
                        ctx, session.id, session_dict, text="hi", backend="claude-code",
                        attachments=None,
                    )
                ),
                timeout=5.0,
            )
        _chat_routes._chat_subscribers[session.id].remove(watch_queue)

        frame_types = [f["t"] for f in _frames(chunks)]
        assert "CHAT_DONE" in frame_types

        broadcast_types: list[str] = []
        while not watch_queue.empty():
            broadcast_types.append(watch_queue.get_nowait()["t"])

        assert "CHAT_USER_MESSAGE" in broadcast_types
        assert "CHAT_DONE" in broadcast_types
    finally:
        core.close()


# ---------------------------------------------------------------------------
# 3. Interrupt emits CHAT_TURN_TERMINATED exactly once
# ---------------------------------------------------------------------------


async def test_interrupt_emits_chat_turn_terminated_exactly_once(tmp_path: "Path") -> None:
    """/interrupt during an active stream must emit CHAT_TURN_TERMINATED once."""
    from kagan.core import KaganCore
    from kagan.server import _chat_routes
    from tests.helpers.chat_engine import SuspendingFactory

    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()
        started = asyncio.Event()
        factory = SuspendingFactory(first_chunk="partial", started=started)

        from kagan.cli.chat._session_picker import chat_session_to_legacy_dict as _to_dict

        session = await core.chat_sessions.create(source="web", label="t")
        pair = await core.chat_sessions.get_with_history(session.id)
        assert pair is not None
        session_dict = _to_dict(*pair)

        watch_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        _chat_routes._chat_subscribers[session.id].append(watch_queue)

        ctx = SimpleNamespace(client=core)
        with _patched_factory(_chat_routes, factory):
            sse_stream = _chat_routes._sse_stream(
                ctx, session.id, session_dict, text="hello", backend="claude-code",
                attachments=None,
            )
            consumer = asyncio.create_task(_drain_sse(sse_stream))
            try:
                await asyncio.wait_for(started.wait(), timeout=5.0)
                await asyncio.sleep(0.05)

                cancel_result = await core.chat.cancel(session.id, reason="user")
                if not cancel_result.was_running:
                    _chat_routes._broadcast(
                        session.id, {"t": "CHAT_TURN_TERMINATED", "reason": "user"}
                    )
                await asyncio.wait_for(consumer, timeout=5.0)
            finally:
                with contextlib.suppress(Exception):
                    _chat_routes._chat_subscribers[session.id].remove(watch_queue)

        terminated_count = 0
        while not watch_queue.empty():
            ev = watch_queue.get_nowait()
            if ev.get("t") == "CHAT_TURN_TERMINATED":
                terminated_count += 1

        assert terminated_count == 1, (
            f"CHAT_TURN_TERMINATED should fire exactly once; saw {terminated_count}"
        )
    finally:
        core.close()


# ---------------------------------------------------------------------------
# 4. Concurrent /stream emits CHAT_ERROR without orphan user row
# ---------------------------------------------------------------------------


async def test_concurrent_stream_emits_chat_error_without_orphan_user_row(
    tmp_path: "Path",
) -> None:
    """Second /stream for the same session emits CHAT_ERROR; no orphan user row."""
    from kagan.core import KaganCore
    from kagan.server import _chat_routes
    from tests.helpers.chat_engine import SuspendingFactory

    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()
        started = asyncio.Event()
        factory = SuspendingFactory(first_chunk="partial", started=started)

        from kagan.cli.chat._session_picker import chat_session_to_legacy_dict as _to_dict

        session = await core.chat_sessions.create(source="web", label="t")
        pair = await core.chat_sessions.get_with_history(session.id)
        assert pair is not None
        session_dict = _to_dict(*pair)

        ctx = SimpleNamespace(client=core)
        with _patched_factory(_chat_routes, factory):
            first_stream = _chat_routes._sse_stream(
                ctx, session.id, session_dict, text="first", backend="claude-code",
                attachments=None,
            )
            second_stream = _chat_routes._sse_stream(
                ctx, session.id, dict(session_dict), text="second", backend="claude-code",
                attachments=None,
            )

            first_consumer = asyncio.create_task(_drain_sse(first_stream))
            await asyncio.wait_for(started.wait(), timeout=5.0)

            second_chunks = await asyncio.wait_for(_drain_sse(second_stream), timeout=5.0)
            second_frames = _frames(second_chunks)

        assert len(second_frames) == 1
        assert second_frames[0]["t"] == "CHAT_ERROR"
        assert "in progress" in second_frames[0]["error"].lower()

        await core.chat.cancel(session.id)
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(first_consumer, timeout=5.0)

        history = await core.chat.history(session.id)
        user_rows = [m for m in history if m.role == "user"]
        assert len(user_rows) == 1
        assert user_rows[0].content == "first"
    finally:
        core.close()


# ---------------------------------------------------------------------------
# Context manager helper
# ---------------------------------------------------------------------------


import contextlib as _contextlib


@_contextlib.contextmanager
def _patched_factory(module: Any, factory: Any) -> Any:
    """Temporarily replace ``SpawnPerTurnACPFactory`` on ``module``."""
    original = module.SpawnPerTurnACPFactory
    module.SpawnPerTurnACPFactory = lambda **_kwargs: factory
    try:
        yield
    finally:
        module.SpawnPerTurnACPFactory = original
