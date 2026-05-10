"""TUI unit tests for apply_chat_event_to_panel with AgentLifecycle events.

Verifies that AgentLifecycle events produce system messages in the ChatPanel
when routed through apply_chat_event_to_panel.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from kagan.core.events import AgentLifecycle
from kagan.tui.screens._chat_runner import apply_chat_event_to_panel

pytestmark = [pytest.mark.tui]


def _panel_mock() -> MagicMock:
    panel = MagicMock()
    panel._turn_tracker = None
    return panel


def _apply(
    kind: str, *, task_id: str | None = "task-abc123", detail: str | None = None
) -> MagicMock:
    panel = _panel_mock()
    event = AgentLifecycle(
        session_id="session-1",
        task_id=task_id,
        kind=kind,  # type: ignore[arg-type]
        detail=detail,
    )
    apply_chat_event_to_panel(panel, event)
    return panel


def test_finished_adds_system_message_with_checkmark() -> None:
    panel = _apply("finished", task_id="abc12345")
    panel.add_system_message.assert_called_once()
    msg = panel.add_system_message.call_args[0][0]
    assert "✓" in msg
    assert "#abc12345" in msg
    assert "finished" in msg


def test_failed_adds_system_message_with_cross_and_detail() -> None:
    panel = _apply("failed", task_id="abc12345", detail="exit 1")
    panel.add_system_message.assert_called_once()
    msg = panel.add_system_message.call_args[0][0]
    assert "✗" in msg
    assert "failed" in msg
    assert "exit 1" in msg


def test_failed_without_detail_has_no_colon_suffix() -> None:
    panel = _apply("failed", task_id="abc12345")
    msg = panel.add_system_message.call_args[0][0]
    assert "failed" in msg
    assert ":" not in msg  # no extra suffix


def test_stopped_adds_system_message_with_circle() -> None:
    panel = _apply("stopped", task_id="abc12345")
    msg = panel.add_system_message.call_args[0][0]
    assert "◯" in msg
    assert "stopped" in msg


def test_started_adds_system_message_with_arrow() -> None:
    panel = _apply("started", task_id="abc12345")
    msg = panel.add_system_message.call_args[0][0]
    assert "▸" in msg
    assert "started" in msg


def test_task_id_truncated_to_eight_chars() -> None:
    panel = _apply("finished", task_id="abcdef1234567890")
    msg = panel.add_system_message.call_args[0][0]
    assert "#abcdef12" in msg
    # Full id not present beyond the truncation
    assert "1234567890" not in msg


def test_none_task_id_shows_task_label() -> None:
    panel = _apply("finished", task_id=None)
    msg = panel.add_system_message.call_args[0][0]
    assert "task" in msg
