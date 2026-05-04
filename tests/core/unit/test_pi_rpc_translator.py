"""Unit tests for the pi RPC JSONL → AgentEvent translator.

Tests cover every pi RPC frame shape documented in
``kagan.core.adapters.pi_rpc.translate_pi_rpc_message``.
No subprocess is spawned — all inputs are synthetic dicts.
"""

from __future__ import annotations

import pytest

from kagan.core.adapters.pi_rpc import translate_pi_rpc_message
from kagan.core.agent_events import (
    AgentEnd,
    AgentStart,
    CompactionOccurred,
    TurnEnd,
    TurnStart,
)
from kagan.core.events_common import (
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
)

pytestmark = [pytest.mark.core, pytest.mark.unit]

_SESSION_ID = "test-session-abc"
_BACKEND = "pi-coding-agent"


def _translate(msg: dict) -> object:
    return translate_pi_rpc_message(msg, session_id=_SESSION_ID, backend=_BACKEND)


# ---------------------------------------------------------------------------
# Agent lifecycle
# ---------------------------------------------------------------------------


def test_agent_start_maps_to_AgentStart() -> None:
    result = _translate({"type": "agent_start"})
    assert isinstance(result, AgentStart)
    assert result.session_id == _SESSION_ID
    assert result.agent_backend == _BACKEND


def test_agent_end_maps_to_AgentEnd_completed() -> None:
    result = _translate({"type": "agent_end", "messages": []})
    assert isinstance(result, AgentEnd)
    assert result.stop_reason == "completed"
    assert result.session_id == _SESSION_ID


# ---------------------------------------------------------------------------
# Turn lifecycle
# ---------------------------------------------------------------------------


def test_turn_start_maps_to_TurnStart() -> None:
    result = _translate({"type": "turn_start"})
    assert isinstance(result, TurnStart)


def test_turn_end_maps_to_TurnEnd() -> None:
    result = _translate({"type": "turn_end", "message": {}, "toolResults": []})
    assert isinstance(result, TurnEnd)


# ---------------------------------------------------------------------------
# Message lifecycle
# ---------------------------------------------------------------------------


def test_message_start_assistant_maps_to_MessageStart() -> None:
    result = _translate({"type": "message_start", "message": {"id": "msg-1", "role": "assistant"}})
    assert isinstance(result, MessageStart)
    assert result.message_id == "msg-1"


def test_message_start_user_returns_none() -> None:
    result = _translate({"type": "message_start", "message": {"id": "msg-2", "role": "user"}})
    assert result is None


def test_message_start_tool_result_returns_none() -> None:
    result = _translate({"type": "message_start", "message": {"id": "msg-3", "role": "tool"}})
    assert result is None


def test_message_start_missing_message_returns_none() -> None:
    result = _translate({"type": "message_start"})
    assert result is None


def test_message_update_text_delta_maps_to_MessageUpdate() -> None:
    result = _translate(
        {
            "type": "message_update",
            "message": {"id": "msg-4", "role": "assistant"},
            "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": "Hello"},
        }
    )
    assert isinstance(result, MessageUpdate)
    assert result.message_id == "msg-4"
    assert result.delta == "Hello"


def test_message_update_thinking_delta_maps_to_MessageUpdate() -> None:
    result = _translate(
        {
            "type": "message_update",
            "message": {"id": "msg-5", "role": "assistant"},
            "assistantMessageEvent": {"type": "thinking_delta", "contentIndex": 0, "delta": "hmm"},
        }
    )
    assert isinstance(result, MessageUpdate)
    assert result.delta == "hmm"


def test_message_update_non_delta_returns_none() -> None:
    result = _translate(
        {
            "type": "message_update",
            "message": {"id": "msg-6", "role": "assistant"},
            "assistantMessageEvent": {"type": "stop_reason"},
        }
    )
    assert result is None


def test_message_update_empty_delta_returns_none() -> None:
    result = _translate(
        {
            "type": "message_update",
            "message": {"id": "msg-7", "role": "assistant"},
            "assistantMessageEvent": {"type": "text_delta", "contentIndex": 0, "delta": ""},
        }
    )
    assert result is None


def test_message_update_missing_ame_returns_none() -> None:
    result = _translate(
        {
            "type": "message_update",
            "message": {"id": "msg-8", "role": "assistant"},
        }
    )
    assert result is None


def test_message_end_assistant_maps_to_MessageEnd() -> None:
    result = _translate(
        {
            "type": "message_end",
            "message": {
                "id": "msg-9",
                "role": "assistant",
                "content": [{"type": "text", "text": "Done."}],
            },
        }
    )
    assert isinstance(result, MessageEnd)
    assert result.message_id == "msg-9"
    assert result.full_text == "Done."


def test_message_end_user_returns_none() -> None:
    result = _translate(
        {
            "type": "message_end",
            "message": {"id": "msg-10", "role": "user", "content": []},
        }
    )
    assert result is None


