from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, cast

from textual import events, on
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import Screen
from textual.widgets import Button, OptionList, Static

from kagan.chat.sessions import get_chat_session
from kagan.core.errors import KaganError, SessionError
from kagan.core.models import Project
from kagan.tui.keybindings import WELCOME_BINDINGS, get_key_for_action
from kagan.tui.screens.confirm import ConfirmModal
from kagan.tui.screens.session_resume_modal import (
    RecentSessionSelection,
    SessionResumeModal,
)
from kagan.tui.screens.setup import OnboardingFlow
from kagan.tui.widgets.hint_bar import KeybindingHint

if TYPE_CHECKING:
    from kagan.core.models import Repository
    from kagan.tui.app import KaganApp


_WELCOME_LOGO = """\
█▄▀  ▄▀▄  █▀▀  ▄▀▄  █▄  █
█▀▄  █▀█  █▄█  █▀█  █ ▀▄█"""


class WelcomeScreen(Screen[None]):
    BINDINGS = [*WELCOME_BINDINGS]

    def __init__(
        self,
        suggest_cwd: bool = True,
        cwd_path: str | None = None,
        cwd_is_git_repo: bool = False,
        highlight_recent: bool = False,
    ) -> None:
        super().__init__(id="welcome-screen")
        self._projects: list[Project] = []
        self._repos_by_project_id: dict[str, list[Repository]] = {}
        resolved_cwd_path = cwd_path or str(Path.cwd())
        resolved_cwd_is_git = cwd_is_git_repo or (Path(resolved_cwd_path) / ".git").exists()

        self._suggest_cwd = suggest_cwd
        self._cwd_path = resolved_cwd_path
        self._cwd_is_git_repo = resolved_cwd_is_git
        self._highlight_recent = highlight_recent

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        with Container(id="welcome-container"):
            yield Static(_WELCOME_LOGO, id="logo")

            if self._suggest_cwd and self._cwd_path:
                with Container(id="cwd-suggestion-banner"):
                    if self._cwd_is_git_repo:
                        yield Static(
                            "Create a project here to start tracking tasks in this codebase",
                            id="cwd-title",
                        )
                    else:
                        yield Static(
                            "Create a project here to start tracking tasks — git will initialize",
                            id="cwd-title",
                        )
                    yield Static(self._cwd_path, id="cwd-path")
                    yield Static(
                        "",
                        classes="modal-action-hint",
                        id="cwd-actions-hint",
                    )

            yield Static("Recent Projects", id="recent-header")
            yield Static("Loading projects…", id="projects-loading")
            yield OptionList(id="project-list")
            yield Button("Resume recent session", id="welcome-resume-session")
            yield Static(
                "Welcome to Kagan! Create your first project to get started.",
                id="first-launch-welcome",
            )
            yield Static(
                "No recent projects. Create a new project or open a folder.",
                id="empty-state",
            )
            yield KeybindingHint(id="welcome-hint")

    async def on_mount(self) -> None:
        await self._reload_projects()
        await self._maybe_hide_cwd_banner()
        self._update_cwd_banner_hint()
        self._update_keybinding_hints()

    async def on_screen_resume(self) -> None:
        await self._reload_projects()
        await self._maybe_hide_cwd_banner()
        self._update_cwd_banner_hint()
        self._update_keybinding_hints()

    async def _maybe_hide_cwd_banner(self) -> None:
        if not self._suggest_cwd or not self._cwd_path:
            return
        banner = self.query_one("#cwd-suggestion-banner", Container)
        resolved = str(Path(self._cwd_path).resolve())
        existing = await self.kagan_app.core.projects.find_by_repo(resolved)
        if existing is not None:
            banner.display = False

    async def action_reload_projects(self) -> None:
        await self._reload_projects()

    async def _reload_projects(self) -> None:
        self._projects = sorted(
            await self.kagan_app.core.projects.list(),
            key=lambda project: project.updated_at,
            reverse=True,
        )
        self._repos_by_project_id.clear()
        for project in self._projects:
            repos = await self.kagan_app.core.projects.repos(project.id)
            self._repos_by_project_id[project.id] = repos

        option_list = self.query_one("#project-list", OptionList)
        option_list.clear_options()
        self.query_one("#projects-loading", Static).display = False
        empty_state = self.query_one("#empty-state", Static)
        first_launch = self.query_one("#first-launch-welcome", Static)

        if self._projects:
            option_list.display = True
            empty_state.display = False
            first_launch.display = False
            option_list.add_options(
                [
                    self._project_label(project, index)
                    for index, project in enumerate(self._projects)
                ]
            )
            option_list.highlighted = 0
            self._update_cwd_banner_hint()
            self._update_keybinding_hints()
            return

        option_list.display = False
        empty_state.display = not self._suggest_cwd
        first_launch.display = True
        self._update_cwd_banner_hint()
        self._update_keybinding_hints()

    def _project_label(self, project: Project, index: int) -> str:
        shortcut = f"[{index + 1}]" if index < 9 else "   "
        repo_count = len(self._repos_by_project_id.get(project.id, []))
        repo_label = "repo" if repo_count == 1 else "repos"
        updated = self._relative_timestamp(project.updated_at)
        return f"{shortcut} {project.name} · {repo_count} {repo_label} · {updated}"

    def _update_keybinding_hints(self) -> None:
        hint_widget = self.query_one("#welcome-hint", KeybindingHint)
        escape_label = "back" if self.kagan_app.project is not None else "quit"
        if self._projects:
            enter_label = "open"
        elif self._cwd_banner_visible():
            enter_label = "create here"
        else:
            enter_label = "new project"
        hints = [
            (get_key_for_action(WELCOME_BINDINGS, "open_selected", "Enter"), enter_label),
            (
                get_key_for_action(WELCOME_BINDINGS, "move_selection_down", "Down / j"),
                "navigate",
            ),
        ]
        if self._cwd_banner_visible():
            hints.append(
                (get_key_for_action(WELCOME_BINDINGS, "create_from_here", "c"), "create here")
            )
        hints.extend(
            [
                (get_key_for_action(WELCOME_BINDINGS, "new_project", "n"), "new"),
                (get_key_for_action(WELCOME_BINDINGS, "open_folder", "o"), "open folder"),
                (get_key_for_action(WELCOME_BINDINGS, "delete_project", "x"), "delete"),
                (",", "settings"),
                (get_key_for_action(WELCOME_BINDINGS, "quit", "Esc"), escape_label),
            ]
        )
        hint_widget.show_hints(hints)

    def _update_cwd_banner_hint(self) -> None:
        if not self._cwd_banner_visible():
            return
        hint = self.query_one("#cwd-actions-hint", Static)
        if self._projects:
            hint.update(
                "[bold]Enter[/] open selected  [bold]c[/] create project here  [bold]Esc[/] dismiss"
            )
            return
        hint.update("[bold]Enter[/] create project here  [bold]Esc[/] dismiss")

    def action_settings(self) -> None:
        self.app.push_screen("settings-modal", callback=self._on_settings_dismissed)

    @on(Button.Pressed, "#welcome-resume-session")
    def _on_resume_recent_session_pressed(self, _: Button.Pressed) -> None:
        self.app.push_screen(SessionResumeModal(), callback=self._on_recent_session_selected)

    def _on_recent_session_selected(self, selection: RecentSessionSelection | None) -> None:
        if selection is None:
            return
        self.run_worker(self._resume_recent_session(selection), exit_on_error=False)

    def _on_settings_dismissed(self, _result: None) -> None:
        from kagan.tui.app import KaganApp

        app = self.app
        if isinstance(app, KaganApp):
            app.run_worker(app._apply_saved_theme(), exclusive=False)

    def action_move_up(self) -> None:
        option_list = self.query_one("#project-list", OptionList)
        if not self._projects:
            return
        current = option_list.highlighted if option_list.highlighted is not None else 0
        option_list.highlighted = max(0, current - 1)

    def action_move_down(self) -> None:
        option_list = self.query_one("#project-list", OptionList)
        if not self._projects:
            return
        current = option_list.highlighted if option_list.highlighted is not None else 0
        option_list.highlighted = min(len(self._projects) - 1, current + 1)

    def action_focus_next(self) -> None:
        self.focus_next()

    def action_focus_prev(self) -> None:
        self.focus_previous()

    async def action_quit(self) -> None:
        await self.kagan_app.action_quit()

    async def _create_project_from_cwd(self) -> None:
        if not self._cwd_path:
            return
        cwd = Path(self._cwd_path)
        existing_project = await self.kagan_app.core.projects.find_by_repo(str(cwd.resolve()))
        if existing_project is not None:
            await self.kagan_app.activate_project(existing_project)
            self.app.switch_screen("kanban-screen")
            return
        try:
            project = await self.kagan_app.core.projects.create(
                cwd.name, repo_paths=[self._cwd_path]
            )
        except SessionError as exc:
            self.app.notify(
                f"Unable to create project from current folder: {exc}", severity="error"
            )
            return
        await self.kagan_app.activate_project(project)
        self.app.switch_screen("kanban-screen")

    def _dismiss_cwd_banner(self) -> None:
        self.query_one("#cwd-suggestion-banner", Container).display = False
        self._update_cwd_banner_hint()

    async def action_open_selected(self) -> None:
        if not self._projects and self._cwd_banner_visible():
            await self._create_project_from_cwd()
            return
        if not self._projects:
            self.action_new_project()
            return
        option_list = self.query_one("#project-list", OptionList)
        await self.action_open_project(str(self._selected_project_index(option_list)))

    async def action_create_from_here(self) -> None:
        if not self._cwd_banner_visible():
            return
        await self._create_project_from_cwd()

    @staticmethod
    def _selected_project_index(option_list: OptionList) -> int:
        selected_index = option_list.highlighted
        if selected_index is None:
            return 0
        return selected_index

    async def action_open_project_1(self) -> None:
        await self._open_project("0")

    async def action_open_project_2(self) -> None:
        await self._open_project("1")

    async def action_open_project_3(self) -> None:
        await self._open_project("2")

    async def action_open_project_4(self) -> None:
        await self._open_project("3")

    async def action_open_project_5(self) -> None:
        await self._open_project("4")

    async def action_open_project_6(self) -> None:
        await self._open_project("5")

    async def action_open_project_7(self) -> None:
        await self._open_project("6")

    async def action_open_project_8(self) -> None:
        await self._open_project("7")

    async def action_open_project_9(self) -> None:
        await self._open_project("8")

    async def _open_project(self, index: str) -> None:
        if not self._projects:
            return
        try:
            selected_index = int(index)
        except ValueError:
            return
        if selected_index < 0 or selected_index >= len(self._projects):
            return
        project = self._projects[selected_index]
        await self.kagan_app.activate_project(project)
        self.app.switch_screen("kanban-screen")

    async def action_open_project(self, index: str) -> None:
        await self._open_project(index)

    def action_new_project(self) -> None:
        self.app.push_screen(OnboardingFlow(mode="new-project"))

    def action_open_folder(self) -> None:
        self.app.push_screen(
            OnboardingFlow(
                mode="open-folder",
                initial_repo_path=self._cwd_path if self._cwd_is_git_repo else None,
            )
        )

    async def _resume_recent_session(self, selection: RecentSessionSelection) -> None:
        try:
            project = await self.kagan_app.core.projects.get(selection.project_id)
            session = await get_chat_session(self.kagan_app.core, selection.session_id)
            if session is None:
                raise KaganError("Selected session is no longer available.")
            await self.kagan_app.activate_project(project)
            await self.kagan_app.orchestrator_sessions.switch(
                f"orchestrator:{selection.session_id}"
            )
        except KaganError as exc:
            self.app.notify(f"Unable to resume session: {exc}", severity="error")
            return
        self.app.switch_screen("kanban-screen")

    async def action_delete_project(self) -> None:
        project = self._get_selected_project()
        if project is None:
            return

        captured_id = project.id
        captured_name = project.name

        async def _on_confirmed(confirmed: bool) -> None:
            if not confirmed:
                return
            try:
                await self.kagan_app.core.projects.delete(captured_id)
                self.app.notify(f"Deleted '{captured_name}'")
                await self._reload_projects()
            except (KaganError, OSError, RuntimeError, ValueError) as exc:
                self.app.notify(f"Failed to delete project: {exc}", severity="error")

        self.app.push_screen(
            ConfirmModal(
                title="Delete Project",
                message=f"Delete project '{captured_name}' and all its tasks?",
            ),
            callback=_on_confirmed,
        )

    def _get_selected_project(self) -> Project | None:
        if not self._projects:
            return None
        option_list = self.query_one("#project-list", OptionList)
        index = self._selected_project_index(option_list)
        if index < 0 or index >= len(self._projects):
            return None
        return self._projects[index]

    async def on_option_list_option_highlighted(self, event: OptionList.OptionHighlighted) -> None:
        if event.option_list.id != "project-list":
            return

    @on(OptionList.OptionSelected, "#project-list")
    async def _on_project_selected(self, _: OptionList.OptionSelected) -> None:
        option_list = self.query_one("#project-list", OptionList)
        selected_index = option_list.highlighted
        if selected_index is None:
            selected_index = 0
        await self.action_open_project(str(selected_index))

    async def on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            event.prevent_default()
            event.stop()
            await self.action_open_selected()
            return
        if event.key == "escape":
            if self._suggest_cwd and self._cwd_path:
                banner = self.query_one("#cwd-suggestion-banner", Container)
                if banner.display:
                    event.prevent_default()
                    event.stop()
                    self._dismiss_cwd_banner()
                    self._update_keybinding_hints()
                    return
        if event.key == "n":
            event.prevent_default()
            event.stop()
            self.action_new_project()
            return
        if event.key == "c":
            event.prevent_default()
            event.stop()
            await self.action_create_from_here()
            return
        if event.key == "o":
            event.prevent_default()
            event.stop()
            self.action_open_folder()
            return
        if event.key == "x":
            event.prevent_default()
            event.stop()
            await self.action_delete_project()
            return
        if event.key == ",":
            event.prevent_default()
            event.stop()
            self.action_settings()
            return
        if event.key == "r":
            event.prevent_default()
            event.stop()
            await self.action_reload_projects()

    def _relative_timestamp(self, value: datetime) -> str:
        delta = datetime.now(UTC) - value.astimezone(UTC)
        seconds = max(int(delta.total_seconds()), 0)
        if seconds < 60:
            return "just now"
        minutes = seconds // 60
        if minutes < 60:
            return f"{minutes}m ago"
        hours = minutes // 60
        if hours < 24:
            return f"{hours}h ago"
        days = hours // 24
        if days < 30:
            return f"{days}d ago"
        months = days // 30
        if months < 12:
            return f"{months}mo ago"
        years = months // 12
        return f"{years}y ago"

    def _cwd_banner_visible(self) -> bool:
        if not self._suggest_cwd or not self._cwd_path:
            return False
        banner = self.query_one("#cwd-suggestion-banner", Container)
        return bool(banner.display)
