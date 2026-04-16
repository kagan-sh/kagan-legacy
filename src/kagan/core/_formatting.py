"""Formatting utilities for analytics and dashboards."""

from __future__ import annotations


def format_percentage(value: float) -> str:
    """Format a decimal (0.0-1.0) as percentage string.

    Args:
        value: Decimal value between 0 and 1.

    Returns:
        Formatted percentage (e.g., "95.5%").
    """
    return f"{value * 100:.1f}%"


def format_duration(seconds: float | None) -> str:
    """Format seconds as human-readable duration.

    Args:
        seconds: Duration in seconds, or None.

    Returns:
        Formatted duration (e.g., "5m 23s", "45s", "--").
    """
    if seconds is None:
        return "--"
    if seconds < 60:
        return f"{round(seconds)}s"
    mins = int(seconds // 60)
    secs = round(seconds % 60)
    return f"{mins}m {secs}s" if secs else f"{mins}m"
