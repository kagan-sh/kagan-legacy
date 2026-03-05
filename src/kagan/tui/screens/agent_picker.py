from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import OptionList, Static
from textual.widgets.option_list import Option

from kagan.chat import list_registered_agent_backends

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp


class AgentPickerModal(ModalScreen[str | None]):
    BINDINGS = [
        Binding("enter", "select_agent", "Select", show=False, priority=True),
        Binding("escape", "dismiss", "Close"),
    ]

    _BACKEND_ALIASES = {
        "gemini": "gemini-cli",
        "kimi": "kimi-cli",
    }

    def __init__(self) -> None:
        super().__init__(id="agent-picker-modal")
        self._agents: list[str] = []
        self._current_agent = "claude-code"

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        with Container(id="agent-picker-container"):
            yield Static("Switch Global Agent", classes="modal-title")
            yield Static(
                "Select the default agent for new orchestrator and AUTO runs.",
                id="agent-picker-description",
            )
            with Vertical(id="agent-picker-body"):
                yield OptionList(id="agent-picker-options")
            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    "Enter select agent  Esc cancel",
                    id="agent-picker-footer-hint",
                    classes="modal-action-hint",
                )

    async def on_mount(self) -> None:
        settings = await self.kagan_app.core.settings.get()
        configured = settings.get("default_agent_backend") or settings.get("default_agent")
        normalized_configured = self._BACKEND_ALIASES.get(configured or "", configured)
        self._current_agent = normalized_configured or "claude-code"

        options = {self._current_agent, *list_registered_agent_backends()}
        self._agents = sorted(options)

        option_list = self.query_one("#agent-picker-options", OptionList)
        option_list.clear_options()
        option_list.add_options(
            [
                Option(
                    f"{agent}{' (current)' if agent == self._current_agent else ''}",
                    id=agent,
                )
                for agent in self._agents
            ]
        )
        option_list.focus()

        selected_index = 0
        for index, agent in enumerate(self._agents):
            if agent == self._current_agent:
                selected_index = index
                break
        option_list.highlighted = selected_index

    async def action_select_agent(self) -> None:
        option_list = self.query_one("#agent-picker-options", OptionList)
        index = option_list.highlighted
        if index is None or index < 0 or index >= len(self._agents):
            self.dismiss(None)
            return

        selected = self._agents[index]
        await self.kagan_app.core.settings.set(
            {
                "default_agent_backend": selected,
                "default_agent": selected,
            }
        )
        self.app.notify(f"Default agent set to {selected}", severity="information")
        self.dismiss(selected)

    @on(OptionList.OptionSelected, "#agent-picker-options")
    async def _on_option_selected(self, _: OptionList.OptionSelected) -> None:
        await self.action_select_agent()

    async def action_dismiss(self, result: str | None = None) -> None:
        self.dismiss(result)
