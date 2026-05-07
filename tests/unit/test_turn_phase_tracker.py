"""Contract tests for TurnPhaseTracker label format."""

from __future__ import annotations

import pytest

from kagan.core.chat._turn_display import TurnPhaseTracker

pytestmark = [pytest.mark.unit]


def test_composing_label_starts_with_composing_and_includes_tokens() -> None:
    t = TurnPhaseTracker()
    t.add_text("a" * 40)  # ≈ 10 tokens
    label = t.composing_label()
    assert label.startswith("Composing ")
    assert "10 tokens" in label


def test_thinking_label_starts_with_thinking_and_includes_tokens() -> None:
    t = TurnPhaseTracker()
    t.set_phase("thinking")
    t.add_text("x" * 80)  # ≈ 20 tokens
    label = t.thinking_label()
    assert label.startswith("Thinking ")
    assert "20 tokens" in label


def test_switching_to_thinking_resets_token_count() -> None:
    t = TurnPhaseTracker()
    t.add_text("a" * 100)  # composing tokens
    t.set_phase("thinking")
    assert "0 tokens" in t.thinking_label()


def test_set_phase_is_idempotent_when_same_phase_repeated() -> None:
    t = TurnPhaseTracker()
    t.add_text("hello")  # 1 token
    t.set_phase("composing")  # same phase — tokens must NOT reset
    assert "1 tokens" in t.composing_label()
