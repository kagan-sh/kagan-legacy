from dataclasses import dataclass
from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Select, Static, Switch, TextArea
from textual.widgets._option_list import Option, OptionList

from kagan.chat import list_registered_agent_backends
from kagan.chat.prompt import _ORCHESTRATOR_SYSTEM_PROMPT
from kagan.core import (
    PERSONA_DEFINITIONS_KEY,
    PERSONA_USER_WHITELIST_KEY,
    load_persona_definitions,
    serialize_persona_definitions,
)

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp
from kagan.tui.keybindings import SETTINGS_BINDINGS, SETTINGS_COMMAND_BINDINGS


def _is_enabled(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True)
class SettingCategory:
    id: str
    name: str
    search_terms: tuple[str, ...]
    is_advanced: bool = False


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
        self._categories = [
            SettingCategory(
                id="general",
                name="General",
                search_terms=("agent", "launcher", "base", "branch", "startup", "recent"),
            ),
            SettingCategory(
                id="automation",
                name="Automation",
                search_terms=("auto", "review", "init", "commit"),
            ),
            SettingCategory(
                id="merge",
                name="Merge Policy",
                search_terms=("merge", "approval", "review", "serialize"),
            ),
            SettingCategory(
                id="appearance",
                name="Appearance",
                search_terms=("theme", "appearance", "color", "pair", "instructions"),
            ),
            SettingCategory(
                id="worktree",
                name="Worktree",
                search_terms=("strategy", "ref", "remote", "local"),
            ),
            SettingCategory(
                id="git_identity",
                name="Git Identity",
                search_terms=("git", "user", "name", "email", "identity", "agent", "kagan"),
                is_advanced=True,
            ),
            SettingCategory(
                id="prompts",
                name="Prompts",
                search_terms=("prompt", "orchestrator", "task", "review", "custom", "persona"),
                is_advanced=True,
            ),
            SettingCategory(
                id="models",
                name="Models",
                search_terms=("model", "claude", "openai", "default", "backend"),
                is_advanced=True,
            ),
        ]
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
                        with Vertical(id="settings-pane-general", classes="settings-pane"):
                            yield self._select_field(
                                "Default agent backend",
                                "settings-default-agent",
                                [(name, name) for name in list_registered_agent_backends()],
                            )
                            yield self._select_field(
                                "PAIR launcher",
                                "settings-pair-launcher",
                                [
                                    ("tmux", "tmux"),
                                    ("nvim", "nvim"),
                                    ("vscode", "vscode"),
                                    ("cursor", "cursor"),
                                    ("windsurf", "windsurf"),
                                    ("kiro", "kiro"),
                                    ("antigravity", "antigravity"),
                                ],
                            )
                            yield self._text_field(
                                "Default base branch",
                                "settings-default-base-branch",
                            )
                            yield self._switch_field(
                                "Open last project on launch",
                                "settings-open-last-project",
                            )
                        with Vertical(id="settings-pane-worktree", classes="settings-pane"):
                            yield self._select_field(
                                "Worktree base ref strategy",
                                "settings-base-ref-strategy",
                                [
                                    ("Local if ahead", "local_if_ahead"),
                                    ("Remote", "remote"),
                                    ("Local", "local"),
                                ],
                            )
                        with Vertical(id="settings-pane-automation", classes="settings-pane"):
                            yield self._switch_field(
                                "Enable auto review",
                                "settings-auto-review",
                            )
                            yield self._switch_field(
                                "Auto init git repo",
                                "settings-auto-init-repo",
                            )
                            yield self._switch_field(
                                "Auto create initial commit",
                                "settings-auto-init-commit",
                            )
                        with Vertical(id="settings-pane-merge", classes="settings-pane"):
                            yield self._switch_field(
                                "Require approval before merge",
                                "settings-require-review-approval",
                            )
                            yield self._switch_field(
                                "Serialize manual merges",
                                "settings-serialize-merges",
                            )
                        with Vertical(id="settings-pane-appearance", classes="settings-pane"):
                            yield self._select_field(
                                "Theme",
                                "settings-theme",
                                [
                                    ("Auto (Kagan Night)", ""),
                                    ("Kagan Night", "kagan"),
                                    ("Kagan 256-color", "kagan-256"),
                                ],
                            )
                            yield self._switch_field(
                                "Skip PAIR instructions popup",
                                "settings-skip-pair-instructions",
                            )
                        with Vertical(id="settings-pane-git_identity", classes="settings-pane"):
                            yield self._select_field(
                                "Git user mode",
                                "settings-git-user-mode",
                                [
                                    ("Kagan Agent (default)", "kagan_agent"),
                                    ("System git profile", "system_default"),
                                    ("Custom", "custom"),
                                ],
                            )
                            yield self._text_field(
                                "Git user name (custom mode)",
                                "settings-git-user-name",
                            )
                            yield self._text_field(
                                "Git email (custom mode)",
                                "settings-git-user-email",
                            )
                        with Vertical(id="settings-pane-prompts", classes="settings-pane"):
                            yield self._textarea_field(
                                "Custom orchestrator prompt (prepended to default)",
                                "settings-custom-orchestrator-prompt",
                            )
                            yield self._textarea_field(
                                "Custom task agent prompt (prepended to default)",
                                "settings-custom-task-prompt",
                            )
                            yield self._textarea_field(
                                "Custom review prompt (prepended to default)",
                                "settings-custom-review-prompt",
                            )
                            yield self._textarea_field(
                                "Persona definitions JSON (key -> name/description/prompt)",
                                "settings-persona-definitions",
                            )
                            yield self._textarea_field(
                                "Trusted persona repos whitelist JSON (owner/repo list)",
                                "settings-persona-repo-whitelist",
                            )
                            yield self._text_field(
                                "Persona repo (owner/repo)",
                                "settings-persona-repo",
                            )
                            yield self._text_field(
                                "Persona preset path",
                                "settings-persona-path",
                            )
                            yield self._text_field(
                                "Persona ref (optional)",
                                "settings-persona-ref",
                            )
                            yield Static(
                                "[bold]Ctrl+A[/] audit  "
                                "[bold]Ctrl+I[/] import  "
                                "[bold]Ctrl+E[/] export",
                                classes="modal-action-hint settings-persona-hint",
                            )
                            yield Static("", id="settings-persona-status")
                        with Vertical(id="settings-pane-models", classes="settings-pane"):
                            yield self._text_field(
                                "Claude default model",
                                "settings-default-model-claude",
                            )
                            yield self._text_field(
                                "OpenAI default model",
                                "settings-default-model-openai",
                            )

            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    "Ctrl+S save  Ctrl+. advanced  / search  Esc close",
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
        default_agent = (
            settings.get("default_agent_backend") or settings.get("default_agent") or "claude-code"
        )
        agent_select = self.query_one("#settings-default-agent", Select)
        available_agents = list_registered_agent_backends()
        if default_agent in available_agents:
            agent_select.value = default_agent
        elif available_agents:
            agent_select.value = available_agents[0]
        else:
            agent_select.value = "claude-code"

        pair_launcher = settings.get("pair_launcher", "tmux")
        pair_select = self.query_one("#settings-pair-launcher", Select)
        pair_select.value = (
            pair_launcher
            if pair_launcher
            in {"tmux", "nvim", "vscode", "cursor", "windsurf", "kiro", "antigravity"}
            else "tmux"
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
        theme_select.value = theme if theme in {"", "kagan", "kagan-256"} else ""

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
        self.query_one("#settings-skip-pair-instructions", Switch).value = _is_enabled(
            settings.get("skip_pair_instructions_popup"),
            default=False,
        )

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

        # Prompt customization fields
        default_orchestrator_prompt = _ORCHESTRATOR_SYSTEM_PROMPT.strip()
        default_task_prompt = self._default_task_prompt().strip()
        default_review_prompt = self._default_review_prompt().strip()
        self.query_one("#settings-custom-orchestrator-prompt", TextArea).text = settings.get(
            "custom_orchestrator_prompt", default_orchestrator_prompt
        )
        self.query_one("#settings-custom-task-prompt", TextArea).text = settings.get(
            "custom_task_prompt", default_task_prompt
        )
        self.query_one("#settings-custom-review-prompt", TextArea).text = settings.get(
            "custom_review_prompt", default_review_prompt
        )
        self.query_one("#settings-persona-definitions", TextArea).text = settings.get(
            PERSONA_DEFINITIONS_KEY,
            serialize_persona_definitions(load_persona_definitions(settings)),
        )
        self.query_one("#settings-persona-repo-whitelist", TextArea).text = settings.get(
            PERSONA_USER_WHITELIST_KEY,
            "[]",
        )
        self.query_one("#settings-persona-path", Input).value = ".kagan/personas.json"
        self.query_one("#settings-persona-status", Static).update(
            "Audit first. Import from trusted repos only."
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
            "general": self.query_one("#settings-pane-general", Vertical),
            "automation": self.query_one("#settings-pane-automation", Vertical),
            "merge": self.query_one("#settings-pane-merge", Vertical),
            "appearance": self.query_one("#settings-pane-appearance", Vertical),
            "worktree": self.query_one("#settings-pane-worktree", Vertical),
            "git_identity": self.query_one("#settings-pane-git_identity", Vertical),
            "prompts": self.query_one("#settings-pane-prompts", Vertical),
            "models": self.query_one("#settings-pane-models", Vertical),
        }
        for pane_id, pane in panes.items():
            visible = pane_id == category_id
            pane.display = visible
            pane.set_class(visible, "active-pane")
        if category_id == "prompts":
            self.call_after_refresh(self._focus_primary_prompt_editor)

    def _focus_primary_prompt_editor(self) -> None:
        editor = self.query_one("#settings-custom-orchestrator-prompt", TextArea)
        editor.focus()
        editor.move_cursor(editor.document.end)

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

    async def action_save(self) -> None:
        await self._persist_settings()

    async def _persist_settings(self) -> None:
        agent_backend_value = self.query_one("#settings-default-agent", Select).value
        default_agent_backend = (
            agent_backend_value if isinstance(agent_backend_value, str) else "claude-code"
        )

        pair_launcher_value = self.query_one("#settings-pair-launcher", Select).value
        strategy_value = self.query_one("#settings-base-ref-strategy", Select).value
        base_branch = self.query_one("#settings-default-base-branch", Input).value.strip() or "main"
        theme_value = self.query_one("#settings-theme", Select).value
        auto_review = self.query_one("#settings-auto-review", Switch).value
        open_last_project = self.query_one("#settings-open-last-project", Switch).value
        auto_init_repo = self.query_one("#settings-auto-init-repo", Switch).value
        auto_init_commit = self.query_one("#settings-auto-init-commit", Switch).value
        require_review_approval = self.query_one("#settings-require-review-approval", Switch).value
        serialize_merges = self.query_one("#settings-serialize-merges", Switch).value
        skip_pair_instructions = self.query_one("#settings-skip-pair-instructions", Switch).value

        git_mode_value = self.query_one("#settings-git-user-mode", Select).value
        git_mode = git_mode_value if isinstance(git_mode_value, str) else "kagan_agent"
        git_user_name = self.query_one("#settings-git-user-name", Input).value.strip()
        git_user_email = self.query_one("#settings-git-user-email", Input).value.strip()
        default_model_claude = self.query_one("#settings-default-model-claude", Input).value.strip()
        default_model_openai = self.query_one("#settings-default-model-openai", Input).value.strip()

        pair_launcher = pair_launcher_value if isinstance(pair_launcher_value, str) else "tmux"
        strategy = strategy_value if isinstance(strategy_value, str) else "local_if_ahead"
        theme = theme_value if isinstance(theme_value, str) else ""

        updates: dict[str, str] = {
            "default_agent_backend": default_agent_backend,
            "default_agent": default_agent_backend,
            "pair_launcher": pair_launcher,
            "default_base_branch": base_branch,
            "worktree_base_ref_strategy": strategy,
            "theme": theme,
            "auto_review": "true" if auto_review else "false",
            "open_last_project_on_startup": "true" if open_last_project else "false",
            "auto_init_git_repo": "true" if auto_init_repo else "false",
            "auto_init_git_initial_commit": "true" if auto_init_commit else "false",
            "require_review_approval": "true" if require_review_approval else "false",
            "serialize_merges": "true" if serialize_merges else "false",
            "skip_pair_instructions_popup": "true" if skip_pair_instructions else "false",
            "git_user_mode": git_mode,
        }

        # Prompt customization
        orchestrator_prompt = self.query_one(
            "#settings-custom-orchestrator-prompt", TextArea
        ).text.strip()
        task_prompt = self.query_one("#settings-custom-task-prompt", TextArea).text.strip()
        review_prompt = self.query_one("#settings-custom-review-prompt", TextArea).text.strip()
        persona_definitions = self.query_one("#settings-persona-definitions", TextArea).text.strip()
        persona_repo_whitelist = self.query_one(
            "#settings-persona-repo-whitelist", TextArea
        ).text.strip()
        updates["custom_orchestrator_prompt"] = (
            ""
            if orchestrator_prompt == _ORCHESTRATOR_SYSTEM_PROMPT.strip()
            else orchestrator_prompt
        )
        updates["custom_task_prompt"] = (
            "" if task_prompt == self._default_task_prompt().strip() else task_prompt
        )
        updates["custom_review_prompt"] = (
            "" if review_prompt == self._default_review_prompt().strip() else review_prompt
        )
        updates[PERSONA_DEFINITIONS_KEY] = persona_definitions
        updates[PERSONA_USER_WHITELIST_KEY] = persona_repo_whitelist or "[]"
        updates["default_model_claude"] = default_model_claude
        updates["default_model_openai"] = default_model_openai
        if git_user_name:
            updates["git_user_name"] = git_user_name
        if git_user_email:
            updates["git_user_email"] = git_user_email

        await self.kagan_app.core.settings.set(updates)
        self.dismiss(None)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def _persona_params(self) -> tuple[str, str, str | None]:
        repo = self.query_one("#settings-persona-repo", Input).value.strip().lower()
        path = (
            self.query_one("#settings-persona-path", Input).value.strip() or ".kagan/personas.json"
        )
        ref_raw = self.query_one("#settings-persona-ref", Input).value.strip()
        return repo, path, ref_raw or None

    def _persona_status(self, message: str) -> None:
        self.query_one("#settings-persona-status", Static).update(message)

    async def action_persona_audit(self) -> None:
        repo, path, ref = self._persona_params()
        if not repo:
            self._persona_status("Set Persona repo first (owner/repo).")
            return
        report = await self.kagan_app.core.persona_presets.audit_repo(repo=repo, path=path, ref=ref)
        self._persona_status(
            f"Audit {report['risk_level']}: {report['persona_count']} personas from {repo}"
        )

    async def action_persona_import(self) -> None:
        repo, path, ref = self._persona_params()
        if not repo:
            self._persona_status("Set Persona repo first (owner/repo).")
            return
        result = await self.kagan_app.core.persona_presets.import_from_github(
            repo=repo,
            path=path,
            ref=ref,
            allow_untrusted=False,
            acknowledge_risk=False,
            merge_mode="merge",
        )
        settings = await self.kagan_app.core.settings.get()
        self.query_one("#settings-persona-definitions", TextArea).text = settings.get(
            PERSONA_DEFINITIONS_KEY,
            serialize_persona_definitions(load_persona_definitions(settings)),
        )
        self._persona_status(
            f"Imported {len(result['imported'])} personas from {repo} ({result['trusted']=})"
        )

    async def action_persona_export(self) -> None:
        repo, path, _ = self._persona_params()
        if not repo:
            self._persona_status("Set Persona repo first (owner/repo).")
            return
        persona_definitions = self.query_one("#settings-persona-definitions", TextArea).text.strip()
        persona_repo_whitelist = self.query_one(
            "#settings-persona-repo-whitelist", TextArea
        ).text.strip()
        await self.kagan_app.core.settings.set(
            {
                PERSONA_DEFINITIONS_KEY: persona_definitions,
                PERSONA_USER_WHITELIST_KEY: persona_repo_whitelist or "[]",
            }
        )
        result = await self.kagan_app.core.persona_presets.export_to_github(repo=repo, path=path)
        self._persona_status(
            f"Exported {result['persona_count']} personas to {result['repo']}:{result['path']}"
        )

    def action_focus_search(self) -> None:
        self.query_one("#settings-search-input", Input).focus()

    async def action_dismiss(self, result: None = None) -> None:
        self.dismiss(result)

    @staticmethod
    def _default_task_prompt() -> str:
        return """Task: <task title>

Description:
<task description>

Acceptance Criteria (EVERY item must pass):
- <criterion 1>
- <criterion 2>

EXPECTED OUTCOME:
All acceptance criteria above are satisfied. Tests pass. No regressions.

MUST DO:
- Commit ALL changes before signaling completion.
- Run the project's test/lint commands if they exist.
- Write a clear commit message explaining WHY, not just what.

After changing files, run:
git add -A
git -c user.name=\"kagan-agent\" -c user.email=\"agent@kagan.local\" \\
  -c commit.gpgsign=false commit -m \"feat: explain why this change was needed\"

MUST NOT DO:
- Do NOT modify files outside the scope of this task.
- Do NOT delete or skip existing tests to make the build pass.
- Do NOT suppress type errors or linter warnings.
- Do NOT leave uncommitted changes.

Only signal completion after committing.
If blocked, explain the reason and signal blocked."""

    @staticmethod
    def _default_review_prompt() -> str:
        return """Review task <task_id>.

<review-protocol>
1. Retrieve the task with task_get to read its acceptance criteria.
2. If the task has NO acceptance criteria, STOP. Respond with:
   'This task has no acceptance criteria — manual human review required.'
   Do NOT approve or reject.
3. If acceptance criteria exist, verify EACH criterion:
   - Check the diff/code changes for evidence that the criterion is met.
   - Mark each criterion as PASS or FAIL with a one-line justification.
4. Review code quality: bugs, missing edge cases, style violations.
5. Verdict:
   - ALL criteria PASS and no blocking issues -> approve.
   - ANY criterion FAIL or blocking issue -> reject with specific feedback.
</review-protocol>"""
