from dataclasses import dataclass
from typing import TYPE_CHECKING, Literal

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.reactive import var
from textual.widgets import Static

if TYPE_CHECKING:
    from textual.timer import Timer


class PermissionPrompt(Vertical):
    @dataclass
    class DecisionMade(Message):
        decision: Literal["allow", "deny", "timeout"]

    remaining_seconds: var[int] = var(0)

    BINDINGS = [
        Binding("a", "allow", "Allow"),
        Binding("d", "deny", "Deny"),
        Binding("escape", "deny", "Deny"),
    ]

    def __init__(
        self,
        text: str = "Permission required",
        *,
        timeout_seconds: int = 30,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        merged_classes = "permission-prompt chat-permission-prompt"
        if classes:
            merged_classes = f"{classes} {merged_classes}"
        super().__init__(id=id, classes=merged_classes)
        self._text = text
        self._timeout_seconds = max(timeout_seconds, 0)
        self._timer: Timer | None = None
        self._resolved = False

    def compose(self) -> ComposeResult:
        yield Static("⚠ Permission required", classes="permission-header")
        yield Static(self._text, id="permission-text", classes="permission-tool")
        yield Static("[a] allow once  ·  [d] deny", classes="permission-controls")
        yield Static("", id="permission-countdown", classes="permission-timer")

    def on_mount(self) -> None:
        self.remaining_seconds = self._timeout_seconds
        self._refresh_countdown()
        if self.remaining_seconds > 0:
            self._timer = self.set_interval(1, self._tick)

    def on_unmount(self) -> None:
        if self._timer is not None:
            self._timer.stop()
            self._timer = None

    def watch_remaining_seconds(self) -> None:
        self._refresh_countdown()

    def action_allow(self) -> None:
        self._resolve("allow")

    def action_deny(self) -> None:
        self._resolve("deny")

    def _tick(self) -> None:
        if self._resolved:
            return
        if self.remaining_seconds <= 0:
            self._resolve("timeout")
            return
        self.remaining_seconds -= 1
        if self.remaining_seconds == 0:
            self._resolve("timeout")

    def _refresh_countdown(self) -> None:
        countdown = self.query_one("#permission-countdown", Static)
        if self.remaining_seconds > 0:
            countdown.update(f"Auto-deny in {self.remaining_seconds}s")
        else:
            countdown.update("Awaiting decision")

    def _resolve(self, decision: Literal["allow", "deny", "timeout"]) -> None:
        if self._resolved:
            return
        self._resolved = True
        if self._timer is not None:
            self._timer.stop()
            self._timer = None
        self.post_message(self.DecisionMade(decision=decision))
