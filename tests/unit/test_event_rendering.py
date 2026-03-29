"""Tests for event rendering — render_event function and helpers."""

import pytest

from kagan.core._event_rendering import (
    RenderableEvent,
    RenderableKind,
    Severity,
    _acp_payload,
    _extract_tool_status,
    _extract_tool_title,
    _format_tool_name,
    render_event,
)

pytestmark = pytest.mark.unit


# -----------------------------------------------------------------------------
# _acp_payload helper tests
# -----------------------------------------------------------------------------


def test_acp_payload_extracts_nested_acp() -> None:
    """Should extract nested payload.acp dict when present."""
    payload = {"acp": {"toolName": "test_tool", "status": "running"}}
    result = _acp_payload(payload)
    assert result == {"toolName": "test_tool", "status": "running"}


def test_acp_payload_returns_empty_dict_when_no_acp() -> None:
    """Should return empty dict when acp key is missing."""
    payload = {"toolName": "test_tool", "status": "running"}
    result = _acp_payload(payload)
    assert result == {}


def test_acp_payload_returns_empty_dict_when_acp_not_dict() -> None:
    """Should return empty dict when acp is not a dict."""
    payload = {"acp": "not_a_dict"}
    result = _acp_payload(payload)
    assert result == {}


def test_acp_payload_handles_empty_payload() -> None:
    """Should handle empty payload gracefully."""
    result = _acp_payload({})
    assert result == {}


# -----------------------------------------------------------------------------
# _format_tool_name helper tests
# -----------------------------------------------------------------------------


def test_format_tool_name_mcp_double_underscore() -> None:
    """Should format mcp__prefix__tool_name as prefix / tool_name."""
    assert _format_tool_name("mcp__kagan__task_get") == "kagan / task_get"
    assert _format_tool_name("mcp__filesystem__read") == "filesystem / read"


def test_format_tool_name_functions_double_underscore() -> None:
    """Should format functions__name as functions / name."""
    assert _format_tool_name("functions__my_func") == "functions / my_func"


def test_format_tool_name_generic_double_underscore() -> None:
    """Should format generic __ separated names with all parts."""
    assert _format_tool_name("a__b__c__d") == "a / b / c / d"


def test_format_tool_name_toolu_prefix() -> None:
    """Should return 'tool call' for toolu_ prefix (Anthropic)."""
    assert _format_tool_name("toolu_abc123") == "tool call"
    assert _format_tool_name("toolu_01ABCxyz") == "tool call"


def test_format_tool_name_call_prefix() -> None:
    """Should return 'tool call' for call_ prefix."""
    assert _format_tool_name("call_abc123") == "tool call"
    assert _format_tool_name("call_xyz789") == "tool call"


def test_format_tool_name_snake_case() -> None:
    """Should convert snake_case to space separated."""
    assert _format_tool_name("my_tool_name") == "my tool name"
    assert _format_tool_name("read_file") == "read file"


def test_format_tool_name_simple_name() -> None:
    """Should return simple names unchanged."""
    assert _format_tool_name("simple") == "simple"


# -----------------------------------------------------------------------------
# _extract_tool_title helper tests
# -----------------------------------------------------------------------------


def test_extract_tool_title_prefers_acp_tool_name() -> None:
    """Should prefer acp.toolName over other fields."""
    payload = {"acp": {"toolName": "acp_tool"}, "name": "payload_name"}
    assert _extract_tool_title(payload) == "acp tool"


def test_extract_tool_title_fallback_chain() -> None:
    """Should fall back through name, title, tool_name, etc."""
    # acp.name
    assert _extract_tool_title({"acp": {"name": "acp_name"}}) == "acp name"
    # acp.title
    assert _extract_tool_title({"acp": {"title": "acp_title"}}) == "acp title"
    # payload.tool_name
    assert _extract_tool_title({"tool_name": "payload_tool"}) == "payload tool"
    # payload.toolName
    assert _extract_tool_title({"toolName": "payloadTool"}) == "payloadTool"
    # payload.name
    assert _extract_tool_title({"name": "payload_name"}) == "payload name"
    # tool_call_id
    assert _extract_tool_title({"tool_call_id": "call_123"}) == "tool call"
    # toolCallId
    assert _extract_tool_title({"toolCallId": "tc_456"}) == "tc 456"
    # id
    assert _extract_tool_title({"id": "simple_id"}) == "simple id"


def test_extract_tool_title_returns_default() -> None:
    """Should return 'tool call' when no name field is found."""
    assert _extract_tool_title({}) == "tool call"
    assert _extract_tool_title({"other": "field"}) == "tool call"


