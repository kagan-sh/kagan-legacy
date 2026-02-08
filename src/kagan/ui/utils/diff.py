"""Shared diff colorization utilities."""

from __future__ import annotations

from rich.markup import escape


def colorize_diff_line(line: str) -> str:
    """Colorize a single diff line with Rich markup."""
    escaped = escape(line)
    if line.startswith("+") and not line.startswith("+++"):
        return f"[green]{escaped}[/green]"
    if line.startswith("-") and not line.startswith("---"):
        return f"[red]{escaped}[/red]"
    if line.startswith("@@"):
        return f"[cyan]{escaped}[/cyan]"
    return escaped


def colorize_diff(content: str) -> str:
    """Colorize a full diff string with Rich markup."""
    return "\n".join(colorize_diff_line(line) for line in content.split("\n"))
