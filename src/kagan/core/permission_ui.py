"""kagan.core.permission_ui — shared permission-UI helpers.

Pure helpers shared between the CLI chat REPL (``kagan.cli.chat``) and the
TUI (``kagan.tui``).  No Click, no Textual, no Rich console — only stdlib and
``loguru``.

Exported symbols
----------------
tool_action_key(tool_call)
    Return the base tool name for session-allow tracking.
format_permission_tool(tool_call)
    Return a short human-readable label for a tool-call.
SessionApprovals
    Cache of tool actions approved for one REPL / TUI session.
session_approvals
    Module-level singleton used by both surfaces.
"""

from __future__ import annotations

from typing import Any

# ---------------------------------------------------------------------------
# Tool action key
# ---------------------------------------------------------------------------


def tool_action_key(tool_call: Any) -> str:
    """Return the base tool name for session-allow tracking (no args embedded).

    Accepts both ACP tool-call objects (with ``title`` / ``name`` attrs) and
    plain dicts (used by the engine's :class:`~kagan.core.permission.PermissionRequest`
    event).  Strips any trailing ``': {...}'`` argument suffix from the title
    field so that repeated calls to the same tool with different arguments
    share one cache key.
    """
    if isinstance(tool_call, dict):
        raw = tool_call.get("title") or tool_call.get("name") or "tool"
    else:
        raw = getattr(tool_call, "title", None) or getattr(tool_call, "name", None) or "tool"
    base = str(raw).split(":")[0].split("{")[0].strip().casefold()
    return base or "tool"


# ---------------------------------------------------------------------------
# Permission tool label
# ---------------------------------------------------------------------------


def format_permission_tool(tool_call: Any) -> str:
    """Return a short human-readable label for a tool-call.

    Prefers ``title`` over ``name``; includes ``kind`` in parentheses when
    available.
    """
    title = getattr(tool_call, "title", None) or getattr(tool_call, "name", None)
    kind = getattr(tool_call, "kind", None)
    if title and kind:
        return f"{title} ({kind})"
    if title:
        return str(title)
    return "tool call"


# ---------------------------------------------------------------------------
# Session-allow cache
# ---------------------------------------------------------------------------


class SessionApprovals:
    """Track tool actions approved for the lifetime of one REPL or TUI session."""

    def __init__(self) -> None:
        self._allowed: set[str] = set()
        self._all_allowed: bool = False

    def is_allowed(self, action_key: str) -> bool:
        """Return ``True`` if *action_key* has been granted or all tools are trusted."""
        return self._all_allowed or action_key in self._allowed

    def grant(self, action_key: str) -> None:
        """Grant approval for a single tool action key."""
        self._allowed.add(action_key)

    def grant_all(self) -> None:
        """Trust all tool calls for the rest of this session."""
        self._all_allowed = True

    def revoke(self, action_key: str) -> None:
        """Remove a previously granted action key."""
        self._allowed.discard(action_key)

    def list_granted(self) -> list[str]:
        """Return a sorted list of explicitly granted action keys."""
        return sorted(self._allowed)


session_approvals: SessionApprovals = SessionApprovals()
"""Module-level singleton — shared by all surfaces within one process."""


__all__ = [
    "SessionApprovals",
    "format_permission_tool",
    "session_approvals",
    "tool_action_key",
]
