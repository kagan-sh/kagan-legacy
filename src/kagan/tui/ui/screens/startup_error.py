"""Startup recovery screen for TUI initialization failures."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import Button, Footer, Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


StartupAction = Callable[[], Awaitable[None] | None]


class StartupErrorScreen(Screen):
    """Render startup failure details and recovery actions."""

    BINDINGS = [
        Binding("r,enter", "retry_startup", "Retry"),
        Binding("shift+r", "restart_core_retry", "Restart Core + Retry"),
        Binding("q,escape", "quit_app", "Quit"),
    ]

    def __init__(
        self,
        *,
        error_message: str,
        on_retry: StartupAction,
        on_restart_core_retry: StartupAction,
        on_quit: StartupAction | None = None,
    ) -> None:
        super().__init__()
        self._error_message = self._normalize_error_message(error_message)
        self._on_retry = on_retry
        self._on_restart_core_retry = on_restart_core_retry
        self._on_quit = on_quit

    @staticmethod
    def _normalize_error_message(message: str) -> str:
        text = message.strip()
        return text if text else "Unknown startup error"

    def compose(self) -> ComposeResult:
        with Container(id="startup-error-container"):
            yield Label("Startup Failed", id="startup-error-title")
            yield Static(
                "Retry startup keeps the current runtime. "
                "Restart core + retry stops the core runtime first.",
                id="startup-error-guidance",
            )
            with Vertical(id="startup-error-details"):
                yield Label("Current error:", id="startup-error-label")
                yield Static(self._error_message, id="startup-error-message")
            with Horizontal(id="startup-error-actions"):
                yield Button("Retry startup", id="startup-error-retry", variant="primary")
                yield Button("Restart core + retry", id="startup-error-restart")
                yield Button("Quit", id="startup-error-quit", variant="error")

        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self.query_one("#startup-error-retry", Button).focus()

    def set_error_message(self, message: str) -> None:
        self._error_message = self._normalize_error_message(message)
        if self.is_mounted:
            self.query_one("#startup-error-message", Static).update(self._error_message)

    def _invoke_action(self, callback: StartupAction | None) -> None:
        if callback is None:
            return

        try:
            result = callback()
        except Exception as exc:
            self.app.log("Startup recovery action failed", error=str(exc))
            self.app.notify(
                f"Startup recovery action failed: {exc}",
                severity="error",
                timeout=10,
            )
            return

        if inspect.isawaitable(result):
            self.run_worker(
                self._run_async_action(result),
                group="startup-error-action",
                exclusive=True,
                exit_on_error=False,
            )

    async def _run_async_action(self, action: Awaitable[None]) -> None:
        try:
            await action
        except Exception as exc:
            self.app.log("Startup recovery action failed", error=str(exc))
            self.app.notify(
                f"Startup recovery action failed: {exc}",
                severity="error",
                timeout=10,
            )

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "startup-error-retry":
            self.action_retry_startup()
        elif event.button.id == "startup-error-restart":
            self.action_restart_core_retry()
        elif event.button.id == "startup-error-quit":
            self.action_quit_app()

    def action_retry_startup(self) -> None:
        self._invoke_action(self._on_retry)

    def action_restart_core_retry(self) -> None:
        self._invoke_action(self._on_restart_core_retry)

    def action_quit_app(self) -> None:
        if self._on_quit is None:
            self.app.exit()
            return
        self._invoke_action(self._on_quit)
