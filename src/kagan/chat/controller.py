"""ChatController — orchestrator agent lifecycle and _OrchestratorACPClient."""

import asyncio
import contextlib
import os
import shutil
import sys
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from uuid import uuid4

import acp
import click
from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ToolCallProgress,
    ToolCallStart,
    UsageUpdate,
)
from loguru import logger
from rich.console import Group
from rich.live import Live
from rich.markup import escape as _rich_escape
from rich.measure import Measurement
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kagan.chat._handshake import execute_handshake
from kagan.chat._signals import install_sigint_handler, restore_sigint_handler
from kagan.chat._streaming import OutputFlushManager, ResponseChunkBuffer
from kagan.chat._title import generate_session_title
from kagan.chat.acp import (
    _ACP_STDIO_BUFFER_LIMIT_BYTES,
    _acp_handshake_timeout_seconds,
)
from kagan.chat.agents import format_agent_backend_list, list_registered_agent_backends
from kagan.chat.commands import (
    SLASH_COMMAND_REGISTRY,
    SlashAction,
    build_slash_presentation_lines,
    resolve_slash_input,
)
from kagan.chat.prompt import (
    _format_user_request_block,
    _runtime_guidance_for_request,
    build_chat_status_line,
    build_orchestrator_prompt,
)
from kagan.chat.repl import (
    _TOOLBAR_STATE,
    WAVE_FRAMES,
    SearchPickerOption,
    _build_prompt_message,
    _build_prompt_placeholder,
    _console,
    _env_flag_enabled,
    _find_git_root,
    _get_prompt_session,
    searchable_picker,
    supports_interactive_picker,
)
from kagan.chat.sessions import (
    build_chat_session_list_items,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    list_chat_sessions,
    resolve_chat_session_selector,
    resolve_task_session_binding,
    save_chat_session,
    set_last_session_id,
)
from kagan.chat.tool_runs import ToolRunTracker
from kagan.core import (
    KAGAN_AGENT_EMAIL,
    KAGAN_AGENT_NAME,
    ACPClientBase,
    BackendCapability,
    DBWatcher,
    build_agent_environment,
    build_mcp_manifest,
    default_db_path,
    get_backend_spec,
    get_system_git_identity,
    resolve_acp_command,
    resolve_orchestrator_prompt,
)
from kagan.core.enums import SessionEventType
from kagan.core.errors import AgentError, KaganError


@dataclass(frozen=True, slots=True)
class _WaveIndicator:
    _start: float = field(default_factory=time.monotonic)

    def __rich_console__(self, console, options):
        elapsed = time.monotonic() - self._start
        idx = int(elapsed / 0.10) % len(WAVE_FRAMES)
        yield from console.render(Text(WAVE_FRAMES[idx], style="dim cyan"), options)

    def __rich_measure__(self, console, options):
        del console, options
        return Measurement(len(WAVE_FRAMES[0]), len(WAVE_FRAMES[0]))


class _TurnWaveAnimation:
    """Turn wave animation helper with clear state management."""

    def __init__(self, _console, frames: tuple[str, ...]) -> None:
        self._console = _console
        self._frames = frames
        self._line_width = len(frames[0])
        self._stop_event = asyncio.Event()
        self._task: asyncio.Task[None] | None = None
        self._active = False

    def _write_wave(self, text: str) -> None:
        self._console.file.write(text)
        self._console.file.flush()

    def _clear_line(self) -> None:
        self._write_wave(f"\r{' ' * self._line_width}\r")

    def stop(self) -> None:
        if self._active:
            self._stop_event.set()

    async def _animate(self) -> None:
        self._active = True
        frame_index = 0
        while not self._stop_event.is_set():
            frame = self._frames[frame_index]
            self._write_wave(f"\r{frame}")
            frame_index = (frame_index + 1) % len(self._frames)
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=0.10)
            except TimeoutError:
                continue
        self._clear_line()
        self._active = False

    async def start(self) -> None:
        self._task = asyncio.create_task(self._animate(), name="chat-turn-wave")

    async def shutdown(self) -> None:
        self._stop_event.set()
        if self._task is not None:
            with contextlib.suppress(asyncio.CancelledError):
                await self._task
        if self._active:
            self._clear_line()


@contextlib.asynccontextmanager
async def _turn_wave_animation(
    _console, frames: tuple[str, ...]
) -> AsyncIterator[Callable[[], None]]:
    animator = _TurnWaveAnimation(_console, frames)
    await animator.start()
    try:
        yield animator.stop
    finally:
        await animator.shutdown()


