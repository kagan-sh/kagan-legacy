"""Slash command autocomplete widget for orchestrator input."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import VerticalGroup
from textual.css.query import NoMatches
from textual.message import Message
from textual.reactive import var
from textual.widgets import OptionList
from textual.widgets.option_list import Option

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.tui.ui.utils.slash_registry import SlashCommand


class SlashComplete(VerticalGroup):
    """Autocomplete dropdown for slash commands - just shows options."""

    DEFAULT_CLASSES = "slash-complete"
    _DEFAULT_VISIBLE_ROWS = 6

    BINDINGS = [
        Binding("escape", "dismiss", "Dismiss", show=False),
        Binding("pageup", "page_up", "Page Up", show=False),
        Binding("pagedown", "page_down", "Page Down", show=False),
        Binding("home", "first", "First", show=False),
        Binding("end", "last", "Last", show=False),
        Binding("up", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("enter", "select", "Select", show=False),
    ]

    slash_commands: var[list[SlashCommand]] = var(list, init=False)
    slash_query: var[str] = var("", init=False)

    @dataclass
    class Completed(Message):
        """Posted when user selects a command."""

        command: str

    @dataclass
    class Dismissed(Message):
        """Posted when user presses Escape."""

        pass

    def __init__(
        self,
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        """Initialize slash autocomplete widget state."""
        super().__init__(id=id, classes=classes)
        self._commands_list: list[SlashCommand] = []

    def compose(self) -> ComposeResult:
        """Render the slash options list container."""
        yield OptionList(id="slash-options")

    def on_mount(self) -> None:
        """Populate options on mount."""
        self._rebuild_options()

    def watch_slash_commands(self) -> None:
        """Rebuild options when commands change."""
        if not self.is_mounted:
            return
        self._rebuild_options()

    def watch_slash_query(self) -> None:
        """Rebuild options when query changes."""
        if not self.is_mounted:
            return
        self._rebuild_options()

    def _rebuild_options(self) -> None:
        """Build the options list from commands."""
        try:
            option_list = self.query_one("#slash-options", OptionList)
        except NoMatches:
            return
        option_list.clear_options()
        self._commands_list = [
            command
            for command in self.slash_commands
            if self._matches_query(command, self.slash_query)
        ]

        for cmd in self._commands_list:
            option_text = f"/{cmd.command}  {cmd.help}"
            option_list.add_option(Option(option_text, id=cmd.command))

        option_list.styles.height = self._DEFAULT_VISIBLE_ROWS
        option_list.styles.min_height = self._DEFAULT_VISIBLE_ROWS
        option_list.styles.max_height = self._DEFAULT_VISIBLE_ROWS

        if self._commands_list:
            option_list.highlighted = 0

    @staticmethod
    def _matches_query(command: SlashCommand, query: str) -> bool:
        normalized_query = query.strip().casefold()
        if not normalized_query:
            return True
        if command.command.casefold().startswith(normalized_query):
            return True
        return any(alias.casefold().startswith(normalized_query) for alias in command.aliases)

    def _safe_navigate(self, action: str) -> None:
        try:
            option_list = self.query_one("#slash-options", OptionList)
        except NoMatches:
            return
        try:
            getattr(option_list, action)()
        except KeyError:
            if action in {"action_cursor_up", "action_page_up", "action_first"}:
                option_list.action_first()
            else:
                option_list.action_last()

    def action_page_up(self) -> None:
        """Page highlight up."""
        self._safe_navigate("action_page_up")

    def action_page_down(self) -> None:
        """Page highlight down."""
        self._safe_navigate("action_page_down")

    def action_first(self) -> None:
        """Move highlight to first option."""
        self._safe_navigate("action_first")

    def action_last(self) -> None:
        """Move highlight to last option."""
        self._safe_navigate("action_last")

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        self._safe_navigate("action_cursor_up")

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        self._safe_navigate("action_cursor_down")

    def action_select(self) -> None:
        """Select the highlighted option."""
        option_list = self.query_one("#slash-options", OptionList)
        if option_list.highlighted is not None:
            idx = option_list.highlighted
            if 0 <= idx < len(self._commands_list):
                cmd = self._commands_list[idx]
                self.post_message(self.Completed(command=cmd.command))

    def action_dismiss(self) -> None:
        self.post_message(self.Dismissed())
