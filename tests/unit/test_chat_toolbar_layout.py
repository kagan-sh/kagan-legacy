"""Unit tests for the always-on custom prompt_toolkit toolbar layout (Change 4)."""

from __future__ import annotations

import pytest

from kagan.cli.chat.repl import (
    _TOOLBAR_STATE,
    ToolbarState,
    _build_status_text,
)

pytestmark = [pytest.mark.unit]


def _reset_toolbar(**kwargs: object) -> None:
    """Reset _TOOLBAR_STATE fields for test isolation."""
    _TOOLBAR_STATE.is_streaming = False
    _TOOLBAR_STATE.agent_backend = ""
    _TOOLBAR_STATE.project_name = ""
    _TOOLBAR_STATE.turn_count = 0
    _TOOLBAR_STATE.queued_count = 0
    _TOOLBAR_STATE.context_pct = None
    _TOOLBAR_STATE.token_used_k = None
    _TOOLBAR_STATE.plan_mode = False
    _TOOLBAR_STATE.pending_approvals = 0
    _TOOLBAR_STATE.current_tool = ""
    _TOOLBAR_STATE.session_label = "orchestrator"
    _TOOLBAR_STATE.workspace_label = ""
    for key, value in kwargs.items():
        setattr(_TOOLBAR_STATE, key, value)


def test_status_text_shows_streaming_state() -> None:
    """When is_streaming=True, the status text includes agent / token info."""
    _reset_toolbar(
        is_streaming=True,
        agent_backend="claude-code",
        turn_count=3,
    )
    text = _build_status_text()
    # Flatten to raw string for assertion
    raw = "".join(t for _, t in text)
    assert "agent" in raw
    assert "3 msgs" in raw


def test_status_text_shows_idle_state() -> None:
    """When is_streaming=False, the status text includes tip and session label."""
    _reset_toolbar(
        is_streaming=False,
        session_label="orchestrator",
        turn_count=0,
    )
    text = _build_status_text()
    raw = "".join(t for _, t in text)
    assert "tip:" in raw
    assert "session:" in raw
    assert "orchestrator" in raw


def test_status_text_shows_queued_indicator() -> None:
    """When queued_count > 0, the status bar shows the queue depth."""
    _reset_toolbar(queued_count=2, agent_backend="claude-code")
    text = _build_status_text()
    raw = "".join(t for _, t in text)
    assert "queued" in raw
    assert "2" in raw


def test_status_text_no_queued_indicator_when_empty() -> None:
    """When queued_count == 0, no queued indicator appears."""
    _reset_toolbar(queued_count=0)
    text = _build_status_text()
    raw = "".join(t for _, t in text)
    assert "queued" not in raw


def test_live_state_has_no_footer_attribute() -> None:
    """_TurnLiveState uses inline_status (single-line Text), not a footer Group.

    The old ``_footer`` callable returned a multi-line Rich Group that caused
    the toolbar to jump mid-screen during streaming.  The replacement
    ``_inline_status`` returns at most a single right-aligned Text line.
    """
    from kagan.cli.chat._streaming import _TurnLiveState

    state = _TurnLiveState()
    assert not hasattr(state, "_footer"), (
        "_TurnLiveState must not have _footer; use _inline_status instead"
    )
    assert hasattr(state, "_inline_status"), (
        "_TurnLiveState must have _inline_status for the compact single-line status"
    )


def test_markdown_streaming_region_has_no_footer_attribute() -> None:
    """MarkdownStreamingRegion is clean — no footer-related attributes."""
    import io

    from rich.console import Console

    from kagan.cli.chat._streaming import MarkdownStreamingRegion

    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None, width=80)
    region = MarkdownStreamingRegion(console)
    assert not hasattr(region, "__rich__"), (
        "MarkdownStreamingRegion should not be a Rich renderable (no footer group)"
    )
    assert not hasattr(region, "_footer"), (
        "MarkdownStreamingRegion should not have a _footer attribute"
    )


def test_toolbar_state_has_queued_count_field() -> None:
    """ToolbarState dataclass has the queued_count field added in Change 3."""
    state = ToolbarState()
    assert hasattr(state, "queued_count")
    assert state.queued_count == 0


def test_toolbar_state_has_project_id_field() -> None:
    """ToolbarState dataclass has the project_id field added in Change 1."""
    state = ToolbarState()
    assert hasattr(state, "project_id")
    assert state.project_id == ""
