from pathlib import Path
from typing import TYPE_CHECKING, cast

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Footer, Input, Select, Static, Switch, TextArea
from textual.widgets._option_list import Option, OptionList

from kagan.cli.chat import resolve_default_agent_backend
from kagan.core import detect_dotfile_overrides
from kagan.tui._utils import is_enabled as _is_enabled
from kagan.tui.keybindings import SETTINGS_BINDINGS, SETTINGS_COMMAND_BINDINGS
from kagan.tui.widgets.settings_fields import (
    CATEGORIES,
    CATEGORY_FIELDS,
    SettingCategory,
    SettingFieldSpec,
    build_agent_backend_options,
    valid_theme_names,
)

if TYPE_CHECKING:
    from textual.timer import Timer

    from kagan.tui.app import KaganApp


class CategoryList(OptionList):
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
            c
            for c in self._categories
            if self._query in c.name.lower()
            or any(self._query in t.lower() for t in c.search_terms)
        ]

    def _render_options(self, preferred_category_id: str | None = None) -> None:
        prev = self.highlighted
        self.clear_options()
        self.add_options([Option(c.name, id=c.id) for c in self._visible])
        if not self._visible:
            self.highlighted = None
            return
        if preferred_category_id is not None:
            for i, c in enumerate(self._visible):
                if c.id == preferred_category_id:
                    self.highlighted = i
                    return
        if prev is not None and 0 <= prev < len(self._visible):
            self.highlighted = prev
            return
        self.highlighted = 0


