from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, OptionList, Static
from textual.widgets.option_list import Option

from kagan.cli.chat import list_registered_agent_backends, resolve_default_agent_backend
from kagan.core import list_available_backends, list_backend_specs
from kagan.tui.keybindings import AGENT_PICKER_BINDINGS

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp

# Backends shown in the default (compact) view
_PROMINENT_BACKENDS: frozenset[str] = frozenset({"claude-code", "codex"})


class AgentPickerModal(ModalScreen[str | None]):
    BINDINGS = AGENT_PICKER_BINDINGS

    _BACKEND_ALIASES = {
        "gemini": "gemini-cli",
        "kimi": "kimi-cli",
    }

    def __init__(self) -> None:
        super().__init__(id="agent-picker-modal")
        self._agents: list[str] = []
        self._current_agent = resolve_default_agent_backend({})
        self._separator_index: int | None = None
        # When True all backends are shown; default is prominent-only
        self._show_all: bool = False

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        with Container(id="agent-picker-container"):
            yield Static("Switch Global Agent", classes="modal-title")
            yield Static(
                "Select the default agent for orchestrator chat and managed task runs.",
                id="agent-picker-description",
            )
            with Vertical(id="agent-picker-body"):
                yield OptionList(id="agent-picker-options")
            yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        settings = await self.kagan_app.core.settings.get()
        configured = settings.get("default_agent_backend")
        normalized_configured = self._BACKEND_ALIASES.get(configured or "", configured)
        self._current_agent = normalized_configured or resolve_default_agent_backend(settings)

        await self._rebuild_list()

    async def _rebuild_list(self) -> None:
        all_registered = sorted({self._current_agent, *list_registered_agent_backends()})
        availability = list_available_backends()
        specs = list_backend_specs()

        # Filter by prominence unless show-all is active.
        # Always include the current agent regardless of the filter.
        if self._show_all:
            visible = all_registered
        else:
            visible = [
                a for a in all_registered if a in _PROMINENT_BACKENDS or a == self._current_agent
            ]

        available = [a for a in visible if availability.get(a, True)]
        unavailable = [a for a in visible if not availability.get(a, True)]
        self._agents = available + unavailable

        option_list = self.query_one("#agent-picker-options", OptionList)
        option_list.clear_options()

        for agent in available:
            spec = specs.get(agent)
            label = _format_agent_label(
                spec.label() if spec is not None else agent,
                is_current=agent == self._current_agent,
                available=True,
                reference=spec.reference if spec is not None else False,
            )
            option_list.add_option(Option(label, id=agent))

        if unavailable:
            self._separator_index = len(available)
            option_list.add_option(Option("[dim]── Not installed ──[/dim]", disabled=True))
            for agent in unavailable:
                spec = specs.get(agent)
                label = _format_agent_label(
                    spec.label() if spec is not None else agent,
                    is_current=agent == self._current_agent,
                    available=False,
                    reference=spec.reference if spec is not None else False,
                )
                option_list.add_option(Option(label, id=agent))
        else:
            self._separator_index = None

        if not self._show_all:
            hidden_count = len(all_registered) - len(visible)
            if hidden_count > 0:
                noun = "backend" if hidden_count == 1 else "backends"
                hint = (
                    f"[dim]── {hidden_count} more {noun}"
                    f" — press [bold]a[/bold] to show all ──[/dim]"
                )
                option_list.add_option(Option(hint, disabled=True))

        option_list.focus()

        # Restore highlight to current agent
        selected_index = 0
        for index, agent in enumerate(self._agents):
            if agent == self._current_agent:
                after_sep = self._separator_index is not None and index >= self._separator_index
                selected_index = index + 1 if after_sep else index
                break
        option_list.highlighted = selected_index

    async def action_toggle_all_backends(self) -> None:
        self._show_all = not self._show_all
        await self._rebuild_list()

    async def action_select_agent(self) -> None:
        option_list = self.query_one("#agent-picker-options", OptionList)
        index = option_list.highlighted
        if index is None or index < 0:
            self.dismiss(None)
            return

        if self._separator_index is not None and index == self._separator_index:
            return

        after_sep = self._separator_index is not None and index > self._separator_index
        agent_index = index - 1 if after_sep else index
        if agent_index >= len(self._agents):
            self.dismiss(None)
            return

        selected = self._agents[agent_index]
        await self.kagan_app.core.settings.set(
            {
                "default_agent_backend": selected,
            }
        )
        self.app.notify(f"Default agent set to {selected}", severity="information")
        self.dismiss(selected)

    @on(OptionList.OptionSelected, "#agent-picker-options")
    async def _on_option_selected(self, _: OptionList.OptionSelected) -> None:
        await self.action_select_agent()

    async def action_dismiss(self, result: str | None = None) -> None:
        self.dismiss(result)


def _format_agent_label(
    label: str,
    *,
    is_current: bool,
    available: bool,
    reference: bool,
) -> str:
    suffixes: list[str] = []
    if reference:
        suffixes.append("reference")
    if is_current:
        suffixes.append("current")
    if not available:
        suffixes.append("unavailable")

    if suffixes:
        label = f"{label} ({', '.join(suffixes)})"
    if not available:
        label = f"[dim]{label}[/dim]"
    return label
