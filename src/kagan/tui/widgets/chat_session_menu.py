"""ChatSessionMenu — session picker / mode badge row of the chat panel.

Subclasses ``Horizontal`` so it 1:1 replaces the previous
``Horizontal(id="chat-overlay-session-switcher")`` container in
``ChatPanel.compose()``. The DOM (id, classes, nested children) is unchanged so
snapshot tests remain byte-identical.

Owns query helpers for the session ``Select`` and the current-session label
``Static``. Session entries, selected key, and orchestrator filtering still
live on ``ChatPanel`` — this widget is just the visible surface those values
render into.
"""

from __future__ import annotations

import contextlib
from typing import Any

from textual.containers import Horizontal
from textual.css.query import NoMatches
from textual.widgets import Select, Static


class ChatSessionMenu(Horizontal):
    """Horizontal container holding the mode badge, session indicator,
    current session label, and the session picker dropdown. Replaces
    ``Horizontal(id="chat-overlay-session-switcher")``.
    """

    DEFAULT_CSS = ""

    # ------- query helpers -------

    def session_selector(self) -> Select[Any] | None:
        try:
            return self.query_one("#chat-overlay-session-select", Select)
        except NoMatches:
            return None

    def current_label_widget(self) -> Static | None:
        try:
            return self.query_one("#chat-overlay-session-current", Static)
        except NoMatches:
            return None

    # ------- mutators -------

    def set_current_label(self, label: str) -> None:
        widget = self.current_label_widget()
        if widget is not None:
            widget.update(label)

    def apply_options(self, options: list[tuple[str, str]], active_key: str) -> None:
        selector = self.session_selector()
        if selector is None:
            return
        set_options = getattr(selector, "set_options", None)
        if callable(set_options):
            set_options(options)
        with contextlib.suppress(Exception):
            selector.value = active_key

    def set_disabled(self, disabled: bool) -> None:
        selector = self.session_selector()
        if selector is not None:
            selector.disabled = disabled