def test_extract_tool_title_handles_mcp_format() -> None:
    """Should correctly format MCP tool names."""
    payload = {"acp": {"toolName": "mcp__kagan__task_create"}}
    assert _extract_tool_title(payload) == "kagan / task_create"


# -----------------------------------------------------------------------------
# _extract_tool_status helper tests
# -----------------------------------------------------------------------------


def test_extract_tool_status_from_acp() -> None:
    """Should extract status from acp.status."""
    payload = {"acp": {"status": "in_progress"}}
    assert _extract_tool_status(payload) == "in_progress"


def test_extract_tool_status_from_payload() -> None:
    """Should extract status from payload.status."""
    payload = {"status": "completed"}
    assert _extract_tool_status(payload) == "completed"


def test_extract_tool_status_uses_fallback() -> None:
    """Should use fallback when no status found."""
    assert _extract_tool_status({}) == "done"
    assert _extract_tool_status({"other": "field"}) == "done"
    assert _extract_tool_status({}, "custom_fallback") == "custom_fallback"


def test_extract_tool_status_acp_takes_precedence() -> None:
    """Should prefer acp.status over payload.status."""
    payload = {"acp": {"status": "acp_status"}, "status": "payload_status"}
    assert _extract_tool_status(payload) == "acp_status"


# -----------------------------------------------------------------------------
# OUTPUT_CHUNK event tests
# -----------------------------------------------------------------------------


def test_render_output_chunk_text() -> None:
    """Should render OUTPUT_CHUNK as TEXT kind."""
    result = render_event("OUTPUT_CHUNK", {"text": "Hello world"})
    assert result is not None
    assert result.kind == RenderableKind.TEXT
    assert result.title == "Output"
    assert result.body == "Hello world"


def test_render_output_chunk_thought() -> None:
    """Should render OUTPUT_CHUNK with thought=True as THOUGHT kind."""
    result = render_event("OUTPUT_CHUNK", {"text": "Thinking...", "thought": True})
    assert result is not None
    assert result.kind == RenderableKind.THOUGHT
    assert result.title == "Thinking"
    assert result.body == "Thinking..."


def test_render_output_chunk_empty_text_returns_none() -> None:
    """Should return None for empty text."""
    assert render_event("OUTPUT_CHUNK", {"text": ""}) is None
    assert render_event("OUTPUT_CHUNK", {"text": None}) is None
    assert render_event("OUTPUT_CHUNK", {}) is None


def test_render_output_chunk_preserves_event_id_and_session_id() -> None:
    """Should preserve event_id and session_id."""
    result = render_event(
        "OUTPUT_CHUNK",
        {"text": "Hello"},
        event_id="evt_123",
        session_id="sess_456",
    )
    assert result is not None
    assert result.event_id == "evt_123"
    assert result.session_id == "sess_456"


# -----------------------------------------------------------------------------
# TOOL_CALL_START event tests
# -----------------------------------------------------------------------------


def test_render_tool_call_start() -> None:
    """Should render TOOL_CALL_START as TOOL_START kind."""
    result = render_event("TOOL_CALL_START", {"tool_name": "read_file"})
    assert result is not None
    assert result.kind == RenderableKind.TOOL_START
    assert result.title == "read file"


def test_render_tool_call_start_with_mcp_tool() -> None:
    """Should correctly format MCP tool names."""
    result = render_event(
        "TOOL_CALL_START", {"acp": {"toolName": "mcp__filesystem__read"}}
    )
    assert result is not None
    assert result.title == "filesystem / read"


def test_render_tool_call_start_with_toolu_id() -> None:
    """Should handle toolu_ prefixed IDs."""
    result = render_event("TOOL_CALL_START", {"tool_call_id": "toolu_abc123"})
    assert result is not None
    assert result.title == "tool call"


# -----------------------------------------------------------------------------
# TOOL_CALL_UPDATE event tests
# -----------------------------------------------------------------------------


def test_render_tool_call_update_skips_completed() -> None:
    """Should return None for completed status."""
    assert render_event("TOOL_CALL_UPDATE", {"status": "completed"}) is None
    assert render_event("TOOL_CALL_UPDATE", {"status": "done"}) is None


def test_render_tool_call_update_in_progress() -> None:
    """Should render in-progress tool updates."""
    result = render_event(
        "TOOL_CALL_UPDATE",
        {"acp": {"toolName": "mcp__kagan__task_get", "status": "running"}},
    )
    assert result is not None
    assert result.kind == RenderableKind.TOOL_UPDATE
    assert result.title == "kagan / task_get"
    assert result.body == "running"


