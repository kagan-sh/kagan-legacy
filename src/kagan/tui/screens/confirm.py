from textual.app import ComposeResult
from textual.containers import Container, Horizontal
from textual.screen import ModalScreen
from textual.widgets import Footer, Static

from kagan.tui.keybindings import CONFIRM_BINDINGS
from kagan.tui.widgets.hint_bar import format_hint


class ConfirmModal(ModalScreen[bool]):
    BINDINGS = CONFIRM_BINDINGS

    def __init__(
        self,
        *,
        title: str,
        message: str,
        detail: str | None = None,
        warning: str | None = None,
        confirm_label: str = "Confirm",
        cancel_label: str = "Cancel",
    ) -> None:
        super().__init__()
        self._title = title
        self._message = message
        self._detail = detail
        self._warning = warning
        self._confirm_label = confirm_label
        self._cancel_label = cancel_label

    def compose(self) -> ComposeResult:
        with Container():
            yield Static(self._title, classes="confirm-title")
            if self._detail is not None:
                yield Static(self._detail, classes="confirm-detail")
            yield Static(self._message, classes="confirm-message")
            if self._warning is not None:
                yield Static(self._warning, classes="confirm-warning")
            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    format_hint(
                        [
                            ("Enter", self._confirm_label.lower()),
                            ("Esc", self._cancel_label.lower()),
                        ]
                    ),
                    classes="modal-action-hint",
                )
        yield Footer(show_command_palette=False)

    def action_confirm(self) -> None:
        self.dismiss(True)

    def action_cancel(self) -> None:
        self.dismiss(False)