def test_message_end_no_content_returns_empty_text() -> None:
    result = _translate(
        {
            "type": "message_end",
            "message": {"id": "msg-11", "role": "assistant"},
        }
    )
    assert isinstance(result, MessageEnd)
    assert result.full_text == ""


# ---------------------------------------------------------------------------
# Tool execution lifecycle
# ---------------------------------------------------------------------------


def test_tool_execution_start_maps_to_ToolExecutionStart() -> None:
    result = _translate(
        {
            "type": "tool_execution_start",
            "toolCallId": "tc-1",
            "toolName": "bash",
            "args": {"command": "ls"},
        }
    )
    assert isinstance(result, ToolExecutionStart)
    assert result.tool_id == "tc-1"
    assert result.name == "bash"
    assert result.args == {"command": "ls"}


def test_tool_execution_start_no_args_is_none() -> None:
    result = _translate(
        {
            "type": "tool_execution_start",
            "toolCallId": "tc-2",
            "toolName": "read",
        }
    )
    assert isinstance(result, ToolExecutionStart)
    assert result.args is None


def test_tool_execution_update_maps_to_ToolExecutionUpdate() -> None:
    result = _translate(
        {
            "type": "tool_execution_update",
            "toolCallId": "tc-3",
            "toolName": "bash",
            "args": {},
            "partialResult": {"content": [{"type": "text", "text": "partial..."}]},
        }
    )
    assert isinstance(result, ToolExecutionUpdate)
    assert result.tool_id == "tc-3"
    assert "partial..." in result.partial_result


def test_tool_execution_end_success_maps_correctly() -> None:
    result = _translate(
        {
            "type": "tool_execution_end",
            "toolCallId": "tc-4",
            "toolName": "bash",
            "result": {"content": [{"type": "text", "text": "ok"}]},
            "isError": False,
        }
    )
    assert isinstance(result, ToolExecutionEnd)
    assert result.tool_id == "tc-4"
    assert result.status == "success"
    assert result.result == "ok"


def test_tool_execution_end_error_maps_correctly() -> None:
    result = _translate(
        {
            "type": "tool_execution_end",
            "toolCallId": "tc-5",
            "toolName": "bash",
            "result": "Command not found",
            "isError": True,
        }
    )
    assert isinstance(result, ToolExecutionEnd)
    assert result.status == "error"
    assert result.result == "Command not found"


def test_tool_execution_end_no_result_is_none_result() -> None:
    result = _translate(
        {
            "type": "tool_execution_end",
            "toolCallId": "tc-6",
            "toolName": "read",
            "isError": False,
        }
    )
    assert isinstance(result, ToolExecutionEnd)
    assert result.result is None


# ---------------------------------------------------------------------------
# Compaction
# ---------------------------------------------------------------------------


def test_compaction_start_maps_to_CompactionOccurred() -> None:
    result = _translate({"type": "compaction_start", "reason": "threshold"})
    assert isinstance(result, CompactionOccurred)
    assert result.backend == _BACKEND


def test_compaction_end_returns_none() -> None:
    result = _translate({"type": "compaction_end", "reason": "threshold", "result": None, "aborted": False, "willRetry": False})
    assert result is None


# ---------------------------------------------------------------------------
# Non-event / unknown frames
# ---------------------------------------------------------------------------


def test_response_ack_returns_none() -> None:
    result = _translate({"type": "response", "command": "prompt", "success": True})
    assert result is None


def test_extension_ui_request_returns_none() -> None:
    result = _translate(
        {"type": "extension_ui_request", "id": "ext-1", "method": "notify", "message": "hello"}
    )
    assert result is None


def test_queue_update_returns_none() -> None:
    result = _translate({"type": "queue_update", "steering": [], "followUp": []})
    assert result is None


def test_unknown_type_returns_none() -> None:
    result = _translate({"type": "totally_unknown_frame", "data": 42})
    assert result is None


def test_missing_type_returns_none() -> None:
    result = _translate({"data": "no type field"})
    assert result is None


def test_non_string_type_returns_none() -> None:
    result = _translate({"type": 42})  # type: ignore[arg-type]
    assert result is None


# ---------------------------------------------------------------------------
# Message ID fallback (missing id field)
# ---------------------------------------------------------------------------


def test_message_start_without_id_generates_uuid() -> None:
    """When the message dict lacks an 'id', a UUID is generated instead of crashing."""
    result = _translate({"type": "message_start", "message": {"role": "assistant"}})
    assert isinstance(result, MessageStart)
    assert result.message_id  # non-empty


def test_tool_execution_start_without_id_generates_uuid() -> None:
    result = _translate({"type": "tool_execution_start", "toolName": "read"})
    assert isinstance(result, ToolExecutionStart)
    assert result.tool_id  # non-empty
