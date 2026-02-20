"""User-facing text helpers for consistent progressive disclosure."""

from __future__ import annotations

from typing import Literal, cast

from kagan.core.safety import normalize_untrusted_text, redact_sensitive_text

type InteractionVerbosity = Literal["tldr", "short", "technical"]

INTERACTION_VERBOSITY_VALUES = frozenset({"tldr", "short", "technical"})

_ERROR_HINT = (
    "Troubleshooting: run `kagan doctor --verbosity technical`, "
    "then check `?` Help and `F12` debug logs."
)
_WARNING_HINT = "Tip: run `kagan doctor --verbosity technical` for detailed diagnostics and fixes."


def normalize_interaction_verbosity(value: object) -> InteractionVerbosity:
    """Normalize interaction verbosity with safe fallback."""
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in INTERACTION_VERBOSITY_VALUES:
            return cast("InteractionVerbosity", normalized)
    return "short"


def format_interaction_notification(
    message: str,
    *,
    verbosity: InteractionVerbosity = "short",
    severity: str = "information",
) -> str:
    """Format a notification message for the target expertise level."""
    safe = redact_sensitive_text(
        normalize_untrusted_text(message, max_chars=1_200),
        redact_pii=True,
    ).strip()
    if not safe:
        safe = "Notification"

    if verbosity == "tldr":
        first_line = next((line.strip() for line in safe.splitlines() if line.strip()), safe)
        return first_line

    if verbosity == "technical":
        normalized_severity = severity.strip().lower()
        if normalized_severity == "error" and _ERROR_HINT not in safe:
            return f"{safe}\n\n{_ERROR_HINT}"
        if normalized_severity == "warning" and _WARNING_HINT not in safe:
            return f"{safe}\n\n{_WARNING_HINT}"

    return safe


def preview_text_for_interaction(
    message: str,
    *,
    verbosity: InteractionVerbosity = "short",
) -> str:
    """Build a short preview tuned to verbosity level."""
    safe = redact_sensitive_text(
        normalize_untrusted_text(message, max_chars=600),
        redact_pii=True,
    ).strip()
    if not safe:
        return ""

    limits = {
        "tldr": 40,
        "short": 80,
        "technical": 160,
    }
    limit = limits[verbosity]
    if len(safe) <= limit:
        return safe
    return f"{safe[: max(limit - 1, 1)]}…"


__all__ = [
    "INTERACTION_VERBOSITY_VALUES",
    "InteractionVerbosity",
    "format_interaction_notification",
    "normalize_interaction_verbosity",
    "preview_text_for_interaction",
]
