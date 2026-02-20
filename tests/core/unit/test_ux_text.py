from __future__ import annotations

from kagan.core.ux_text import (
    format_interaction_notification,
    normalize_interaction_verbosity,
    preview_text_for_interaction,
)


def test_normalize_interaction_verbosity_defaults_to_short() -> None:
    assert normalize_interaction_verbosity("verbose") == "short"
    assert normalize_interaction_verbosity(None) == "short"


def test_format_interaction_notification_tldr_uses_first_line() -> None:
    message = "Primary guidance\nAdditional details"
    formatted = format_interaction_notification(message, verbosity="tldr")
    assert formatted == "Primary guidance"


def test_format_interaction_notification_technical_adds_warning_hint() -> None:
    formatted = format_interaction_notification(
        "Pair launcher unavailable",
        verbosity="technical",
        severity="warning",
    )
    assert "Pair launcher unavailable" in formatted
    assert "kagan doctor --verbosity technical" in formatted


def test_format_interaction_notification_redacts_sensitive_values() -> None:
    formatted = format_interaction_notification(
        "Authorization: Bearer super-secret-token owner=dev@example.com",
        verbosity="short",
    )
    assert "super-secret-token" not in formatted
    assert "dev@example.com" not in formatted
    assert "[REDACTED]" in formatted


def test_preview_text_for_interaction_obeys_verbosity_limits() -> None:
    text = "x" * 100
    assert len(preview_text_for_interaction(text, verbosity="tldr")) <= 40
    assert len(preview_text_for_interaction(text, verbosity="short")) <= 80
    assert len(preview_text_for_interaction(text, verbosity="technical")) <= 160
