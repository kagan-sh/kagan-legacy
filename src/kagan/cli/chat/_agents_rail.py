"""Inline running-agents rail for the chat REPL.

After each REPL turn this module formats and prints a compact summary of
active agent sessions — mirroring the Claude Code "↓ to manage" rail.

Public helpers:

- ``format_rail_line`` — format a single summary line ("● 3 local agents · ↓ to manage")
- ``format_agent_rows`` — format the per-agent detail lines
- ``format_agents_rail`` — combine both into the full rail text (list of strings)
- ``print_agents_rail`` — print the rail to a Rich Console (no-op if empty)
- ``_resolve_picker_choice`` — pure function: map picker index → AgentPickerRow
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from rich.console import Console

    from kagan.core._sessions_query import ActiveAgentRow

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class AgentPickerRow:
    """Row shown inside the ↓ picker and returned by _resolve_picker_choice."""

    label: str
    """Short label — "main" for orchestrator, or the persona/role name."""
    session_id: str | None
    """None means "return to orchestrator mode" (detach)."""
    agent_role: str | None
    """worker / reviewer / None for orchestrator slot."""
    task_id: str | None
    task_title: str | None
    context_tokens: int | None


# ---------------------------------------------------------------------------
# Duration formatting
# ---------------------------------------------------------------------------

_MINUTE = 60
_HOUR = 3600


def _format_elapsed(seconds: float) -> str:
    """Format elapsed seconds into a compact human-readable string."""
    if seconds < _MINUTE:
        return f"{int(seconds)}s"
    if seconds < _HOUR:
        minutes, secs = divmod(int(seconds), _MINUTE)
        return f"{minutes}m {secs}s"
    hours, remainder = divmod(int(seconds), _HOUR)
    minutes = remainder // _MINUTE
    return f"{hours}h {minutes}m"


def _elapsed_since(started_at: datetime) -> float:
    """Return elapsed seconds since *started_at* (assumed UTC)."""
    if started_at.tzinfo is None:
        started_at = started_at.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - started_at).total_seconds())


def _format_tokens(tokens: int | None) -> str:
    if tokens is None:
        return ""
    k = tokens / 1000
    if k >= 100:
        return f"↓{k:.0f}k"
    return f"↓{k:.1f}k"


# ---------------------------------------------------------------------------
# Rail formatting
# ---------------------------------------------------------------------------


def format_rail_line(count: int) -> str:
    """Return the single-line summary header.

    Example: "● 3 local agents · ↓ to manage"
    Returns an empty string when count is zero.
    """
    if count == 0:
        return ""
    word = "agent" if count == 1 else "agents"
    return f"● {count} local {word} · ↓ to manage"


def format_agent_rows(rows: list[ActiveAgentRow]) -> list[str]:
    """Format per-agent detail lines.

    Each line looks like:
        ⎇ eng-core    Implement kg chat: …    23s · ↓82k
    """
    result: list[str] = []
    for row in rows:
        role_label = (row.agent_role or "worker").lower()
        title = row.task_title or row.task_id or "unknown"
        if len(title) > 40:
            title = title[:39] + "…"
        elapsed = _elapsed_since(row.started_at)
        elapsed_str = _format_elapsed(elapsed)
        token_count = (row.input_tokens or 0) + (row.output_tokens or 0)
        token_str = _format_tokens(token_count if token_count > 0 else None)
        meta = elapsed_str
        if token_str:
            meta = f"{meta} · {token_str}"
        result.append(f"  ⎇ {role_label:<12} {title:<42} {meta}")
    return result


def format_agents_rail(rows: list[ActiveAgentRow]) -> list[str]:
    """Return all rail lines (header + detail rows).

    Returns an empty list when there are no active agents — callers should
    suppress output entirely in that case (no nag).
    """
    if not rows:
        return []
    lines = [format_rail_line(len(rows))]
    lines.extend(format_agent_rows(rows))
    return lines


def print_agents_rail(rows: list[ActiveAgentRow], console: Console) -> None:
    """Print the agents rail to *console*; no-op if rows is empty."""
    lines = format_agents_rail(rows)
    if not lines:
        return
    for line in lines:
        console.print(f"[dim]{line}[/dim]")


# ---------------------------------------------------------------------------
# Picker helpers
# ---------------------------------------------------------------------------


def build_picker_rows(
    rows: list[ActiveAgentRow],
    *,
    orchestrator_label: str = "main",
) -> list[AgentPickerRow]:
    """Build the list shown in the ↓ picker.

    The first row is always "main" (orchestrator/detach).  Subsequent rows
    are the active agents in the same order as *rows*.
    """
    picker: list[AgentPickerRow] = [
        AgentPickerRow(
            label=orchestrator_label,
            session_id=None,
            agent_role=None,
            task_id=None,
            task_title="Return to orchestrator",
            context_tokens=None,
        )
    ]
    for row in rows:
        token_count = (row.input_tokens or 0) + (row.output_tokens or 0)
        picker.append(
            AgentPickerRow(
                label=(row.agent_role or "worker").lower(),
                session_id=row.session_id,
                agent_role=row.agent_role,
                task_id=row.task_id,
                task_title=row.task_title,
                context_tokens=token_count if token_count > 0 else None,
            )
        )
    return picker


def _resolve_picker_choice(rows: list[AgentPickerRow], idx: int) -> AgentPickerRow | None:
    """Return the AgentPickerRow at *idx*, or None if out of range.

    This is a pure function — easy to unit-test without any UI overhead.
    """
    if not rows or idx < 0 or idx >= len(rows):
        return None
    return rows[idx]


__all__ = [
    "AgentPickerRow",
    "_resolve_picker_choice",
    "build_picker_rows",
    "format_agent_rows",
    "format_agents_rail",
    "format_rail_line",
    "print_agents_rail",
]
