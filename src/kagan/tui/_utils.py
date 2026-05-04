"""Shared TUI utility helpers."""

__all__ = ["is_enabled"]


def is_enabled(value: str | None, *, default: bool) -> bool:
    """Return True if the setting value is truthy, False if falsy.

    A missing value (``None``) returns ``default``.  Explicit disable tokens
    are ``"0"``, ``"false"``, ``"no"``, and ``"off"`` (case-insensitive).
    Any other non-empty string is treated as enabled.
    """
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}
