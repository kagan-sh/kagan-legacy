"""ChatInput — command-line row of the chat panel.

Subclasses ``Horizontal`` so it 1:1 replaces the previous
``Horizontal(id="chat-overlay-command-line", classes="chat-input-row chat-command-line")``
container in ``ChatPanel.compose()``. The DOM (id, classes, nested children) is
unchanged so snapshot tests remain byte-identical.

Owns the input widget query helpers and is the natural home for the prompt
input itself. The slash and mention completion overlay siblings remain in
``ChatPanel.compose()`` (moving them would change the DOM); they are queried
through the parent ``ChatPanel`` when the input is being read or written.
"""

from __future__ import annotations

from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.widgets import Input


class ChatInput(Horizontal):
    """Horizontal container holding the input shell, the in-input session
    badge, and the input wrapper. Replaces
    ``Horizontal(id="chat-overlay-command-line", classes="chat-input-row chat-command-line")``.
    """

    DEFAULT_CSS = ""

    # ------- query helpers -------

    def input_widget(self) -> Input:
        return self.query_one("#chat-overlay-input", Input)

    def input_widget_safe(self) -> Input | None:
        try:
            return self.input_widget()
        except NoMatches:
            return None

    # ------- value helpers -------

    @property
    def value(self) -> str:
        widget = self.input_widget_safe()
        return widget.value if widget is not None else ""

    @value.setter
    def value(self, text: str) -> None:
        widget = self.input_widget_safe()
        if widget is None:
            return
        widget.value = text

    def has_focus(self) -> bool:
        widget = self.input_widget_safe()
        return bool(widget and widget.has_focus)

    def focus_input(self) -> None:
        widget = self.input_widget_safe()
        if widget is not None:
            widget.focus()

    def insert_text_at_cursor(self, text: str) -> None:
        widget = self.input_widget_safe()
        if widget is None:
            return
        widget.insert_text_at_cursor(text)
