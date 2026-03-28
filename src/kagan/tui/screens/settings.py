from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Literal, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.theme import BUILTIN_THEMES
from textual.widgets import Button, Footer, Input, Select, Static, Switch, TextArea
from textual.widgets._option_list import Option, OptionList

from kagan.chat import list_registered_agent_backends
from kagan.core import (
    detect_dotfile_overrides,
)

if TYPE_CHECKING:
    from textual.timer import Timer

    from kagan.tui.app import KaganApp
from kagan.tui.keybindings import SETTINGS_BINDINGS, SETTINGS_COMMAND_BINDINGS


def _is_enabled(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


# Kagan custom theme names.
_KAGAN_THEME_NAMES = {"kagan", "kagan-256"}


def _build_theme_options() -> list[tuple[str, str]]:
    options: list[tuple[str, str]] = [
        ("Auto (Kagan Night)", ""),
        ("Kagan Night", "kagan"),
        ("Kagan 256-color", "kagan-256"),
    ]
    for name in sorted(BUILTIN_THEMES):
        label = name.replace("-", " ").title()
        options.append((label, name))
    return options


def _valid_theme_names() -> set[str]:
    return {"", *_KAGAN_THEME_NAMES, *BUILTIN_THEMES}


@dataclass(frozen=True)
class SettingCategory:
    id: str
    name: str
    search_terms: tuple[str, ...]
    is_advanced: bool = False


@dataclass(frozen=True)
class SettingFieldSpec:
    kind: Literal["switch", "select", "text", "textarea", "static"]
    label: str = ""
    field_id: str | None = None
    options: tuple[tuple[str, str], ...] = ()
    options_factory: Callable[[], list[tuple[str, str]]] | None = None
    text: str = ""
    classes: str = "settings-field-label-top"


class CategoryList(OptionList):
    @dataclass
    class CategoryChanged:
        category_id: str | None

    def __init__(self, categories: list[SettingCategory]) -> None:
        self._categories = categories
        self._visible: list[SettingCategory] = categories[:]
        self._query = ""
        super().__init__(id="settings-nav")

    @property
    def visible_count(self) -> int:
        return len(self._visible)

    def selected_category_id(self) -> str | None:
        index = self.highlighted
        if index is None or index < 0 or index >= len(self._visible):
            return None
        return self._visible[index].id

    def on_mount(self) -> None:
        self._render_options()

    def filter_categories(self, query: str) -> str | None:
        self._query = query.strip().lower()
        self._apply_filter()
        self._render_options()
        return self.selected_category_id()

    def set_categories(self, categories: list[SettingCategory]) -> str | None:
        selected_id = self.selected_category_id()
        self._categories = categories
        self._apply_filter()
        self._render_options(preferred_category_id=selected_id)
        return self.selected_category_id()

    def _apply_filter(self) -> None:
        if not self._query:
            self._visible = self._categories[:]
            return
        self._visible = [
            category
            for category in self._categories
            if self._query in category.name.lower()
            or any(self._query in term.lower() for term in category.search_terms)
        ]

    def _render_options(self, preferred_category_id: str | None = None) -> None:
        previous_highlight = self.highlighted
        self.clear_options()
        self.add_options([Option(category.name, id=category.id) for category in self._visible])
        if not self._visible:
            self.highlighted = None
            return

        if preferred_category_id is not None:
            for index, category in enumerate(self._visible):
                if category.id == preferred_category_id:
                    self.highlighted = index
                    return

        if previous_highlight is not None and 0 <= previous_highlight < len(self._visible):
            self.highlighted = previous_highlight
            return

        self.highlighted = 0


class SettingsModal(ModalScreen[None]):
    BINDINGS = [
        *SETTINGS_BINDINGS,
        *SETTINGS_COMMAND_BINDINGS,
    ]

    def __init__(self) -> None:
        super().__init__(id="settings-modal")
        self._auto_save_timer: Timer | None = None
        self._categories = [
            SettingCategory(
                id="essentials",
                name="Essentials",
                search_terms=(
                    "agent",
                    "backend",
                    "theme",
                    "appearance",
                    "color",
                    "instructions",
                    "custom",
                    "prompt",
                    "additional",
                    "dotfile",
                ),
            ),
            SettingCategory(
                id="workflow",
                name="Workflow",
                search_terms=(
                    "review",
                    "strict",
                    "planning",
                    "confirm",
                    "auto",
                    "approval",
                    "merge",
                ),
            ),
            SettingCategory(
                id="git",
                name="Git",
                search_terms=(
                    "git",
                    "user",
                    "name",
                    "email",
                    "identity",
                    "agent",
                    "kagan",
                    "base",
                    "branch",
                ),
            ),
            SettingCategory(
                id="advanced",
                name="Advanced",
                search_terms=(
                    "worktree",
                    "strategy",
                    "ref",
                    "remote",
                    "local",
                    "serialize",
                    "init",
                    "commit",
                    "launcher",
                    "startup",
                    "recent",
                    "model",
                    "claude",
                    "openai",
                    "attached",
                    "instructions",
                    "popup",
                ),
                is_advanced=True,
            ),
        ]
        self._category_fields: dict[str, tuple[SettingFieldSpec, ...]] = {
            "essentials": (
                SettingFieldSpec(
                    "select",
                    "Default agent backend",
                    "settings-default-agent",
                    options_factory=list_registered_agent_backends,
                ),
                SettingFieldSpec(
                    "select",
                    "Theme",
                    "settings-theme",
                    options_factory=_build_theme_options,
                ),
                SettingFieldSpec(
                    "textarea", "Additional instructions", "settings-additional-instructions"
                ),
                SettingFieldSpec(
                    "static",
                    text=(
                        "[dim]Appended to every agent prompt — your preferences,\n"
                        "conventions, and workflow rules.\n\n"
                        "Examples: 'Use conventional commits' ·\n"
                        "'Always explain tradeoffs first' ·\n"
                        "'Commit messages in Portuguese'[/dim]"
                    ),
                ),
                SettingFieldSpec("static", field_id="settings-dotfile-status"),
                SettingFieldSpec(
                    "static",
                    text="[dim]Full prompt overrides -> .kagan/prompts/[/dim]",
                ),
            ),
            "workflow": (
                SettingFieldSpec("switch", "Enable auto review", "settings-auto-review"),
                SettingFieldSpec(
                    "switch", "Require approval before merge", "settings-require-review-approval"
                ),
                SettingFieldSpec(
                    "switch", "Auto-confirm plans for single tasks", "settings-auto-confirm-single"
                ),
                SettingFieldSpec(
                    "select",
                    "Review strictness",
                    "settings-review-strictness",
                    options=(
                        ("Strict", "strict"),
                        ("Balanced", "balanced"),
                        ("Relaxed", "relaxed"),
                    ),
                ),
            ),
            "git": (
                SettingFieldSpec(
                    "select",
                    "Git user mode",
                    "settings-git-user-mode",
                    options=(
                        ("Kagan Agent (default)", "kagan_agent"),
                        ("System git profile", "system_default"),
                        ("Custom", "custom"),
                    ),
                ),
                SettingFieldSpec("text", "Git user name (custom mode)", "settings-git-user-name"),
                SettingFieldSpec("text", "Git email (custom mode)", "settings-git-user-email"),
                SettingFieldSpec("text", "Default base branch", "settings-default-base-branch"),
            ),
            "advanced": (
                SettingFieldSpec(
                    "select",
                    "Worktree base ref strategy",
                    "settings-base-ref-strategy",
                    options=(
                        ("Local if ahead", "local_if_ahead"),
                        ("Remote", "remote"),
                        ("Local", "local"),
                    ),
                ),
                SettingFieldSpec(
                    "select",
                    "Planning depth",
                    "settings-planning-depth",
                    options=(
                        ("Always plan", "always"),
                        ("Multi-task only", "multi_task"),
                        ("Never plan", "never"),
                    ),
                ),
                SettingFieldSpec("switch", "Serialize manual merges", "settings-serialize-merges"),
                SettingFieldSpec("switch", "Auto init git repo", "settings-auto-init-repo"),
                SettingFieldSpec(
                    "switch", "Auto create initial commit", "settings-auto-init-commit"
                ),
                SettingFieldSpec(
                    "select",
                    "Interactive launcher",
                    "settings-attached-launcher",
                    options=(
                        ("tmux", "tmux"),
                        ("nvim", "nvim"),
                        ("vscode", "vscode"),
                        ("cursor", "cursor"),
                        ("windsurf", "windsurf"),
                        ("kiro", "kiro"),
                        ("antigravity", "antigravity"),
                    ),
                ),
                SettingFieldSpec(
                    "select",
                    "Bare `kagan` startup surface",
                    "settings-startup-surface",
                    options=(
                        ("TUI", "tui"),
                        ("Web", "web"),
                        ("Chat", "chat"),
                        ("Show chooser on next launch", "ask"),
                    ),
                ),
                SettingFieldSpec(
                    "switch", "TUI: open last project on launch", "settings-open-last-project"
                ),
                SettingFieldSpec(
                    "switch",
                    "Skip attach instructions popup",
                    "settings-skip-attached-instructions",
                ),
                SettingFieldSpec("text", "Claude default model", "settings-default-model-claude"),
                SettingFieldSpec("text", "OpenAI default model", "settings-default-model-openai"),
            ),
        }
        self._show_advanced = False

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        with Vertical(id="settings-container"):
            with Vertical(id="settings-header"):
                with Horizontal(classes="settings-header-top"):
                    yield Static("Settings", classes="modal-title")
                    yield Input(
                        placeholder="Search sections or settings...",
                        id="settings-search-input",
                    )
                yield Static("", id="settings-search-status")

            with Horizontal(id="settings-main"):
                with Vertical(id="settings-nav-pane"):
                    yield CategoryList(self._visible_nav_categories())
                    yield Button("Show advanced ▸", id="settings-advanced-toggle")
                with Vertical(id="settings-detail-pane"):
                    yield Static("", classes="settings-detail-title", id="settings-detail-title")
                    with Vertical(id="settings-detail-content"):
                        for category in self._categories:
                            with Vertical(
                                id=f"settings-pane-{category.id}",
                                classes="settings-pane",
                            ):
                                yield from self._build_category_fields(category.id)

            with Horizontal(classes="modal-action-row"):
                yield Button("Close", id="settings-close")
            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    "Auto-saved  ·  Ctrl+. advanced  / search  Esc close",
                    id="settings-footer-hint",
                    classes="modal-action-hint",
                )
        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        settings = await self.kagan_app.core.settings.get()

        self._sync_navigation()
        self._set_values(settings)
        self.query_one(CategoryList).focus()
        self._update_search_status("")

    def _set_values(self, settings: dict[str, str]) -> None:
        # --- Orchestration ---
        self.query_one("#settings-auto-confirm-single", Switch).value = _is_enabled(
            settings.get("auto_confirm_single_tasks"),
            default=False,
        )

        review_strictness = settings.get("review_strictness", "balanced")
        review_select = self.query_one("#settings-review-strictness", Select)
        review_select.value = (
            review_strictness
            if review_strictness in {"strict", "balanced", "relaxed"}
            else "balanced"
        )

        planning = settings.get("planning_depth", "always")
        planning_select = self.query_one("#settings-planning-depth", Select)
        planning_select.value = (
            planning if planning in {"always", "multi_task", "never"} else "always"
        )

        # --- General ---
        default_agent = settings.get("default_agent_backend") or "claude-code"
        agent_select = self.query_one("#settings-default-agent", Select)
        available_agents = list_registered_agent_backends()
        if default_agent in available_agents:
            agent_select.value = default_agent
        elif available_agents:
            agent_select.value = available_agents[0]
        else:
            agent_select.value = "claude-code"

        attached_launcher = settings.get("attached_launcher", "tmux")
        attached_select = self.query_one("#settings-attached-launcher", Select)
        attached_select.value = (
            attached_launcher
            if attached_launcher
            in {"tmux", "nvim", "vscode", "cursor", "windsurf", "kiro", "antigravity"}
            else "tmux"
        )
        startup_surface = settings.get("startup_default_surface") or settings.get(
            "ui.surface_chooser_last_choice", "tui"
        )
        startup_surface_select = self.query_one("#settings-startup-surface", Select)
        startup_surface_select.value = (
            startup_surface if startup_surface in {"tui", "web", "chat", "ask"} else "tui"
        )

        self.query_one("#settings-default-base-branch", Input).value = settings.get(
            "default_base_branch", "main"
        )

        strategy = settings.get("worktree_base_ref_strategy", "local_if_ahead")
        strategy_select = self.query_one("#settings-base-ref-strategy", Select)
        strategy_select.value = (
            strategy if strategy in {"local_if_ahead", "remote", "local"} else "local_if_ahead"
        )
        theme = settings.get("theme", "")
        theme_select = self.query_one("#settings-theme", Select)
        theme_select.value = theme if theme in _valid_theme_names() else ""

        # --- Automation ---
        self.query_one("#settings-auto-review", Switch).value = _is_enabled(
            settings.get("auto_review"),
            default=True,
        )
        self.query_one("#settings-open-last-project", Switch).value = _is_enabled(
            settings.get("open_last_project_on_startup"),
            default=False,
        )
        self.query_one("#settings-auto-init-repo", Switch).value = _is_enabled(
            settings.get("auto_init_git_repo"),
            default=True,
        )
        self.query_one("#settings-auto-init-commit", Switch).value = _is_enabled(
            settings.get("auto_init_git_initial_commit"),
            default=True,
        )
        self.query_one("#settings-require-review-approval", Switch).value = _is_enabled(
            settings.get("require_review_approval"),
            default=False,
        )
        self.query_one("#settings-serialize-merges", Switch).value = _is_enabled(
            settings.get("serialize_merges"),
            default=False,
        )
        self.query_one("#settings-skip-attached-instructions", Switch).value = _is_enabled(
            settings.get("skip_attached_instructions_popup"),
            default=False,
        )

        # --- Git Identity ---
        git_mode = settings.get("git_user_mode", "kagan_agent")
        git_mode_select = self.query_one("#settings-git-user-mode", Select)
        git_mode_select.value = (
            git_mode if git_mode in {"kagan_agent", "system_default", "custom"} else "kagan_agent"
        )
        self.query_one("#settings-git-user-name", Input).value = settings.get("git_user_name", "")
        self.query_one("#settings-git-user-email", Input).value = settings.get("git_user_email", "")
        self.query_one("#settings-default-model-claude", Input).value = settings.get(
            "default_model_claude", ""
        )
        self.query_one("#settings-default-model-openai", Input).value = settings.get(
            "default_model_openai", ""
        )

        # --- Additional Instructions ---
        self.query_one("#settings-additional-instructions", TextArea).text = settings.get(
            "additional_instructions", ""
        )

        # Dotfile status
        overrides = detect_dotfile_overrides(Path.cwd())
        if overrides:
            names = ", ".join(f"{k}.md" for k in sorted(overrides))
            self.query_one("#settings-dotfile-status", Static).update(
                f"[green]Prompt overrides active:[/green] {names}"
            )
        else:
            self.query_one("#settings-dotfile-status", Static).update(
                "[dim]No prompt overrides active[/dim]"
            )

    @on(Input.Changed, "#settings-search-input")
    async def _on_search_changed(self, event: Input.Changed) -> None:
        category_list = self.query_one(CategoryList)
        category_list.set_categories(self._search_scope_categories(event.value))
        category_id = category_list.filter_categories(event.value)
        self._mount_detail(category_id)
        self._update_search_status(event.value)

    @on(OptionList.OptionHighlighted, "#settings-nav")
    async def _on_category_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        category_list = self.query_one(CategoryList)
        category_id = category_list.selected_category_id()
        if category_id is None and event.option is not None and event.option.id is not None:
            category_id = event.option.id
        self._mount_detail(category_id)

    @on(Button.Pressed, "#settings-advanced-toggle")
    async def _on_advanced_toggle_pressed(self, _: Button.Pressed) -> None:
        self.action_toggle_advanced()

    @on(Button.Pressed, "#settings-close")
    def _on_close_pressed(self, _: Button.Pressed) -> None:
        self.action_cancel()

    # --- Auto-save handlers ---

    @on(Switch.Changed)
    def _on_switch_auto_save(self, _: Switch.Changed) -> None:
        self._schedule_auto_save()

    @on(Select.Changed)
    def _on_select_auto_save(self, event: Select.Changed) -> None:
        # Ignore navigation-only selects (the category list is an OptionList, not Select)
        self._schedule_auto_save()

    @on(Input.Changed)
    def _on_input_auto_save(self, event: Input.Changed) -> None:
        if event.input.id == "settings-search-input":
            return
        self._schedule_auto_save()

    @on(TextArea.Changed)
    def _on_textarea_auto_save(self, event: TextArea.Changed) -> None:
        self._schedule_auto_save()

    def _schedule_auto_save(self) -> None:
        if self._auto_save_timer is not None:
            self._auto_save_timer.stop()
        self._auto_save_timer = self.set_timer(0.4, self._fire_auto_save)

    def _fire_auto_save(self) -> None:
        self._auto_save_timer = None
        self.run_worker(self._save_all_settings(), exit_on_error=False)

    def action_toggle_advanced(self) -> None:
        self._show_advanced = not self._show_advanced
        self._sync_navigation()

    def _search_scope_categories(self, query: str) -> list[SettingCategory]:
        if query.strip():
            return self._categories
        return self._visible_nav_categories()

    def _visible_nav_categories(self) -> list[SettingCategory]:
        if self._show_advanced:
            return self._categories
        return [category for category in self._categories if not category.is_advanced]

    def _sync_navigation(self) -> None:
        query = self.query_one("#settings-search-input", Input).value
        category_list = self.query_one(CategoryList)
        category_list.set_categories(self._search_scope_categories(query))
        selected_id = category_list.filter_categories(query)
        self._mount_detail(selected_id)
        self._update_advanced_toggle_label()
        self._update_search_status(query)

    def _update_advanced_toggle_label(self) -> None:
        advanced_count = sum(1 for category in self._categories if category.is_advanced)
        label = (
            f"Hide advanced ▾ ({advanced_count})"
            if self._show_advanced
            else f"Show advanced ▸ ({advanced_count})"
        )
        toggle = self.query_one("#settings-advanced-toggle", Button)
        toggle.label = label
        toggle.set_class(self._show_advanced, "active")

    def _mount_detail(self, category_id: str | None) -> None:
        title = self.query_one("#settings-detail-title", Static)
        if category_id is None:
            title.update("No section selected")
            self._show_pane(None)
            return

        category_name = next(
            (category.name for category in self._categories if category.id == category_id),
            category_id.title(),
        )
        title.update(category_name)
        self._show_pane(category_id)

    def _show_pane(self, category_id: str | None) -> None:
        panes = {
            category.id: self.query_one(f"#settings-pane-{category.id}", Vertical)
            for category in self._categories
        }
        for pane_id, pane in panes.items():
            visible = pane_id == category_id
            pane.display = visible
            pane.set_class(visible, "active-pane")

    def _build_category_fields(self, category_id: str) -> list[Static | Vertical | Horizontal]:
        return [self._render_field(field) for field in self._category_fields[category_id]]

    def _render_field(self, field: SettingFieldSpec) -> Static | Vertical | Horizontal:
        if field.kind == "switch" and field.field_id is not None:
            return self._switch_field(field.label, field.field_id)
        if field.kind == "select" and field.field_id is not None:
            raw_options = (
                field.options_factory() if field.options_factory is not None else field.options
            )
            if field.field_id == "settings-default-agent":
                options = [(name, name) for name in cast("list[str]", raw_options)]
            else:
                options = list(raw_options)
            return self._select_field(field.label, field.field_id, options)
        if field.kind == "text" and field.field_id is not None:
            return self._text_field(field.label, field.field_id)
        if field.kind == "textarea" and field.field_id is not None:
            return self._textarea_field(field.label, field.field_id)
        if field.field_id is not None:
            return Static(field.text, id=field.field_id, classes=field.classes)
        return Static(field.text, classes=field.classes)

    def _text_field(self, label: str, field_id: str) -> Vertical:
        return Vertical(
            Static(label, classes="settings-field-label-top"),
            Input(id=field_id, classes="settings-input"),
            classes="settings-field-group",
        )

    def _select_field(
        self,
        label: str,
        field_id: str,
        options: list[tuple[str, str]],
    ) -> Vertical:
        return Vertical(
            Static(label, classes="settings-field-label-top"),
            Select(options=options, id=field_id, allow_blank=False, classes="settings-select"),
            classes="settings-field-group",
        )

    def _textarea_field(self, label: str, field_id: str) -> Vertical:
        return Vertical(
            Static(label, classes="settings-field-label-top"),
            TextArea(id=field_id, classes="settings-textarea"),
            classes="settings-field-group",
        )

    def _switch_field(self, label: str, field_id: str) -> Horizontal:
        return Horizontal(
            Static(label, classes="settings-field-label-inline"),
            Switch(id=field_id, classes="settings-checkbox"),
            classes="settings-field-row",
        )

    def _update_search_status(self, query: str) -> None:
        category_list = self.query_one(CategoryList)
        total = len(self._search_scope_categories(query))
        visible = category_list.visible_count
        if query.strip():
            message = f"{visible}/{total} sections shown"
        else:
            mode = "including advanced" if self._show_advanced else "basic sections"
            message = f"{total} sections • {mode}; search matches category names and settings"
        self.query_one("#settings-search-status", Static).update(message)

    async def _save_all_settings(self) -> None:
        agent_backend_value = self.query_one("#settings-default-agent", Select).value
        default_agent_backend = (
            agent_backend_value if isinstance(agent_backend_value, str) else "claude-code"
        )

        attached_launcher_value = self.query_one("#settings-attached-launcher", Select).value
        startup_surface_value = self.query_one("#settings-startup-surface", Select).value
        strategy_value = self.query_one("#settings-base-ref-strategy", Select).value
        base_branch = self.query_one("#settings-default-base-branch", Input).value.strip() or "main"
        theme_value = self.query_one("#settings-theme", Select).value
        auto_review = self.query_one("#settings-auto-review", Switch).value
        open_last_project = self.query_one("#settings-open-last-project", Switch).value
        auto_init_repo = self.query_one("#settings-auto-init-repo", Switch).value
        auto_init_commit = self.query_one("#settings-auto-init-commit", Switch).value
        require_review_approval = self.query_one("#settings-require-review-approval", Switch).value
        serialize_merges = self.query_one("#settings-serialize-merges", Switch).value
        skip_attached_instructions = self.query_one(
            "#settings-skip-attached-instructions", Switch
        ).value

        git_mode_value = self.query_one("#settings-git-user-mode", Select).value
        git_mode = git_mode_value if isinstance(git_mode_value, str) else "kagan_agent"
        git_user_name = self.query_one("#settings-git-user-name", Input).value.strip()
        git_user_email = self.query_one("#settings-git-user-email", Input).value.strip()
        default_model_claude = self.query_one("#settings-default-model-claude", Input).value.strip()
        default_model_openai = self.query_one("#settings-default-model-openai", Input).value.strip()

        attached_launcher = (
            attached_launcher_value if isinstance(attached_launcher_value, str) else "tmux"
        )
        startup_surface = startup_surface_value if isinstance(startup_surface_value, str) else "tui"
        strategy = strategy_value if isinstance(strategy_value, str) else "local_if_ahead"
        theme = theme_value if isinstance(theme_value, str) else ""

        # Orchestration settings
        auto_confirm = self.query_one("#settings-auto-confirm-single", Switch).value
        review_strictness_value = self.query_one("#settings-review-strictness", Select).value
        planning_value = self.query_one("#settings-planning-depth", Select).value

        updates: dict[str, str] = {
            "default_agent_backend": default_agent_backend,
            "attached_launcher": attached_launcher,
            "startup_default_surface": startup_surface,
            "default_base_branch": base_branch,
            "worktree_base_ref_strategy": strategy,
            "theme": theme,
            "auto_review": "true" if auto_review else "false",
            "open_last_project_on_startup": "true" if open_last_project else "false",
            "auto_init_git_repo": "true" if auto_init_repo else "false",
            "auto_init_git_initial_commit": "true" if auto_init_commit else "false",
            "require_review_approval": "true" if require_review_approval else "false",
            "serialize_merges": "true" if serialize_merges else "false",
            "skip_attached_instructions_popup": ("true" if skip_attached_instructions else "false"),
            "git_user_mode": git_mode,
            "auto_confirm_single_tasks": "true" if auto_confirm else "false",
            "review_strictness": (
                review_strictness_value if isinstance(review_strictness_value, str) else "balanced"
            ),
            "planning_depth": planning_value if isinstance(planning_value, str) else "always",
        }

        # Additional instructions
        additional = self.query_one("#settings-additional-instructions", TextArea).text.strip()
        updates["additional_instructions"] = additional

        updates["default_model_claude"] = default_model_claude
        updates["default_model_openai"] = default_model_openai
        if git_user_name:
            updates["git_user_name"] = git_user_name
        if git_user_email:
            updates["git_user_email"] = git_user_email

        await self.kagan_app.core.settings.set(updates)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_focus_search(self) -> None:
        self.query_one("#settings-search-input", Input).focus()

    async def action_dismiss(self, result: None = None) -> None:
        self.dismiss(result)
