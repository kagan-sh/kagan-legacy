"""Offline banner widget for agent unavailability."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from textual.binding import Binding, BindingType
from textual.containers import Horizontal
from textual.message import Message
from textual.widgets import Button, Label, Static

if TYPE_CHECKING:
    from textual.app import ComposeResult


class OfflineBanner(Static):
    """Banner shown when agent is unavailable."""

    can_focus = True

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "reconnect", "Reconnect", key_display="Enter", show=False),
        Binding("r", "reconnect", "Reconnect", show=False),
        Binding("escape", "dismiss", "Dismiss", key_display="Esc", show=False),
        Binding("d", "dismiss", "Dismiss", show=False),
    ]

    class Reconnect(Message):
        """User clicked reconnect."""

        pass

    class Dismissed(Message):
        """User dismissed banner."""

        pass

    def __init__(self, message: str | None = None) -> None:
        """Initialize banner content with a default offline message."""
        super().__init__()
        self._message = message or "Agent unavailable"

    def compose(self) -> ComposeResult:
        """Render offline status text with reconnect/dismiss actions."""
        yield Label("⚠️  OFFLINE MODE", id="offline-title")
        yield Label(self._message, id="offline-message")
        with Horizontal(id="offline-actions"):
            yield Button("Reconnect", id="offline-reconnect", variant="primary")
            yield Button("Dismiss", id="offline-dismiss")

    def action_reconnect(self) -> None:
        """Request reconnect from keyboard or button flow."""
        self.post_message(self.Reconnect())

    def action_dismiss(self) -> None:
        """Dismiss banner from keyboard or button flow."""
        self.post_message(self.Dismissed())
        self.remove()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        event.stop()
        if event.button.id == "offline-reconnect":
            self.action_reconnect()
        elif event.button.id == "offline-dismiss":
            self.action_dismiss()