class _OrchestratorACPClient(ACPClientBase):
    def __init__(self) -> None:
        self._conn: acp.Agent | None = None
        self._streaming = False
        self._show_thoughts = _env_flag_enabled("KAGAN_CHAT_SHOW_THOUGHTS", default=False)
        self._tool_runs = ToolRunTracker()
        self._response_chunks = ResponseChunkBuffer()
        self._output_flusher = OutputFlushManager(_console)
        self._first_update_notified = False
        self._on_first_update: Callable[[], None] | None = None
        self.last_usage: Any = None

    def start_turn(self, *, on_first_update: Callable[[], None] | None = None) -> None:
        self._output_flusher.shutdown()
        self._response_chunks.clear()
        self._output_flusher.clear()
        self._tool_runs.start_turn()
        self._first_update_notified = False
        self._on_first_update = on_first_update
        self.last_usage = None

    def _notify_first_update(self) -> None:
        if self._first_update_notified:
            return
        self._first_update_notified = True
        if self._on_first_update is None:
            return
        self._on_first_update()

    def finish_turn(self) -> str:
        self._output_flusher.flush(force=True)
        response = self._response_chunks.get_all().strip()
        return response

    def tool_report(self, query: str | None) -> tuple[str, bool]:
        return self._tool_runs.tool_report(query)

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        if isinstance(update, AgentMessageChunk):
            content = getattr(update, "content", None)
            if content and getattr(content, "type", None) == "text":
                text = getattr(content, "text", "") or ""
                if text:
                    self._streaming = True
                    self._notify_first_update()
                    self._response_chunks.append(text)
                    self._output_flusher.queue_chunk(text)
                    self._output_flusher.flush()
        elif isinstance(update, AgentThoughtChunk):
            if self._show_thoughts:
                content = getattr(update, "content", None)
                if content and getattr(content, "type", None) == "text":
                    text = getattr(content, "text", "") or ""
                    if text:
                        self._notify_first_update()
                        self._output_flusher.flush(force=True)
                        _console.print(f"[dim]{_rich_escape(text)}[/dim]", end="", highlight=False)
                        _console.file.flush()
        elif isinstance(update, ToolCallStart):
            self._notify_first_update()
            self._output_flusher.flush(force=True)
            title = getattr(update, "title", None) or getattr(update, "name", None) or "tool"
            tool_key = self._tool_runs.tool_key(update)
            if self._tool_runs.status_for(tool_key) != "started":
                self._tool_runs.set_status(tool_key, "started")
                key_arg = self._tool_runs.extract_tool_key_arg(update)
                run = self._tool_runs.ensure_tool_run(update=update, title=title, key_arg=key_arg)
                run.status = "running"
                run.args = self._tool_runs.serialize_payload(
                    self._tool_runs.extract_tool_args(update)
                )
                arg_suffix = f"({key_arg})" if key_arg else ""
                _console.print(f"\n  [dim]● {title}{arg_suffix}[/dim]", highlight=False)
        elif isinstance(update, ToolCallProgress):
            self._notify_first_update()
            self._output_flusher.flush(force=True)
            status = getattr(update, "status", None)
            title = getattr(update, "title", None) or "tool"
            tool_key = self._tool_runs.tool_key(update)
            if status and self._tool_runs.status_for(tool_key) == status:
                return
            key_arg = self._tool_runs.extract_tool_key_arg(update)
            run = self._tool_runs.ensure_tool_run(update=update, title=title, key_arg=key_arg)
            if status:
                run.status = str(status)
            args = self._tool_runs.serialize_payload(self._tool_runs.extract_tool_args(update))
            if args:
                run.args = args
            result = self._tool_runs.serialize_payload(self._tool_runs.extract_tool_result(update))
            if result:
                run.result = result
            arg_suffix = f"({key_arg})" if key_arg else ""
            if status == "completed":
                self._tool_runs.set_status(tool_key, status)
                run.ended_at = run.ended_at or time.monotonic()
                duration = ""
                if run.started_at and run.ended_at:
                    elapsed = run.ended_at - run.started_at
                    duration = f" [dim]{elapsed:.1f}s[/dim]" if elapsed >= 0.1 else ""
                _console.print(f"  [green]● {title}{arg_suffix}[/green]{duration}", highlight=False)
            elif status == "failed":
                self._tool_runs.set_status(tool_key, status)
                run.ended_at = run.ended_at or time.monotonic()
                _console.print(f"  [red]● {title}{arg_suffix} failed[/red]", highlight=False)
        elif isinstance(update, UsageUpdate):
            self._notify_first_update()
            self.last_usage = update

    async def request_permission(self, options: Any, session_id: str, tool_call: Any, **_kw: Any):
        from acp.schema import AllowedOutcome, RequestPermissionResponse

        for option in options:
            if option.kind in {"allow_always", "allow_once"}:
                return RequestPermissionResponse(
                    outcome=AllowedOutcome(outcome="selected", option_id=option.option_id)
                )
        from acp.schema import DeniedOutcome

        return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))


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
        self._acp_conn: Any | None = None
        self._acp_client: _OrchestratorACPClient | None = None
        self._acp_session_id: str | None = None
        self._is_primed = False
        self._restart_requested = False
        self._turn_count = 0
        self._chat_session_id: str | None = None
        self._chat_session_source = "repl"
        self._persist_repl_session = True
        self._chat_history: list[tuple[str, str]] = []
        self._rendered_messages: list[str] = []
        self._restored_messages_printed = False
        self._session_title: str | None = None
        self._title_task: asyncio.Task[None] | None = None
        self._project_name: str | None = None
        self._watcher = DBWatcher(client)

    async def hydrate_persistent_session(self, *, explicit_session_id: str | None = None) -> None:
        selected = await self._resolve_initial_session(explicit_session_id)
        if selected is None:
            selected = await create_chat_session(
                self.client,
                source="repl",
                label="REPL session",
                agent_backend=self.agent_backend,
                project_id=self.client.active_project_id,
            )
        await self._attach_session(selected, switching=False)

    async def _resolve_initial_session(
        self, explicit_session_id: str | None
    ) -> dict[str, Any] | None:
        if explicit_session_id:
            persisted = await get_chat_session(self.client, explicit_session_id)
            if persisted is not None:
                return persisted
            return await resolve_task_session_binding(self.client, explicit_session_id)
        # Always start a fresh session — users reconnect via /sessions or --session-id
        return None

    async def _attach_session(self, session: dict[str, Any], *, switching: bool) -> bool:
        previous_session_id = self._chat_session_id
        session_id = str(session.get("id") or "").strip()
        if not session_id:
            return False
        source = str(session.get("source") or "repl").strip() or "repl"
        self._chat_session_id = session_id
        self._chat_session_source = source
        self._persist_repl_session = source == "repl"
        self._mcp_session_id = session_id
        self._is_primed = False
        history = session.get("orchestrator_history") or []
        self._chat_history = [
            (str(item[0]).strip(), str(item[1]).strip())
            for item in history
            if isinstance(item, list | tuple) and len(item) == 2
        ]
        rendered = session.get("messages_rendered") or []
        self._rendered_messages = [str(line).rstrip() for line in rendered if str(line).strip()]
        self._turn_count = sum(1 for role, _ in self._chat_history if role == "assistant")
        self._restored_messages_printed = False
        # Restore session title from persisted label
        persisted_label = str(session.get("label") or "")
        default_label = f"Session {session_id}"
        self._session_title = persisted_label if persisted_label != default_label else None
        backend = session.get("agent_backend")
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
            await set_last_session_id(self.client, scope="repl", session_id=session_id)
            await self._persist_session()
        return self._restart_requested

    def _append_turn(self, user_text: str, assistant_reply: str) -> None:
        self._chat_history.append(("user", user_text))
        self._rendered_messages.append(f"You: {user_text.strip()}")
        if assistant_reply:
            self._chat_history.append(("assistant", assistant_reply))
            self._rendered_messages.append(f"Agent: {assistant_reply}")
        self._chat_history = self._chat_history[-120:]
        self._rendered_messages = self._rendered_messages[-300:]

    async def _persist_session(self) -> None:
        if self._chat_session_id is None or not self._persist_repl_session:
            return
        await save_chat_session(
            self.client,
            {
                "id": self._chat_session_id,
                "label": self._session_title or f"Session {self._chat_session_id}",
                "source": self._chat_session_source,
                "agent_backend": self.agent_backend,
                "orchestrator_history": [[role, content] for role, content in self._chat_history],
                "messages_rendered": self._rendered_messages,
            },
        )
        await set_last_session_id(self.client, scope="repl", session_id=self._chat_session_id)

    async def _generate_session_title(self, user_message: str, assistant_reply: str) -> None:
        title = await generate_session_title(
            self.client,
            user_message=user_message,
            assistant_reply=assistant_reply,
            agent_backend=self.agent_backend,
        )
        if title:
            self._session_title = title
            await self._persist_session()

    def _print_restored_messages(self) -> None:
        if self._restored_messages_printed or not self._rendered_messages:
            return
        _console.print("[dim]Resumed transcript:[/dim]")
        for line in self._rendered_messages[-120:]:
            _console.print(line)
        _console.print()
        self._restored_messages_printed = True

    async def _open_sessions(self, query: str | None) -> bool:
        sessions = await list_chat_sessions(self.client, project_id=self.client.active_project_id)
        if not sessions:
            _console.print("[dim]No persisted sessions yet.[/dim]")
            return False

        items = build_chat_session_list_items(sessions, current_session_id=self._chat_session_id)
        sessions_by_id: dict[str, dict[str, Any]] = {
            str(session.get("id") or ""): session for session in sessions
        }

        selected: dict[str, Any] | None = None
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
                self._print_session_list(items)
                return False
            selected_id = await searchable_picker(
                "Select session",
                [self._build_session_picker_option(item) for item in items],
            )
            if selected_id is None:
                return False
            selected = sessions_by_id.get(selected_id)
            if selected is None:
                return False

        should_restart = await self._attach_session(selected, switching=True)
        _console.print(f"[green]Attached session:[/green] {selected_id or selected.get('id')}")
        if not should_restart:
            self._print_restored_messages()
        return should_restart

    def _print_session_list(self, items: list[Any]) -> None:
        table = Table(box=None, show_header=False, pad_edge=False)
        table.add_column(justify="right", style="dim", no_wrap=True)
        table.add_column(no_wrap=True)
        table.add_column(style="dim", no_wrap=True)
        table.add_column(style="dim", no_wrap=True)
        table.add_column(no_wrap=True)
        for item in items:
            marker = "[bold cyan]● current[/bold cyan]" if item.is_current else ""
            table.add_row(
                str(item.index),
                item.label,
                item.agent_backend or "",
                item.updated_relative or "",
                marker,
            )
        _console.print(table)
        _console.print()
        _console.print("[dim]/sessions <n> attach · /new create · /delete <n> remove[/dim]")

    def _build_session_picker_option(self, item: Any) -> SearchPickerOption:
        meta_parts = [part for part in (item.agent_backend, item.updated_relative) if part]
        if item.is_current:
            meta_parts.append("current")
        return SearchPickerOption(
            value=item.session_id,
            label=f"{item.index}. {item.label}",
            meta=" · ".join(meta_parts),
        )

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
        created = await create_chat_session(
            self.client,
            source="repl",
            label="REPL session",
            agent_backend=self.agent_backend,
            project_id=self.client.active_project_id,
        )
        should_restart = await self._attach_session(created, switching=True)
        _console.print(f"[green]New session:[/green] {created['id']}")
        return should_restart

    async def _delete_session(self, query: str) -> None:
        sessions = await list_chat_sessions(self.client)
        if not sessions:
            _console.print("[dim]No sessions to delete.[/dim]")
            return

        items = build_chat_session_list_items(sessions, current_session_id=self._chat_session_id)
        sessions_by_id: dict[str, dict[str, Any]] = {
            str(session.get("id") or ""): session for session in sessions
        }

        target_item = resolve_chat_session_selector(items, query)
        target = sessions_by_id.get(target_item.session_id) if target_item is not None else None
        if target is None:
            _console.print(f"[red]Unknown session: {query}[/red]")
            return

        target_id = str(target.get("id") or "")
        target_label = str(target.get("label") or target_id)
        if target_id == self._chat_session_id:
            _console.print("[red]Cannot delete the current session.[/red]")
            return

        deleted = await delete_chat_session(self.client, target_id)
        if deleted:
            _console.print(f"[green]Deleted:[/green] {target_label} [{target_id}]")
        else:
            _console.print(f"[red]Failed to delete session {target_id}.[/red]")

    async def ensure_project(self) -> bool:
        """Resolve an active project from CWD.  Always checks CWD on every boot.

        Returns False if no project could be resolved or created.
        """
        cwd = Path.cwd()
        cwd_str = str(cwd)

        # 1. Try to match CWD to a known project by repo path.
        project = await self.client.projects.find_by_repo(cwd_str)
        if project is not None:
            await self.client.projects.set_active(project.id)
            self._project_name = project.name
            return True

        # 2. Try to match by git root.
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
                        return True

        # 3. No match — bootstrap a new project for this CWD.
        result = await self._bootstrap_project()
        if result:
            await self._refresh_project_name()
        return result

    async def _refresh_project_name(self) -> None:
        projects = await self.client.projects.list()
        active_id = self.client.active_project_id
        for p in projects:
            if p.id == active_id:
                self._project_name = p.name
                return
        self._project_name = None

    async def _bootstrap_project(self) -> bool:
        cwd = Path.cwd()
        git_root = _find_git_root(cwd)

        repo_root = git_root or cwd
        repo_path = str(repo_root)
        default_name = repo_root.name

        if not sys.stdin.isatty():
            _console.print(
                "[red]No project found.[/red] Run [bold]kagan[/bold] interactively "
                "or use [bold]kg chat --project <name>[/bold] to specify one."
            )
            return False

        _console.print()
        _console.print("[bold]No project found.[/bold] Let's create one.")
        if git_root is None:
            _console.print(
                "[dim]No git repo detected. Core will initialize one based on settings.[/dim]"
            )
        else:
            _console.print(f"[dim]Detected git repo:[/dim] {repo_path}")
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
            _console.print(f"[green]\u2713[/green] Using system git profile: {label}")
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
                f"[green]\u2713[/green] Using custom identity: {custom_name} <{custom_email}>"
            )
        else:
            await self.client.settings.set({"git_user_mode": "kagan_agent"})
            _console.print(
                f"[green]\u2713[/green] Using default: {KAGAN_AGENT_NAME} <{KAGAN_AGENT_EMAIL}>"
            )

    async def _create_project(self, name: str, repo_path: str) -> bool:
        project_id: str | None = None
        try:
            project = await self.client.projects.create(name)
            project_id = project.id
            await self.client.projects.add_repo(project.id, repo_path)
            await self.client.projects.set_active(project.id)
            _console.print(f"[green]\u2713[/green] Created project [bold]{name}[/bold]")
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
                    f"[green]\u2713[/green] Using existing project [bold]{existing.name}[/bold]"
                )
                return True

            logger.exception("Failed to bootstrap project")
            _console.print(f"[red]Failed to create project:[/red] {exc}")
            return False

    def _resolve_acp_command(self) -> tuple[str, list[str]]:
        backend = get_backend_spec(self.agent_backend)
        if not backend.has_capability(BackendCapability.ACP_STREAMING):
            raise AgentError(
                f"Agent backend {self.agent_backend!r} does not support ACP. "
                "Set a different orchestrator agent or use an ACP-capable backend."
            )

        acp_cmd = resolve_acp_command(self.agent_backend)
        if not acp_cmd:
            raise AgentError(f"No ACP command configured for backend {self.agent_backend!r}")

        exe = acp_cmd[0]
        if shutil.which(exe) is None:
            hint = ""
            if exe == "npx":
                hint = " Install Node.js first: https://nodejs.org/"
            raise AgentError(f"ACP executable {exe!r} not found on PATH.{hint}")

        return acp_cmd[0], acp_cmd[1:]

    async def run(self, *, prompt: str | None = None) -> None:
        while True:
            self._restart_requested = False
            self._is_primed = False
            await self._run_agent_session(prompt=prompt)
            if not self._restart_requested:
                break
            prompt = None
            _console.print()
            _console.print(f"[bold cyan]Switching to {self.agent_backend}...[/bold cyan]")

    async def _run_agent_session(self, *, prompt: str | None = None) -> None:
        try:
            exe, exe_args = self._resolve_acp_command()
        except AgentError as exc:
            _console.print(f"[red]{exc}[/red]")
            return

        session_id = self._mcp_session_id or uuid4().hex[:8]
        db_path = str(default_db_path())
        mcp_content = build_mcp_manifest(
            session_id=session_id,
            db_path=db_path,
            role="ORCHESTRATOR",
            project_id=self.client.active_project_id,
        )
        cwd = Path.cwd()
        mcp_path = cwd / ".mcp.json"
        try:
            await asyncio.to_thread(mcp_path.write_text, mcp_content, "utf-8")
        except OSError as exc:
            import errno

            if exc.errno == errno.ENOSPC:  # No space left on device
                raise AgentError(
                    f"Cannot write MCP manifest to {mcp_path}: Disk is full. "
                    f"Free up disk space and try again."
                ) from exc
            raise AgentError(f"Failed to write MCP manifest to {mcp_path}: {exc}") from exc
        logger.debug("Wrote .mcp.json with admin access at {}", mcp_path)

        backend = get_backend_spec(self.agent_backend)
        env = build_agent_environment(
            session_id=session_id,
            task_id=None,
            backend_env_vars=backend.env_vars,
        )

        self._acp_client = _OrchestratorACPClient()

        try:
            async with acp.spawn_agent_process(
                self._acp_client,
                exe,
                *exe_args,
                cwd=str(cwd),
                env=env,
                transport_kwargs={"limit": _ACP_STDIO_BUFFER_LIMIT_BYTES},
            ) as (conn, proc):
                self._acp_conn = conn
                logger.info("ACP agent process spawned pid={}", proc.pid)

                ready_event = asyncio.Event()
                handshake_error: Exception | None = None

                async def _do_handshake():
                    nonlocal handshake_error
                    try:
                        acp_session_id, error = await execute_handshake(
                            conn,
                            self.agent_backend,
                            session_id,
                            self.client.active_project_id,
                            cwd,
                        )
                        if error is not None:
                            handshake_error = error
                        else:
                            self._acp_session_id = acp_session_id
                    except (
                        TimeoutError,
                        acp.RequestError,
                        OSError,
                        RuntimeError,
                        ValueError,
                    ) as exc:
                        handshake_error = exc
                    except Exception as exc:
                        handshake_error = exc
                    finally:
                        ready_event.set()

                handshake_task = asyncio.create_task(_do_handshake())

                skip_anim = os.environ.get("KAGAN_CHAT_SKIP_BOOT_ANIMATION") == "1"
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

                await handshake_task

                if handshake_error:
                    if isinstance(handshake_error, TimeoutError):
                        timeout_s = _acp_handshake_timeout_seconds(self.agent_backend)
                        _console.print(
                            "[red]"
                            f"ACP handshake timed out after {timeout_s:.0f}s. "
                            "Set KAGAN_ACP_HANDSHAKE_TIMEOUT_SECONDS "
                            "(or KAGAN_ACP_STARTUP_TIMEOUT_SECONDS) to increase this limit."
                            "[/red]"
                        )
                    else:
                        logger.exception("ACP handshake failed")
                        _console.print(f"[red]ACP handshake failed: {handshake_error}[/red]")
                    return

                _console.print("[green]\u2713[/green] Agent ready.")
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

        except (FileNotFoundError, PermissionError) as exc:
            _console.print(f"[red]Failed to spawn agent: {exc}[/red]")
        except Exception as exc:
            logger.exception("Unexpected ACP agent session failure")
            _console.print(f"[red]Agent session failed: {exc}[/red]")
        finally:
            await self._watcher.close()
            self._acp_conn = None
            self._acp_session_id = None
            if mcp_path.exists():
                with contextlib.suppress(OSError):
                    mcp_path.unlink()

    async def _send(self, text: str) -> None:
        if self._acp_conn is None or self._acp_session_id is None:
            _console.print("[red]No agent connected. Try restarting.[/red]")
            return

        ctx = self._watcher.drain_context()
        request_text = f"{ctx}\n\n{text}" if ctx else text

        runtime_guidance = _runtime_guidance_for_request(request_text)
        request_block = (
            request_text if runtime_guidance is None else f"{request_text}\n\n{runtime_guidance}"
        )

        prompt_blocks: list[Any] = [acp.text_block(request_block)]
        if not self._is_primed:
            resumed_text = build_orchestrator_prompt(
                self._chat_history, request_text, history_limit=20
            )
            settings = await self.client.settings.get()
            system_prompt = resolve_orchestrator_prompt(settings, Path.cwd())
            prompt_blocks = [
                acp.text_block(system_prompt),
                acp.text_block(_format_user_request_block(resumed_text)),
            ]
            self._is_primed = True

        _TOOLBAR_STATE.context_pct = None
        _console.print()
        _console.print(f"[bold]You:[/bold] {text}")

        interrupted = False
        async with _turn_wave_animation(_console, WAVE_FRAMES) as stop_animation:
            if self._acp_client is not None:
                self._acp_client.start_turn(on_first_update=stop_animation)
            prompt_task = asyncio.create_task(
                self._acp_conn.prompt(
                    session_id=self._acp_session_id,
                    prompt=prompt_blocks,
                ),
                name="chat-prompt",
            )
            original_sigint = install_sigint_handler(prompt_task)
            try:
                await prompt_task
            except asyncio.CancelledError:
                interrupted = True
            except (acp.RequestError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
                logger.exception("Failed to send prompt to agent")
                _console.print(f"\n[red]Agent error: {exc}[/red]")
                return
            except Exception as exc:
                logger.exception("Unexpected failure while sending prompt to agent")
                _console.print(f"\n[red]Agent error: {exc}[/red]")
                return
            finally:
                restore_sigint_handler(original_sigint)

        assistant_reply = ""
        if self._acp_client is not None:
            try:
                assistant_reply = self._acp_client.finish_turn()
            except Exception:
                logger.debug("finish_turn failed, treating as empty reply", exc_info=True)

        self._append_turn(text, assistant_reply)

        if interrupted:
            _console.print("\n[dim]Interrupted.[/dim]")
            await self._persist_session()
            return

        _console.print()  # newline after streamed output
        self._turn_count += 1
        _TOOLBAR_STATE.turn_count = self._turn_count

        if self._turn_count == 1 and self._session_title is None:
            self._title_task = asyncio.create_task(
                self._generate_session_title(text, assistant_reply),
                name="chat-title-gen",
            )

        status_line = build_chat_status_line(
            mode="repl",
            session_label="orchestrator",
            message_count=self._turn_count,
        )
        _console.print(f"[dim]{status_line}[/dim]")
        if self._acp_client is not None and self._acp_client.last_usage is not None:
            usage = self._acp_client.last_usage
            metrics_parts: list[str] = []
            if usage.used is not None and usage.size is not None and usage.size > 0:
                used_k = usage.used / 1000
                size_k = usage.size / 1000
                _TOOLBAR_STATE.context_pct = usage.used / usage.size
                if size_k >= 1000:
                    metrics_parts.append(f"ctx {used_k:.0f}k/{size_k:.0f}k")
                else:
                    metrics_parts.append(f"ctx {used_k:.1f}k/{size_k:.1f}k")
            if usage.cost is not None:
                metrics_parts.append(f"${usage.cost.amount:.2f}")
            if metrics_parts:
                _console.print(f"[dim]  {' · '.join(metrics_parts)}[/dim]")
            # Context window warning
            if usage.used is not None and usage.size is not None and usage.size > 0:
                pct = usage.used / usage.size
                if pct > 0.8:
                    _console.print(
                        f"[bold red]  ⚠ Context window {pct:.0%} full — "
                        f"agent may degrade[/bold red]"
                    )
                elif pct > 0.6:
                    _console.print(f"[yellow]  ⚠ Context window {pct:.0%} full[/yellow]")
        else:
            _TOOLBAR_STATE.context_pct = None
        await self._persist_session()

    async def _event_watcher(self) -> None:
        """Background coroutine that prints one-line notifications for task events."""
        try:
            async for event in self.client.tasks.events.stream_all(replay=False):
                if event.event_type == SessionEventType.AGENT_FAILED:
                    error = (event.payload or {}).get("error", "Agent failed")
                    _console.print(
                        f"\n[bold red]  \u26a0 Task {event.task_id[:8]}: {error}[/bold red]"
                    )
                elif event.event_type == SessionEventType.AGENT_COMPLETED:
                    _console.print(
                        f"\n[green]  \u2713 Task {event.task_id[:8]}: Agent completed[/green]"
                    )
        except asyncio.CancelledError:
            return
        except Exception:
            logger.opt(exception=True).warning("Event watcher stopped unexpectedly")

    async def _repl_loop(self) -> None:
        _console.print(
            "[dim]Press [bold]/help[/bold] for commands and [bold]Ctrl-D[/bold] to exit.[/dim]\n"
        )
        watcher_task = asyncio.create_task(self._event_watcher())
        try:
            while True:
                try:
                    line = await _get_prompt_session().prompt_async(
                        _build_prompt_message(),
                        placeholder=_build_prompt_placeholder(),
                    )
                except EOFError:
                    break
                except KeyboardInterrupt:
                    continue

                stripped = line.strip()
                if not stripped:
                    continue

                if stripped.startswith("/"):
                    if await self._handle_slash(stripped):
                        break  # /exit or agent switch
                    continue

                try:
                    await self._send(stripped)
                except KeyboardInterrupt:
                    continue  # Safety net — SIGINT handler should handle this in _send()
                except (acp.RequestError, TimeoutError, OSError, RuntimeError, ValueError) as exc:
                    logger.exception("Chat send failed")
                    _console.print(f"[red]Error:[/red] {exc}")
        finally:
            watcher_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await watcher_task
            if not self._restart_requested:
                _console.print("\n[dim]Session ended.[/dim]")

    async def _handle_slash(self, text: str) -> bool:
        result = resolve_slash_input(
            text,
            session_label="Orchestrator",
            session_key="orchestrator",
            runtime_session_id=self._acp_session_id,
            current_backend=self.agent_backend,
            available_backends=list_registered_agent_backends(),
            project_name=self._project_name,
            project_id=self.client.active_project_id,
            turn_count=self._turn_count,
        )
        if not result.handled:
            return False

        # Print any info/error presentation lines
        for line in build_slash_presentation_lines(result):
            if line.tone == "error":
                _console.print(f"[red]{line.text}[/red]")
            else:
                _console.print(line.text)

        match result.action:
            case SlashAction.CLEAR:
                click.clear()
            case SlashAction.SHOW_HELP:
                self._print_help_documentation()
            case SlashAction.SHOW_AGENTS:
                return await self._show_agent_picker()
            case SlashAction.SWITCH_AGENT:
                return await self._switch_agent(result.data or result.selected_agent or "")
            case SlashAction.LIST_SESSIONS:
                return await self._open_sessions(result.data or result.sessions_query)
            case SlashAction.DELETE_SESSION:
                await self._delete_session(result.data or result.delete_session_query or "")
            case SlashAction.NEW_SESSION:
                return await self._create_new_session()
            case SlashAction.SHOW_TOOL:
                self._show_tool_report(result.data or result.tool_query)
            case SlashAction.SHOW_STATUS:
                self._print_status_panel()
            case SlashAction.SHOW_PROJECT:
                self._print_project_info()
            case SlashAction.SWITCH_PROJECT:
                await self._switch_project(result.data or result.project_switch_requested or "")
            case SlashAction.CLOSE:
                return True
            case _:
                pass

        return False

    def _print_help_documentation(self) -> None:
        # Build reverse alias map: {target: [aliases]}
        aliases = SLASH_COMMAND_REGISTRY.aliases
        reverse_aliases: dict[str, list[str]] = {}
        for alias, target in aliases.items():
            reverse_aliases.setdefault(target, []).append(alias)

        spec_by_name = {spec.name: spec for spec in SLASH_COMMAND_REGISTRY.specs()}
        sections = [
            ("Global", ["help", "flow", "status", "clear", "exit"]),
            ("Sessions", ["new", "sessions", "delete"]),
            ("Workspace", ["project", "agents", "tool"]),
        ]

        def _label_for(name: str) -> str:
            parts = [f"/{name}"]
            for alias in sorted(reverse_aliases.get(name, [])):
                parts.append(f"/{alias}")
            return ", ".join(parts)

        blocks: list[object] = []
        for title, names in sections:
            table = Table(box=None, show_header=False, pad_edge=False, padding=(0, 2, 0, 0))
            table.add_column(style="bold cyan", no_wrap=True)
            table.add_column(style="default")
            for name in names:
                spec = spec_by_name.get(name)
                if spec is None:
                    continue
                table.add_row(_label_for(name), spec.description)
            blocks.append(Text(title, style="bold"))
            blocks.append(table)

        keyboard = Table(box=None, show_header=False, pad_edge=False, padding=(0, 2, 0, 0))
        keyboard.add_column(style="bold cyan", no_wrap=True)
        keyboard.add_column(style="default")
        keyboard.add_row("Ctrl-J / Alt-Enter", "Insert a newline")
        keyboard.add_row("Ctrl-C", "Clear the current input")
        keyboard.add_row("Ctrl-D", "Exit the chat session")

        blocks.extend(
            [
                Text("Keyboard", style="bold"),
                keyboard,
                Text("Type a request, / for commands, or ? for shortcuts", style="dim"),
                Text("Docs: https://docs.kagan.sh/", style="dim"),
            ]
        )

        _console.print(
            Panel(
                Group(*blocks),
                title="Help Guide",
                border_style="green",
                padding=(1, 2),
                expand=False,
            )
        )

    def _print_status_panel(self) -> None:
        session_label = self._session_title or self._chat_session_id or "none"
        session_id_short = (self._chat_session_id or "?")[:8]
        parts = [
            f"project: {self._project_name or 'none'}",
            f"session: {session_label} ({session_id_short})",
            f"agent: {self.agent_backend}",
            f"turns: {self._turn_count}",
        ]
        line = " · ".join(parts)
        cols = shutil.get_terminal_size().columns
        if len(line) <= cols:
            _console.print(f"[dim]{line}[/dim]")
        else:
            for part in parts:
                _console.print(f"  [dim]{part}[/dim]")

    def _print_project_info(self) -> None:
        if self._project_name:
            _console.print(f"[bold]Project:[/bold] {self._project_name}")
            _console.print(f"[dim]ID:[/dim] {self.client.active_project_id or 'unknown'}")
        else:
            _console.print("[dim]No active project.[/dim]")

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

    def _show_tool_report(self, query: str | None) -> None:
        if self._acp_client is None:
            _console.print("[dim]No active agent connection.[/dim]")
            return

        report, pager_mode = self._acp_client.tool_report(query)
        if pager_mode:
            with _console.pager(styles=False):
                _console.print(report, highlight=False)
            return

        _console.print(report, highlight=False)

    async def _switch_agent(self, new_backend: str) -> bool:
        if new_backend == self.agent_backend:
            _console.print(f"[dim]Already using {new_backend}.[/dim]")
            return False

        _console.print(f"[bold]Switching to {new_backend}...[/bold]")
        self.agent_backend = new_backend
        _TOOLBAR_STATE.agent_backend = new_backend
        self._restart_requested = True
        await self.client.settings.set({"default_agent_backend": new_backend})
        await self._persist_session()
        return True  # break REPL loop → run() will restart with new backend