class SettingsModal(ModalScreen[None]):
    BINDINGS = [*SETTINGS_BINDINGS, *SETTINGS_COMMAND_BINDINGS]

    def __init__(self) -> None:
        super().__init__(id="settings-modal")
        self._auto_save_timer: Timer | None = None
        self._categories = CATEGORIES
        self._category_fields = CATEGORY_FIELDS
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
                        tooltip="Type to filter categories",
                    )
                yield Static("", id="settings-search-status")
            with Horizontal(id="settings-main"):
                with Vertical(id="settings-nav-pane"):
                    yield CategoryList(self._visible_nav_categories())
                    yield Button(
                        "Show advanced ▸",
                        id="settings-advanced-toggle",
                        tooltip="Show or hide advanced settings",
                    )
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
                yield Button("Close", id="settings-close", tooltip="Close settings (Esc)")
            with Horizontal(classes="modal-action-hint-row"):
                yield Static(
                    "Auto-saved  ·  / search  Esc close",
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
        def _sw(wid: str, key: str, *, default: bool) -> None:
            self.query_one(wid, Switch).value = _is_enabled(settings.get(key), default=default)

        def _sel(wid: str, value: str, allowed: set[str], fallback: str) -> None:
            self.query_one(wid, Select).value = value if value in allowed else fallback

        available_agents = {v for _, v in build_agent_backend_options()}
        default_agent = resolve_default_agent_backend(settings)
        if default_agent not in available_agents:
            default_agent = resolve_default_agent_backend({})
        self.query_one("#settings-default-agent", Select).value = default_agent

        _sel(
            "#settings-review-strictness",
            settings.get("review_strictness", "balanced"),
            {"strict", "balanced", "relaxed"},
            "balanced",
        )
        _sel(
            "#settings-planning-depth",
            settings.get("planning_depth", "always"),
            {"always", "multi_task", "never"},
            "always",
        )
        _sel(
            "#settings-theme",
            settings.get("theme", ""),
            valid_theme_names(),
            "",
        )
        _sel(
            "#settings-attached-launcher",
            settings.get("attached_launcher", "tmux"),
            {"tmux", "nvim", "vscode", "cursor", "windsurf", "kiro", "antigravity"},
            "tmux",
        )
        startup_surface = settings.get("startup_default_surface") or settings.get(
            "ui.surface_chooser_last_choice", "tui"
        )
        _sel("#settings-startup-surface", startup_surface, {"tui", "web", "chat", "ask"}, "tui")
        _sel(
            "#settings-base-ref-strategy",
            settings.get("worktree_base_ref_strategy", "local_if_ahead"),
            {"local_if_ahead", "remote", "local"},
            "local_if_ahead",
        )
        _sel(
            "#settings-git-user-mode",
            settings.get("git_user_mode", "kagan_agent"),
            {"kagan_agent", "system_default", "custom"},
            "kagan_agent",
        )

        self.query_one("#settings-default-base-branch", Input).value = settings.get(
            "default_base_branch", "main"
        )
        self.query_one("#settings-git-user-name", Input).value = settings.get("git_user_name", "")
        self.query_one("#settings-git-user-email", Input).value = settings.get("git_user_email", "")
        self.query_one("#settings-additional-instructions", TextArea).text = settings.get(
            "additional_instructions", ""
        )

        _sw("#settings-auto-confirm-single", "auto_confirm_single_tasks", default=False)
        _sw("#settings-auto-review", "auto_review", default=True)
        _sw("#settings-open-last-project", "open_last_project_on_startup", default=False)
        _sw("#settings-auto-init-repo", "auto_init_git_repo", default=True)
        _sw("#settings-auto-init-commit", "auto_init_git_initial_commit", default=True)
        _sw("#settings-require-review-approval", "require_review_approval", default=False)
        _sw(
            "#settings-skip-attached-instructions",
            "skip_attached_instructions_popup",
            default=False,
        )

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
        clist = self.query_one(CategoryList)
        clist.set_categories(self._search_scope_categories(event.value))
        category_id = clist.filter_categories(event.value)
        self._mount_detail(category_id)
        self._update_search_status(event.value)

    @on(OptionList.OptionHighlighted, "#settings-nav")
    async def _on_category_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        clist = self.query_one(CategoryList)
        category_id = clist.selected_category_id()
        if category_id is None and event.option is not None and event.option.id is not None:
            category_id = event.option.id
        self._mount_detail(category_id)

    @on(Button.Pressed, "#settings-advanced-toggle")
    async def _on_advanced_toggle_pressed(self, _: Button.Pressed) -> None:
        self.action_toggle_advanced()

    @on(Button.Pressed, "#settings-close")
    def _on_close_pressed(self, _: Button.Pressed) -> None:
        self.action_cancel()

    @on(Switch.Changed)
    def _on_switch_auto_save(self, _: Switch.Changed) -> None:
        self._schedule_auto_save()

    @on(Select.Changed)
    def _on_select_auto_save(self, _: Select.Changed) -> None:
        self._schedule_auto_save()

    @on(Input.Changed)
    def _on_input_auto_save(self, event: Input.Changed) -> None:
        if event.input.id == "settings-search-input":
            return
        self._schedule_auto_save()

    @on(TextArea.Changed)
    def _on_textarea_auto_save(self, _: TextArea.Changed) -> None:
        self._schedule_auto_save()

    def _schedule_auto_save(self) -> None:
        if self._auto_save_timer is not None:
            self._auto_save_timer.stop()
        self._auto_save_timer = self.set_timer(0.4, self._fire_auto_save)

    def _fire_auto_save(self) -> None:
        self._auto_save_timer = None
        self.run_worker(self._save_all_settings(), exit_on_error=False)

    async def _save_all_settings(self) -> None:
        def _sv(wid: str, allowed: set[str], fallback: str) -> str:
            val = self.query_one(wid, Select).value
            return val if isinstance(val, str) and val in allowed else fallback

        def _bool(wid: str) -> str:
            return "true" if self.query_one(wid, Switch).value else "false"

        agent_val = self.query_one("#settings-default-agent", Select).value
        available_agents = {v for _, v in build_agent_backend_options()}
        default_agent = (
            agent_val
            if isinstance(agent_val, str) and agent_val in available_agents
            else resolve_default_agent_backend({})
        )

        updates: dict[str, str] = {
            "default_agent_backend": default_agent,
            "theme": _sv("#settings-theme", valid_theme_names(), ""),
            "review_strictness": _sv(
                "#settings-review-strictness", {"strict", "balanced", "relaxed"}, "balanced"
            ),
            "planning_depth": _sv(
                "#settings-planning-depth", {"always", "multi_task", "never"}, "always"
            ),
            "attached_launcher": _sv(
                "#settings-attached-launcher",
                {"tmux", "nvim", "vscode", "cursor", "windsurf", "kiro", "antigravity"},
                "tmux",
            ),
            "startup_default_surface": _sv(
                "#settings-startup-surface", {"tui", "web", "chat", "ask"}, "tui"
            ),
            "worktree_base_ref_strategy": _sv(
                "#settings-base-ref-strategy",
                {"local_if_ahead", "remote", "local"},
                "local_if_ahead",
            ),
            "git_user_mode": _sv(
                "#settings-git-user-mode",
                {"kagan_agent", "system_default", "custom"},
                "kagan_agent",
            ),
            "default_base_branch": (
                self.query_one("#settings-default-base-branch", Input).value.strip() or "main"
            ),
            "additional_instructions": (
                self.query_one("#settings-additional-instructions", TextArea).text.strip()
            ),
            "auto_review": _bool("#settings-auto-review"),
            "open_last_project_on_startup": _bool("#settings-open-last-project"),
            "auto_init_git_repo": _bool("#settings-auto-init-repo"),
            "auto_init_git_initial_commit": _bool("#settings-auto-init-commit"),
            "require_review_approval": _bool("#settings-require-review-approval"),
            "skip_attached_instructions_popup": _bool("#settings-skip-attached-instructions"),
            "auto_confirm_single_tasks": _bool("#settings-auto-confirm-single"),
        }

        git_user_name = self.query_one("#settings-git-user-name", Input).value.strip()
        git_user_email = self.query_one("#settings-git-user-email", Input).value.strip()
        if git_user_name:
            updates["git_user_name"] = git_user_name
        if git_user_email:
            updates["git_user_email"] = git_user_email

        await self.kagan_app.core.settings.set(updates)

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
        return [c for c in self._categories if not c.is_advanced]

    def _sync_navigation(self) -> None:
        query = self.query_one("#settings-search-input", Input).value
        clist = self.query_one(CategoryList)
        clist.set_categories(self._search_scope_categories(query))
        selected_id = clist.filter_categories(query)
        self._mount_detail(selected_id)
        self._update_advanced_toggle_label()
        self._update_search_status(query)

    def _update_advanced_toggle_label(self) -> None:
        advanced_count = sum(1 for c in self._categories if c.is_advanced)
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
            (c.name for c in self._categories if c.id == category_id),
            category_id.title(),
        )
        title.update(category_name)
        self._show_pane(category_id)

    def _show_pane(self, category_id: str | None) -> None:
        for c in self._categories:
            pane = self.query_one(f"#settings-pane-{c.id}", Vertical)
            visible = c.id == category_id
            pane.display = visible
            pane.set_class(visible, "active-pane")

    def _build_category_fields(self, category_id: str) -> list[Static | Vertical | Horizontal]:
        return [self._render_field(f) for f in self._category_fields[category_id]]

    def _render_field(self, field: SettingFieldSpec) -> Static | Vertical | Horizontal:
        if field.kind == "switch" and field.field_id is not None:
            return self._switch_field(field.label, field.field_id)
        if field.kind == "select" and field.field_id is not None:
            raw = field.options_factory() if field.options_factory is not None else field.options
            return self._select_field(field.label, field.field_id, list(raw))
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
            Input(id=field_id, classes="settings-input", tooltip=label),
            classes="settings-field-group",
        )

    def _select_field(self, label: str, field_id: str, options: list[tuple[str, str]]) -> Vertical:
        return Vertical(
            Static(label, classes="settings-field-label-top"),
            Select(
                options=options,
                id=field_id,
                allow_blank=False,
                classes="settings-select",
                tooltip=label,
            ),
            classes="settings-field-group",
        )

    def _textarea_field(self, label: str, field_id: str) -> Vertical:
        return Vertical(
            Static(label, classes="settings-field-label-top"),
            TextArea(id=field_id, classes="settings-textarea", tooltip=label),
            classes="settings-field-group",
        )

    def _switch_field(self, label: str, field_id: str) -> Horizontal:
        return Horizontal(
            Static(label, classes="settings-field-label-inline"),
            Switch(id=field_id, classes="settings-checkbox", tooltip=label),
            classes="settings-field-row",
        )

    def _update_search_status(self, query: str) -> None:
        clist = self.query_one(CategoryList)
        total = len(self._search_scope_categories(query))
        visible = clist.visible_count
        if query.strip():
            message = f"{visible}/{total} sections shown"
        else:
            mode = "including advanced" if self._show_advanced else "basic sections"
            message = f"{total} sections • {mode}; search matches category names and settings"
        self.query_one("#settings-search-status", Static).update(message)

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_focus_search(self) -> None:
        self.query_one("#settings-search-input", Input).focus()

    async def action_dismiss(self, result: None = None) -> None:
        self.dismiss(result)
