from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Rule, Static, TextArea

from kagan.tui.keybindings import REJECTION_INPUT_BINDINGS
from kagan.tui.widgets.hint_bar import format_hint


class RejectionInputModal(ModalScreen[str | None]):
    BINDINGS = REJECTION_INPUT_BINDINGS
    BACKLOG_SENTINEL = "__kagan_backlog__"

    def __init__(self, *, task_label: str) -> None:
        super().__init__()
        self._task_label = task_label

    def compose(self) -> ComposeResult:
        with Vertical(id="rejection-input-container"):
            yield Static("Send back for rework", classes="modal-title")
            yield Static(self._task_label, classes="task-label")
            yield Rule()
            yield Static(
                "What should change before this task can be approved?",
                classes="prompt-label",
            )
            yield TextArea(id="feedback-input")
            yield Rule()
            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    format_hint(
                        [
                            ("Enter", "back to in progress"),
                            ("Ctrl+S", "submit"),
                            ("Esc", "cancel"),
                        ]
                    ),
                    classes="modal-action-hint",
                )
            with Horizontal(classes="modal-action-row"):
                yield Button("Send to in progress", id="rejection-send", variant="primary")
                yield Button("Send to backlog", id="rejection-backlog")
                yield Button("Cancel", id="rejection-cancel")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self.query_one(TextArea).focus()

    @on(Button.Pressed, "#rejection-send")
    def _on_send_pressed(self) -> None:
        self.action_send_back()

    @on(Button.Pressed, "#rejection-backlog")
    def _on_backlog_pressed(self) -> None:
        self.action_backlog()

    @on(Button.Pressed, "#rejection-cancel")
    def _on_cancel_pressed(self) -> None:
        self.action_cancel()

    def action_send_back(self) -> None:
        feedback = self.query_one(TextArea).text.strip()
        self.dismiss(feedback or "Needs more work")

    def action_backlog(self) -> None:
        feedback = self.query_one(TextArea).text.strip()
        if feedback:
            self.dismiss(f"{self.BACKLOG_SENTINEL}:{feedback}")
            return
        self.dismiss(self.BACKLOG_SENTINEL)

    def action_cancel(self) -> None:
        self.dismiss(None)
