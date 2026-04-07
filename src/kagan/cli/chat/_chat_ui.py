"""UI rendering helpers for chat — panels, tables, tool reports, session lists."""

import shutil
from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kagan.cli.chat._chat_acp import _OrchestratorACPClient
from kagan.cli.chat.commands import SLASH_COMMAND_REGISTRY
from kagan.cli.chat.repl import SearchPickerOption, _console


def print_help_documentation() -> None:
    """Render the /help guide panel."""
    # Build reverse alias map: {target: [aliases]}
    aliases = SLASH_COMMAND_REGISTRY.aliases
    reverse_aliases: dict[str, list[str]] = {}
    for alias, target in aliases.items():
        reverse_aliases.setdefault(target, []).append(alias)

    spec_by_name = {spec.name: spec for spec in SLASH_COMMAND_REGISTRY.specs()}
    sections = [
        ("Global", ["help", "flow", "status", "clear", "exit"]),
        ("Sessions", ["new", "sessions", "delete"]),
        ("Workspace", ["project", "agents", "tool"]),
    ]

    def _label_for(name: str) -> str:
        parts = [f"/{name}"]
        for a in sorted(reverse_aliases.get(name, [])):
            parts.append(f"/{a}")
        return ", ".join(parts)

    blocks: list[object] = []
    for title, names in sections:
        table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 2, 0, 0))
        table.add_column(style="bold cyan", no_wrap=True)
        table.add_column(style="default")
        for name in names:
            spec = spec_by_name.get(name)
            if spec is None:
                continue
            table.add_row(_label_for(name), spec.description)
        blocks.append(Text(title, style="bold"))
        blocks.append(table)

    keyboard = Table(box=None, show_header=False, pad_edge=False, padding=(0, 2, 0, 0))
    keyboard.add_column(style="bold cyan", no_wrap=True)
    keyboard.add_column(style="default")
    keyboard.add_row("Esc", "Cancel agent & edit last message")
    keyboard.add_row("Ctrl-J", "Insert a newline")
    keyboard.add_row("Ctrl-C", "Clear the current input")
    keyboard.add_row("Ctrl-D", "Exit the chat session")

    blocks.extend(
        [
            Text("Keyboard", style="bold"),
            keyboard,
            Text("Type a request, / for commands, or ? for shortcuts", style="dim"),
            Text("Docs: https://docs.kagan.sh/", style="dim"),
        ]
    )

    _console.print(
        Panel(
            Group(*blocks),
            title="Help Guide",
            border_style="green",
            padding=(1, 2),
            expand=False,
        )
    )


def print_status_panel(
    *,
    session_title: str | None,
    chat_session_id: str | None,
    project_name: str | None,
    agent_backend: str,
    turn_count: int,
) -> None:
    """Render the /status one-liner or multi-line panel."""
    session_label = session_title or chat_session_id or "none"
    session_id_short = (chat_session_id or "?")[:8]
    parts = [
        f"project: {project_name or 'none'}",
        f"session: {session_label} ({session_id_short})",
        f"agent: {agent_backend}",
        f"turns: {turn_count}",
    ]
    line = " · ".join(parts)
    cols = shutil.get_terminal_size().columns
    if len(line) <= cols:
        _console.print(f"[dim]{line}[/dim]")
    else:
        for part in parts:
            _console.print(f"  [dim]{part}[/dim]")


def print_project_info(*, project_name: str | None, project_id: str | None) -> None:
    """Render /project info."""
    if project_name:
        _console.print(f"[bold]Project:[/bold] {project_name}")
        _console.print(f"[dim]ID:[/dim] {project_id or 'unknown'}")
    else:
        _console.print("[dim]No active project.[/dim]")


def print_repo_info(*, repo_name: str | None, repo_id: str | None) -> None:
    """Render /repo info."""
    if repo_name:
        _console.print(f"[bold]Repo:[/bold] {repo_name}")
        _console.print(f"[dim]ID:[/dim] {repo_id or 'unknown'}")
    else:
        _console.print("[dim]No repo selected.[/dim]")


def print_session_list(items: list[Any]) -> None:
    """Render a table of sessions for non-interactive terminals."""
    table = Table(box=None, show_header=False, pad_edge=False)
    table.add_column(justify="right", style="dim", no_wrap=True)
    table.add_column(no_wrap=True)
    table.add_column(style="dim", no_wrap=True)
    table.add_column(style="dim", no_wrap=True)
    table.add_column(no_wrap=True)
    for item in items:
        marker = "[bold cyan]● current[/bold cyan]" if item.is_current else ""
        table.add_row(
            str(item.index),
            item.label,
            item.agent_backend or "",
            item.updated_relative or "",
            marker,
        )
    _console.print(table)
    _console.print()
    _console.print("[dim]/sessions <n> attach · /new create · /delete <n> remove[/dim]")


def build_session_picker_option(item: Any) -> SearchPickerOption:
    """Build a picker option from a session list item."""
    meta_parts = [part for part in (item.agent_backend, item.updated_relative) if part]
    if item.is_current:
        meta_parts.append("current")
    return SearchPickerOption(
        value=item.session_id,
        label=f"{item.index}. {item.label}",
        meta=" · ".join(meta_parts),
    )


def show_tool_report(acp_client: _OrchestratorACPClient | None, query: str | None) -> None:
    """Render tool usage report."""
    if acp_client is None:
        _console.print("[dim]No active agent connection.[/dim]")
        return

    report, pager_mode = acp_client.tool_report(query)
    if pager_mode:
        with _console.pager(styles=False):
            _console.print(report, highlight=False)
        return

    _console.print(report, highlight=False)


def print_restored_messages(rendered_messages: list[str]) -> None:
    """Print resumed transcript from prior session."""
    if not rendered_messages:
        return
    _console.print("[dim]Resumed transcript:[/dim]")
    for line in rendered_messages[-120:]:
        _console.print(line)
    _console.print()
