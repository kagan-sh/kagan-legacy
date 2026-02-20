"""Terminal installation modal for PAIR backends."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Label, LoadingIndicator, Static

from kagan.tui.terminals.installer import get_manual_install_fallback

if TYPE_CHECKING:
    from textual.app import ComposeResult


class TerminalInstallModal(ModalScreen[bool]):
    """Prompt user to install terminal backend.

    Returns:
        True when install succeeds, False otherwise.
    """

    BINDINGS = [("enter", "install", "Install"), ("escape", "cancel", "Cancel")]

    def __init__(self, backend: str = "tmux") -> None:
        super().__init__()
        self._backend = backend
        self._installing = False

    def compose(self) -> ComposeResult:
        title = "Install tmux" if self._backend == "tmux" else "Install Terminal"
        fallback = get_manual_install_fallback(self._backend)

        with Container(id="terminal-install-container"):
            yield Label(title, classes="modal-title")
            yield Static(
                "PAIR session requires this terminal backend before opening the session.",
                id="terminal-install-description",
            )
            yield Static(fallback, id="terminal-install-fallback")
            yield LoadingIndicator(id="terminal-install-spinner")
            yield Static("", id="terminal-install-status")

            with Horizontal(classes="modal-action-hint-row"):
                yield Label(
                    "Press [bold]Enter[/bold] to install, [bold]Esc[/bold] to cancel",
                    classes="modal-action-hint",
                    id="terminal-install-action-hint",
                )

    def on_mount(self) -> None:
        self.query_one("#terminal-install-spinner", LoadingIndicator).display = False
        self.query_one("#terminal-install-status", Static).display = False

    def _set_action_hint(self, message: str) -> None:
        self.query_one("#terminal-install-action-hint", Label).update(message)

    def _do_install(self) -> None:
        if self._installing:
            return

        self._installing = True
        self._set_action_hint("Installing terminal backend...")
        self.query_one("#terminal-install-spinner", LoadingIndicator).display = True
        status = self.query_one("#terminal-install-status", Static)
        status.update("Installing...")
        status.display = True
        self.run_worker(self._run_install(), group="terminal-install")

    async def _run_install(self) -> None:
        from kagan.tui.terminals.installer import install_terminal

        success, message = await install_terminal(self._backend)

        self.query_one("#terminal-install-spinner", LoadingIndicator).display = False
        status = self.query_one("#terminal-install-status", Static)

        if success:
            status.update(f"[green]{message}[/green]")
            await asyncio.sleep(1.2)
            self.dismiss(True)
            return

        status.update(f"[red]{message}[/red]")
        self._set_action_hint("Press [bold]Enter[/bold] to retry, [bold]Esc[/bold] to cancel")
        self._installing = False

    def action_install(self) -> None:
        self._do_install()

    def action_cancel(self) -> None:
        if not self._installing:
            self.dismiss(False)
