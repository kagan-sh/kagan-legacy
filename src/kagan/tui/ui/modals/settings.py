"""Settings modal for editing configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, ClassVar

from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, Rule, Select, Static, Switch

from kagan.core.builtin_agents import BUILTIN_AGENTS
from kagan.core.config import (
    DEFAULT_ORCHESTRATOR_PERSONA,
    DEFAULT_PR_REVIEWER_PERSONA,
    DEFAULT_WORKER_PERSONA,
)
from kagan.tui.keybindings import SETTINGS_BINDINGS
from kagan.tui.ui.modals.description_editor import DescriptionEditorModal

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.core.config import (
        DoctorVerbosityLiteral,
        KaganConfig,
        PairTerminalBackendLiteral,
        WorktreeBaseRefStrategyLiteral,
    )


def _normalize_pair_terminal_backend(value: object) -> PairTerminalBackendLiteral:
    match value:
        case "tmux" | "nvim" | "vscode" | "cursor" as backend:
            return backend
        case _:
            return "tmux"


def _normalize_worktree_base_ref_strategy(value: object) -> WorktreeBaseRefStrategyLiteral:
    match value:
        case "remote" | "local_if_ahead" | "local" as strategy:
            return strategy
        case _:
            return "local_if_ahead"


def _normalize_doctor_verbosity(value: object) -> DoctorVerbosityLiteral:
    match value:
        case "tldr" | "short" | "technical" as verbosity:
            return verbosity
        case _:
            return "short"


def _normalize_persona(value: str, *, default: str) -> str:
    cleaned = value.strip()
    return cleaned or default


def _truncate_persona(text: str, max_len: int = 60) -> str:
    """Return a single-line truncation of a persona string for preview."""
    first_line = text.split("\n", 1)[0].strip()
    if len(first_line) > max_len:
        return first_line[: max_len - 1] + "\u2026"
    if "\n" in text:
        return first_line + " \u2026"
    return first_line


class PersonaField(Static, can_focus=True):
    """Focusable preview that opens a fullscreen editor on Enter.

    Shows a truncated single-line preview of the persona text.
    Press Enter to open the full-screen editor; Esc or Ctrl+S in the
    editor returns the edited value.
    """

    BINDINGS: ClassVar[list[BindingType]] = [
        Binding("enter", "open_editor", "Edit", show=False),
    ]

    def __init__(
        self,
        text: str,
        *,
        field_id: str,
        editor_title: str = "Edit Persona",
        default: str = "",
        **kwargs: Any,
    ) -> None:
        super().__init__("", id=field_id, **kwargs)
        self._text = text
        self._editor_title = editor_title
        self._default = default

    @property
    def persona_value(self) -> str:
        return self._text

    def on_mount(self) -> None:
        self._refresh_preview()

    def _refresh_preview(self) -> None:
        display = self._text or self._default
        preview = _truncate_persona(display)
        line_count = display.count("\n") + 1 if display else 0
        suffix = f"  [{line_count}L]" if line_count > 1 else ""
        hint = "  [dim][Enter] edit[/dim]"
        self.update(f"{preview}{suffix}{hint}")

    def action_open_editor(self) -> None:
        self.app.push_screen(
            DescriptionEditorModal(
                description=self._text,
                title=self._editor_title,
            ),
            callback=self._on_editor_dismiss,
        )

    def _on_editor_dismiss(self, result: str | None) -> None:
        if result is not None:
            self._text = result
            self._refresh_preview()


class SettingsModal(ModalScreen[bool]):
    """Modal for editing application settings."""

    BINDINGS = SETTINGS_BINDINGS

    def __init__(self, config: KaganConfig, api: Any, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._api = api
        self._is_saving = False

    def compose(self) -> ComposeResult:
        with Container(id="settings-container"):
            yield Label("Settings", classes="modal-title")

            yield Rule()
            yield Label("Auto Review", classes="section-title")
            with Horizontal(classes="setting-row"):
                yield Switch(
                    value=self._config.general.auto_review,
                    id="auto-review-switch",
                )
                yield Label("Enable auto review", classes="setting-label")

            yield Rule()
            yield Label("Orchestrator Permissions", classes="section-title")
            with Horizontal(classes="setting-row"):
                yield Switch(
                    value=self._config.general.auto_approve,
                    id="auto-approve-switch",
                )
                yield Label(
                    "Auto-approve orchestrator tool calls",
                    classes="setting-label",
                )
            with Horizontal(classes="setting-row"):
                yield Switch(
                    value=self._config.general.auto_skill_discovery,
                    id="auto-skill-discovery-switch",
                )
                yield Label(
                    "Enable local auto skill discovery (trusted metadata only)",
                    classes="setting-label",
                )

            yield Rule()
            yield Label("Merge Policy", classes="section-title")
            with Horizontal(classes="setting-row"):
                yield Switch(
                    value=self._config.general.require_review_approval,
                    id="require-review-approval-switch",
                )
                yield Label("Require approval before merge", classes="setting-label")
            with Horizontal(classes="setting-row"):
                yield Switch(
                    value=self._config.general.serialize_merges,
                    id="serialize-merges-switch",
                )
                yield Label("Serialize manual merges", classes="setting-label")

            yield Rule()
            yield Label("General", classes="section-title")
            with Vertical(classes="input-group"):
                yield Label("Max concurrent agents", classes="input-label")
                yield Input(
                    value=str(self._config.general.max_concurrent_agents),
                    id="max-agents-input",
                    placeholder="3",
                    type="integer",
                )
            with Vertical(classes="input-group"):
                yield Label("Default agent", classes="input-label")
                agent_options: list[tuple[str, str]] = [
                    (agent.config.name, name) for name, agent in BUILTIN_AGENTS.items()
                ]
                yield Select[str](
                    options=agent_options,
                    value=self._config.general.default_worker_agent,
                    id="default-agent-select",
                    allow_blank=False,
                )
            with Vertical(classes="input-group"):
                yield Label("Worker persona", classes="input-label")
                yield PersonaField(
                    self._config.general.worker_persona,
                    field_id="worker-persona-field",
                    editor_title="Edit Worker Persona",
                    default=DEFAULT_WORKER_PERSONA,
                )
            with Vertical(classes="input-group"):
                yield Label("Orchestrator persona", classes="input-label")
                yield PersonaField(
                    self._config.general.orchestrator_persona,
                    field_id="orchestrator-persona-field",
                    editor_title="Edit Orchestrator Persona",
                    default=DEFAULT_ORCHESTRATOR_PERSONA,
                )
            with Vertical(classes="input-group"):
                yield Label("PR reviewer persona", classes="input-label")
                yield PersonaField(
                    self._config.general.pr_reviewer_persona,
                    field_id="pr-reviewer-persona-field",
                    editor_title="Edit PR Reviewer Persona",
                    default=DEFAULT_PR_REVIEWER_PERSONA,
                )
            with Vertical(classes="input-group"):
                yield Label("PAIR terminal", classes="input-label")
                yield Select[str](
                    options=[
                        ("tmux", "tmux"),
                        ("Neovim", "nvim"),
                        ("VS Code", "vscode"),
                        ("Cursor", "cursor"),
                    ],
                    value=self._config.general.default_pair_terminal_backend,
                    id="default-pair-terminal-select",
                    allow_blank=False,
                )
            with Vertical(classes="input-group"):
                yield Label("Worktree base ref", classes="input-label")
                yield Select[str](
                    options=[
                        ("Remote (origin/<base>)", "remote"),
                        ("Local if ahead", "local_if_ahead"),
                        ("Local", "local"),
                    ],
                    value=self._config.general.worktree_base_ref_strategy,
                    id="worktree-base-ref-strategy-select",
                    allow_blank=False,
                )
            with Vertical(classes="input-group"):
                yield Label("Doctor verbosity", classes="input-label")
                yield Select[str](
                    options=[
                        ("TL;DR", "tldr"),
                        ("Short", "short"),
                        ("Technical", "technical"),
                    ],
                    value=self._config.general.doctor_verbosity,
                    id="doctor-verbosity-select",
                    allow_blank=False,
                )
            with Vertical(classes="input-group"):
                yield Label("Interaction verbosity", classes="input-label")
                yield Select[str](
                    options=[
                        ("TL;DR", "tldr"),
                        ("Short", "short"),
                        ("Technical", "technical"),
                    ],
                    value=self._config.general.interaction_verbosity,
                    id="interaction-verbosity-select",
                    allow_blank=False,
                )

            yield Rule()
            yield Label("Model Defaults", classes="section-title")
            with Vertical(classes="input-group"):
                yield Label("Claude", classes="input-label")
                yield Input(
                    value=self._config.general.default_model_claude or "",
                    id="default-model-claude-input",
                    placeholder="sonnet",
                )
            with Vertical(classes="input-group"):
                yield Label("OpenCode", classes="input-label")
                yield Input(
                    value=self._config.general.default_model_opencode or "",
                    id="default-model-opencode-input",
                    placeholder="anthropic/claude-sonnet-4-5",
                )
            with Vertical(classes="input-group"):
                yield Label("Codex", classes="input-label")
                yield Input(
                    value=self._config.general.default_model_codex or "",
                    id="default-model-codex-input",
                    placeholder="gpt-5.2-codex",
                )
            with Vertical(classes="input-group"):
                yield Label("Gemini", classes="input-label")
                yield Input(
                    value=self._config.general.default_model_gemini or "",
                    id="default-model-gemini-input",
                    placeholder="auto | pro | flash | gemini-2.5-flash",
                )
            with Vertical(classes="input-group"):
                yield Label("Kimi", classes="input-label")
                yield Input(
                    value=self._config.general.default_model_kimi or "",
                    id="default-model-kimi-input",
                    placeholder="kimi-k2-turbo-preview",
                )
            with Vertical(classes="input-group"):
                yield Label("Copilot", classes="input-label")
                yield Input(
                    value=self._config.general.default_model_copilot or "",
                    id="default-model-copilot-input",
                    placeholder="Claude Sonnet 4.5 (switch via /model)",
                )

            yield Rule()
            yield Label("UI Preferences", classes="section-title")
            with Horizontal(classes="setting-row"):
                yield Switch(
                    value=self._config.ui.skip_pair_instructions,
                    id="skip-pair-instructions-switch",
                )
                yield Label("Skip PAIR instructions popup", classes="setting-label")
            with Vertical(classes="input-group"):
                yield Label("Theme", classes="input-label")
                theme_options: list[tuple[str, str]] = [
                    ("Auto (Kagan Night)", ""),
                    ("Kagan Night", "kagan"),
                    ("Kagan 256-color", "kagan-256"),
                    ("Dracula", "dracula"),
                    ("Tokyo Night", "tokyo-night"),
                    ("Catppuccin Mocha", "catppuccin-mocha"),
                    ("Catppuccin Latte", "catppuccin-latte"),
                    ("Nord", "nord"),
                    ("Gruvbox", "gruvbox"),
                    ("Monokai", "monokai"),
                    ("Solarized Dark", "solarized-dark"),
                    ("Solarized Light", "solarized-light"),
                    ("Rose Pine", "rose-pine"),
                    ("Rose Pine Moon", "rose-pine-moon"),
                    ("Rose Pine Dawn", "rose-pine-dawn"),
                    ("Atom One Dark", "atom-one-dark"),
                    ("Atom One Light", "atom-one-light"),
                    ("Flexoki", "flexoki"),
                    ("Textual Dark", "textual-dark"),
                    ("Textual Light", "textual-light"),
                    ("Textual ANSI", "textual-ansi"),
                ]
                yield Select[str](
                    options=theme_options,
                    value=self._config.ui.theme or "",
                    id="theme-select",
                    allow_blank=False,
                )

            yield Rule()
            with Horizontal(classes="modal-action-hint-row"):
                yield Label(
                    "Press [bold]Ctrl+S[/bold] to save, [bold]Esc[/bold] to cancel",
                    classes="modal-action-hint",
                    id="settings-action-hint",
                )

        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self.query_one("#auto-review-switch", Switch).focus()

    def _set_action_hint(self, message: str) -> None:
        self.query_one("#settings-action-hint", Label).update(message)

    def action_save(self) -> None:
        """Save settings to config file."""
        if self._is_saving:
            return

        updates = self._collect_updates()
        if updates is None:
            return

        self._is_saving = True
        self._set_action_hint("Saving settings...")
        self.run_worker(
            self._save_updates(updates),
            group="settings-save",
            exclusive=True,
            exit_on_error=False,
        )

    def _collect_updates(self) -> dict[str, object] | None:
        auto_review = self.query_one("#auto-review-switch", Switch).value
        auto_approve = self.query_one("#auto-approve-switch", Switch).value
        auto_skill_discovery = self.query_one("#auto-skill-discovery-switch", Switch).value
        require_review_approval = self.query_one("#require-review-approval-switch", Switch).value
        serialize_merges = self.query_one("#serialize-merges-switch", Switch).value
        skip_pair_instructions = self.query_one("#skip-pair-instructions-switch", Switch).value
        max_agents_str = self.query_one("#max-agents-input", Input).value
        default_agent_select = self.query_one("#default-agent-select", Select)
        default_agent = str(default_agent_select.value) if default_agent_select.value else "claude"
        worker_persona = _normalize_persona(
            self.query_one("#worker-persona-field", PersonaField).persona_value,
            default=DEFAULT_WORKER_PERSONA,
        )
        orchestrator_persona = _normalize_persona(
            self.query_one("#orchestrator-persona-field", PersonaField).persona_value,
            default=DEFAULT_ORCHESTRATOR_PERSONA,
        )
        pr_reviewer_persona = _normalize_persona(
            self.query_one("#pr-reviewer-persona-field", PersonaField).persona_value,
            default=DEFAULT_PR_REVIEWER_PERSONA,
        )
        pair_terminal_select = self.query_one("#default-pair-terminal-select", Select)
        pair_terminal_backend = _normalize_pair_terminal_backend(pair_terminal_select.value)
        base_ref_strategy_select = self.query_one("#worktree-base-ref-strategy-select", Select)
        worktree_base_ref_strategy = _normalize_worktree_base_ref_strategy(
            base_ref_strategy_select.value
        )
        doctor_verbosity_select = self.query_one("#doctor-verbosity-select", Select)
        doctor_verbosity = _normalize_doctor_verbosity(doctor_verbosity_select.value)
        interaction_verbosity_select = self.query_one("#interaction-verbosity-select", Select)
        interaction_verbosity = _normalize_doctor_verbosity(interaction_verbosity_select.value)
        default_model_claude = self.query_one("#default-model-claude-input", Input).value
        default_model_claude = default_model_claude.strip() or None
        default_model_opencode = self.query_one("#default-model-opencode-input", Input).value
        default_model_opencode = default_model_opencode.strip() or None
        default_model_codex = self.query_one("#default-model-codex-input", Input).value
        default_model_codex = default_model_codex.strip() or None
        default_model_gemini = self.query_one("#default-model-gemini-input", Input).value
        default_model_gemini = default_model_gemini.strip() or None
        default_model_kimi = self.query_one("#default-model-kimi-input", Input).value
        default_model_kimi = default_model_kimi.strip() or None
        default_model_copilot = self.query_one("#default-model-copilot-input", Input).value
        default_model_copilot = default_model_copilot.strip() or None

        theme_select = self.query_one("#theme-select", Select)
        theme = str(theme_select.value) if theme_select.value else ""

        try:
            max_agents = int(max_agents_str) if max_agents_str else 3
        except ValueError:
            self.app.notify("Invalid numeric value", severity="error")
            return None

        return {
            "general.auto_review": auto_review,
            "general.auto_approve": auto_approve,
            "general.auto_skill_discovery": auto_skill_discovery,
            "general.require_review_approval": require_review_approval,
            "general.serialize_merges": serialize_merges,
            "general.max_concurrent_agents": max_agents,
            "general.default_worker_agent": default_agent,
            "general.worker_persona": worker_persona,
            "general.orchestrator_persona": orchestrator_persona,
            "general.pr_reviewer_persona": pr_reviewer_persona,
            "general.default_pair_terminal_backend": pair_terminal_backend,
            "general.worktree_base_ref_strategy": worktree_base_ref_strategy,
            "general.doctor_verbosity": doctor_verbosity,
            "general.interaction_verbosity": interaction_verbosity,
            "general.default_model_claude": default_model_claude,
            "general.default_model_opencode": default_model_opencode,
            "general.default_model_codex": default_model_codex,
            "general.default_model_gemini": default_model_gemini,
            "general.default_model_kimi": default_model_kimi,
            "general.default_model_copilot": default_model_copilot,
            "ui.skip_pair_instructions": skip_pair_instructions,
            "ui.theme": theme or None,
        }

    @staticmethod
    def _apply_updates(config: KaganConfig, updates: dict[str, object]) -> None:
        for key, value in updates.items():
            section_name, field_name = key.split(".", 1)
            section = getattr(config, section_name, None)
            if section is None:
                continue
            if hasattr(section, field_name):
                setattr(section, field_name, value)

    async def _save_updates(self, updates: dict[str, object]) -> None:
        try:
            success, message, *_rest = await self._api.update_settings(updates)
        except Exception as exc:
            self.app.notify(f"Failed to save settings: {exc}", severity="error")
            self._is_saving = False
            self._set_action_hint("Press [bold]Ctrl+S[/bold] to save, [bold]Esc[/bold] to cancel")
            return

        if not success:
            self.app.notify(message or "Failed to save settings", severity="error")
            self._is_saving = False
            self._set_action_hint("Press [bold]Ctrl+S[/bold] to save, [bold]Esc[/bold] to cancel")
            return

        self._apply_updates(self._config, updates)

        # Apply theme change live so the user sees it immediately.
        theme_value = updates.get("ui.theme")
        if theme_value and isinstance(theme_value, str):
            if theme_value in self.app.available_themes:
                self.app.theme = theme_value
        elif theme_value is None and "ui.theme" in updates:
            # User chose "Auto" — reset to default detection.
            from kagan.core.terminal import supports_truecolor

            self.app.theme = "kagan" if supports_truecolor() else "kagan-256"

        self.dismiss(True)

    def action_cancel(self) -> None:
        if self._is_saving:
            return
        self.dismiss(False)
