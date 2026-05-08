import inspect
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from loguru import logger
from textual.app import App, SystemCommand
from textual.binding import Binding, BindingType
from textual.screen import Screen

from kagan.cli.doctor import DoctorCheck
from kagan.core import KaganCore, install_asyncio_subprocess_exception_filter
from kagan.core.errors import KaganError, NotFoundError
from kagan.core.models import Project
from kagan.tui._utils import is_enabled as _is_enabled
from kagan.tui.keybindings import APP_BINDINGS
from kagan.tui.orchestrator_sessions import TuiOrchestratorSessionStore
from kagan.tui.screens.agent_picker import AgentPickerModal
from kagan.tui.screens.analytics import AnalyticsModal
from kagan.tui.screens.confirm import ConfirmModal
from kagan.tui.screens.doctor_modal import DoctorModal, emit_doctor_warned_telemetry_async
from kagan.tui.screens.gateway import AttachedInstructionsModal  # noqa: F401
from kagan.tui.screens.help import HelpModal
from kagan.tui.screens.kanban import KanbanScreen
from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
from kagan.tui.screens.repo_picker import RepoPickerModal
from kagan.tui.screens.session_dashboard import SessionDashboardScreen
from kagan.tui.screens.settings import SettingsModal
from kagan.tui.screens.setup import OnboardingFlow
from kagan.tui.screens.task_screen import TaskScreen
from kagan.tui.screens.workspace import WorkspaceScreen
from kagan.tui.textual_compat import apply_textual_compat_workarounds
from kagan.tui.theme import KAGAN_THEME, KAGAN_THEME_256


def _any_backend_available(checks: list[DoctorCheck]) -> bool:
    backend_detail = [
        c
        for c in checks
        if c.category == "backend" and c.name.startswith(("backend:", "agent backend:"))
    ]
    if backend_detail:
        return any(c.status == "pass" for c in backend_detail)
    backend_summary = [
        c
        for c in checks
        if c.category == "backend" and c.name in {"agent backends", "agent backend"}
    ]
    if not backend_summary:
        return True
    return any(
        c.category == "backend"
        and c.status == "pass"
        and c.name in {"agent backends", "agent backend"}
        for c in backend_summary
    )


def _has_startup_doctor_failures(checks: list[DoctorCheck]) -> bool:
    return any(c.status == "fail" for c in checks)


