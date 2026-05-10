"""Rich approval panel for chat REPL permission requests.

Renders a bordered yellow panel with:
- Human-readable action header (strips mcp__kagan__ prefix)
- Typed body preview (bash syntax-highlight for shell commands, pretty-print for MCP args)
- 4-option menu with arrow-key nav and number hotkeys
- Inline feedback capture for option 4 (Reject + tell model)
- Footer hint line
- Agent identity metadata if available
"""

from __future__ import annotations

import os
from typing import Any

from rich.console import Group
from rich.markup import escape as _rich_escape
from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text

from kagan.cli.chat._theme import APPROVAL

# Maximum lines to show in approval preview body
_MAX_PREVIEW_LINES = 4

_APPROVAL_OPTIONS: list[tuple[str, str]] = [
    ("Approve once", "allow_once"),
    ("Approve tool for session", "allow_always"),
    ("Allow all for session", "allow_all_session"),
    ("Reject", "reject_once"),
    ("Reject — tell the model what to do", "reject_feedback"),
]


def _tc(tool_call: Any, *keys: str) -> Any:
    """Get an attribute from a tool_call that may be a dict or an object."""
    for k in keys:
        v = tool_call.get(k) if isinstance(tool_call, dict) else getattr(tool_call, k, None)
        if v:
            return v
    return None


def _use_ascii_spinner() -> bool:
    """Return True when the terminal cannot render Unicode spinners."""
    return bool(os.environ.get("NO_COLOR")) or os.environ.get("TERM", "") == "dumb"


def no_color() -> bool:
    """Honor the NO_COLOR convention (https://no-color.org)."""
    return bool(os.environ.get("NO_COLOR"))


