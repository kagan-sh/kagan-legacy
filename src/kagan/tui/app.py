"""Main Kagan TUI application."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import signal
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from textual.app import App, SeverityLevel, SystemCommand
from textual.signal import Signal

from kagan.core.agents.agent_factory import AgentFactory, create_agent
from kagan.core.config import KaganConfig
from kagan.core.constants import KAGAN_BRANCH_CONFIGURED_KEY
from kagan.core.debug_log import setup_debug_logging
from kagan.core.git_utils import get_current_branch
from kagan.core.policy import CapabilityProfile, SessionNamespace, SessionOrigin
from kagan.core.process_liveness import pid_exists
from kagan.core.runtime_context import CoreRuntimeContext, resolve_runtime_context
from kagan.core.services.runtime import RuntimeContextState, RuntimeSessionEvent
from kagan.core.terminal import supports_truecolor
from kagan.core.ux_text import format_interaction_notification, normalize_interaction_verbosity
from kagan.sdk import CoreFailureError, KaganSDK
from kagan.tui._api_adapter import CoreBackedApi, CoreBackedContext
from kagan.tui.keybindings import APP_BINDINGS
from kagan.tui.textual_compat import apply_textual_compat_workarounds
from kagan.tui.theme import KAGAN_THEME, KAGAN_THEME_256
from kagan.tui.ui.screens.kanban import KanbanScreen
from kagan.tui.ui.screens.setup_flow import OnboardingScreen
from kagan.version import get_kagan_runtime_hash, get_kagan_version

if TYPE_CHECKING:
    from collections.abc import Iterable

    from textual.screen import Screen
    from textual.worker import Worker

    from kagan.core.bootstrap import AppContext
    from kagan.core.ipc.client import IPCClient
    from kagan.tui.ui.types import ProjectView, RepoView

_logger = logging.getLogger(__name__)


def resolve_tui_mouse_enabled() -> bool:
    """Return whether terminal mouse reporting should be enabled for TUI sessions.

    Mouse reporting is enabled by default so Kanban cards can be focused via click.
    Set ``KAGAN_TUI_MOUSE=0`` (or ``false``, ``no``, ``off``) to disable it for
    terminal-native text selection workflows.
    """
    raw = os.environ.get("KAGAN_TUI_MOUSE")
    if raw is None or not raw.strip():
        return True
    value = raw.strip().lower()
    return value not in {"0", "false", "no", "off"}


class KaganApp(App):
    """Kagan TUI Application - AI-powered Kanban board."""

    TITLE = "KAGAN"
    CSS_PATH = "styles/kagan.tcss"
    TASK_EVENT_BRIDGE_TIMEOUT_SECONDS = 45.0
    # Keep '.' available for command palette entry from any screen.
    COMMAND_PALETTE_BINDING = "ctrl+shift+p"

    BINDINGS = APP_BINDINGS

    def __init__(
        self,
        db_path: str | None = None,
        config_path: str | None = None,
        runtime_context: CoreRuntimeContext | None = None,
        project_root: str | Path | None = None,
        agent_factory: AgentFactory = create_agent,
    ) -> None:
        """Initialize the TUI app and default runtime state."""
        apply_textual_compat_workarounds()
        super().__init__()

        resolved_runtime_context = runtime_context or resolve_runtime_context(
            config_path=Path(config_path).expanduser().resolve(strict=False)
            if config_path is not None
            else None,
            db_path=(
                Path(db_path).expanduser().resolve(strict=False) if db_path is not None else None
            ),
        )
        self.runtime_context = resolved_runtime_context
        self.db_path = resolved_runtime_context.db_path
        self.config_path = resolved_runtime_context.config_path

        self.register_theme(KAGAN_THEME)
        self.register_theme(KAGAN_THEME_256)

        # Load persisted theme preference early (before full init) so the
        # correct theme is visible from the first paint.
        _early_config = KaganConfig.load(self.config_path)
        persisted_theme = _early_config.ui.theme
        if persisted_theme and persisted_theme in self.available_themes:
            self.theme = persisted_theme
        elif supports_truecolor():
            self.theme = "kagan"
        else:
            self.theme = "kagan-256"

        self._theme_persist_ready = False

        self.task_changed_signal: Signal[str] = Signal(self, "task_changed")

        self.project_root = Path(project_root) if project_root else Path.cwd()
        self._ctx: Any | None = None
        self._core_client: IPCClient | None = None
        self.config: KaganConfig = KaganConfig()
        self._agent_factory = agent_factory
        self._startup_worker: Worker[None] | None = None
        self._startup_maintenance_worker: Worker[None] | None = None
        self._task_event_bridge_worker: Worker[None] | None = None
        self._core_status: str = "DISCONNECTED"
        self._startup_self_heal_attempted = False
        self._passive_task_events_enabled = False

    @property
    def ctx(self) -> AppContext:
        """Get the application context for service access."""
        assert self._ctx is not None, "AppContext not initialized"
        return self._ctx

    def _interaction_verbosity(self) -> str:
        config = getattr(self, "config", None)
        general = getattr(config, "general", None)
        configured = getattr(general, "interaction_verbosity", None)
        return normalize_interaction_verbosity(configured)

    def has_passive_task_event_bridge(self) -> bool:
        worker = self._task_event_bridge_worker
        return bool(
            self._passive_task_events_enabled and worker is not None and not worker.is_finished
        )

    @staticmethod
    def _apply_settings_updates_to_config(config: KaganConfig, updates: dict[str, object]) -> None:
        for key, value in updates.items():
            if "." not in key:
                continue
            section_name, field_name = key.split(".", 1)
            section = getattr(config, section_name, None)
            if section is None:
                continue
            if hasattr(section, field_name):
                setattr(section, field_name, value)

    def apply_settings_updates(self, updates: dict[str, object]) -> None:
        """Apply dotted settings updates to in-memory config mirrors."""
        self._apply_settings_updates_to_config(self.config, updates)
        ctx = getattr(self, "_ctx", None)
        if ctx is not None:
            ctx.config = self.config

    async def persist_settings_updates(self, updates: dict[str, object]) -> tuple[bool, str]:
        success, message, updated, _settings = await self.ctx.api.update_settings(updates)
        if success:
            if isinstance(updated, dict) and updated:
                self.apply_settings_updates(updated)
            else:
                self.apply_settings_updates(updates)
        return success, message

    def watch_theme(self, new_theme: str) -> None:
        """Persist theme changes so the choice survives restarts."""
        if not getattr(self, "_theme_persist_ready", False):
            return
        ctx = getattr(self, "_ctx", None)
        if ctx is None:
            return
        self.run_worker(
            self._persist_theme(new_theme),
            group="theme-persist",
            exclusive=True,
            exit_on_error=False,
        )

    async def _persist_theme(self, theme_name: str) -> None:
        """Save the theme preference through the settings API."""
        try:
            success, message = await self.persist_settings_updates({"ui.theme": theme_name})
            if not success:
                self.log(
                    "Failed to persist theme preference",
                    theme=theme_name,
                    error=message,
                )
        except Exception:  # quality-allow-broad-except
            self.log("Failed to persist theme preference", theme=theme_name)

    def notify(
        self,
        message: str,
        *,
        title: str = "",
        severity: SeverityLevel = "information",
        timeout: float | None = None,
        markup: bool = True,
    ) -> None:
        """Render app notifications with globally configured interaction verbosity."""
        formatted = format_interaction_notification(
            message,
            verbosity=self._interaction_verbosity(),
            severity=severity,
        )
        super().notify(
            formatted,
            title=title,
            severity=severity,
            timeout=timeout,
            markup=markup,
        )

    async def on_mount(self) -> None:
        """Initialize app on mount."""
        setup_debug_logging()

        if not self._config_exists():
            await self.push_screen(OnboardingScreen())
            return

        self._run_startup_worker()

    def _config_exists(self) -> bool:
        """Check if the config file exists (determines first boot vs normal boot)."""
        return self.config_path.exists()

    def _run_startup_worker(self) -> None:
        """Start app initialization in an exclusive startup worker."""
        if self._startup_worker is not None and not self._startup_worker.is_finished:
            return
        self._startup_worker = self.run_worker(
            self._initialize_app(),
            group="startup",
            exclusive=True,
            exit_on_error=False,
        )

    async def _initialize_app(self) -> None:
        """Initialize all app components.

        Wraps the full startup sequence in error handling so failures are
        logged and surfaced to the user instead of producing a blank screen.
        """
        startup_error: BaseException
        try:
            await self._initialize_app_inner()
            return
        except Exception as exc:  # quality-allow-broad-except
            _logger.exception("TUI initialization failed: %s", exc)
            startup_error = exc

        if self._should_attempt_startup_self_heal(startup_error):
            try:
                await self._attempt_runtime_self_heal(error=startup_error)
            except Exception as exc:  # quality-allow-broad-except
                _logger.exception("Startup self-heal failed: %s", exc)
                startup_error = exc
            else:
                try:
                    await self._initialize_app_inner()
                    return
                except Exception as exc:  # quality-allow-broad-except
                    _logger.exception("TUI initialization retry failed: %s", exc)
                    startup_error = exc

        await self._present_startup_failure(startup_error)

    @classmethod
    def _is_runtime_mismatch_error(cls, error: BaseException) -> bool:
        runtime_mismatch_codes = {
            "AUTH_STALE_TOKEN",
            "CLIENT_BUILD_HASH_REQUIRED",
            "CLIENT_OUTDATED",
            "CLIENT_VERSION_REQUIRED",
            "MCP_OUTDATED",
        }
        if isinstance(error, CoreFailureError) and error.code in runtime_mismatch_codes:
            return True

        message = str(error).strip().lower()
        if not message:
            return False
        return "build hash" in message and "does not match core build hash" in message

    def _should_attempt_startup_self_heal(self, error: BaseException) -> bool:
        if self._startup_self_heal_attempted:
            return False
        return self._is_runtime_mismatch_error(error)

    async def _attempt_runtime_self_heal(self, *, error: BaseException) -> None:
        """Attempt one runtime restart before surfacing startup failure."""
        self._startup_self_heal_attempted = True
        self.log("Attempting startup self-heal", error=str(error))
        await self._shutdown_core_connections()
        await self._restart_core_runtime()

    async def _shutdown_core_connections(self) -> None:
        """Close stale startup runtime handles before reconnecting."""
        self._theme_persist_ready = False
        if self._ctx is not None:
            with contextlib.suppress(Exception):
                await self._ctx.close()
            self._ctx = None

        if self._core_client is not None:
            with contextlib.suppress(Exception):
                await self._core_client.close()
            self._core_client = None
        self._core_status = "DISCONNECTED"

    async def _restart_core_runtime(self) -> None:
        """Terminate running core process so startup can reconnect to a fresh runtime."""
        from kagan.core.ipc.discovery import discover_core_endpoint
        from kagan.core.services.runtime import (
            cleanup_stale_runtime_files,
            discover_running_pid_fallback,
        )

        endpoint = discover_core_endpoint(runtime_context=self.runtime_context)
        pid = endpoint.pid if endpoint is not None else None
        if pid is None:
            pid = discover_running_pid_fallback(runtime_context=self.runtime_context)
        if pid is None:
            cleanup_stale_runtime_files(runtime_context=self.runtime_context)
            return

        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            cleanup_stale_runtime_files(runtime_context=self.runtime_context)
            return
        except PermissionError as exc:
            msg = f"Permission denied while stopping core PID {pid}"
            raise RuntimeError(msg) from exc

        deadline = asyncio.get_running_loop().time() + 3.0
        while asyncio.get_running_loop().time() < deadline:
            if not pid_exists(pid):
                cleanup_stale_runtime_files(runtime_context=self.runtime_context)
                return
            await asyncio.sleep(0.1)

        hard_kill_signal = getattr(signal, "SIGKILL", signal.SIGTERM)
        try:
            os.kill(pid, hard_kill_signal)
        except ProcessLookupError:
            cleanup_stale_runtime_files(runtime_context=self.runtime_context)
            return
        except PermissionError as exc:
            msg = f"Permission denied while force-stopping core PID {pid}"
            raise RuntimeError(msg) from exc

        await asyncio.sleep(0.1)
        if pid_exists(pid):
            msg = f"Core PID {pid} did not exit during startup recovery"
            raise RuntimeError(msg)
        cleanup_stale_runtime_files(runtime_context=self.runtime_context)

    async def _present_startup_failure(self, error: BaseException) -> None:
        message = str(error).strip() or "Unknown startup error"
        self.log("STARTUP ERROR", error=message)
        self.notify(
            f"Startup failed: {message}",
            severity="error",
            timeout=15,
        )
        await self._present_startup_error_screen(error)

    async def _present_startup_error_screen(self, error: BaseException) -> None:
        from kagan.tui.ui.screens.startup_error import StartupErrorScreen

        message = str(error).strip() or "Unknown startup error"
        if isinstance(self.screen, StartupErrorScreen):
            self.screen.set_error_message(message)
            return

        await self.push_screen(
            StartupErrorScreen(
                error_message=message,
                on_retry=self._retry_startup_from_error_screen,
                on_restart_core_retry=self._restart_core_and_retry_from_error_screen,
                on_quit=self._quit_from_startup_error_screen,
            )
        )

    async def _retry_startup_from_error_screen(self) -> None:
        from kagan.tui.ui.screens.startup_error import StartupErrorScreen

        if self._startup_worker is not None and not self._startup_worker.is_finished:
            return

        if isinstance(self.screen, StartupErrorScreen):
            self.pop_screen()
        self._run_startup_worker()

    async def _restart_core_and_retry_from_error_screen(self) -> None:
        try:
            await self._attempt_runtime_self_heal(error=RuntimeError("Manual startup recovery"))
        except Exception as exc:  # quality-allow-broad-except
            await self._present_startup_failure(exc)
            return
        await self._retry_startup_from_error_screen()

    def _quit_from_startup_error_screen(self) -> None:
        self.exit()

    async def _initialize_app_inner(self) -> None:
        """Core initialization logic (extracted for error boundary)."""
        self.config = KaganConfig.load(self.config_path)
        self.log("Config loaded", path=str(self.config_path))

        from kagan.core.ipc.client import IPCClient
        from kagan.core.services.runtime import ensure_core_running

        endpoint = await ensure_core_running(
            config=self.config,
            config_path=self.config_path,
            db_path=self.db_path,
            runtime_context=self.runtime_context,
        )
        client = IPCClient(endpoint)
        await client.connect()

        self._core_client = client
        self._core_status = "CONNECTED"
        self.log(
            "Attached to core",
            transport=endpoint.transport,
            address=endpoint.address,
        )

        session_id = f"{SessionNamespace.TUI.value}:{os.getpid()}-{id(self):x}"
        sdk = KaganSDK(
            session_id=session_id,
            session_origin=SessionOrigin.TUI.value,
            client_version=get_kagan_version(),
            client_build_hash=get_kagan_runtime_hash(),
            capability_profile=CapabilityProfile.MAINTAINER,
            endpoint=endpoint,
            runtime_context=self.runtime_context,
        )
        await sdk.connect()
        self._ctx = CoreBackedContext(
            config=self.config,
            config_path=self.config_path,
            db_path=self.db_path,
            api=CoreBackedApi(sdk),
            sdk=sdk,
        )
        self._start_task_event_bridge(endpoint=endpoint, session_id=session_id)
        self.log("Core-backed context initialized", session_id=session_id)

        # Enable theme auto-persistence now that the core is connected and
        # settings can be persisted via the SDK.
        self._theme_persist_ready = True

        await self._startup_screen_decision()
        self._run_startup_maintenance_worker()

    def _start_task_event_bridge(self, *, endpoint: object, session_id: str) -> None:
        if self._task_event_bridge_worker is not None:
            if not self._task_event_bridge_worker.is_finished:
                return
        self._task_event_bridge_worker = self.run_worker(
            self._run_task_event_bridge(endpoint=endpoint, session_id=session_id),
            group="task-event-bridge",
            exclusive=True,
            exit_on_error=False,
        )

    async def _run_task_event_bridge(self, *, endpoint: object, session_id: str) -> None:
        if self._ctx is None:
            return
        event_session_id = f"{session_id}:events"
        event_sdk = KaganSDK(
            session_id=event_session_id,
            session_origin=SessionOrigin.TUI.value,
            client_version=get_kagan_version(),
            client_build_hash=get_kagan_runtime_hash(),
            capability_profile=CapabilityProfile.MAINTAINER,
            endpoint=endpoint,
            runtime_context=self.runtime_context,
        )
        self._ctx.event_sdk = event_sdk
        try:
            await event_sdk.connect()
        except Exception as exc:  # quality-allow-broad-except
            self._passive_task_events_enabled = False
            self.log("Passive task event bridge disabled", error=str(exc))
            return

        self._passive_task_events_enabled = True
        self.log("Passive task event bridge connected", session_id=event_session_id)

        try:
            while True:
                if self._ctx is None:
                    return
                if self._ctx.active_project_id is None:
                    await asyncio.sleep(0.5)
                    continue
                event_result = await event_sdk.tasks_wait_any(
                    timeout_seconds=self.TASK_EVENT_BRIDGE_TIMEOUT_SECONDS
                )
                if not event_result.changed:
                    continue
                task_id = str(event_result.task_id or "").strip()
                if not task_id:
                    continue
                self.task_changed_signal.publish(task_id)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # quality-allow-broad-except
            self.log("Passive task event bridge stopped", error=str(exc))
        finally:
            self._passive_task_events_enabled = False
            with contextlib.suppress(Exception):
                await event_sdk.close()
            if self._ctx is not None and self._ctx.event_sdk is event_sdk:
                self._ctx.event_sdk = None

    def _continue_after_welcome(self) -> None:
        """Called when welcome screen completes to continue app initialization."""
        self.call_later(self._run_init_after_welcome)

    def _run_init_after_welcome(self) -> None:
        """Run initialization after welcome screen."""
        self._run_startup_worker()

    def on_onboarding_screen_completed(self, message: OnboardingScreen.Completed) -> None:
        """Handle OnboardingScreen.Completed message."""
        self.config = message.config
        self.call_later(self._continue_after_onboarding)

    def _continue_after_onboarding(self) -> None:
        """Called after OnboardingScreen completes to continue startup flow.

        Pops the onboarding screen, reinitializes context (now that config exists),
        and continues to the normal startup screen decision flow.
        """

        self.pop_screen()
        self._run_startup_worker()

    async def _startup_screen_decision(self) -> None:
        """Decide the startup flow from runtime session controller state."""
        ctx = self.ctx
        cwd = self.project_root
        decision = await ctx.api.decide_startup(cwd)

        if decision.should_open_project and decision.project_id is not None:
            opened = await self.open_project_session(
                decision.project_id,
                preferred_repo_id=decision.preferred_repo_id,
                preferred_path=decision.preferred_path,
                allow_picker=False,
                screen_mode="push",
            )
            if opened:
                return

        from kagan.tui.ui.screens.welcome import WelcomeScreen

        await self.push_screen(
            WelcomeScreen(
                suggest_cwd=decision.suggest_cwd,
                cwd_path=decision.cwd_path,
                cwd_is_git_repo=decision.cwd_is_git_repo,
            )
        )
        self.log(
            "WelcomeScreen pushed",
            suggest_cwd=decision.suggest_cwd,
            cwd_path=decision.cwd_path,
            cwd_is_git_repo=decision.cwd_is_git_repo,
        )

    def _apply_runtime_session_state(self, state: RuntimeContextState) -> None:
        """Apply runtime session state to mutable app context."""
        self.ctx.active_project_id = state.project_id
        self.ctx.active_repo_id = state.repo_id

    async def _dispatch_runtime_session(
        self,
        event: RuntimeSessionEvent,
        *,
        project_id: str | None = None,
        repo_id: str | None = None,
    ) -> RuntimeContextState:
        """Dispatch a session event and sync AppContext from controller state."""
        try:
            state = await self.ctx.api.dispatch_runtime_session(
                event,
                project_id=project_id,
                repo_id=repo_id,
            )
        except Exception as exc:
            self.log("Runtime session persist failed", error=str(exc))
            state = self.ctx.api.runtime_state
        self._apply_runtime_session_state(state)
        return state

    async def open_project_session(
        self,
        project_id: str,
        *,
        preferred_repo_id: str | None = None,
        preferred_path: Path | None = None,
        allow_picker: bool = True,
        screen_mode: Literal["push", "switch"] = "switch",
    ) -> bool:
        """Open a project, resolve active repo, and navigate to the main screen."""
        project = await self.ctx.api.open_project(project_id)
        await self._dispatch_runtime_session(
            RuntimeSessionEvent.PROJECT_SELECTED,
            project_id=project.id,
        )
        if not await self._set_active_repo_for_project(
            project,
            preferred_repo_id=preferred_repo_id,
            preferred_path=preferred_path,
            allow_picker=allow_picker,
        ):
            return False
        await self._show_main_screen(mode=screen_mode)
        return True

    async def _set_active_repo_for_project(
        self,
        project: ProjectView,
        *,
        preferred_repo_id: str | None = None,
        preferred_path: Path | None = None,
        allow_picker: bool = True,
    ) -> bool:
        """Resolve and apply the active repo for a project.

        Returns False if repo selection was cancelled or the repo is locked.
        """
        repo = await self._select_repo_for_project(
            project,
            preferred_repo_id=preferred_repo_id,
            preferred_path=preferred_path,
            allow_picker=allow_picker,
        )
        if repo is None:
            self._clear_active_repo()
            await self._dispatch_runtime_session(RuntimeSessionEvent.REPO_CLEARED)
            return False
        return await self._apply_active_repo(repo, project_id=project.id)

    async def _select_repo_for_project(
        self,
        project: ProjectView,
        *,
        preferred_repo_id: str | None = None,
        preferred_path: Path | None = None,
        allow_picker: bool = True,
    ) -> RepoView | None:
        """Return the repo to use for a project, optionally using a picker."""
        repos = await self.ctx.api.get_project_repos(project.id)
        if not repos:
            return None

        if preferred_repo_id is not None:
            preferred_repo = next((repo for repo in repos if repo.id == preferred_repo_id), None)
            if preferred_repo is not None:
                return preferred_repo

        if preferred_path is not None:
            matched = self._match_repo_for_path(repos, preferred_path)
            if matched:
                return matched

        if len(repos) == 1 or not allow_picker:
            return repos[0]

        current_repo_id = self.ctx.active_repo_id
        if current_repo_id is not None and all(repo.id != current_repo_id for repo in repos):
            current_repo_id = None

        from kagan.tui.ui.screens.repo_picker import RepoPickerScreen

        selected_repo_id = await self.push_screen_wait(
            RepoPickerScreen(
                project,
                repos,
                current_repo_id=current_repo_id,
            )
        )
        if not selected_repo_id:
            return None
        return next((repo for repo in repos if repo.id == selected_repo_id), None)

    def _match_repo_for_path(self, repos: list[RepoView], path: Path) -> RepoView | None:
        """Return the repo whose path contains the given path."""
        resolved_path = path.resolve()
        for repo in repos:
            repo_path = Path(repo.path).resolve()
            if resolved_path == repo_path or resolved_path.is_relative_to(repo_path):
                return repo
        return None

    async def _apply_active_repo(self, repo: RepoView, *, project_id: str | None = None) -> bool:
        """Apply repo selection to app context and services."""
        self.project_root = Path(repo.path)
        await self._dispatch_runtime_session(
            RuntimeSessionEvent.REPO_SELECTED,
            project_id=project_id or self.ctx.active_project_id,
            repo_id=repo.id,
        )

        if not (repo.scripts or {}).get(KAGAN_BRANCH_CONFIGURED_KEY):
            await self._first_time_branch_setup(repo)

        return True

    async def _first_time_branch_setup(self, repo: RepoView) -> None:
        """Sync repo base branch from the currently checked out branch."""
        branch = await get_current_branch(self.project_root)
        if not branch:
            self.log("Skipped first-time branch setup: no checked-out branch detected")
            return
        await self.ctx.api.update_repo_default_branch(repo.id, branch, mark_configured=True)

    def _clear_active_repo(self) -> None:
        """Clear active repo selection when a project has no repos."""
        self.ctx.active_repo_id = None

    async def _show_main_screen(self, *, mode: Literal["push", "switch"] = "push") -> None:
        """Navigate to the main screen (Kanban with chat overlay fullscreen)."""
        screen = KanbanScreen()
        if mode == "switch":
            await self.switch_screen(screen)
        else:
            await self.push_screen(screen)
        self.log("KanbanScreen shown, app ready", mode=mode)

    async def on_unmount(self) -> None:
        """Clean up on unmount."""
        await self.cleanup()

    def _run_startup_maintenance_worker(self) -> None:
        """Run startup maintenance in the background after first screen is shown."""
        if self._startup_maintenance_worker is not None:
            if not self._startup_maintenance_worker.is_finished:
                return
        self._startup_maintenance_worker = self.run_worker(
            self._run_startup_maintenance(),
            group="startup-maintenance",
            exclusive=True,
            exit_on_error=False,
        )

    async def _run_startup_maintenance(self) -> None:
        """Run non-critical startup cleanup without blocking initial interaction."""
        try:
            valid_task_ids = await self._list_active_task_ids()
            await self._reconcile_worktrees(valid_task_ids=valid_task_ids)
            await self._reconcile_sessions(valid_task_ids=valid_task_ids)
            await self._run_janitor()
        except Exception as exc:  # quality-allow-broad-except
            self.log("Startup maintenance failed", error=str(exc))

    async def _list_active_task_ids(self) -> set[str]:
        """Return current task ids for the active project."""
        ctx = self.ctx
        tasks = await ctx.api.list_tasks(project_id=ctx.active_project_id)
        return {task.id for task in tasks}

    async def _reconcile_worktrees(self, *, valid_task_ids: set[str] | None = None) -> None:
        """Remove orphaned worktrees from previous runs."""
        ctx = self.ctx
        if valid_task_ids is None:
            valid_task_ids = await self._list_active_task_ids()
        cleaned = await ctx.api.cleanup_orphaned_workspaces(valid_task_ids)
        if cleaned:
            self.log(f"Cleaned up {len(cleaned)} orphan worktree(s)")

    async def _reconcile_sessions(self, *, valid_task_ids: set[str] | None = None) -> None:
        """Kill orphaned tmux sessions from previous runs."""
        from kagan.core.tmux import TmuxError, run_tmux

        try:
            output = await run_tmux("list-sessions", "-F", "#{session_name}")
            kagan_sessions = [s for s in output.split("\n") if s.startswith("kagan-")]
            if valid_task_ids is None:
                valid_task_ids = await self._list_active_task_ids()

            for session_name in kagan_sessions:
                task_id = session_name.replace("kagan-", "")
                if task_id not in valid_task_ids:
                    await run_tmux("kill-session", "-t", session_name)
                    self.log(f"Killed orphaned session: {session_name}")
                else:
                    continue
        except TmuxError:
            pass

    async def _run_janitor(self) -> None:
        """Run janitor to prune stale worktrees and clean up orphan kagan/* branches."""
        ctx = self.ctx
        workspaces = await ctx.api.list_workspaces()
        valid_workspace_ids: set[str] = set()
        for workspace in workspaces:
            if isinstance(workspace, dict):
                raw_workspace_id = workspace.get("id") or workspace.get("workspace_id")
            else:
                raw_workspace_id = getattr(workspace, "id", None)
            workspace_id = str(raw_workspace_id or "").strip()
            if workspace_id:
                valid_workspace_ids.add(workspace_id)

        result = await ctx.api.cleanup_workspace_artifacts(valid_workspace_ids)

        if result is not None and result.total_cleaned > 0:
            details: list[str] = []
            if result.worktrees_pruned > 0:
                details.append(f"{result.worktrees_pruned} stale worktree ref(s)")
            if result.branches_deleted:
                details.append(f"{len(result.branches_deleted)} orphan branch(es)")
            self.log(f"Janitor cleaned: {', '.join(details)}")

    async def cleanup(self) -> None:
        """Terminate all agents and close resources.

        Shutdown order:
        1. Stop orchestrator agents.
        2. Mark the DB repository as closing (prevents new sessions).
        3. Unbind signals (prevents new workers being scheduled).
        4. Cancel all in-flight Textual workers and wait for them to finish.
        5. Close the AppContext (stops automation, disposes DB engine).
        6. Release the instance lock.
        """
        # Cancel in-flight workers and wait for them to settle before
        # disposing the DB engine.  During shutdown, workers that were
        # already mid-flight may fail with RepositoryClosing, ValueError
        # ("Connection closed"), or get cancelled outright — all expected.
        self.workers.cancel_all()
        with contextlib.suppress(Exception, asyncio.CancelledError):
            await self.workers.wait_for_complete()

        if self._ctx:
            await self._ctx.close()
            self._ctx = None
        self._passive_task_events_enabled = False

        if self._core_client is not None:
            with contextlib.suppress(Exception):
                await self._core_client.close()
            self._core_client = None
            self._core_status = "DISCONNECTED"

    async def action_open_project_selector(self) -> None:
        """Return to the project selector screen."""
        from kagan.tui.ui.screens.welcome import WelcomeScreen

        if isinstance(self.screen, WelcomeScreen):
            return

        await self.switch_screen(WelcomeScreen(highlight_recent=True))

    def action_open_repo_selector(self) -> None:
        """Open the repository selector for the active project."""
        self.run_worker(
            self._open_repo_selector(),
            group="app-open-repo-selector",
            exclusive=True,
            exit_on_error=False,
        )

    async def _open_repo_selector(self) -> None:
        """Worker entry for opening the repository selector."""
        invoking_screen = self.screen
        try:
            api = self.ctx.api
        except AssertionError:
            self.notify("App not initialized yet", severity="warning")
            return

        project = None
        if self.ctx.active_project_id is not None:
            project = await api.get_project(self.ctx.active_project_id)
        if project is None:
            project = await api.find_project_by_repo_path(str(self.project_root))
        if project is None:
            self.notify("No active project to select a repository", severity="warning")
            return

        repos = await api.get_project_repos(project.id)

        current_repo_id = self.ctx.active_repo_id
        from kagan.tui.ui.screens.repo_picker import RepoPickerScreen

        selected_repo_id = await self.push_screen_wait(
            RepoPickerScreen(
                project,
                repos,
                current_repo_id=current_repo_id,
            )
        )
        if not selected_repo_id or selected_repo_id == current_repo_id:
            return

        selected_repo = next((repo for repo in repos if repo.id == selected_repo_id), None)
        if selected_repo is None:
            return

        if not await self._apply_active_repo(selected_repo, project_id=project.id):
            return

        from kagan.tui.ui.screens.kanban import KanbanScreen

        reset_target = None
        if isinstance(invoking_screen, KanbanScreen):
            reset_target = invoking_screen
        elif isinstance(self.screen, KanbanScreen):
            reset_target = self.screen
        if reset_target is not None:
            await reset_target.reset_for_repo_change()
        await self._sync_active_screen_header()
        display_name = selected_repo.display_name or selected_repo.name
        self.notify(f"Active repository: {display_name}", severity="information")

    async def _sync_active_screen_header(self) -> None:
        """Sync header context and git branch for the active screen."""
        from textual.css.query import NoMatches

        from kagan.tui.ui.screens.base import KaganScreen
        from kagan.tui.ui.widgets.header import KaganHeader

        screen = self.screen
        if not isinstance(screen, KaganScreen):
            return
        try:
            header = screen.query_one(KaganHeader)
        except NoMatches:
            return

        await screen.sync_header_context(header)
        if self.ctx.active_repo_id is None:
            header.update_branch("")
            return
        branch = await get_current_branch(self.project_root)
        header.update_branch(branch)

    def _run_action(self, action: str, *, target: str = "screen") -> None:
        if target == "app":
            action_method = getattr(self, f"action_{action}", None)
            if action_method is None:
                return
            result = action_method()
            if asyncio.iscoroutine(result):
                self.run_worker(result)
            return

        screen = self.screen
        if hasattr(screen, "run_action"):
            result = screen.run_action(action)
            if asyncio.iscoroutine(result):
                self.run_worker(result)

    def get_system_commands(self, screen: Screen) -> Iterable[SystemCommand]:
        """Expose command palette actions for app-level navigation and utilities."""
        yield from super().get_system_commands(screen)
        yield SystemCommand("Help", "Open help", self.action_show_help)
        yield SystemCommand(
            "Projects",
            "Open project selector",
            lambda: self._run_action("open_project_selector", target="app"),
        )
        yield SystemCommand(
            "Repositories",
            "Open repo selector",
            lambda: self._run_action("open_repo_selector", target="app"),
        )
        if isinstance(screen, KanbanScreen):
            yield SystemCommand(
                "AI Assistant Docked",
                "Toggle docked AI Assistant panel (Ctrl+O)",
                lambda: self._run_action("toggle_orchestrator_dock"),
            )
            yield SystemCommand(
                "AI Assistant Fullscreen",
                "Toggle fullscreen AI Assistant panel (Ctrl+P)",
                lambda: self._run_action("toggle_orchestrator_fullscreen"),
            )
        yield SystemCommand(
            "Debug Log",
            "Open debug log viewer",
            lambda: self._run_action("toggle_debug_log", target="app"),
        )
        yield SystemCommand("Quit", "Exit Kagan", self.exit)

    def action_show_help(self) -> None:
        """Open the help modal."""
        from kagan.tui.ui.modals import HelpModal

        self.push_screen(HelpModal())

    def action_toggle_debug_log(self) -> None:
        """Toggle the debug log viewer (F12). Disabled in production builds."""
        from kagan.core.limits import DEBUG_BUILD

        if not DEBUG_BUILD:
            self.notify("Debug log disabled in production builds", severity="warning")
            return

        from kagan.tui.ui.modals.debug_log import DebugLogModal

        self.push_screen(DebugLogModal())


def run() -> None:
    """Run the Kagan application."""
    app = KaganApp()
    app.run(mouse=resolve_tui_mouse_enabled())


if __name__ == "__main__":
    run()
