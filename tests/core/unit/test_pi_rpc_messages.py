"""Unit tests for the pi RPC boundary models (pi_rpc_messages.py).

Validates that ``parse_pi_rpc_message`` correctly validates known frame
shapes, returns typed model instances, and gracefully handles unknown
or malformed frames. No subprocess is spawned — all inputs are synthetic dicts.
"""

from __future__ import annotations

import pytest

from kagan.core.adapters.pi_rpc_messages import (
    PiAgentEnd,
    PiAgentStart,
    PiAssistantMessageEvent,
    PiAutoRetryEnd,
    PiAutoRetryStart,
    PiCompactionEnd,
    PiCompactionStart,
    PiExtensionUiRequest,
    PiMessage,
    PiMessageEnd,
    PiMessageStart,
    PiMessageUpdate,
    PiQueueUpdate,
    PiResponseAck,
    PiSessionInfoChanged,
    PiThinkingLevelChanged,
    PiToolCallEnd,
    PiToolCallStart,
    PiToolCallUpdate,
    PiTurnEnd,
    PiTurnStart,
    parse_pi_rpc_message,
)

pytestmark = [pytest.mark.core, pytest.mark.unit]


# ---------------------------------------------------------------------------
# parse_pi_rpc_message dispatch
# ---------------------------------------------------------------------------


def test_agent_start_returns_PiAgentStart() -> None:
    result = parse_pi_rpc_message({"type": "agent_start"})
    assert isinstance(result, PiAgentStart)


def test_agent_end_returns_PiAgentEnd() -> None:
    result = parse_pi_rpc_message({"type": "agent_end", "messages": []})
    assert isinstance(result, PiAgentEnd)
    assert result.messages == []


def test_turn_start_returns_PiTurnStart() -> None:
    result = parse_pi_rpc_message({"type": "turn_start"})
    assert isinstance(result, PiTurnStart)


def test_turn_end_returns_PiTurnEnd() -> None:
    result = parse_pi_rpc_message({"type": "turn_end", "message": {}, "toolResults": []})
    assert isinstance(result, PiTurnEnd)


def test_message_start_returns_PiMessageStart() -> None:
    result = parse_pi_rpc_message(
        {"type": "message_start", "message": {"id": "m1", "role": "assistant"}}
    )
    assert isinstance(result, PiMessageStart)
    assert isinstance(result.message, PiMessage)
    assert result.message.role == "assistant"
    assert result.message.id == "m1"


def test_message_update_returns_PiMessageUpdate_with_ame() -> None:
    result = parse_pi_rpc_message(
        {
            "type": "message_update",
            "message": {"id": "m2", "role": "assistant"},
            "assistantMessageEvent": {"type": "text_delta", "delta": "hi"},
        }
    )
    assert isinstance(result, PiMessageUpdate)
    assert result.assistantMessageEvent is not None
    assert isinstance(result.assistantMessageEvent, PiAssistantMessageEvent)
    assert result.assistantMessageEvent.delta == "hi"


def test_message_update_missing_ame_sets_none() -> None:
    result = parse_pi_rpc_message(
        {"type": "message_update", "message": {"id": "m3", "role": "assistant"}}
    )
    assert isinstance(result, PiMessageUpdate)
    assert result.assistantMessageEvent is None


def test_message_end_returns_PiMessageEnd() -> None:
    result = parse_pi_rpc_message(
        {
            "type": "message_end",
            "message": {
                "id": "m4",
                "role": "assistant",
                "content": [{"type": "text", "text": "done"}],
            },
        }
    )
    assert isinstance(result, PiMessageEnd)
    assert result.message.role == "assistant"
    assert len(result.message.content) == 1


def test_tool_execution_start_returns_PiToolCallStart() -> None:
    result = parse_pi_rpc_message(
        {
            "type": "tool_execution_start",
            "toolCallId": "tc-1",
            "toolName": "bash",
            "args": {"command": "ls"},
        }
    )
    assert isinstance(result, PiToolCallStart)
    assert result.toolCallId == "tc-1"
    assert result.toolName == "bash"
    assert result.args == {"command": "ls"}


def test_tool_execution_start_optional_fields_default_to_none() -> None:
    result = parse_pi_rpc_message({"type": "tool_execution_start"})
    assert isinstance(result, PiToolCallStart)
    assert result.toolCallId is None
    assert result.toolName is None
    assert result.args is None


def test_tool_execution_update_returns_PiToolCallUpdate() -> None:
    result = parse_pi_rpc_message(
        {
            "type": "tool_execution_update",
            "toolCallId": "tc-2",
            "partialResult": {"content": [{"type": "text", "text": "partial"}]},
        }
    )
    assert isinstance(result, PiToolCallUpdate)
    assert result.toolCallId == "tc-2"
    assert isinstance(result.partialResult, dict)


