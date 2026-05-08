"""Unit tests for the compact in-Live status renderable (kimi-cli parity).

build_live_status_inline() replaces the old multi-line build_live_footer()
Group that caused the toolbar to jump mid-screen during streaming.  The new
function returns at most one right-aligned Text line showing token / context
usage.  The full 3-line toolbar continues to live in prompt_toolkit's
bottom_toolbar callback (viewport-pinned).
"""

from __future__ import annotations

import pytest
from rich.text import Text

from kagan.cli.chat.repl import (
    _TOOLBAR_STATE,
    build_live_status_inline,
)

pytestmark = [pytest.mark.unit]


def _reset_toolbar(**kwargs: object) -> None:
    _TOOLBAR_STATE.is_streaming = True  # inline status only active while streaming
    _TOOLBAR_STATE.token_used_k = None
    _TOOLBAR_STATE.context_pct = None
    _TOOLBAR_STATE.agent_backend = ""
    _TOOLBAR_STATE.project_name = ""
    _TOOLBAR_STATE.turn_count = 0
    _TOOLBAR_STATE.queued_count = 0
    _TOOLBAR_STATE.plan_mode = False
    _TOOLBAR_STATE.pending_approvals = 0
    _TOOLBAR_STATE.current_tool = ""
    _TOOLBAR_STATE.session_label = "orchestrator"
    _TOOLBAR_STATE.workspace_label = ""
    for key, value in kwargs.items():
        setattr(_TOOLBAR_STATE, key, value)


def test_inline_status_is_right_justified_with_both_token_and_context() -> None:
    """When token_used_k and context_pct are both set, the Text is right-justified."""
    _reset_toolbar(token_used_k=12.4, context_pct=0.38)
    result = build_live_status_inline()
    assert isinstance(result, Text)
    assert result.justify == "right"
    assert "tok" in result.plain
    assert "ctx" in result.plain
    assert "38%" in result.plain


def test_inline_status_is_single_line() -> None:
    """The rendered status contains no embedded newlines — it is a single line."""
    _reset_toolbar(token_used_k=5.0, context_pct=0.20)
    result = build_live_status_inline()
    assert result is not None
    assert "\n" not in result.plain


def test_inline_status_only_context_pct_when_token_not_set() -> None:
    """With only context_pct set the status shows ctx percentage only."""
    _reset_toolbar(token_used_k=None, context_pct=0.55)
    result = build_live_status_inline()
    assert result is not None
    assert "ctx 55%" in result.plain
    # No stray token label when token_used_k is absent
    assert "tok" not in result.plain


def test_inline_status_only_token_k_when_context_pct_not_set() -> None:
    """With only token_used_k set the status shows the token count only."""
    _reset_toolbar(token_used_k=8.3, context_pct=None)
    result = build_live_status_inline()
    assert result is not None
    assert "8.3k tok" in result.plain
    assert "ctx" not in result.plain


def test_inline_status_returns_none_when_both_values_absent() -> None:
    """When neither token_used_k nor context_pct is set, returns None (nothing shown)."""
    _reset_toolbar(token_used_k=None, context_pct=None)
    result = build_live_status_inline()
    assert result is None


def test_inline_status_returns_none_when_not_streaming() -> None:
    """build_live_status_inline returns None when is_streaming=False."""
    _reset_toolbar(is_streaming=False, token_used_k=10.0, context_pct=0.50)
    _TOOLBAR_STATE.is_streaming = False
    result = build_live_status_inline()
    assert result is None


def test_inline_status_zero_values_return_none() -> None:
    """Zero context_pct with no token count still returns None — nothing to show."""
    _reset_toolbar(token_used_k=None, context_pct=None)
    result = build_live_status_inline()
    assert result is None


def test_inline_status_contains_no_rule_separator() -> None:
    """The compact status must never include the '─' rule (that belongs to prompt_toolkit only)."""
    _reset_toolbar(token_used_k=20.0, context_pct=0.80)
    result = build_live_status_inline()
    assert result is not None
    assert "─" not in result.plain


def test_inline_status_contains_no_tip_line() -> None:
    """The compact status must never include the 'tip:' rotating tip (prompt_toolkit only)."""
    _reset_toolbar(token_used_k=20.0, context_pct=0.80)
    result = build_live_status_inline()
    assert result is not None
    assert "tip:" not in result.plain
