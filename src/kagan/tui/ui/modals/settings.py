"""Settings modal for editing configuration."""

from __future__ import annotations

from contextlib import suppress
from typing import TYPE_CHECKING, Any, ClassVar

from textual import on
from textual.binding import Binding, BindingType
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Checkbox, Footer, Input, Label, OptionList, Select, Static
from textual.widgets.option_list import Option

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


def _multiline_persona_preview(
    text: str,
    *,
    max_lines: int = 3,
    max_line_chars: int = 96,
) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if not lines:
        return "(empty)"

    preview: list[str] = []
    for raw_line in lines[:max_lines]:
        line = raw_line
        if len(line) > max_line_chars:
            line = line[: max_line_chars - 1].rstrip() + "\u2026"
        preview.append(line)

    hidden_lines = len(lines) - len(preview)
    if hidden_lines > 0:
        preview.append(f"\u2026 (+{hidden_lines} more lines)")
    return "\n".join(preview)


class PersonaField(Static, can_focus=True):
    """Focusable preview that opens a fullscreen editor on Enter.

    Shows a concise multi-line preview of the persona text.
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
        preview = _multiline_persona_preview(display)
        line_count = display.count("\n") + 1 if display else 0
        summary = f"[dim]{line_count} line(s) · [Enter] edit[/dim]"
        self.update(f"{preview}\n{summary}")

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

    SECTION_DEFINITIONS: ClassVar[tuple[tuple[str, str], ...]] = (
        ("section-general", "General"),
        ("section-auto-review", "Automation"),
        ("section-orchestrator", "Orchestrator"),
        ("section-merge-policy", "Merge Policy"),
        ("section-model-defaults", "Model Defaults"),
        ("section-ui-preferences", "UI Preferences"),
    )
    DEFAULT_ACTION_HINT: ClassVar[str] = "[bold]Ctrl+S[/bold] save  |  [bold]Esc[/bold] cancel"

    BINDINGS = [
        *SETTINGS_BINDINGS,
        Binding("ctrl+f", "focus_search", "Search", show=False),
        Binding("/", "focus_search", "Search", show=False),
    ]

    def __init__(self, config: KaganConfig, api: Any, **kwargs) -> None:
        super().__init__(**kwargs)
        self._config = config
        self._api = api
        self._is_saving = False
        self._active_section_id = "section-general"
        self._search_query = ""
        self._rebuilding_nav = False

    @staticmethod
    def _search_name(label: str, search_text: str = "") -> str:
        return f"{label} {search_text}".strip().lower()

    @staticmethod
    def _section_item_class(section_id: str) -> str:
        return f"settings-item-{section_id}"

    @staticmethod
    def _empty_label_id(section_id: str) -> str:
        return f"settings-empty-{section_id}"

    def _compose_switch_row(
        self,
        *,
        section_id: str,
        switch_id: str,
        value: bool,
        label: str,
        search_text: str = "",
    ) -> ComposeResult:
        yield Checkbox(
            label,
            value=value,
            compact=True,
            id=switch_id,
            classes=f"setting-row settings-item {self._section_item_class(section_id)}",
            name=self._search_name(label, search_text),
        )

    def _compose_input_group(
        self,
        *,
        section_id: str,
        label: str,
        widget: Any,
        search_text: str = "",
        classes: str = "input-group",
    ) -> ComposeResult:
        with Vertical(
            classes=f"{classes} settings-item {self._section_item_class(section_id)}",
            name=self._search_name(label, search_text),
        ):
            yield Label(label, classes="input-label")
            yield widget

    def compose(self) -> ComposeResult:
        agent_options: list[tuple[str, str]] = [
            (agent.config.name, name) for name, agent in BUILTIN_AGENTS.items()
        ]
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

        with Container(id="settings-container"):
            yield Label("Settings", classes="modal-title")
            yield Input(id="settings-search", placeholder="Search settings...")
            yield Static("", id="settings-search-status", classes="settings-search-status")

            with Horizontal(id="settings-workspace"):
                with Vertical(id="settings-nav-pane"):
                    yield Label("Sections", classes="settings-nav-title")
                    yield OptionList(
                        *(
                            Option(title, id=section_id)
                            for section_id, title in self.SECTION_DEFINITIONS
                        ),
                        id="settings-nav",
                    )

                with VerticalScroll(id="settings-sections"):
                    with Vertical(classes="settings-section settings-pane", id="section-general"):
                        yield Label("General", classes="settings-pane-title")
                        yield Static(
                            "No matching settings in this section.",
                            id=self._empty_label_id("section-general"),
                            classes="settings-pane-empty",
                        )
                        yield from self._compose_input_group(
                            section_id="section-general",
                            label="Max concurrent agents",
                            widget=Input(
                                value=str(self._config.general.max_concurrent_agents),
                                id="max-agents-input",
                                placeholder="3",
                                type="integer",
                            ),
                        )
                        yield from self._compose_input_group(
                            section_id="section-general",
                            label="Default agent",
                            widget=Select[str](
                                options=agent_options,
                                value=self._config.general.default_worker_agent,
                                id="default-agent-select",
                                allow_blank=False,
                                compact=True,
                            ),
                        )
                        yield from self._compose_input_group(
                            section_id="section-general",
                            label="Worker persona",
                            search_text="implementation prompt",
                            widget=PersonaField(
                                self._config.general.worker_persona,
                                field_id="worker-persona-field",
                                editor_title="Edit Worker Persona",
                                default=DEFAULT_WORKER_PERSONA,
                            ),
                        )
                        yield from self._compose_input_group(
                            section_id="section-general",
                            label="Orchestrator persona",
                            search_text="planning prompt",
                            widget=PersonaField(
                                self._config.general.orchestrator_persona,
                                field_id="orchestrator-persona-field",
                                editor_title="Edit Orchestrator Persona",
                                default=DEFAULT_ORCHESTRATOR_PERSONA,
                            ),
                        )
                        yield from self._compose_input_group(
                            section_id="section-general",
                            label="PR reviewer persona",
                            search_text="review prompt",
                            widget=PersonaField(
                                self._config.general.pr_reviewer_persona,
                                field_id="pr-reviewer-persona-field",
                                editor_title="Edit PR Reviewer Persona",
                                default=DEFAULT_PR_REVIEWER_PERSONA,
                            ),
                        )
                        with Horizontal(classes="settings-input-row"):
                            yield from self._compose_input_group(
                                section_id="section-general",
                                label="PAIR terminal",
                                search_text="tmux nvim vscode cursor",
                                classes="input-group input-group-half",
                                widget=Select[str](
                                    options=[
                                        ("tmux", "tmux"),
                                        ("Neovim", "nvim"),
                                        ("VS Code", "vscode"),
                                        ("Cursor", "cursor"),
                                    ],
                                    value=self._config.general.default_pair_terminal_backend,
                                    id="default-pair-terminal-select",
                                    allow_blank=False,
                                    compact=True,
                                ),
                            )
                            yield from self._compose_input_group(
                                section_id="section-general",
                                label="Worktree base ref",
                                search_text="remote local ahead",
                                classes="input-group input-group-half",
                                widget=Select[str](
                                    options=[
                                        ("Remote (origin/<base>)", "remote"),
                                        ("Local if ahead", "local_if_ahead"),
                                        ("Local", "local"),
                                    ],
                                    value=self._config.general.worktree_base_ref_strategy,
                                    id="worktree-base-ref-strategy-select",
                                    allow_blank=False,
                                    compact=True,
                                ),
                            )
                        with Horizontal(classes="settings-input-row"):
                            yield from self._compose_input_group(
                                section_id="section-general",
                                label="Doctor verbosity",
                                classes="input-group input-group-half",
                                widget=Select[str](
                                    options=[
                                        ("TL;DR", "tldr"),
                                        ("Short", "short"),
                                        ("Technical", "technical"),
                                    ],
                                    value=self._config.general.doctor_verbosity,
                                    id="doctor-verbosity-select",
                                    allow_blank=False,
                                    compact=True,
                                ),
                            )
                            yield from self._compose_input_group(
                                section_id="section-general",
                                label="Interaction verbosity",
                                classes="input-group input-group-half",
                                widget=Select[str](
                                    options=[
                                        ("TL;DR", "tldr"),
                                        ("Short", "short"),
                                        ("Technical", "technical"),
                                    ],
                                    value=self._config.general.interaction_verbosity,
                                    id="interaction-verbosity-select",
                                    allow_blank=False,
                                    compact=True,
                                ),
                            )

                    with Vertical(
                        classes="settings-section settings-pane",
                        id="section-auto-review",
                    ):
                        yield Label("Automation", classes="settings-pane-title")
                        yield Static(
                            "No matching settings in this section.",
                            id=self._empty_label_id("section-auto-review"),
                            classes="settings-pane-empty",
                        )
                        yield from self._compose_switch_row(
                            section_id="section-auto-review",
                            switch_id="auto-review-switch",
                            value=self._config.general.auto_review,
                            label="Enable auto review",
                        )
                        yield from self._compose_switch_row(
                            section_id="section-auto-review",
                            switch_id="auto-commit-changes-switch",
                            value=self._config.general.auto_commit_changes,
                            label="Allow automation to auto-commit and auto-push branches",
                            search_text="auto commit auto push",
                        )

                    with Vertical(
                        classes="settings-section settings-pane",
                        id="section-orchestrator",
                    ):
                        yield Label("Orchestrator", classes="settings-pane-title")
                        yield Static(
                            "No matching settings in this section.",
                            id=self._empty_label_id("section-orchestrator"),
                            classes="settings-pane-empty",
                        )
                        yield from self._compose_switch_row(
                            section_id="section-orchestrator",
                            switch_id="auto-approve-switch",
                            value=self._config.general.auto_approve,
                            label="Auto-approve orchestrator tool calls",
                            search_text="permissions",
                        )
                        yield from self._compose_switch_row(
                            section_id="section-orchestrator",
                            switch_id="auto-skill-discovery-switch",
                            value=self._config.general.auto_skill_discovery,
                            label="Enable local auto skill discovery (trusted metadata)",
                            search_text="skills",
                        )

                    with Vertical(
                        classes="settings-section settings-pane",
                        id="section-merge-policy",
                    ):
                        yield Label("Merge Policy", classes="settings-pane-title")
                        yield Static(
                            "No matching settings in this section.",
                            id=self._empty_label_id("section-merge-policy"),
                            classes="settings-pane-empty",
                        )
                        yield from self._compose_switch_row(
                            section_id="section-merge-policy",
                            switch_id="require-review-approval-switch",
                            value=self._config.general.require_review_approval,
                            label="Require approval before merge",
                        )
                        yield from self._compose_switch_row(
                            section_id="section-merge-policy",
                            switch_id="serialize-merges-switch",
                            value=self._config.general.serialize_merges,
                            label="Serialize merge operations",
                        )

                    with Vertical(
                        classes="settings-section settings-pane",
                        id="section-model-defaults",
                    ):
                        yield Label("Model Defaults", classes="settings-pane-title")
                        yield Static(
                            "No matching settings in this section.",
                            id=self._empty_label_id("section-model-defaults"),
                            classes="settings-pane-empty",
                        )
                        with Horizontal(classes="settings-input-row"):
                            yield from self._compose_input_group(
                                section_id="section-model-defaults",
                                label="Claude",
                                classes="input-group input-group-half",
                                widget=Input(
                                    value=self._config.general.default_model_claude or "",
                                    id="default-model-claude-input",
                                    placeholder="sonnet",
                                ),
                            )
                            yield from self._compose_input_group(
                                section_id="section-model-defaults",
                                label="OpenCode",
                                classes="input-group input-group-half",
                                widget=Input(
                                    value=self._config.general.default_model_opencode or "",
                                    id="default-model-opencode-input",
                                    placeholder="anthropic/claude-sonnet-4-5",
                                ),
                            )
                        with Horizontal(classes="settings-input-row"):
                            yield from self._compose_input_group(
                                section_id="section-model-defaults",
                                label="Codex",
                                classes="input-group input-group-half",
                                widget=Input(
                                    value=self._config.general.default_model_codex or "",
                                    id="default-model-codex-input",
                                    placeholder="gpt-5.2-codex",
                                ),
                            )
                            yield from self._compose_input_group(
                                section_id="section-model-defaults",
                                label="Gemini",
                                classes="input-group input-group-half",
                                widget=Input(
                                    value=self._config.general.default_model_gemini or "",
                                    id="default-model-gemini-input",
                                    placeholder="auto | pro | flash | gemini-2.5-flash",
                                ),
                            )
                        with Horizontal(classes="settings-input-row"):
                            yield from self._compose_input_group(
                                section_id="section-model-defaults",
                                label="Kimi",
                                classes="input-group input-group-half",
                                widget=Input(
                                    value=self._config.general.default_model_kimi or "",
                                    id="default-model-kimi-input",
                                    placeholder="kimi-k2-turbo-preview",
                                ),
                            )
                            yield from self._compose_input_group(
                                section_id="section-model-defaults",
                                label="Copilot",
                                classes="input-group input-group-half",
                                widget=Input(
                                    value=self._config.general.default_model_copilot or "",
                                    id="default-model-copilot-input",
                                    placeholder="Claude Sonnet 4.5 (switch via /model)",
                                ),
                            )

                    with Vertical(
                        classes="settings-section settings-pane",
                        id="section-ui-preferences",
                    ):
                        yield Label("UI Preferences", classes="settings-pane-title")
                        yield Static(
                            "No matching settings in this section.",
                            id=self._empty_label_id("section-ui-preferences"),
                            classes="settings-pane-empty",
                        )
                        yield from self._compose_switch_row(
                            section_id="section-ui-preferences",
                            switch_id="skip-pair-instructions-switch",
                            value=self._config.ui.skip_pair_instructions,
                            label="Skip PAIR instructions popup",
                        )
                        yield from self._compose_switch_row(
                            section_id="section-ui-preferences",
                            switch_id="show-beginner-hints-switch",
                            value=self._config.ui.show_beginner_hints,
                            label="Show beginner quick-start hints",
                        )
                        yield from self._compose_input_group(
                            section_id="section-ui-preferences",
                            label="Theme",
                            widget=Select[str](
                                options=theme_options,
                                value=self._config.ui.theme or "",
                                id="theme-select",
                                allow_blank=False,
                                compact=True,
                            ),
                        )

            with Horizontal(classes="modal-action-hint-row"):
                yield Label(
                    self.DEFAULT_ACTION_HINT,
                    classes="modal-action-hint",
                    id="settings-action-hint",
                )

        yield Footer(show_command_palette=False)

    def on_mount(self) -> None:
        self._activate_section(self._active_section_id)
        self._apply_settings_filter("")
        self.action_focus_search()

    @on(OptionList.OptionHighlighted, "#settings-nav")
    def _on_nav_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if self._rebuilding_nav:
            return
        if event.option.id:
            self._activate_section(str(event.option.id))

    @on(OptionList.OptionSelected, "#settings-nav")
    def _on_nav_option_selected(self, event: OptionList.OptionSelected) -> None:
        if self._rebuilding_nav:
            return
        if event.option.id:
            section_id = str(event.option.id)
            self._activate_section(section_id)
            self._focus_first_control(section_id)

    @on(Input.Changed, "#settings-search")
    def _on_search_changed(self, event: Input.Changed) -> None:
        self._apply_settings_filter(event.value)

    def action_focus_search(self) -> None:
        with suppress(NoMatches):
            self.query_one("#settings-search", Input).focus()

    def _highlight_nav_option(self, section_id: str) -> None:
        with suppress(NoMatches):
            nav = self.query_one("#settings-nav", OptionList)
            for index, option in enumerate(nav.options):
                if option.id == section_id:
                    nav.highlighted = index
                    break

    def _activate_section(self, section_id: str) -> None:
        valid_section_ids = {sid for sid, _ in self.SECTION_DEFINITIONS}
        if section_id not in valid_section_ids:
            return
        self._active_section_id = section_id
        for candidate_id, _ in self.SECTION_DEFINITIONS:
            with suppress(NoMatches):
                pane = self.query_one(f"#{candidate_id}", Vertical)
                is_active = candidate_id == section_id
                pane.display = is_active
                pane.set_class(is_active, "active-pane")
        self._highlight_nav_option(section_id)

    def _focus_first_control(self, section_id: str) -> None:
        with suppress(NoMatches):
            section = self.query_one(f"#{section_id}", Vertical)
            for widget in section.query("Checkbox, Input, Select, PersonaField"):
                if widget.display:
                    widget.focus()
                    return

    def _rebuild_nav_options(self, section_counts: dict[str, int], *, query: str) -> None:
        with suppress(NoMatches):
            nav = self.query_one("#settings-nav", OptionList)
            self._rebuilding_nav = True
            try:
                nav.clear_options()
                for section_id, title in self.SECTION_DEFINITIONS:
                    label = title
                    if query:
                        label = f"{title} ({section_counts.get(section_id, 0)})"
                    nav.add_option(Option(label, id=section_id))
                self._highlight_nav_option(self._active_section_id)
            finally:
                self._rebuilding_nav = False

    def _update_search_status(
        self,
        query: str,
        total_matches: int,
        section_counts: dict[str, int],
    ) -> None:
        with suppress(NoMatches):
            status = self.query_one("#settings-search-status", Static)
            if not query:
                status.update("")
                status.display = False
                return
            if total_matches == 0:
                status.update("[dim]No settings matched your search.[/dim]")
                status.display = True
                return
            matched_sections = sum(1 for value in section_counts.values() if value > 0)
            match_word = "match" if total_matches == 1 else "matches"
            section_word = "section" if matched_sections == 1 else "sections"
            status.update(
                f"[dim]{total_matches} {match_word} across {matched_sections} {section_word}[/dim]"
            )
            status.display = True

    def _apply_settings_filter(self, raw_query: str) -> None:
        query = " ".join(raw_query.lower().split())
        self._search_query = query

        total_matches = 0
        section_counts: dict[str, int] = {}
        for section_id, _ in self.SECTION_DEFINITIONS:
            matched_count = 0
            for item in self.query(f".{self._section_item_class(section_id)}"):
                searchable_name = item.name or ""
                matched = not query or query in searchable_name
                item.display = matched
                if matched:
                    matched_count += 1
            section_counts[section_id] = matched_count
            total_matches += matched_count

            with suppress(NoMatches):
                empty_hint = self.query_one(f"#{self._empty_label_id(section_id)}", Static)
                empty_hint.display = bool(query and matched_count == 0)

        self._rebuild_nav_options(section_counts, query=query)
        self._update_search_status(query, total_matches, section_counts)

        if query and section_counts.get(self._active_section_id, 0) == 0:
            for section_id, _ in self.SECTION_DEFINITIONS:
                if section_counts.get(section_id, 0) > 0:
                    self._activate_section(section_id)
                    break

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
        auto_review = self.query_one("#auto-review-switch", Checkbox).value
        auto_commit_changes = self.query_one("#auto-commit-changes-switch", Checkbox).value
        auto_approve = self.query_one("#auto-approve-switch", Checkbox).value
        auto_skill_discovery = self.query_one("#auto-skill-discovery-switch", Checkbox).value
        require_review_approval = self.query_one("#require-review-approval-switch", Checkbox).value
        serialize_merges = self.query_one("#serialize-merges-switch", Checkbox).value
        skip_pair_instructions = self.query_one("#skip-pair-instructions-switch", Checkbox).value
        show_beginner_hints = self.query_one("#show-beginner-hints-switch", Checkbox).value
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
            "general.auto_commit_changes": auto_commit_changes,
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
            "ui.show_beginner_hints": show_beginner_hints,
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
            self._set_action_hint(self.DEFAULT_ACTION_HINT)
            return

        if not success:
            self.app.notify(message or "Failed to save settings", severity="error")
            self._is_saving = False
            self._set_action_hint(self.DEFAULT_ACTION_HINT)
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