class KaganApp(App[None]):
    BINDINGS = APP_BINDINGS

    CSS_PATH = [
        "styles/app.tcss",
        "styles/kanban.tcss",
        "styles/chat.tcss",
        "styles/session_dashboard.tcss",
        "styles/task_screen.tcss",
        "styles/workspace.tcss",
        "screens/doctor_modal.tcss",
    ]

    SCREENS = {
        "kanban-screen": KanbanScreen,
        "orchestrator-overlay": OrchestratorOverlay,
        "session-dashboard-screen": SessionDashboardScreen,
        "repo-picker-modal": RepoPickerModal,
        "agent-picker-modal": AgentPickerModal,
        "analytics-modal": AnalyticsModal,
        "settings-modal": SettingsModal,
        "setup-flow": OnboardingFlow,
        "help-modal": HelpModal,
        "task-screen": TaskScreen,
        "workspace-screen": WorkspaceScreen,
    }

    def __init__(
        self,
        *,
        db_path: str | Path | None = None,
        startup_chat_session_id: str | None = None,
        startup_checks: list[DoctorCheck] | None = None,
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
        self._startup_checks: list[DoctorCheck] | None = startup_checks

        self.register_theme(KAGAN_THEME)
        self.register_theme(KAGAN_THEME_256)
        self.theme = KAGAN_THEME.name

    async def on_mount(self) -> None:
        install_asyncio_subprocess_exception_filter()
        await self._apply_saved_theme()
        await self._route_startup()
        self.run_worker(self._startup_cleanup(), exclusive=False)

    async def on_unmount(self) -> None:
        await self.core.aclose()

    async def _apply_saved_theme(self) -> None:
        settings = await self.core.settings.get()
        theme_name = settings.get("theme", "")
        if theme_name and theme_name in self.available_themes:
            self.theme = theme_name
        elif not theme_name:
            self.theme = KAGAN_THEME.name
        reduce_motion = _is_enabled(settings.get("reduce_motion"), default=False)
        self.set_class(reduce_motion, "reduce-motion")

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        for command in super().get_system_commands(screen):
            if command.title == "Keys":
                continue
            yield command

    async def _route_startup(self) -> None:
        checks = self._startup_checks
        if checks is not None and len(checks) > 0:
            has_fail = _has_startup_doctor_failures(checks)
            has_warn = any(c.status == "warn" for c in checks)
            if has_fail or has_warn:
                fail_count = sum(1 for c in checks if c.status == "fail")
                warn_count = sum(1 for c in checks if c.status == "warn")
                # Telemetry always fires on raw counts — we don't lose signal.
                self.run_worker(
                    emit_doctor_warned_telemetry_async(
                        self.core,
                        fail_count=fail_count,
                        warn_count=warn_count,
                    ),
                    exit_on_error=False,
                )
            if has_fail:
                self.push_screen(
                    DoctorModal(checks, allow_skip=_any_backend_available(checks)),
                    callback=self._on_doctor_modal_dismissed,
                )
                return

        settings = await self.core.settings.get()
        last_project_id = settings.get("ui.last_project_id")
        open_last = _is_enabled(settings.get("open_last_project_on_startup"), default=False)
        if open_last and last_project_id:
            try:
                project = await self.core.projects.get(last_project_id)
            except NotFoundError:
                await self.core.settings.set({"ui.last_project_id": None})
            except KaganError as exc:
                logger.warning("Failed to load last project: {}", exc)
            else:
                await self.activate_project(project)
                self.push_screen("kanban-screen")
                return

        self.push_screen(OnboardingFlow(mode="project-picker", dismissible=False))

    def _on_doctor_modal_dismissed(self, _skipped: bool) -> None:
        """Called when DoctorModal is dismissed (user clicked Skip anyway)."""
        self.run_worker(self._route_startup_after_doctor(), exit_on_error=False)

    async def _route_startup_after_doctor(self) -> None:
        """Continue normal startup routing after DoctorModal is dismissed."""
        self._startup_checks = []  # Clear checks so we don't loop back into doctor
        await self._route_startup()

    async def activate_project(self, project: Project) -> None:
        # Use set_active_project to avoid redundant DB lookup
        # since we already have the full Project object
        await self.core.projects.set_active_project(project)

        self.project = project
        settings = await self.core.settings.get()
        selected_repo_id = settings.get(self._repo_setting_key(project.id)) or None
        try:
            repo = await self.core.projects.resolve_repo(
                project.id, selected_repo_id=selected_repo_id
            )
            self.selected_repo_id = repo.id
            self.selected_repo_name = repo.name
            if repo.id != selected_repo_id:
                await self.remember_selected_repo(repo.id)
        except KaganError:
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
            if self.project is None:
                self.push_screen(OnboardingFlow(mode="new-project"))
            else:
                screen.action_new_task()

    def action_help_quit(self) -> None:
        from kagan.tui.widgets.chat import ChatPanel

        for panel in self.screen.query(ChatPanel):
            if panel.display and panel.handle_interrupt():
                return

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
        handler = getattr(self.screen, "action_open_settings", None)
        if callable(handler):
            result: Any = handler()
            if inspect.isawaitable(result):
                self.run_worker(result, exit_on_error=False)

    async def action_open_orchestrator_chat(self) -> None:
        handler = getattr(self.screen, "action_open_orchestrator_chat", None)
        if callable(handler):
            result: Any = handler()
            if inspect.isawaitable(result):
                await result

    def action_open_orchestrator(self) -> None:
        if isinstance(self.screen, OrchestratorOverlay):
            self.screen._focus_input()
            return
        self.push_screen(OrchestratorOverlay())

    def action_show_help(self) -> None:
        sections: list[tuple[str, tuple[tuple[str, str], ...]]] = []

        def rows_from(bindings: list[BindingType] | None) -> tuple[tuple[str, str], ...]:
            if not bindings:
                return ()
            rows: list[tuple[str, str]] = []
            seen: set[tuple[str, str]] = set()
            for binding in bindings:
                if not isinstance(binding, Binding) or not binding.description:
                    continue
                row = (binding.key_display or binding.key, binding.description)
                if row in seen:
                    continue
                rows.append(row)
                seen.add(row)
            return tuple(rows)

        focused_widget = self.focused
        if focused_widget is not None:
            focused_rows = rows_from(getattr(type(focused_widget), "BINDINGS", None))
            if focused_rows:
                sections.append((f"Current Widget: {type(focused_widget).__name__}", focused_rows))

        current_screen = self.screen
        screen_rows = rows_from(getattr(type(current_screen), "BINDINGS", None))
        if screen_rows:
            sections.append((f"Current Screen: {type(current_screen).__name__}", screen_rows))

        self.push_screen(HelpModal(context_sections=tuple(sections)))

    async def action_open_project_selector(self) -> None:
        self.push_screen(OnboardingFlow(mode="open-folder"))

    async def action_open_repo_selector(self) -> None:
        await self._open_repo_picker()

    async def _open_repo_picker(self) -> None:
        if self.project is None:
            self.notify("Open a project before selecting a repository.", severity="warning")
            return
        self.push_screen(RepoPickerModal())

    def action_toggle_mode(self) -> None:
        handler = getattr(self.screen, "action_toggle_mode", None)
        if callable(handler):
            handler()
            return
        if isinstance(self.screen, KanbanScreen):
            self.switch_screen("workspace-screen")
        else:
            self.push_screen("kanban-screen")
