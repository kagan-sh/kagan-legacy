"""Yolo-mode disclaimer prompt — explicit acknowledgement gate."""

import sys
from typing import Any

_DISCLAIMER_TITLE = "[bold red]:warning:  YOLO MODE :warning:[/bold red]"
_DISCLAIMER_BODY = (
    "You are about to start the chat with [bold]--yolo[/bold] enabled.\n\n"
    "Every tool call requested by the agent will be [bold red]auto-approved "
    "without prompting[/bold red]. This includes:\n"
    "  • Editing or deleting files\n"
    "  • Running shell commands\n"
    "  • Making network requests\n"
    "  • Calling MCP tools and external integrations\n\n"
    "Use this only inside disposable sandboxes or worktrees you trust the\n"
    "agent to operate on unattended. You assume full responsibility for any\n"
    "destructive actions taken on your behalf."
)
_ACK_PHRASE = "I ACCEPT"


def confirm_yolo_disclaimer(console: Any) -> bool:
    """Display the yolo disclaimer and require an explicit typed acknowledgement.

    Returns True only when the user types the acknowledgement phrase exactly.
    Aborts (returns False) on EOF, Ctrl+C, non-interactive stdio, or any other
    response.
    """
    console.print()
    console.print(_DISCLAIMER_TITLE)
    console.print(_DISCLAIMER_BODY)
    console.print()

    if not (sys.stdin.isatty() and sys.stdout.isatty()):
        console.print(
            "[yellow]--yolo requires an interactive terminal for "
            "acknowledgement; aborting.[/yellow]"
        )
        return False

    console.print(
        f"[bold]Type [red]{_ACK_PHRASE}[/red] to continue, anything else to abort:[/bold]"
    )
    try:
        answer = input("> ").strip()
    except (EOFError, KeyboardInterrupt):
        console.print("[yellow]Yolo mode declined.[/yellow]")
        return False

    if answer != _ACK_PHRASE:
        console.print("[yellow]Yolo mode declined.[/yellow]")
        return False

    console.print("[bold red]Yolo mode active — all tool calls will be auto-approved.[/bold red]")
    console.print()
    return True
