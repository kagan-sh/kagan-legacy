"""StatusBar widget for displaying agent status and contextual hints."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING

from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class StatusBar(Widget):
    """Status bar showing agent state and contextual hints."""

    status: reactive[str] = reactive("waiting")
    hint: reactive[str] = reactive("Initializing agent...")

    STATUS_INDICATORS = {
        "ready": "●",
        "thinking": "◐",
        "error": "✗",
        "waiting": "○",
        "initializing": "○",  # Same as waiting
    }

    def __init__(self, **kwargs) -> None:
        if "id" not in kwargs:
            kwargs["id"] = "planner-status-bar"
        super().__init__(**kwargs)

    def compose(self) -> ComposeResult:
        yield Static("", classes="status-left")
        yield Static("", classes="status-right")

    def on_mount(self) -> None:
        """Initialize status display on mount."""
        self._update_display()

    def watch_status(self, _status: str) -> None:
        """Update display when status changes."""
        self._update_display()

    def watch_hint(self, _hint: str) -> None:
        """Update display when hint changes."""
        self._update_display()

    def update_status(self, status: str, hint: str = "") -> None:
        """Update status and hint text.

        Args:
            status: Status state ("ready", "thinking", "error", "waiting")
            hint: Optional contextual hint text
        """
        self.status = status
        if hint:
            self.hint = hint

    def _update_display(self) -> None:
        """Update the status bar display."""
        symbol = self.STATUS_INDICATORS.get(self.status, "○")
        status_text = f"{symbol} {self.status.capitalize()}"

        with suppress(NoMatches):
            self.query_one(".status-left", Static).update(status_text)
            self.query_one(".status-right", Static).update(self.hint)
