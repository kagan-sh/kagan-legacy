import inspect
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from loguru import logger
from textual.app import App, SystemCommand
from textual.screen import Screen

from kagan.core import KaganCore
from kagan.core.errors import KaganError, NotFoundError
from kagan.core.models import Project
from kagan.tui.keybindings import APP_BINDINGS
from kagan.tui.orchestrator_sessions import TuiOrchestratorSessionStore
from kagan.tui.screens.agent_picker import AgentPickerModal
from kagan.tui.screens.confirm import ConfirmModal
from kagan.tui.screens.gateway import PairInstructionsModal  # noqa: F401
from kagan.tui.screens.help import HelpModal
from kagan.tui.screens.kanban import KanbanScreen
from kagan.tui.screens.repo_picker import RepoPickerModal
from kagan.tui.screens.session_dashboard import SessionDashboardScreen
from kagan.tui.screens.settings import SettingsModal
from kagan.tui.screens.setup import OnboardingFlow
from kagan.tui.screens.task_screen import TaskScreen
from kagan.tui.screens.welcome import WelcomeScreen
from kagan.tui.textual_compat import apply_textual_compat_workarounds
from kagan.tui.theme import KAGAN_THEME, KAGAN_THEME_256


def _is_enabled(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


class KaganApp(App[None]):
    BINDINGS = APP_BINDINGS

    CSS_PATH = [
        "styles/app.tcss",
        "styles/kanban.tcss",
        "styles/chat.tcss",
        "styles/session_dashboard.tcss",
        "styles/task_screen.tcss",
    ]

    SCREENS = {
        "welcome-screen": WelcomeScreen,
        "kanban-screen": KanbanScreen,
        "session-dashboard-screen": SessionDashboardScreen,
        "repo-picker-modal": RepoPickerModal,
        "agent-picker-modal": AgentPickerModal,
        "settings-modal": SettingsModal,
        "setup-flow": OnboardingFlow,
        "help-modal": HelpModal,
        "task-screen": TaskScreen,
    }

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        startup_chat_session_id: str | None = None,
        **kwargs,
    ) -> None:
        apply_textual_compat_workarounds()
        super().__init__(**kwargs)
        self.core = KaganCore(db_path=db_path)
        self.orchestrator_sessions = TuiOrchestratorSessionStore(
            self.core,
            startup_session_id=startup_chat_session_id,
        )
        self.project: Project | None = None
        self.selected_repo_id: str | None = None
        self.selected_repo_name: str | None = None

        # Register themes in __init__ so the correct theme is visible from first paint.
        self.register_theme(KAGAN_THEME)
        self.register_theme(KAGAN_THEME_256)
        self.theme = KAGAN_THEME.name

    async def on_mount(self) -> None:
        await self._route_startup()
        self.run_worker(self._startup_cleanup(), exclusive=False)

    def on_unmount(self) -> None:
        self.core.close()

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        for command in super().get_system_commands(screen):
            if command.title == "Keys":
                continue
            yield command

    async def _route_startup(self) -> None:
        settings = await self.core.settings.get()
        last_project_id = settings.get("ui.last_project_id")
        open_last_project = _is_enabled(
            settings.get("open_last_project_on_startup"),
            default=False,
        )
        if open_last_project and last_project_id:
            try:
                project = await self.core.projects.get(last_project_id)
            except NotFoundError:
                # Project was deleted, clear the setting
                await self.core.settings.set({"ui.last_project_id": None})
                self.push_screen("welcome-screen")
                return
            except KaganError as exc:
                logger.warning("Failed to load last project: {}", exc)
                self.push_screen("welcome-screen")
                return
            await self.activate_project(project)
            self.push_screen("kanban-screen")
            return
        self.push_screen("welcome-screen")

    async def activate_project(self, project: Project) -> None:
        await self.core.projects.set_active(project.id)
        self.project = project
        settings = await self.core.settings.get()
        selected_repo_id = settings.get(self._repo_setting_key(project.id)) or None
        repos = await self.core.projects.repos(project.id)
        if selected_repo_id and any(repo.id == selected_repo_id for repo in repos):
            self.selected_repo_id = selected_repo_id
            self.selected_repo_name = next(
                (repo.name for repo in repos if repo.id == selected_repo_id),
                None,
            )
        elif repos:
            self.selected_repo_id = repos[0].id
            self.selected_repo_name = repos[0].name
            await self.remember_selected_repo(repos[0].id)
        else:
            self.selected_repo_id = None
            self.selected_repo_name = None
        await self.core.settings.set({"ui.last_project_id": project.id})

    async def remember_selected_repo(self, repo_id: str | None) -> None:
        if self.project is None:
            self.selected_repo_id = repo_id
            self.selected_repo_name = None
            return
        self.selected_repo_id = repo_id
        repos = await self.core.projects.repos(self.project.id)
        self.selected_repo_name = next((repo.name for repo in repos if repo.id == repo_id), None)
        value = repo_id or ""
        await self.core.settings.set({self._repo_setting_key(self.project.id): value})

    def _repo_setting_key(self, project_id: str) -> str:
        return f"ui.selected_repo.{project_id}"

    async def _startup_cleanup(self) -> None:
        """Remove orphaned worktrees left from prior sessions (best-effort)."""
        import contextlib

        with contextlib.suppress(KaganError, OSError, RuntimeError):
            removed = await self.core.worktrees.cleanup_orphans()
            if removed:
                from loguru import logger

                logger.debug("Startup: removed {} orphaned worktree(s)", removed)

    def _kanban_screen(self) -> KanbanScreen | None:
        if isinstance(self.screen, KanbanScreen):
            return self.screen
        return None

    def action_toggle_chat(self) -> None:
        screen = self._kanban_screen()
        if screen is not None:
            screen.action_toggle_chat()

    def action_peek_task(self) -> None:
        screen = self._kanban_screen()
        if screen is not None:
            screen.action_peek_task()

    def action_review_task(self) -> None:
        screen = self._kanban_screen()
        if screen is not None:
            screen.action_review_task()

    def action_new_task(self) -> None:
        screen = self._kanban_screen()
        if screen is not None:
            screen.action_new_task()
            return
        if isinstance(self.screen, WelcomeScreen):
            self.screen.action_new_project()

    async def action_quit(self) -> None:
        settings = await self.core.settings.get()
        if not _is_enabled(settings.get("confirm_quit"), default=True):
            self.exit()
            return

        def _on_confirm(confirmed: bool) -> None:
            if confirmed:
                self.exit()

        self.push_screen(
            ConfirmModal(
                title="Quit Kagan",
                message="Are you sure you want to shut down the TUI?",
                confirm_label="Quit",
                cancel_label="Cancel",
            ),
            callback=_on_confirm,
        )

    async def action_open_repo_picker(self) -> None:
        await self._open_repo_picker()

    def action_open_settings(self) -> None:
        screen = self._kanban_screen()
        if screen is not None:
            screen.action_open_settings()

    async def action_open_orchestrator_chat(self) -> None:
        handler = getattr(self.screen, "action_open_orchestrator_chat", None)
        if callable(handler):
            result: Any = handler()
            if inspect.isawaitable(result):
                await result

    async def action_open_task_chat(self) -> None:
        handler = getattr(self.screen, "action_open_task_chat", None)
        if callable(handler):
            result: Any = handler()
            if inspect.isawaitable(result):
                await result

    def action_show_help(self) -> None:
        self.push_screen("help-modal")

    def action_toggle_debug_log(self) -> None:
        """Toggle the debug log viewer (F12). Stub for future implementation."""
        self.notify("Debug log not yet implemented.", severity="information")

    async def action_open_project_selector(self) -> None:
        """Return to the project selector (welcome screen)."""
        self.switch_screen("welcome-screen")

    async def action_open_repo_selector(self) -> None:
        """Open the repository selector for the active project."""
        await self._open_repo_picker()

    async def _open_repo_picker(self) -> None:
        if self.project is None:
            self.notify("Open a project before selecting a repository.", severity="warning")
            return
        self.push_screen(RepoPickerModal())
