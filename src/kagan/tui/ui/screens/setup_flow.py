"""First-boot onboarding screen for Kagan."""

from __future__ import annotations

import contextlib
from dataclasses import dataclass
from typing import TYPE_CHECKING

from textual.containers import Container, Horizontal, Vertical
from textual.css.query import NoMatches
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Button, Checkbox, Footer, Label, Rule, Select, Static

from kagan.core.builtin_agents import BUILTIN_AGENTS, list_builtin_agents
from kagan.core.config import GeneralConfig, KaganConfig
from kagan.core.constants import KAGAN_LOGO
from kagan.tui.keybindings import ONBOARDING_BINDINGS, get_key_for_action
from kagan.tui.ui.widgets.keybinding_hint import KeybindingHint

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.tui.app import KaganApp


class OnboardingScreen(Screen):
    """First-boot onboarding screen shown when no config exists.

    Collects initial settings:
    - AI Assistant selection (Claude/OpenCode)
    - Auto review toggle

    On submit, creates config.toml and posts message to continue startup.
    Base branch is not collected here; it is determined per-project from
    the actual repository branches when linking a repo.
    """

    BINDINGS = ONBOARDING_BINDINGS

    @dataclass
    class Completed(Message):
        """Message posted when onboarding is complete."""

        config: KaganConfig

    def __init__(self) -> None:
        super().__init__()
        self._selected_agent: str = "claude"
        self._auto_review: bool = True
        self._is_saving: bool = False

    @property
    def kagan_app(self) -> KaganApp:
        """Get the typed KaganApp instance."""
        from kagan.tui.app import KaganApp

        app = self.app
        if not isinstance(app, KaganApp):
            msg = "Kagan app context is unavailable for onboarding."
            raise RuntimeError(msg)
        return app

    def compose(self) -> ComposeResult:
        agent_options = [
            (agent.config.name, agent.config.short_name) for agent in list_builtin_agents()
        ]

        with Container(id="onboarding-container"):
            yield Static(KAGAN_LOGO, id="onboarding-logo")
            yield Label("First-Time Setup", id="onboarding-subtitle")
            yield Rule(id="onboarding-divider")

            with Vertical(id="onboarding-form"):
                yield Label("AI Assistant", classes="form-label")
                yield Select(
                    options=agent_options,
                    value="claude",
                    id="agent-select",
                    allow_blank=False,
                    compact=True,
                )

                with Horizontal(id="auto-review-row"):
                    with Vertical(id="auto-review-info"):
                        yield Checkbox(
                            "Enable auto review",
                            id="auto-review-switch",
                            value=self._auto_review,
                            compact=True,
                            classes="onboarding-auto-review-checkbox",
                        )
                        yield Label(
                            "Automatically run AI review when tasks complete",
                            classes="form-hint",
                        )

            with Horizontal(id="onboarding-actions"):
                yield Button(
                    "Continue to Kagan",
                    id="btn-continue",
                    variant="primary",
                )
            yield Label(
                "Tip: Tab moves between controls. Enter continues.",
                id="onboarding-keyboard-hint",
            )

        yield KeybindingHint(id="onboarding-hint", classes="keybinding-hint")
        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self.call_after_refresh(self._focus_default_action)
        self._update_keybinding_hints()

    def _focus_default_action(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#btn-continue", Button).focus()

    @staticmethod
    def _focusable_selector() -> str:
        return "#agent-select, #auto-review-switch, #btn-continue"

    def _update_keybinding_hints(self) -> None:
        hint_widget = self.query_one("#onboarding-hint", KeybindingHint)
        hint_widget.show_hints(
            [
                (get_key_for_action(ONBOARDING_BINDINGS, "focus_next"), "next"),
                (get_key_for_action(ONBOARDING_BINDINGS, "focus_previous"), "previous"),
                (get_key_for_action(ONBOARDING_BINDINGS, "continue_setup"), "continue"),
                (get_key_for_action(ONBOARDING_BINDINGS, "quit"), "quit"),
            ]
        )

    def action_focus_next(self) -> None:
        self.focus_next(self._focusable_selector())

    def action_focus_previous(self) -> None:
        self.focus_previous(self._focusable_selector())

    def action_continue_setup(self) -> None:
        if self._is_saving:
            return
        self._is_saving = True
        with contextlib.suppress(NoMatches):
            self.query_one("#btn-continue", Button).disabled = True
        self.run_worker(
            self._save_and_continue(),
            group="onboarding-save",
            exclusive=True,
            exit_on_error=False,
        )

    def on_select_changed(self, event: Select.Changed) -> None:
        """Handle dropdown selection changes."""
        if event.select.id == "agent-select" and event.value is not None:
            self._selected_agent = str(event.value)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        """Handle auto review checkbox changes."""
        if event.checkbox.id == "auto-review-switch":
            self._auto_review = event.value

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "btn-continue":
            self.action_continue_setup()

    async def _save_and_continue(self) -> None:
        """Save configuration and signal completion."""
        try:
            config = KaganConfig(
                general=GeneralConfig(
                    default_worker_agent=self._selected_agent,
                    auto_review=self._auto_review,
                ),
                agents={name: agent.config for name, agent in BUILTIN_AGENTS.items()},
            )

            config_path = self.kagan_app.config_path
            config_path.parent.mkdir(parents=True, exist_ok=True)
            await config.save(config_path)

            self.app.notify("Configuration saved!", severity="information")
            self.app.post_message(self.Completed(config=config))
        finally:
            self._is_saving = False
            with contextlib.suppress(NoMatches):
                self.query_one("#btn-continue", Button).disabled = False

    def action_quit(self) -> None:
        """Quit the application."""
        self.app.exit()
