"""Modal for switching the default global agent."""

from __future__ import annotations

from typing import TYPE_CHECKING

from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Label, OptionList, Static
from textual.widgets.option_list import Option

from kagan.core.builtin_agents import AGENT_PRIORITY, BUILTIN_AGENTS

if TYPE_CHECKING:
    from textual.app import ComposeResult


class GlobalAgentPickerModal(ModalScreen[str | None]):
    """Pick the default global agent used by orchestrator and AUTO tasks."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
    ]

    def __init__(self, current_agent: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._current_agent = current_agent

    def compose(self) -> ComposeResult:
        with Container(id="agent-picker-container"):
            yield Label("Switch Global Agent", classes="modal-title")
            yield Static(
                "Select the default agent for new orchestrator and AUTO runs.",
                id="agent-picker-description",
            )

            options = []
            for short_name in AGENT_PRIORITY:
                builtin = BUILTIN_AGENTS.get(short_name)
                if builtin is None:
                    continue
                suffix = " (current)" if short_name == self._current_agent else ""
                options.append(Option(f"{builtin.config.name}{suffix}", id=short_name))

            with Vertical(id="agent-picker-body"):
                yield OptionList(*options, id="agent-picker-options")

            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    "Enter select agent  |  Esc cancel",
                    classes="modal-action-hint",
                )

    def on_mount(self) -> None:
        """Focus option list and highlight current selection."""
        option_list = self.query_one("#agent-picker-options", OptionList)
        option_list.focus()
        for idx, option in enumerate(option_list.options):
            if option.id == self._current_agent:
                option_list.highlighted = idx
                break

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        """Apply the selected agent."""
        if event.option.id:
            self.dismiss(event.option.id)

    def action_cancel(self) -> None:
        self.dismiss(None)