def test_render_tool_call_update_with_payload_status() -> None:
    """Should render update with payload-level status."""
    result = render_event(
        "TOOL_CALL_UPDATE", {"tool_name": "my_tool", "status": "pending"}
    )
    assert result is not None
    assert result.body == "pending"


# -----------------------------------------------------------------------------
# AGENT_STATUS event tests
# -----------------------------------------------------------------------------


def test_render_agent_status() -> None:
    """Should render AGENT_STATUS as NOTE kind."""
    result = render_event("AGENT_STATUS", {"status": "working", "agent": "claude"})
    assert result is not None
    assert result.kind == RenderableKind.NOTE
    assert result.title == "Agent status"
    assert result.severity == Severity.INFO
    assert result.metadata == {"status": "working", "agent": "claude"}


def test_render_agent_status_empty_payload() -> None:
    """Should handle empty payload."""
    result = render_event("AGENT_STATUS", {})
    assert result is not None
    assert result.metadata == {}


# -----------------------------------------------------------------------------
# TASK_STATUS_CHANGED event tests
# -----------------------------------------------------------------------------


def test_render_task_status_changed() -> None:
    """Should render TASK_STATUS_CHANGED as STATUS_CHANGE kind."""
    result = render_event(
        "TASK_STATUS_CHANGED", {"from": "pending", "to": "in_progress"}
    )
    assert result is not None
    assert result.kind == RenderableKind.STATUS_CHANGE
    assert result.title == "pending -> in_progress"
    assert result.metadata == {"from": "pending", "to": "in_progress"}


def test_render_task_status_changed_with_defaults() -> None:
    """Should use '?' for missing status values."""
    result = render_event("TASK_STATUS_CHANGED", {})
    assert result is not None
    assert result.title == "? -> ?"


def test_render_task_status_changed_partial_values() -> None:
    """Should handle partial status values."""
    result = render_event("TASK_STATUS_CHANGED", {"from": "running"})
    assert result.title == "running -> ?"
    result = render_event("TASK_STATUS_CHANGED", {"to": "completed"})
    assert result.title == "? -> completed"


# -----------------------------------------------------------------------------
# CRITERION_VERDICT event tests
# -----------------------------------------------------------------------------


def test_render_criterion_verdict_pass() -> None:
    """Should render PASS verdict with SUCCESS severity."""
    result = render_event(
        "CRITERION_VERDICT",
        {"verdict": "PASS", "reason": "All checks passed", "criterion": "test"},
    )
    assert result is not None
    assert result.kind == RenderableKind.VERDICT
    assert result.title == "PASS"
    assert result.body == "All checks passed"
    assert result.severity == Severity.SUCCESS
    assert result.metadata["verdict"] == "PASS"


def test_render_criterion_verdict_fail() -> None:
    """Should render FAIL verdict with WARNING severity."""
    result = render_event(
        "CRITERION_VERDICT",
        {"verdict": "FAIL", "reason": "Missing documentation", "criterion": "docs"},
    )
    assert result is not None
    assert result.kind == RenderableKind.VERDICT
    assert result.title == "FAIL"
    assert result.body == "Missing documentation"
    assert result.severity == Severity.WARNING


def test_render_criterion_verdict_missing_reason() -> None:
    """Should handle missing reason gracefully."""
    result = render_event("CRITERION_VERDICT", {"verdict": "PASS"})
    assert result is not None
    assert result.body == ""


def test_render_criterion_verdict_unknown_verdict() -> None:
    """Should treat unknown verdicts as FAIL."""
    result = render_event("CRITERION_VERDICT", {"verdict": "UNKNOWN"})
    assert result is not None
    assert result.title == "FAIL"
    assert result.severity == Severity.WARNING


# -----------------------------------------------------------------------------
# AGENT_COMPLETED event tests
# -----------------------------------------------------------------------------


def test_render_agent_completed() -> None:
    """Should render AGENT_COMPLETED with SUCCESS severity."""
    result = render_event("AGENT_COMPLETED", {})
    assert result is not None
    assert result.kind == RenderableKind.NOTE
    assert result.title == "Agent completed"
    assert result.severity == Severity.SUCCESS


def test_render_agent_completed_ignores_payload() -> None:
    """Should ignore payload for completed events."""
    result = render_event("AGENT_COMPLETED", {"extra": "data"})
    assert result is not None
    assert result.metadata == {}


