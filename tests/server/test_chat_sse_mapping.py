"""Server-level mapping test for ``_chat_event_to_sse_frame``.

Pins the wire shape between :class:`ChatEvent` and the SSE frames consumed by
the web client and VS Code extension. The full end-to-end SSE producer is
exercised by ``tests/core/unit/test_chat_engine.py`` plus this mapping pin —
adding a real httpx-driven SSE round-trip is left as a follow-up
(see TODO below).
"""

from __future__ import annotations

from datetime import UTC, datetime

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

pytestmark = [pytest.mark.unit]


def test_assistant_chunk_maps_to_chat_chunk() -> None:
    frame = _chat_event_to_sse_frame(AssistantChunk(text="hi"))
    assert frame == {"t": "CHAT_CHUNK", "content": "hi"}


def test_assistant_chunk_thought_carries_flag() -> None:
    frame = _chat_event_to_sse_frame(AssistantChunk(text="thinking", thought=True))
    assert frame == {"t": "CHAT_CHUNK", "content": "thinking", "thought": True}


def test_tool_call_start_maps_to_chat_tool_start() -> None:
    frame = _chat_event_to_sse_frame(ToolCallStart(tool_id="abc", title="Read"))
    assert frame == {"t": "CHAT_TOOL_START", "tool": "Read"}


def test_tool_call_progress_maps_to_chat_tool_progress() -> None:
    frame = _chat_event_to_sse_frame(ToolCallProgress(tool_id="abc", status="completed"))
    assert frame == {"t": "CHAT_TOOL_PROGRESS", "tool": "abc", "status": "completed"}


def test_assistant_message_persisted_maps_to_chat_assistant_message() -> None:
    frame = _chat_event_to_sse_frame(
        AssistantMessagePersisted(message_id=42, content="done", terminated=False)
    )
    assert frame == {
        "t": "CHAT_ASSISTANT_MESSAGE",
        "message_id": 42,
        "content": "done",
        "terminated": False,
    }


def test_turn_done_maps_to_chat_done() -> None:
    frame = _chat_event_to_sse_frame(TurnDone(full_response="ok"))
    assert frame == {"t": "CHAT_DONE", "full_response": "ok"}


def test_turn_error_maps_to_chat_error() -> None:
    frame = _chat_event_to_sse_frame(TurnError(message="boom"))
    assert frame == {"t": "CHAT_ERROR", "error": "boom"}


def test_turn_cancelled_maps_to_chat_turn_terminated() -> None:
    frame = _chat_event_to_sse_frame(TurnCancelled(reason="user"))
    assert frame == {"t": "CHAT_TURN_TERMINATED", "reason": "user"}


def test_turn_started_is_not_emitted_inline() -> None:
    """``TurnStarted`` is mapped at the producer level (with ``by_source``),
    not by the pure event mapping function. Returning ``None`` here keeps the
    mapping side-effect-free.
    """
    frame = _chat_event_to_sse_frame(TurnStarted(at=datetime.now(UTC)))
    assert frame is None


def test_usage_update_has_no_sse_analogue() -> None:
    """Usage updates are a future feature — no wire shape today."""
    frame = _chat_event_to_sse_frame(UsageUpdate(used=10, size=100))
    assert frame is None


# TODO: end-to-end SSE test — drive POST /api/chat/{id}/stream against a
# mounted FastMCP app with a fake ``ACPSessionFactory``, assert the full
# frame sequence (CHAT_USER_MESSAGE -> CHAT_TURN_STARTED -> CHAT_CHUNK* ->
# CHAT_ASSISTANT_MESSAGE -> CHAT_DONE -> CHAT_SESSION_UPDATED).
