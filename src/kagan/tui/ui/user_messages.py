"""Shared user-facing copy for common TUI messaging."""

from __future__ import annotations

PERMISSION_HEADER = "Permission required"
PERMISSION_ACTION_HINT = "Y/Enter allow once \u00b7 A always \u00b7 N/Esc deny"


def permission_tool_line(title: str) -> str:
    """Format permission prompt tool context."""
    return f"Tool: {title}"


def permission_timer_line(remaining_seconds: int) -> str:
    """Format countdown copy for permission prompts."""
    minutes, seconds = divmod(max(remaining_seconds, 0), 60)
    return f"Awaiting decision\u2026 {minutes}:{seconds:02d}"


def task_deleted_close_message(surface: str) -> str:
    """Format deletion message when a modal must close for stale task state."""
    return f"Task deleted. Closing {surface}."


def task_moved_close_message(status_value: str) -> str:
    """Format status-transition message when review/output modal closes."""
    return f"Task moved to {status_value.upper()}. Closing output."
