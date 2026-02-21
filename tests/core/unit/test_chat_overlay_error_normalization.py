from __future__ import annotations

from kagan.tui.ui.widgets.chat_overlay_helpers import normalize_agent_failure_for_ui


def test_normalize_agent_failure_strips_nested_error_prefixes() -> None:
    message, hint = normalize_agent_failure_for_ui("Error: Agent error: internal error")
    assert message == "Internal error"
    assert hint is None


def test_normalize_agent_failure_adds_session_remediation_hint() -> None:
    message, hint = normalize_agent_failure_for_ui("Error: Session not found")
    assert message == "The active agent session is unavailable."
    assert hint is not None
    assert "/new session" in hint


def test_normalize_agent_failure_normalizes_timeout_copy() -> None:
    message, hint = normalize_agent_failure_for_ui("request timeout while waiting for response")
    assert message == "The agent timed out before finishing."
    assert hint == "Try a narrower prompt or resend your request."


def test_normalize_agent_failure_handles_empty_input() -> None:
    message, hint = normalize_agent_failure_for_ui("   ")
    assert message == "The agent stopped unexpectedly."
    assert hint is None
