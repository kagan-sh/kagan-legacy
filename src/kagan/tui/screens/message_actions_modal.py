from textual.app import ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from kagan.tui.keybindings import MESSAGE_ACTIONS_BINDINGS
from kagan.tui.widgets.hint_bar import format_hint


class MessageActionsModal(ModalScreen[str | None]):
    """Modal for user message actions: copy text or go back."""

    BINDINGS = MESSAGE_ACTIONS_BINDINGS

    def __init__(
        self,
        message_text: str,
        *,
        title: str = "Message Actions",
    ) -> None:
        super().__init__(id="message-actions-modal")
        self._message_text = message_text
        self._title = title

    def compose(self) -> ComposeResult:
        with Container(id="message-actions-container"):
            yield Static(self._title, classes="modal-title")
            with Vertical(id="message-actions-content"):
                yield OptionList(
                    Option("Copy", id="copy"),
                    Option("Back", id="back"),
                    id="message-actions-options",
                )
            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    format_hint(
                        [
                            ("Enter", "select"),
                            ("Esc", "cancel"),
                        ]
                    ),
                    classes="modal-action-hint",
                )
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self.query_one("#message-actions-options", OptionList).focus()

    def action_select(self) -> None:
        option_list = self.query_one("#message-actions-options", OptionList)
        highlighted = option_list.highlighted
        if highlighted is None:
            highlighted = 0

        options = ["copy", "back"]
        if highlighted < 0 or highlighted >= len(options):
            self.dismiss(None)
            return

        selected = options[highlighted]
        if selected == "copy":
            self.app.copy_to_clipboard(self._message_text)
            self.app.notify("Copied to clipboard", severity="information")
        self.dismiss(selected)

    def action_cancel(self) -> None:
        self.dismiss(None)