def test_tool_execution_end_success_returns_PiToolCallEnd() -> None:
    result = parse_pi_rpc_message(
        {
            "type": "tool_execution_end",
            "toolCallId": "tc-3",
            "result": {"content": [{"type": "text", "text": "ok"}]},
            "isError": False,
        }
    )
    assert isinstance(result, PiToolCallEnd)
    assert result.toolCallId == "tc-3"
    assert result.isError is False


def test_tool_execution_end_error_returns_PiToolCallEnd() -> None:
    result = parse_pi_rpc_message(
        {
            "type": "tool_execution_end",
            "toolCallId": "tc-4",
            "result": "command not found",
            "isError": True,
        }
    )
    assert isinstance(result, PiToolCallEnd)
    assert result.isError is True
    assert result.result == "command not found"


def test_tool_execution_end_defaults_is_error_false() -> None:
    result = parse_pi_rpc_message({"type": "tool_execution_end"})
    assert isinstance(result, PiToolCallEnd)
    assert result.isError is False
    assert result.result is None


def test_compaction_start_returns_PiCompactionStart() -> None:
    result = parse_pi_rpc_message({"type": "compaction_start", "reason": "threshold"})
    assert isinstance(result, PiCompactionStart)
    assert result.reason == "threshold"


def test_compaction_end_returns_PiCompactionEnd() -> None:
    result = parse_pi_rpc_message({"type": "compaction_end"})
    assert isinstance(result, PiCompactionEnd)


def test_response_ack_returns_PiResponseAck() -> None:
    result = parse_pi_rpc_message({"type": "response", "command": "prompt", "success": True})
    assert isinstance(result, PiResponseAck)


def test_extension_ui_request_returns_PiExtensionUiRequest() -> None:
    result = parse_pi_rpc_message({"type": "extension_ui_request", "id": "x1", "method": "notify"})
    assert isinstance(result, PiExtensionUiRequest)


def test_queue_update_returns_PiQueueUpdate() -> None:
    result = parse_pi_rpc_message({"type": "queue_update", "steering": [], "followUp": []})
    assert isinstance(result, PiQueueUpdate)


def test_session_info_changed_returns_PiSessionInfoChanged() -> None:
    result = parse_pi_rpc_message({"type": "session_info_changed", "name": "test"})
    assert isinstance(result, PiSessionInfoChanged)


def test_thinking_level_changed_returns_PiThinkingLevelChanged() -> None:
    result = parse_pi_rpc_message({"type": "thinking_level_changed", "level": "high"})
    assert isinstance(result, PiThinkingLevelChanged)


def test_auto_retry_start_returns_PiAutoRetryStart() -> None:
    result = parse_pi_rpc_message(
        {
            "type": "auto_retry_start",
            "attempt": 1,
            "maxAttempts": 3,
            "delayMs": 1000,
            "errorMessage": "oops",
        }
    )
    assert isinstance(result, PiAutoRetryStart)


def test_auto_retry_end_returns_PiAutoRetryEnd() -> None:
    result = parse_pi_rpc_message({"type": "auto_retry_end", "success": True, "attempt": 1})
    assert isinstance(result, PiAutoRetryEnd)


# ---------------------------------------------------------------------------
# Unknown / malformed frames
# ---------------------------------------------------------------------------


def test_unknown_type_returns_none() -> None:
    result = parse_pi_rpc_message({"type": "totally_unknown_frame"})
    assert result is None


def test_missing_type_returns_none() -> None:
    result = parse_pi_rpc_message({"data": "no type"})
    assert result is None


def test_non_string_type_returns_none() -> None:
    result = parse_pi_rpc_message({"type": 42})  # type: ignore[arg-type]
    assert result is None


# ---------------------------------------------------------------------------
# extra="allow" — unknown fields do not raise
# ---------------------------------------------------------------------------


def test_extra_fields_are_accepted_on_PiAgentStart() -> None:
    result = parse_pi_rpc_message({"type": "agent_start", "future_field": "ignored"})
    assert isinstance(result, PiAgentStart)


def test_extra_fields_are_accepted_on_PiToolCallStart() -> None:
    result = parse_pi_rpc_message(
        {"type": "tool_execution_start", "toolCallId": "tc-x", "newUnknown": 99}
    )
    assert isinstance(result, PiToolCallStart)


# ---------------------------------------------------------------------------
# PiMessage defaults
# ---------------------------------------------------------------------------


def test_PiMessage_content_defaults_to_empty_list() -> None:
    result = parse_pi_rpc_message({"type": "message_start", "message": {"role": "user"}})
    assert isinstance(result, PiMessageStart)
    assert result.message.content == []
    assert result.message.id is None


# ---------------------------------------------------------------------------
# PiAssistantMessageEvent delta default
# ---------------------------------------------------------------------------


def test_PiAssistantMessageEvent_delta_defaults_to_empty_string() -> None:
    result = parse_pi_rpc_message(
        {
            "type": "message_update",
            "message": {"role": "assistant"},
            "assistantMessageEvent": {"type": "stop_reason"},
        }
    )
    assert isinstance(result, PiMessageUpdate)
    assert result.assistantMessageEvent is not None
    assert result.assistantMessageEvent.delta == ""
