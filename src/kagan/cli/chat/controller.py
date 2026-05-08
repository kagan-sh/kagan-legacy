"""ChatController — Rich-console renderer over the long-lived ChatEngine.

Phase 5c rewires the controller onto :class:`kagan.core.chat.ChatEngine` +
:class:`kagan.core.chat.LongLivedACPFactory`. Every chat turn now:

1. Persists the user message via ``client.chat.push_user(session_id, text)``.
2. Streams assistant events from
   ``client.chat.stream_assistant(session_id, prompt_blocks=..., acp_factory=factory)``.
3. Dispatches events to :class:`CLIRenderer` for printing and
   :class:`PermissionUI` for permission resolution
   (which routes back to ``engine.resolve_permission``).
4. Routes ``Ctrl-C`` through ``engine.cancel(session_id)``; session switches
   call ``engine.detach(session_id)`` + ``factory.restart()``.

The legacy ``_OrchestratorACPClient`` and the local ``_chat_history`` /
``_persist_session`` / ``_generate_session_title`` mirroring are gone — the
engine + ChatSessions own them.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import sys
from pathlib import Path
from typing import Any

import acp
import click
from loguru import logger
from prompt_toolkit.patch_stdout import patch_stdout
from rich.live import Live

from kagan.cli.chat._approval_panel import strip_tool_prefix
from kagan.cli.chat._chat_ui import (
    build_session_picker_option,
    export_analytics_json,
    print_analytics_panel,
    print_help_documentation,
    print_project_info,
    print_repo_info,
    print_restored_messages,
    print_session_list,
    print_status_panel,
    show_tool_report,
)
from kagan.cli.chat._permission_ui import PermissionUI, _SendResult, _WaveIndicator
from kagan.cli.chat._renderer import CLIRenderer
from kagan.cli.chat._session_picker import (
    ChatSessionView,
    build_chat_session_list_items,
    chat_session_to_view,
    resolve_chat_session_selector,
)
from kagan.cli.chat._signals import install_sigint_handler, restore_sigint_handler
from kagan.cli.chat._streaming import _TurnLiveState
from kagan.cli.chat.agents import format_agent_backend_list, list_registered_agent_backends
from kagan.cli.chat.commands import (
    SlashAction,
    SlashCommandOutcome,
    build_slash_presentation_lines,
    resolve_slash_input,
)
from kagan.cli.chat.prompt import (
    _format_user_request_block,
    _runtime_guidance_for_request,
    build_chat_status_line,
)
from kagan.cli.chat.repl import (
    _TOOLBAR_STATE,
    SearchPickerOption,
    _build_prompt_message,
    _build_prompt_placeholder,
    _console,
    _env_flag_enabled,
    _find_git_root,
    _get_prompt_session,
    _release_prompt_session,
    build_live_status_inline,
    rotate_tip_on_submit,
    searchable_picker,
    supports_interactive_picker,
)
from kagan.core import (
    KAGAN_AGENT_EMAIL,
    KAGAN_AGENT_NAME,
    DBWatcher,
    get_system_git_identity,
)
from kagan.core.chat import LongLivedACPFactory
from kagan.core.chat.events import (
    AssistantChunk,
    AssistantMessagePersisted,
    PermissionRequest,
    TurnCancelled,
    TurnDone,
    TurnError,
    TurnStarted,
    UsageUpdate,
)
from kagan.core.chat.events import (
    ToolCallProgress as ChatToolCallProgress,
)
from kagan.core.chat.events import (
    ToolCallStart as ChatToolCallStart,
)
from kagan.core.errors import AgentError, KaganError

__all__ = [
    "ChatController",
    "_SendResult",
    "_WaveIndicator",
]


_SLASH_ACTION_HANDLER_NAMES: dict[SlashAction, str] = {
    SlashAction.CLEAR: "_handle_slash_clear",
    SlashAction.SHOW_HELP: "_handle_slash_help",
    SlashAction.SHOW_AGENTS: "_handle_slash_show_agents",
    SlashAction.SWITCH_AGENT: "_handle_slash_switch_agent",
    SlashAction.LIST_SESSIONS: "_handle_slash_list_sessions",
    SlashAction.DELETE_SESSION: "_handle_slash_delete_session",
    SlashAction.NEW_SESSION: "_handle_slash_new_session",
    SlashAction.SHOW_TOOL: "_handle_slash_show_tool",
    SlashAction.SHOW_STATUS: "_handle_slash_show_status",
    SlashAction.SHOW_ANALYTICS: "_handle_slash_show_analytics",
    SlashAction.SHOW_PROJECT: "_handle_slash_show_project",
    SlashAction.SWITCH_PROJECT: "_handle_slash_switch_project",
    SlashAction.SWITCH_REPO: "_handle_slash_switch_repo",
    SlashAction.SHOW_REPO: "_handle_slash_show_repo",
    SlashAction.SHOW_APPROVALS: "_handle_slash_show_approvals",
    SlashAction.ATTACH_AGENT: "_handle_slash_attach_agent",
    SlashAction.DETACH_AGENT: "_handle_slash_detach_agent",
    SlashAction.CLOSE: "_handle_slash_close",
}


def _settings_flag_enabled(settings: dict[str, str], key: str, *, default: bool) -> bool:
    raw_value = settings.get(key)
    if raw_value is None:
        return default
    return raw_value.strip().lower() not in {"0", "false", "no", "off"}


def _bootstrap_repository_status(
    *,
    repo_path: str,
    git_root: Path | None,
    auto_init_git: bool,
) -> str:
    if git_root is not None:
        return f"[dim]Detected git root; linking it as the Repository:[/dim] {repo_path}"
    if auto_init_git:
        return (
            "[dim]No git repository detected in this folder. Kagan will create a "
            "Project, link this folder as its Repository, and core will initialize "
            "git for it.[/dim]"
        )
    return (
        "[yellow]No git repository detected in this folder.[/yellow] "
        "Auto git initialization is disabled; run [bold]git init[/bold] here "
        "or enable auto-init before linking it as a Repository."
    )


def _bootstrap_noninteractive_message(
    *,
    repo_path: str,
    git_root: Path | None,
    auto_init_git: bool,
) -> str:
    status = _bootstrap_repository_status(
        repo_path=repo_path,
        git_root=git_root,
        auto_init_git=auto_init_git,
    )
    return (
        "[red]No Kagan Project is linked to this folder.[/red]\n"
        f"{status}\n"
        "Run [bold]kg chat[/bold] in an interactive terminal to create the Project, "
        "or run [bold]kg tui[/bold] and use [bold]Open Folder[/bold]."
    )


class ChatController:
    def __init__(
        self,
        client: Any,
        *,
        agent_backend: str = "claude-code",
        mcp_session_id: str | None = None,
        prefer_session_backend: bool = True,
    ) -> None:
        self.client = client
        self.agent_backend = agent_backend
        self._mcp_session_id = mcp_session_id
        self._prefer_session_backend = prefer_session_backend
        self._restart_requested = False
        self._turn_count = 0
        self._chat_session_id: str | None = None
        self._chat_session_source = "repl"
        self._persist_repl_session = True
        self._rendered_messages: list[str] = []
        self._restored_messages_printed = False
        self._session_title: str | None = None
        self._project_name: str | None = None
        self._selected_repo_id: str | None = None
        self._selected_repo_name: str | None = None
        # In-memory tracking of the currently attached agent session (set by
        # /attach, cleared by /detach).  When set, typed messages are routed to
        # the worker/reviewer session instead of the orchestrator.
        self._attached_agent_session_id: str | None = None
        self._watcher = DBWatcher(client)

        show_thoughts = _env_flag_enabled("KAGAN_CHAT_SHOW_THOUGHTS", default=False)
        self._renderer = CLIRenderer(_console, show_thoughts=show_thoughts)
        self._permission_ui = PermissionUI(renderer=self._renderer, engine=client.chat)
        self._factory: LongLivedACPFactory | None = None
        self._permission_tasks: set[asyncio.Task[None]] = set()

    # ------------------------------------------------------------------
    # Session management
    # ------------------------------------------------------------------

    async def hydrate_persistent_session(
        self,
        *,
        explicit_session_id: str | None = None,
    ) -> None:
        """Resolve or create the initial chat session.

        Behaviour:
        - ``explicit_session_id`` (``--session-id <id>``): resume that specific session.
        - Otherwise: always create a fresh session immediately (no picker at launch).
        """
        selected = await self._resolve_initial_session(explicit_session_id)
        if selected is None:
            row = await self.client.chat_sessions.create(
                source="repl",
                label="REPL session",
                agent_backend=self.agent_backend,
                project_id=self.client.active_project_id,
            )
            selected = chat_session_to_view(row, [])
        await self._attach_session(selected, switching=False)

    async def _resolve_initial_session(
        self,
        explicit_session_id: str | None,
    ) -> ChatSessionView | None:
        # Explicit session ID takes priority
        if explicit_session_id:
            cs = self.client.chat_sessions
            pair = await cs.get_with_history(explicit_session_id)
            if pair is not None:
                row, msgs = pair
                return chat_session_to_view(row, msgs)
            binding = await cs.resolve_task_binding(explicit_session_id)
            if binding is None:
                return None
            return ChatSessionView(
                id=binding.id,
                label=binding.label,
                source=binding.source,
                agent_backend=binding.agent_backend,
                project_id=None,
                orchestrator_history=[],
                messages_rendered=[
                    f"System: Attached to task session {binding.id} (status: {binding.status})."
                ],
                updated_at="",
            )

        # Default: always start fresh (no picker)
        return None

    async def _attach_session(self, session: ChatSessionView, *, switching: bool) -> bool:
        previous_session_id = self._chat_session_id
        session_id = session.id.strip()
        if not session_id:
            return False
        source = session.source.strip() or "repl"
        self._chat_session_id = session_id
        self._chat_session_source = source
        self._persist_repl_session = source == "repl"
        self._mcp_session_id = session_id

        self._rendered_messages = [
            str(line).rstrip() for line in session.messages_rendered if str(line).strip()
        ]
        history = session.orchestrator_history
        self._turn_count = sum(
            1
            for pair in history
            if isinstance(pair, list | tuple)
            and len(pair) == 2
            and str(pair[0]).strip() == "assistant"
        )
        # Render restored history if not already shown — engine + ChatSessions
        # own the persistence; controller just renders it once on attach.
        if not self._rendered_messages and history:
            self._rendered_messages = [
                f"{'You' if str(role).strip() == 'user' else 'Agent'}: {str(content).strip()}"
                for role, content in (
                    pair for pair in history if isinstance(pair, list | tuple) and len(pair) == 2
                )
            ]
        self._restored_messages_printed = False
        persisted_label = session.label
        default_label = f"Session {session_id}"
        self._session_title = persisted_label if persisted_label != default_label else None
        backend = session.agent_backend
        if (
            self._prefer_session_backend
            and isinstance(backend, str)
            and backend.strip()
            and backend != self.agent_backend
        ):
            self.agent_backend = backend
            if switching:
                self._restart_requested = True

        if switching and previous_session_id is not None and previous_session_id != session_id:
            self._restart_requested = True

        if self._persist_repl_session:
            await self.client.chat_sessions.set_last_session_id(scope="repl", session_id=session_id)
        return self._restart_requested

    def _print_restored_messages(self) -> None:
        if self._restored_messages_printed or not self._rendered_messages:
            return
        print_restored_messages(self._rendered_messages)
        self._restored_messages_printed = True

    async def _open_sessions(self, query: str | None) -> bool:
        pairs = await self.client.chat_sessions.list_with_history(
            project_id=self.client.active_project_id
        )
        sessions = [chat_session_to_view(row, msgs) for row, msgs in pairs]
        if not sessions:
            _console.print("[dim]No persisted sessions yet.[/dim]")
            return False

        items = build_chat_session_list_items(sessions, current_session_id=self._chat_session_id)
        sessions_by_id: dict[str, ChatSessionView] = {session.id: session for session in sessions}

        selected: ChatSessionView | None = None
        selected_id: str | None = None
        if query:
            selected_item = resolve_chat_session_selector(items, query)
            if selected_item is not None:
                selected_id = selected_item.session_id
                selected = sessions_by_id.get(selected_id)
            if selected is None:
                _console.print(f"[red]Unknown session selector: {query}[/red]")
                return False
        else:
            if not supports_interactive_picker():
                print_session_list(items)
                return False
            selected_id = await searchable_picker(
                "Select session",
                [build_session_picker_option(item) for item in items],
            )
            if selected_id is None:
                return False
            selected = sessions_by_id.get(selected_id)
            if selected is None:
                return False

        should_restart = await self._attach_session(selected, switching=True)
        _console.print(f"[green]Attached session:[/green] {selected_id or selected.id}")
        if not should_restart:
            self._print_restored_messages()
        return should_restart

    async def _show_agent_picker(self) -> bool:
        backends = list_registered_agent_backends()
        if not supports_interactive_picker():
            for line in format_agent_backend_list(backends, current_backend=self.agent_backend):
                _console.print(line)
            return False

        selected_backend = await searchable_picker(
            "Select agent backend",
            [
                SearchPickerOption(
                    value=backend,
                    label=f"{index}. {backend}",
                    meta="current" if backend == self.agent_backend else "",
                )
                for index, backend in enumerate(backends, start=1)
            ],
        )
        if selected_backend is None:
            return False
        return await self._switch_agent(selected_backend)

    async def _create_new_session(self) -> bool:
        row = await self.client.chat_sessions.create(
            source="repl",
            label="REPL session",
            agent_backend=self.agent_backend,
            project_id=self.client.active_project_id,
        )
        created = chat_session_to_view(row, [])
        should_restart = await self._attach_session(created, switching=True)
        _console.print(f"[green]New session:[/green] {created.id}")
        return should_restart

    async def _delete_session(self, query: str) -> None:
        pairs = await self.client.chat_sessions.list_with_history()
        sessions = [chat_session_to_view(row, msgs) for row, msgs in pairs]
        if not sessions:
            _console.print("[dim]No sessions to delete.[/dim]")
            return

        items = build_chat_session_list_items(sessions, current_session_id=self._chat_session_id)
        sessions_by_id: dict[str, ChatSessionView] = {session.id: session for session in sessions}

        target_item = resolve_chat_session_selector(items, query)
        target = sessions_by_id.get(target_item.session_id) if target_item is not None else None
        if target is None:
            _console.print(f"[red]Unknown session: {query}[/red]")
            return

        target_id = target.id
        target_label = target.label or target_id
        if target_id == self._chat_session_id:
            _console.print("[red]Cannot delete the current session.[/red]")
            return

        deleted = await self.client.chat_sessions.delete(target_id)
        if deleted:
            _console.print(f"[green]Deleted:[/green] {target_label} [{target_id}]")
        else:
            _console.print(f"[red]Failed to delete session {target_id}.[/red]")

    # ------------------------------------------------------------------
    # Project management
    # ------------------------------------------------------------------

    async def ensure_project(self) -> bool:
        cwd = Path.cwd()
        cwd_str = str(cwd)

        project = await self.client.projects.find_by_repo(cwd_str)
        if project is not None:
            await self.client.projects.set_active(project.id)
            self._project_name = project.name
            await self._auto_select_repo(project.id)
            return True

        git_root = _find_git_root(cwd)
        if git_root is not None:
            resolved_git_root = git_root.resolve()
            projects = await self.client.projects.list()
            for proj in projects:
                repos = await self.client.projects.repos(proj.id)
                for repo in repos:
                    if Path(repo.path).expanduser().resolve() == resolved_git_root:
                        await self.client.projects.set_active(proj.id)
                        await self._refresh_project_name()
                        await self._auto_select_repo(proj.id)
                        return True

        result = await self._bootstrap_project()
        if result:
            await self._refresh_project_name()
            if self.client.active_project_id:
                await self._auto_select_repo(self.client.active_project_id)
        return result

    async def _refresh_project_name(self) -> None:
        projects = await self.client.projects.list()
        active_id = self.client.active_project_id
        for p in projects:
            if p.id == active_id:
                self._project_name = p.name
                return
        self._project_name = None

    async def _auto_select_repo(self, project_id: str) -> None:
        repos = await self.client.projects.repos(project_id)
        if len(repos) == 1:
            self._selected_repo_id = repos[0].id
            self._selected_repo_name = repos[0].name
        else:
            self._selected_repo_id = None
            self._selected_repo_name = None

    async def _bootstrap_project(self) -> bool:
        cwd = Path.cwd()
        git_root = _find_git_root(cwd)

        repo_root = git_root or cwd
        repo_path = str(repo_root)
        default_name = repo_root.name
        settings = await self.client.settings.get()
        auto_init_git = _settings_flag_enabled(settings, "auto_init_git_repo", default=True)

        if not sys.stdin.isatty():
            _console.print(
                _bootstrap_noninteractive_message(
                    repo_path=repo_path,
                    git_root=git_root,
                    auto_init_git=auto_init_git,
                )
            )
            return False

        _console.print()
        _console.print("[bold]No Kagan Project is linked to this folder.[/bold]")
        _console.print("Let's create one.")
        _console.print(
            _bootstrap_repository_status(
                repo_path=repo_path,
                git_root=git_root,
                auto_init_git=auto_init_git,
            )
        )
        _console.print()

        try:
            name = await _get_prompt_session().prompt_async(f"Project name [{default_name}]: ")
        except (EOFError, KeyboardInterrupt):
            _console.print("[dim]Cancelled.[/dim]")
            return False

        name = name.strip() or default_name

        await self._ensure_git_identity()

        return await self._create_project(name, repo_path)

    async def _ensure_git_identity(self) -> None:
        settings = await self.client.settings.get()
        if "git_user_mode" in settings:
            return

        if not sys.stdin.isatty():
            await self.client.settings.set({"git_user_mode": "kagan_agent"})
            return

        sys_name, sys_email = await get_system_git_identity()
        has_system_identity = sys_name != KAGAN_AGENT_NAME or sys_email != KAGAN_AGENT_EMAIL

        _console.print("[bold]Git identity for agent commits:[/bold]")
        _console.print(f"  [cyan]1[/cyan] Kagan Agent <{KAGAN_AGENT_EMAIL}> [dim](default)[/dim]")
        if has_system_identity:
            _console.print(f"  [cyan]2[/cyan] Use my git profile ({sys_name} <{sys_email}>)")
        else:
            _console.print("  [cyan]2[/cyan] Use my git profile [dim](not configured)[/dim]")
        _console.print("  [cyan]3[/cyan] Custom name & email")
        _console.print()

        try:
            choice = await _get_prompt_session().prompt_async("Choice [1]: ")
        except (EOFError, KeyboardInterrupt):
            choice = ""

        choice = choice.strip() or "1"

        if choice == "2":
            await self.client.settings.set({"git_user_mode": "system_default"})
            label = f"{sys_name} <{sys_email}>"
            _console.print(f"[green]✓[/green] Using system git profile: {label}")
        elif choice == "3":
            try:
                custom_name = await _get_prompt_session().prompt_async(
                    f"Git user name [{KAGAN_AGENT_NAME}]: "
                )
                custom_email = await _get_prompt_session().prompt_async(
                    f"Git email [{KAGAN_AGENT_EMAIL}]: "
                )
            except (EOFError, KeyboardInterrupt):
                _console.print("[dim]Cancelled — using default.[/dim]")
                await self.client.settings.set({"git_user_mode": "kagan_agent"})
                return

            custom_name = custom_name.strip() or KAGAN_AGENT_NAME
            custom_email = custom_email.strip() or KAGAN_AGENT_EMAIL
            await self.client.settings.set(
                {
                    "git_user_mode": "custom",
                    "git_user_name": custom_name,
                    "git_user_email": custom_email,
                }
            )
            _console.print(
                f"[green]✓[/green] Using custom identity: {custom_name} <{custom_email}>"
            )
        else:
            await self.client.settings.set({"git_user_mode": "kagan_agent"})
            _console.print(
                f"[green]✓[/green] Using default: {KAGAN_AGENT_NAME} <{KAGAN_AGENT_EMAIL}>"
            )

    async def _create_project(self, name: str, repo_path: str) -> bool:
        project_id: str | None = None
        try:
            project = await self.client.projects.create(name)
            project_id = project.id
            await self.client.projects.add_repo(project.id, repo_path)
            await self.client.projects.set_active(project.id)
            _console.print(f"[green]✓[/green] Created project [bold]{name}[/bold]")
            logger.info("Bootstrapped project={} repo={}", project.id, repo_path)
            return True
        except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
            if project_id is not None:
                try:
                    await self.client.projects.delete(project_id)
                except (KaganError, OSError, RuntimeError, ValueError):
                    logger.exception("Failed to cleanup bootstrap project id={}", project_id)

            existing = await self.client.projects.find_by_repo(repo_path)
            if existing is not None:
                await self.client.projects.set_active(existing.id)
                logger.info("Recovered existing project={} repo={}", existing.id, repo_path)
                _console.print(
                    f"[green]✓[/green] Using existing project [bold]{existing.name}[/bold]"
                )
                return True

            logger.exception("Failed to bootstrap project")
            _console.print(f"[red]Failed to create project:[/red] {exc}")
            return False

    # ------------------------------------------------------------------
    # Agent ACP lifecycle
    # ------------------------------------------------------------------

    async def run(self, *, prompt: str | None = None) -> None:
        while True:
            self._restart_requested = False
            await self._run_agent_session(prompt=prompt)
            if not self._restart_requested:
                break
            prompt = None
            _console.print()
            _console.print(f"[bold cyan]Switching to {self.agent_backend}...[/bold cyan]")

    async def _run_agent_session(self, *, prompt: str | None = None) -> None:
        cwd = Path.cwd()
        factory = LongLivedACPFactory(
            client=self.client,
            agent_backend=self.agent_backend,
            cwd=cwd,
        )
        # Show wave indicator while the factory enters (spawn + handshake).
        skip_anim = os.environ.get("KAGAN_CHAT_SKIP_BOOT_ANIMATION") == "1"
        ready_event = asyncio.Event()
        spawn_error: BaseException | None = None

        async def _enter_factory() -> None:
            nonlocal spawn_error
            try:
                await factory.__aenter__()
            except BaseException as exc:
                spawn_error = exc
            finally:
                ready_event.set()

        enter_task = asyncio.create_task(_enter_factory(), name="chat-factory-enter")
        if skip_anim:
            await ready_event.wait()
        else:
            with Live(
                _WaveIndicator(),
                console=_console,
                refresh_per_second=10,
                transient=True,
            ) as live:
                wave = _WaveIndicator()
                while not ready_event.is_set():
                    await asyncio.sleep(0.05)
                    live.update(wave, refresh=True)

        await enter_task
        if spawn_error is not None:
            if isinstance(spawn_error, AgentError):
                _console.print(f"[red]{spawn_error}[/red]")
            else:
                logger.exception("ACP factory entry failed", exc_info=spawn_error)
                _console.print(f"[red]Agent session failed: {spawn_error}[/red]")
            return

        self._factory = factory
        self._permission_ui.bind_engine(self.client.chat)

        try:
            _console.print("[green]✓[/green] Agent ready.")
            _TOOLBAR_STATE.agent_backend = self.agent_backend
            _TOOLBAR_STATE.project_name = Path.cwd().name
            status_line = build_chat_status_line(
                mode="repl",
                session_label="orchestrator",
                message_count=self._turn_count,
            )
            _console.print(f"[dim]{status_line}[/dim]")
            _console.print()
            if prompt is None:
                self._print_restored_messages()

            await self._watcher.initialize()
            await self._watcher.subscribe()

            if prompt is not None:
                await self._send(text=prompt)
            else:
                await self._repl_loop()
        finally:
            await self._watcher.close()
            with contextlib.suppress(Exception):
                await factory.__aexit__(None, None, None)
            # Drain any orphaned permission-handling tasks.
            for task in list(self._permission_tasks):
                if not task.done():
                    task.cancel()
            for task in list(self._permission_tasks):
                with contextlib.suppress(BaseException):
                    await task
            self._permission_tasks.clear()
            self._factory = None

    # ------------------------------------------------------------------
    # Sending a turn — drives the engine
    # ------------------------------------------------------------------

    async def _send(self, text: str) -> _SendResult:
        if self._chat_session_id is None or self._factory is None:
            _console.print("[red]No agent connected. Try restarting.[/red]")
            return _SendResult()

        ctx = self._watcher.drain_context()
        request_text = f"{ctx}\n\n{text}" if ctx else text

        runtime_guidance = _runtime_guidance_for_request(request_text)
        request_block = (
            request_text if runtime_guidance is None else f"{request_text}\n\n{runtime_guidance}"
        )

        prompt_blocks: list[Any] = [acp.text_block(_format_user_request_block(request_block))]

        # Persist the user message via the engine.
        try:
            await self.client.chat.push_user(self._chat_session_id, text)
        except (KaganError, ValueError) as exc:
            _console.print(f"[red]Failed to record user message: {exc}[/red]")
            return _SendResult()

        _TOOLBAR_STATE.context_pct = None
        _TOOLBAR_STATE.is_streaming = True
        _console.print()
        _console.print(f"[bold]You:[/bold] {text}")

        live_state = _TurnLiveState(inline_status=build_live_status_inline)
        self._permission_ui.reset_batch_queue()

        interrupted = False
        had_error = False

        # Build a synthetic Task wrapping the engine consumption so SIGINT can
        # cancel the whole turn through the engine. The handler still fires
        # ``engine.cancel`` for the partial-on-cancel persist contract.
        with Live(live_state, console=_console, auto_refresh=False, transient=True) as _live:

            async def _consume_stream() -> None:
                nonlocal had_error
                stream = self.client.chat.stream_assistant(
                    self._chat_session_id,
                    prompt_blocks=prompt_blocks,
                    agent_backend=self.agent_backend,
                    acp_factory=self._factory,
                )
                try:
                    async for event in stream:
                        self._dispatch_event(event)
                        _live.refresh()
                        if isinstance(event, TurnError):
                            had_error = True
                finally:
                    with contextlib.suppress(BaseException):
                        await stream.aclose()

            async def _refresh_clock() -> None:
                # Drives spinner animation and elapsed-time label at 10 fps.
                # Runs in the same asyncio event loop as prompt_toolkit so
                # refresh calls are serialised with toolbar redraws — no
                # byte-level interleaving with the threaded auto_refresh.
                try:
                    while True:
                        await asyncio.sleep(0.1)
                        _live.refresh()
                except asyncio.CancelledError:
                    pass

            self._renderer.start_turn(live_state=live_state)
            refresh_task = asyncio.create_task(_refresh_clock(), name="chat-live-clock")
            consume_task = asyncio.create_task(_consume_stream(), name="chat-engine-consume")
            original_sigint = install_sigint_handler(consume_task)
            try:
                await consume_task
            except asyncio.CancelledError:
                interrupted = True
                with contextlib.suppress(BaseException):
                    await self.client.chat.cancel(self._chat_session_id)
                self._permission_ui.cancel_batch_queue()
            except (acp.RequestError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
                logger.exception("Chat engine consume failed")
                _console.print(f"\n[red]Agent error: {exc}[/red]")
                had_error = True
            except Exception as exc:
                logger.exception("Unexpected chat engine consume failure")
                _console.print(f"\n[red]Agent error: {exc}[/red]")
                had_error = True
            finally:
                refresh_task.cancel()
                restore_sigint_handler(original_sigint)
                _TOOLBAR_STATE.is_streaming = False

        # Finalize any pending Markdown the renderer was still buffering.
        self._renderer.finish_turn()

        if interrupted:
            _console.print("\n[dim]Interrupted.[/dim]")
            return _SendResult(was_cancelled=True)

        _console.print()
        if not had_error:
            self._turn_count += 1
        _TOOLBAR_STATE.turn_count = self._turn_count

        status_line = build_chat_status_line(
            mode="repl",
            session_label="orchestrator",
            message_count=self._turn_count,
        )
        _console.print(f"[dim]{status_line}[/dim]")
        self._print_usage_line()
        return _SendResult()

    def _dispatch_event(self, event: Any) -> None:
        if isinstance(event, AssistantChunk):
            self._renderer.on_assistant_chunk(event.text, thought=event.thought)
        elif isinstance(event, ChatToolCallStart):
            self._renderer.on_tool_call_start(event)
        elif isinstance(event, ChatToolCallProgress):
            self._renderer.on_tool_call_progress(event)
        elif isinstance(event, UsageUpdate):
            self._renderer.on_usage_update(event)
        elif isinstance(event, PermissionRequest):
            self._spawn_permission_task(event)
        elif isinstance(event, TurnCancelled | TurnError | AssistantMessagePersisted):
            self._renderer.finalize_pending_markdown()
        elif isinstance(event, TurnDone | TurnStarted):
            return

    def _spawn_permission_task(self, event: PermissionRequest) -> None:
        if self._chat_session_id is None:
            return
        session_id = self._chat_session_id

        async def _runner() -> None:
            try:
                await self._permission_ui.handle_request(event, session_id)
            except asyncio.CancelledError:
                # Best-effort: ensure the engine doesn't keep waiting on us.
                with contextlib.suppress(Exception):
                    await self.client.chat.resolve_permission(
                        session_id, event.future_id, outcome="deny"
                    )
                raise
            except Exception:
                logger.exception("Permission handler raised; routing as deny")
                with contextlib.suppress(Exception):
                    await self.client.chat.resolve_permission(
                        session_id, event.future_id, outcome="deny"
                    )

        task = asyncio.create_task(_runner(), name=f"chat-permission-{event.future_id}")
        self._permission_tasks.add(task)
        task.add_done_callback(self._permission_tasks.discard)

    def _print_usage_line(self) -> None:
        usage = self._renderer.last_usage
        if usage is None:
            _TOOLBAR_STATE.context_pct = None
            return
        used = getattr(usage, "used", None)
        size = getattr(usage, "size", None)
        cost = getattr(usage, "cost", None)
        metrics_parts: list[str] = []
        if used is not None and size is not None and size > 0:
            used_k = used / 1000
            size_k = size / 1000
            _TOOLBAR_STATE.context_pct = used / size
            if size_k >= 1000:
                metrics_parts.append(f"ctx {used_k:.0f}k/{size_k:.0f}k")
            else:
                metrics_parts.append(f"ctx {used_k:.1f}k/{size_k:.1f}k")
        if cost is not None:
            metrics_parts.append(f"${cost:.2f}")
        if metrics_parts:
            _console.print(f"[dim]  {' · '.join(metrics_parts)}[/dim]")
        if used is not None and size is not None and size > 0:
            pct = used / size
            if pct > 0.8:
                _console.print(
                    f"[bold red]  ⚠ Context window {pct:.0%} full — agent may degrade[/bold red]"
                )
            elif pct > 0.6:
                _console.print(f"[yellow]  ⚠ Context window {pct:.0%} full[/yellow]")

    # ------------------------------------------------------------------
    # REPL loop and slash commands
    # ------------------------------------------------------------------

    async def _event_watcher(self) -> None:
        try:
            async for event in self.client.tasks.events.stream_all(replay=False):
                if event.event_type == "agent_failed":
                    error = (event.payload or {}).get("error", "Agent failed")
                    _console.print(f"\n[bold red]  ⚠ Task {event.task_id[:8]}: {error}[/bold red]")
                elif event.event_type == "agent_completed":
                    _console.print(
                        f"\n[green]  ✓ Task {event.task_id[:8]}: Agent completed[/green]"
                    )
        except asyncio.CancelledError:
            return
        except Exception:
            logger.opt(exception=True).warning("Event watcher stopped unexpectedly")

    async def _handle_repl_message(
        self,
        stripped: str,
        drain_pending: asyncio.Queue[str],
    ) -> bool:
        """Process one user message in the REPL loop.

        Returns True if the REPL loop should exit (e.g. ``/close`` issued).
        On cancel, empties *drain_pending* and updates the toolbar counter.

        When a non-slash message is typed while an agent session is attached
        (via ``/attach``), the message is routed to that session's event stream
        rather than the orchestrator — mirroring the TUI overlay behaviour.
        """
        rotate_tip_on_submit()
        if stripped.startswith("/"):
            return await self._handle_slash(stripped)
        if self._attached_agent_session_id is not None:
            await self._send_to_attached(stripped)
            return False
        try:
            result = await self._send(stripped)
        except KeyboardInterrupt:
            return False
        except (acp.RequestError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
            logger.exception("Chat send failed")
            _console.print(f"[red]Error:[/red] {exc}")
            return False
        if result.was_cancelled:
            # Clear pending queue on cancel — user pressed Esc
            while not drain_pending.empty():
                with contextlib.suppress(asyncio.QueueEmpty):
                    drain_pending.get_nowait()
            _TOOLBAR_STATE.queued_count = 0
        return False

    async def _send_to_attached(self, text: str) -> None:
        """Route a message to the currently attached agent session.

        On success, echoes the message to the console for confirmation.  If the
        session is no longer accepting input (COMPLETED, FAILED, etc.), prints
        an inline notice and clears the attachment so subsequent messages go to
        the orchestrator.
        """
        from kagan.core.errors import KaganError

        session_id = self._attached_agent_session_id
        if session_id is None:
            return
        try:
            await self.client.send_message_to_session(session_id, text)
            _console.print(f"[dim]→ {session_id[:8]}:[/dim] {text}")
        except KaganError as exc:
            _console.print(f"[dim]Agent session has finished — detaching. ({exc})[/dim]")
            self._attached_agent_session_id = None
            with contextlib.suppress(Exception):
                if self._chat_session_id:
                    await self.client.attach_chat(self._chat_session_id, None)
        except Exception as exc:
            logger.opt(exception=True).warning("_send_to_attached failed")
            _console.print(f"[red]Send error:[/red] {exc}")

    async def _repl_loop(self) -> None:
        _console.print(
            "[dim]Press [bold]/help[/bold] for commands, "
            "[bold]Ctrl-C[/bold] clear · [bold]Ctrl-D[/bold] exit.[/dim]\n"
        )
        submit_queue: asyncio.Queue[str | None] = asyncio.Queue()
        # Holds messages typed while a send is in progress (multi-turn queue).
        drain_pending: asyncio.Queue[str] = asyncio.Queue()
        session = _get_prompt_session(submit_queue)
        watcher_task = asyncio.create_task(self._event_watcher())
        done = False

        async def _pump_queue() -> None:
            nonlocal done
            while not done:
                if await self._drain_pending_messages(drain_pending):
                    done = True
                    return
                try:
                    text = await asyncio.wait_for(submit_queue.get(), timeout=0.05)
                except TimeoutError:
                    continue
                if text is None:
                    done = True
                    return
                stripped = text.strip()
                if not stripped:
                    continue
                if _TOOLBAR_STATE.is_streaming:
                    await drain_pending.put(stripped)
                    _TOOLBAR_STATE.queued_count = drain_pending.qsize()
                    continue
                if await self._handle_repl_message(stripped, drain_pending):
                    done = True
                    return

        try:
            with patch_stdout(raw=True):
                pump_task = asyncio.create_task(_pump_queue(), name="chat-repl-pump")
                prompt_task: asyncio.Task[str] = asyncio.create_task(
                    session.prompt_async(
                        _build_prompt_message,
                        placeholder=_build_prompt_placeholder,
                    ),
                    name="chat-repl-prompt",
                )
                try:
                    await asyncio.wait(
                        [pump_task, prompt_task],
                        return_when=asyncio.FIRST_COMPLETED,
                    )
                finally:
                    done = True
                    submit_queue.put_nowait(None)
                    while not drain_pending.empty():
                        with contextlib.suppress(asyncio.QueueEmpty):
                            drain_pending.get_nowait()
                    _TOOLBAR_STATE.queued_count = 0
                    for task in (pump_task, prompt_task):
                        if not task.done():
                            task.cancel()
                        with contextlib.suppress(asyncio.CancelledError, Exception):
                            await task
        finally:
            watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher_task
            _release_prompt_session()
            if not self._restart_requested:
                _console.print("\n[dim]Session ended.[/dim]")

    async def _drain_pending_messages(
        self,
        drain_pending: asyncio.Queue[str],
    ) -> bool:
        """Drain pre-queued messages accumulated while streaming was active.

        Returns True if the REPL loop should exit.
        """
        while not drain_pending.empty():
            try:
                queued_text = drain_pending.get_nowait()
            except asyncio.QueueEmpty:
                break
            _TOOLBAR_STATE.queued_count = drain_pending.qsize()
            if await self._handle_repl_message(queued_text, drain_pending):
                return True
        return False

    async def _handle_slash(self, text: str) -> bool:
        result = resolve_slash_input(
            text,
            session_label="Orchestrator",
            session_key="orchestrator",
            runtime_session_id=self._chat_session_id,
            current_backend=self.agent_backend,
            available_backends=list_registered_agent_backends(),
            project_name=self._project_name,
            project_id=self.client.active_project_id,
            turn_count=self._turn_count,
        )
        if not result.handled:
            return False

        self._print_slash_presentation(result)
        return await self._dispatch_slash_action(result)

    def _print_slash_presentation(self, result: SlashCommandOutcome) -> None:
        for line in build_slash_presentation_lines(result):
            if line.tone == "error":
                _console.print(f"[red]{line.text}[/red]")
            else:
                _console.print(line.text)

    async def _dispatch_slash_action(self, result: SlashCommandOutcome) -> bool:
        handler_name = _SLASH_ACTION_HANDLER_NAMES.get(result.action)
        if handler_name is None:
            return False
        handler = getattr(self, handler_name)
        return await handler(result)

    async def _handle_slash_clear(self, result: SlashCommandOutcome) -> bool:
        del result
        click.clear()
        return False

    async def _handle_slash_help(self, result: SlashCommandOutcome) -> bool:
        del result
        print_help_documentation()
        return False

    async def _handle_slash_show_agents(self, result: SlashCommandOutcome) -> bool:
        del result
        return await self._show_agent_picker()

    async def _handle_slash_switch_agent(self, result: SlashCommandOutcome) -> bool:
        return await self._switch_agent(result.data or result.selected_agent or "")

    async def _handle_slash_list_sessions(self, result: SlashCommandOutcome) -> bool:
        return await self._handle_session_switch(
            self._open_sessions(result.data or result.sessions_query)
        )

    async def _handle_slash_delete_session(self, result: SlashCommandOutcome) -> bool:
        await self._delete_session(result.data or result.delete_session_query or "")
        return False

    async def _handle_slash_new_session(self, result: SlashCommandOutcome) -> bool:
        del result
        return await self._handle_session_switch(self._create_new_session())

    async def _handle_slash_show_tool(self, result: SlashCommandOutcome) -> bool:
        show_tool_report(self._renderer, result.data or result.tool_query)
        return False

    async def _handle_slash_show_status(self, result: SlashCommandOutcome) -> bool:
        del result
        print_status_panel(
            session_title=self._session_title,
            chat_session_id=self._chat_session_id,
            project_name=self._project_name,
            agent_backend=self.agent_backend,
            turn_count=self._turn_count,
        )
        return False

    async def _handle_slash_show_analytics(self, result: SlashCommandOutcome) -> bool:
        await self._handle_analytics(result.data)
        return False

    async def _handle_slash_show_project(self, result: SlashCommandOutcome) -> bool:
        del result
        print_project_info(
            project_name=self._project_name,
            project_id=self.client.active_project_id,
        )
        return False

    async def _handle_slash_switch_project(self, result: SlashCommandOutcome) -> bool:
        await self._switch_project(result.data or result.project_switch_requested or "")
        return False

    async def _handle_slash_switch_repo(self, result: SlashCommandOutcome) -> bool:
        await self._switch_repo(result.data or result.repo_switch_requested or "")
        return False

    async def _handle_slash_show_repo(self, result: SlashCommandOutcome) -> bool:
        del result
        print_repo_info(
            repo_name=self._selected_repo_name,
            repo_id=self._selected_repo_id,
        )
        return False

    async def _handle_slash_show_approvals(self, result: SlashCommandOutcome) -> bool:
        self._show_approvals(result.data or "")
        return False

    async def _handle_slash_attach_agent(self, result: SlashCommandOutcome) -> bool:
        if result.data:
            await self._attach_agent(result.data)
        return False

    async def _handle_slash_detach_agent(self, result: SlashCommandOutcome) -> bool:
        del result
        await self._detach_agent()
        return False

    async def _handle_slash_close(self, result: SlashCommandOutcome) -> bool:
        del result
        return True

    async def _handle_session_switch(self, action: Any) -> bool:
        """Run a session-changing slash action; detach engine state if it triggers a restart."""
        should_restart = await action
        if should_restart and self._chat_session_id is not None:
            with contextlib.suppress(Exception):
                await self.client.chat.detach(self._chat_session_id)
        return should_restart

    async def _handle_analytics(self, data: str | None) -> None:
        if data and data.startswith("export:"):
            path = data[len("export:") :] or None
            await export_analytics_json(self.client, path)
        else:
            await print_analytics_panel(self.client)

    def _show_approvals(self, data: str) -> None:
        from kagan.cli.chat._permission_ui import get_session_approvals

        approvals = get_session_approvals()

        if data.startswith("revoke:"):
            target = data[len("revoke:") :]
            if target:
                approvals.revoke(target)
                _console.print(f"[green]Revoked approval:[/green] {target}")
            else:
                _console.print("[red]Usage: /approvals revoke <name>[/red]")
            return

        granted = approvals.list_granted()
        if not granted:
            _console.print("[dim]No session approvals granted yet.[/dim]")
            return
        _console.print("[bold]Session-granted approvals:[/bold]")
        for name in granted:
            display = strip_tool_prefix(name)
            _console.print(f"  [green]✓[/green] {display}  [dim](/approvals revoke {name})[/dim]")

    async def _switch_project(self, name: str) -> None:
        projects = await self.client.projects.list()
        target = None
        for p in projects:
            if p.name.casefold() == name.casefold():
                target = p
                break
        if target is None:
            _console.print(f"[red]Project not found: {name}[/red]")
            available = ", ".join(p.name for p in projects) if projects else "none"
            _console.print(f"[dim]Available: {available}[/dim]")
            return
        await self.client.projects.set_active(target.id)
        self._project_name = target.name
        _TOOLBAR_STATE.project_name = target.name
        _console.print(f"[green]Switched to project:[/green] {target.name}")
        await self._auto_select_repo(target.id)

    async def _switch_repo(self, name: str) -> None:
        if not self.client.active_project_id:
            _console.print("[red]No active project.[/red]")
            return
        repos = await self.client.projects.repos(self.client.active_project_id)
        target = None
        for r in repos:
            if r.name.casefold() == name.casefold() or r.id == name:
                target = r
                break
        if target is None:
            _console.print(f"[red]Repo not found:[/red] {name}")
            available = ", ".join(r.name for r in repos)
            if available:
                _console.print(f"[dim]Available repos:[/dim] {available}")
            return
        self._selected_repo_id = target.id
        self._selected_repo_name = target.name
        _console.print(f"[green]Switched to repo:[/green] {target.name}")

    async def _switch_agent(self, new_backend: str) -> bool:
        if new_backend == self.agent_backend:
            _console.print(f"[dim]Already using {new_backend}.[/dim]")
            return False

        _console.print(f"[bold]Switching to {new_backend}...[/bold]")
        self.agent_backend = new_backend
        _TOOLBAR_STATE.agent_backend = new_backend
        self._restart_requested = True
        await self.client.settings.set({"default_agent_backend": new_backend})
        return True

    async def _attach_agent(self, target_id: str) -> None:
        """Resolve *target_id* (task-id or session-id) and attach the chat session.

        Heuristic: try as a task-id first via ``resolve_active_session``.  If
        that yields no result, treat the id as a bare session-id and call
        ``attach_chat`` directly.  On any lookup failure a clear error is
        printed and the REPL state is not modified.
        """
        if self._chat_session_id is None:
            _console.print("[red]No active chat session — cannot attach.[/red]")
            return

        # Try resolving as task-id.
        session_id: str | None = None
        agent_role: str | None = None
        try:
            tasks = await self.client.tasks.list()
            matched_task = next(
                (t for t in tasks if t.id == target_id or t.id.startswith(target_id)),
                None,
            )
            if matched_task is not None:
                resolved = await self.client.resolve_active_session(matched_task.id)
                if resolved is not None:
                    session_id = resolved.id
                    agent_role = getattr(resolved, "agent_role", None)
        except Exception:
            logger.opt(exception=True).warning(
                "_attach_agent: task lookup failed for {}", target_id
            )

        # Fall back to treating target_id as a raw session-id.
        if session_id is None:
            # Check running agents to see if this session exists.
            try:
                project_id = self.client.active_project_id
                rows = await self.client.list_running_agents(project_id=project_id)
                matched_row = next(
                    (
                        r
                        for r in rows
                        if r.session_id == target_id or r.session_id.startswith(target_id)
                    ),
                    None,
                )
                if matched_row is not None:
                    session_id = matched_row.session_id
                    agent_role = matched_row.agent_role
            except Exception:
                logger.opt(exception=True).warning(
                    "_attach_agent: session lookup failed for {}", target_id
                )

        if session_id is None:
            _console.print(f"[red]Unknown task or session: {target_id}[/red]")
            return

        try:
            await self.client.attach_chat(self._chat_session_id, session_id, agent_role=agent_role)
        except Exception as exc:
            logger.opt(exception=True).warning("_attach_agent: attach_chat failed")
            _console.print(f"[red]Attach failed: {exc}[/red]")
            return

        self._attached_agent_session_id = session_id
        role_label = (agent_role or "worker").capitalize()
        _console.print(f"[green]Attached:[/green] {role_label} · {session_id[:8]}")
        _console.print(
            "[dim]Attached — messages are routed to the agent session. /detach to return.[/dim]"
        )

    async def _detach_agent(self) -> None:
        """Detach the current chat session from any agent, returning to orchestrator."""
        if self._chat_session_id is None:
            _console.print("[dim]No active chat session.[/dim]")
            return

        try:
            await self.client.attach_chat(self._chat_session_id, None)
        except Exception as exc:
            logger.opt(exception=True).warning("_detach_agent: attach_chat(None) failed")
            _console.print(f"[red]Detach failed: {exc}[/red]")
            return

        self._attached_agent_session_id = None
        _console.print("[green]Detached → Orchestrator[/green]")