# -----------------------------------------------------------------------------
# AGENT_FAILED event tests
# -----------------------------------------------------------------------------


def test_render_agent_failed() -> None:
    """Should render AGENT_FAILED with ERROR severity."""
    result = render_event("AGENT_FAILED", {"error": "Connection timeout"})
    assert result is not None
    assert result.kind == RenderableKind.ERROR
    assert result.title == "Agent failed"
    assert result.body == "Connection timeout"
    assert result.severity == Severity.ERROR


def test_render_agent_failed_fallback_to_details() -> None:
    """Should use 'details' field if 'error' not present."""
    result = render_event("AGENT_FAILED", {"details": "Unknown error occurred"})
    assert result is not None
    assert result.body == "Unknown error occurred"


def test_render_agent_failed_default_message() -> None:
    """Should use default message when no error or details."""
    result = render_event("AGENT_FAILED", {})
    assert result is not None
    assert result.body == "Agent failed"


def test_render_agent_failed_prefers_error_over_details() -> None:
    """Should prefer 'error' over 'details'."""
    result = render_event(
        "AGENT_FAILED", {"error": "Primary error", "details": "Secondary details"}
    )
    assert result.body == "Primary error"


# -----------------------------------------------------------------------------
# MERGE_COMPLETED event tests
# -----------------------------------------------------------------------------


def test_render_merge_completed() -> None:
    """Should render MERGE_COMPLETED with SUCCESS severity."""
    result = render_event("MERGE_COMPLETED", {})
    assert result is not None
    assert result.kind == RenderableKind.MERGE
    assert result.title == "Merge completed"
    assert result.severity == Severity.SUCCESS


def test_render_merge_completed_ignores_payload() -> None:
    """Should ignore payload for merge completed."""
    result = render_event("MERGE_COMPLETED", {"branch": "feature"})
    assert result is not None
    assert result.body == ""


# -----------------------------------------------------------------------------
# MERGE_FAILED event tests
# -----------------------------------------------------------------------------


def test_render_merge_failed() -> None:
    """Should render MERGE_FAILED with ERROR severity."""
    result = render_event("MERGE_FAILED", {"error": "Merge conflict"})
    assert result is not None
    assert result.kind == RenderableKind.MERGE
    assert result.title == "Merge failed"
    assert result.body == "Merge conflict"
    assert result.severity == Severity.ERROR


def test_render_merge_failed_default_message() -> None:
    """Should use 'unknown' when no error provided."""
    result = render_event("MERGE_FAILED", {})
    assert result is not None
    assert result.body == "unknown"


# -----------------------------------------------------------------------------
# PLAN_UPDATE event tests
# -----------------------------------------------------------------------------


def test_render_plan_update() -> None:
    """Should render PLAN_UPDATE as PLAN kind."""
    result = render_event("PLAN_UPDATE", {"steps": ["step1", "step2"]})
    assert result is not None
    assert result.kind == RenderableKind.PLAN
    assert result.title == "Plan updated"


def test_render_plan_update_empty_payload() -> None:
    """Should handle empty payload."""
    result = render_event("PLAN_UPDATE", {})
    assert result is not None
    assert result.kind == RenderableKind.PLAN


# -----------------------------------------------------------------------------
# AUTO_REVIEW_STARTED event tests
# -----------------------------------------------------------------------------


def test_render_auto_review_started() -> None:
    """Should render AUTO_REVIEW_STARTED as NOTE kind."""
    result = render_event("AUTO_REVIEW_STARTED", {})
    assert result is not None
    assert result.kind == RenderableKind.NOTE
    assert result.title == "Auto-review started"


def test_render_auto_review_started_ignores_payload() -> None:
    """Should ignore payload."""
    result = render_event("AUTO_REVIEW_STARTED", {"reviewer": "kagan"})
    assert result is not None
    assert result.metadata == {}


# -----------------------------------------------------------------------------
# Unknown event type tests
# -----------------------------------------------------------------------------


def test_render_unknown_event_type() -> None:
    """Should render unknown event types as generic NOTE."""
    result = render_event("UNKNOWN_EVENT", {"data": "value"})
    assert result is not None
    assert result.kind == RenderableKind.NOTE
    assert result.title == "UNKNOWN_EVENT"
    assert result.body == "{'data': 'value'}"


def test_render_unknown_event_type_empty_payload() -> None:
    """Should handle unknown event with empty payload."""
    result = render_event("CUSTOM_EVENT", {})
    assert result is not None
    assert result.title == "CUSTOM_EVENT"
    assert result.body == ""