def strip_tool_prefix(name: str) -> str:
    """Remove mcp__kagan__ prefix and convert underscores to spaces for display."""
    for prefix in ("mcp__kagan__", "mcp__"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    return name.replace("_", " ").strip()


def _tool_display_name(tool_call: Any) -> str:
    """Return a human-readable tool name from an ACP tool_call object or dict."""
    raw = _tc(tool_call, "title", "name") or "tool call"
    return strip_tool_prefix(str(raw))


def _is_shell_command(tool_call: Any) -> bool:
    raw = _tc(tool_call, "title", "name") or ""
    lower = str(raw).casefold()
    return any(kw in lower for kw in ("shell", "bash", "exec", "run", "command"))


def _extract_shell_command(tool_call: Any) -> str | None:
    """Try to pull the shell command string out of tool args."""
    for attr in ("raw_input", "rawInput", "arguments", "args"):
        val = _tc(tool_call, attr)
        if not val:
            continue
        if isinstance(val, str):
            import json

            try:
                obj = json.loads(val)
                if isinstance(obj, dict):
                    for key in ("command", "cmd", "shell", "script"):
                        if key in obj:
                            return str(obj[key])
                    # first string value
                    for v in obj.values():
                        if isinstance(v, str):
                            return v
            except (json.JSONDecodeError, ValueError):
                return val.strip()
        elif isinstance(val, dict):
            for key in ("command", "cmd", "shell", "script"):
                if key in val:
                    return str(val[key])
    return None


def _extract_key_args_preview(tool_call: Any) -> str | None:
    """Extract up to _MAX_PREVIEW_LINES lines of key arguments for display."""
    import json

    for attr in ("raw_input", "rawInput", "arguments", "args"):
        val = _tc(tool_call, attr)
        if not val:
            continue
        parsed: dict[str, object] | None = None
        if isinstance(val, dict):
            parsed = {str(k): v for k, v in val.items()}
        elif isinstance(val, str):
            try:
                obj = json.loads(val)
                if isinstance(obj, dict):
                    parsed = {str(k): v for k, v in obj.items()}
            except (json.JSONDecodeError, ValueError):
                pass
        if parsed is None:
            continue
        lines = []
        for k, v in list(parsed.items())[:_MAX_PREVIEW_LINES]:
            vstr = str(v)
            if len(vstr) > 80:
                vstr = vstr[:77] + "..."
            lines.append(f"  {k}: {vstr}")
        if len(parsed) > _MAX_PREVIEW_LINES:
            lines.append(f"  ... ({len(parsed) - _MAX_PREVIEW_LINES} more args)")
        return "\n".join(lines)
    return None


def build_approval_panel(
    tool_call: Any,
    *,
    selected_index: int = 0,
    feedback_draft: str = "",
    queue_depth: int = 0,
    queue_position: int = 0,
) -> Panel:
    """Build a Rich Panel for an ACP permission request.

    Args:
        tool_call: ACP tool_call object from request_permission.
        selected_index: Currently highlighted menu row (0-based).
        feedback_draft: Text typed so far for option-4 rejection feedback.
        queue_depth: Total pending approvals (0 = single, shown as queue N of M).
        queue_position: 1-based position in queue.
    """
    display_name = _tool_display_name(tool_call)
    lines: list[object] = []

    # Header — declarative: describe what the agent will execute, not its intent.
    header_text = f"Agent will run [bold]{_rich_escape(display_name)}[/bold]"
    lines.append(Text.from_markup(f"[yellow]{header_text}[/yellow]"))

    # Agent metadata (subagent / source task)
    agent_id = getattr(tool_call, "agent_id", None)
    subagent_type = getattr(tool_call, "subagent_type", None)
    source_desc = getattr(tool_call, "source_description", None)
    if agent_id or subagent_type:
        parts = [p for p in (subagent_type, agent_id) if p]
        lines.append(Text(f"Agent: {' / '.join(parts)}", style=APPROVAL.meta))
    if source_desc:
        lines.append(Text(f"Task: {source_desc}", style=APPROVAL.meta))

    lines.append(Text(""))

    # Body: shell command or MCP args preview
    if _is_shell_command(tool_call):
        cmd = _extract_shell_command(tool_call)
        if cmd:
            truncated = "\n".join(cmd.splitlines()[:_MAX_PREVIEW_LINES])
            if len(cmd.splitlines()) > _MAX_PREVIEW_LINES:
                truncated += "\n... (truncated)"
            lines.append(Syntax(truncated, "bash", theme="ansi_dark", word_wrap=False))
        else:
            lines.append(Text("(shell command)", style=APPROVAL.dim))
    else:
        preview = _extract_key_args_preview(tool_call)
        if preview:
            lines.append(Text(preview, style=APPROVAL.dim))
        else:
            raw = _tc(tool_call, "title", "name") or ""
            lines.append(Text(strip_tool_prefix(str(raw)), style=APPROVAL.dim))

    lines.append(Text(""))

    # Menu options
    panel_options = _build_display_options()
    for i, (label, _kind) in enumerate(panel_options):
        num = i + 1
        is_feedback = i == 4
        if i == selected_index:
            if is_feedback and feedback_draft:
                cursor_display = f"→ [{num}] Reject: {feedback_draft}█"
                lines.append(Text(cursor_display, style=APPROVAL.cursor))
            else:
                lines.append(Text(f"→ [{num}] {label}", style=APPROVAL.focused))
        else:
            lines.append(Text(f"  [{num}] {label}", style=APPROVAL.dim))

    # Keyboard hint footer
    lines.append(Text(""))
    if selected_index == 4 and feedback_draft:
        hint = "  Type feedback  Enter submit  Esc cancel"
    else:
        hint = "  ▲/▼ select  1-5 choose  ↵ confirm"
    lines.append(Text(hint, style=APPROVAL.hint))

    # Queue depth indicator
    title = "[bold]approval[/bold]"
    if queue_depth > 1:
        title = f"[bold]approval[/bold]  [dim]{queue_position}/{queue_depth}[/dim]"

    return Panel(
        Group(*lines),
        border_style=APPROVAL.border,
        title=title,
        title_align="left",
        padding=(0, 1),
    )


_DISPLAY_OPTIONS: list[tuple[str, str]] = [
    ("Approve once", "allow_once"),
    ("Approve tool for session", "allow_always"),
    ("Allow all for session", "allow_all_session"),
    ("Reject", "reject_once"),
    ("Reject — tell the model what to do", "reject_feedback"),
]


def _build_display_options() -> list[tuple[str, str]]:
    """Return the fixed 5-slot panel option list.

    The panel surface is constant; ACP options aren't consulted because
    `_map_approval_result` resolves the user's choice by slot index.
    """
    return list(_DISPLAY_OPTIONS)


def get_rich_spinner_name() -> str:
    """Return Rich spinner name appropriate for the terminal."""
    return "line" if _use_ascii_spinner() else "dots"