def test_render_unknown_event_type_none_payload_values() -> None:
    """Should handle None values in payload."""
    result = render_event("NULL_EVENT", {"key": None})
    assert result is not None
    assert "None" in result.body


# -----------------------------------------------------------------------------
# ACP payload nesting tests (across multiple event types)
# -----------------------------------------------------------------------------


def test_acp_nesting_in_tool_events() -> None:
    """Should correctly extract tool info from nested acp payload."""
    payload = {
        "acp": {
            "toolName": "mcp__kagan__task_list",
            "status": "executing",
        }
    }
    start_result = render_event("TOOL_CALL_START", payload)
    assert start_result is not None
    assert start_result.title == "kagan / task_list"

    update_result = render_event("TOOL_CALL_UPDATE", payload)
    assert update_result is not None
    assert update_result.body == "executing"


def test_acp_nesting_with_empty_acp() -> None:
    """Should fall back to top-level fields when acp is empty."""
    payload = {"acp": {}, "tool_name": "fallback_tool", "status": "fallback_status"}
    result = render_event("TOOL_CALL_START", payload)
    assert result is not None
    assert result.title == "fallback tool"


# -----------------------------------------------------------------------------
# Malformed payload tests
# -----------------------------------------------------------------------------


def test_render_handles_none_payload_gracefully() -> None:
    """Should handle None values in payload gracefully."""
    # These should not crash
    result = render_event("OUTPUT_CHUNK", {"text": None})
    assert result is None  # Empty text returns None

    result = render_event("CRITERION_VERDICT", {"verdict": None})
    assert result is not None
    assert result.title == "FAIL"  # None != "PASS"


def test_render_handles_non_string_values() -> None:
    """Should convert non-string values to strings."""
    result = render_event("AGENT_FAILED", {"error": 12345})
    assert result is not None
    assert result.body == "12345"

    result = render_event("TASK_STATUS_CHANGED", {"from": 1, "to": 2})
    assert result is not None
    assert result.title == "1 -> 2"


# -----------------------------------------------------------------------------
# Event ID and Session ID propagation tests
# -----------------------------------------------------------------------------


def test_event_id_and_session_id_propagation() -> None:
    """Should propagate event_id and session_id through all event types."""
    event_types = [
        ("OUTPUT_CHUNK", {"text": "test"}),
        ("TOOL_CALL_START", {"tool_name": "test"}),
        ("AGENT_STATUS", {}),
        ("TASK_STATUS_CHANGED", {"from": "a", "to": "b"}),
        ("CRITERION_VERDICT", {"verdict": "PASS"}),
        ("AGENT_COMPLETED", {}),
        ("AGENT_FAILED", {}),
        ("MERGE_COMPLETED", {}),
        ("MERGE_FAILED", {}),
        ("PLAN_UPDATE", {}),
        ("AUTO_REVIEW_STARTED", {}),
    ]

    for event_type, payload in event_types:
        result = render_event(
            event_type, payload, event_id="evt_123", session_id="sess_456"
        )
        if result is not None:
            assert result.event_id == "evt_123", f"Failed for {event_type}"
            assert result.session_id == "sess_456", f"Failed for {event_type}"


# -----------------------------------------------------------------------------
# Event type aliases (if supported)
# -----------------------------------------------------------------------------


def test_stream_output_alias() -> None:
    """Should handle STREAM_OUTPUT as alias for OUTPUT_CHUNK if used."""
    # STREAM_OUTPUT is not explicitly handled, should fall through to unknown
    result = render_event("STREAM_OUTPUT", {"text": "streaming"})
    assert result is not None
    assert result.kind == RenderableKind.NOTE  # Falls through to generic handler
    assert result.title == "STREAM_OUTPUT"


def test_tool_start_alias() -> None:
    """TOOL_START should be treated as unknown (TOOL_CALL_START is the handled type)."""
    result = render_event("TOOL_START", {"tool_name": "test"})
    assert result is not None
    assert result.kind == RenderableKind.NOTE
    assert result.title == "TOOL_START"


def test_tool_output_alias() -> None:
    """TOOL_OUTPUT should be treated as unknown (TOOL_CALL_UPDATE is the handled type)."""
    result = render_event("TOOL_OUTPUT", {"status": "done"})
    assert result is not None
    assert result.kind == RenderableKind.NOTE
    assert result.title == "TOOL_OUTPUT"
