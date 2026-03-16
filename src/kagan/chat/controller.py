"""ChatController — orchestrator agent lifecycle and _OrchestratorACPClient."""

import asyncio
import contextlib
import os
import shutil
import signal
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
    ClientCapabilities,
    Implementation,
    McpServerStdio,
    ToolCallProgress,
    ToolCallStart,
)
from loguru import logger
from rich.live import Live
from rich.markup import escape as _rich_escape
from rich.measure import Measurement
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from kagan.chat._title import generate_session_title
from kagan.chat.acp import (
    _ACP_CLIENT_NAME,
    _ACP_CLIENT_TITLE,
    _ACP_CLIENT_VERSION,
    _acp_handshake_timeout_seconds,
)
from kagan.chat.agents import format_agent_backend_list, list_registered_agent_backends
from kagan.chat.commands import (
    SLASH_COMMAND_REGISTRY,
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
    _build_prompt_message,
    _console,
    _env_flag_enabled,
    _find_git_root,
    _get_prompt_session,
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
    DBWatcher,
    build_agent_environment,
    build_mcp_manifest,
    default_db_path,
    get_backend,
    get_system_git_identity,
    resolve_orchestrator_prompt,
)
from kagan.core.errors import AgentError, KaganError

_ACP_STDIO_BUFFER_LIMIT_BYTES = 50 * 1024 * 1024
_ACP_STDIO_BUFFER_LIMIT_BYTES = 50 * 1024 * 1024
_STREAM_FLUSH_INTERVAL_SECONDS = 1 / 30


@dataclass(frozen=True, slots=True)
class _WaveIndicator:
    """Animated wave indicator for Rich.Live during ACP handshake."""

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
        """Stop the animation."""
        if self._active:
            self._stop_event.set()

    async def _animate(self) -> None:
        """Animation loop."""
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
        """Start the animation."""
        self._task = asyncio.create_task(self._animate(), name="chat-turn-wave")

    async def shutdown(self) -> None:
        """Shutdown the animation and cleanup."""
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
    """Context manager for turn wave animation. Yields callback to stop animation."""
    animator = _TurnWaveAnimation(_console, frames)
    await animator.start()
    try:
        yield animator.stop
    finally:
        await animator.shutdown()


class _OrchestratorACPClient(ACPClientBase):
    """ACP client that streams agent output to the Rich console."""

    def __init__(self) -> None:
        self._conn: acp.Agent | None = None
        self._streaming = False
        self._show_thoughts = _env_flag_enabled("KAGAN_CHAT_SHOW_THOUGHTS", default=False)
        self._tool_runs = ToolRunTracker()
        self._response_chunks: list[str] = []
        self._pending_output_chunks: list[str] = []
        self._last_output_flush = float("-inf")
        self._flush_handle: asyncio.TimerHandle | None = None
        self._first_update_notified = False
        self._on_first_update: Callable[[], None] | None = None

    def start_turn(self, *, on_first_update: Callable[[], None] | None = None) -> None:
        self._cancel_flush_timer()
        self._response_chunks = []
        self._pending_output_chunks = []
        self._last_output_flush = float("-inf")
        self._tool_runs.start_turn()
        self._first_update_notified = False
        self._on_first_update = on_first_update

    def _flush_pending_output(self, *, force: bool = False) -> None:
        self._cancel_flush_timer()
        if not self._pending_output_chunks:
            return
        now = time.monotonic()
        if not force and now - self._last_output_flush < _STREAM_FLUSH_INTERVAL_SECONDS:
            remaining = _STREAM_FLUSH_INTERVAL_SECONDS - (now - self._last_output_flush)
            try:
                loop = asyncio.get_running_loop()
                self._flush_handle = loop.call_later(remaining, self._do_deferred_flush)
            except RuntimeError:
                pass  # No event loop — will flush on next call or finish_turn
            return
        merged = "".join(self._pending_output_chunks)
        self._pending_output_chunks = []
        _console.print(merged, end="", highlight=False, markup=False)
        _console.file.flush()
        self._last_output_flush = now

    def _cancel_flush_timer(self) -> None:
        if self._flush_handle is not None:
            self._flush_handle.cancel()
            self._flush_handle = None

    def _do_deferred_flush(self) -> None:
        """Callback invoked by the event-loop timer to flush buffered output."""
        self._flush_handle = None
        self._flush_pending_output(force=True)

    def _notify_first_update(self) -> None:
        if self._first_update_notified:
            return
        self._first_update_notified = True
        if self._on_first_update is None:
            return
        self._on_first_update()

    def finish_turn(self) -> str:
        self._flush_pending_output(force=True)
        response = "".join(self._response_chunks).strip()
        self._response_chunks = []
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
                    self._pending_output_chunks.append(text)
                    self._flush_pending_output()
        elif isinstance(update, AgentThoughtChunk):
            if self._show_thoughts:
                content = getattr(update, "content", None)
                if content and getattr(content, "type", None) == "text":
                    text = getattr(content, "text", "") or ""
                    if text:
                        self._notify_first_update()
                        self._flush_pending_output(force=True)
                        _console.print(f"[dim]{_rich_escape(text)}[/dim]", end="", highlight=False)
                        _console.file.flush()
        elif isinstance(update, ToolCallStart):
            self._notify_first_update()
            self._flush_pending_output(force=True)
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
                label = (
                    f"▶ {run.display_id} {title} ({key_arg})"
                    if key_arg
                    else f"▶ {run.display_id} {title}"
                )
                _console.print(f"\n[dim cyan]{label}[/dim cyan]", highlight=False)
        elif isinstance(update, ToolCallProgress):
            self._notify_first_update()
            self._flush_pending_output(force=True)
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
            if status == "completed":
                self._tool_runs.set_status(tool_key, status)
                run.ended_at = run.ended_at or time.monotonic()
                label = (
                    f"  ✓ {run.display_id} {title} ({key_arg})"
                    if key_arg
                    else f"  ✓ {run.display_id} {title}"
                )
                _console.print(f"[dim green]{label}[/dim green]", highlight=False)
            elif status == "failed":
                self._tool_runs.set_status(tool_key, status)
                run.ended_at = run.ended_at or time.monotonic()
                _console.print(f"[dim red]  ✗ {run.display_id} {title}[/dim red]", highlight=False)

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
    """Manages the orchestrator agent lifecycle.

    Spawns a claude-code ACP agent with admin MCP access in CWD.
    User messages are forwarded to the agent; responses stream back.
    """

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
        # DB-change context injection
        self._watcher = DBWatcher(client)

    async def hydrate_persistent_session(self, *, explicit_session_id: str | None = None) -> None:
        selected = await self._resolve_initial_session(explicit_session_id)
        if selected is None:
            selected = await create_chat_session(
                self.client,
                source="repl",
                label="REPL session",
                agent_backend=self.agent_backend,
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
        """Record a user/assistant exchange in conversation history."""
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
        """Generate a human-readable session title from the first exchange."""
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
        sessions = await list_chat_sessions(self.client, source="repl")
        if query is not None and query.lower() == "new":
            created = await create_chat_session(
                self.client,
                source="repl",
                label="REPL session",
                agent_backend=self.agent_backend,
            )
            return await self._attach_session(created, switching=True)
        if not sessions:
            _console.print("[dim]No persisted sessions yet. Use /sessions new.[/dim]")
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
            _console.print("Sessions:")
            for item in items:
                current = " [bold cyan]● current[/bold cyan]" if item.is_current else ""
                backend = f" [dim]{item.agent_backend}[/dim]" if item.agent_backend else ""
                time_str = f"  [dim]{item.updated_relative}[/dim]" if item.updated_relative else ""
                _console.print(f"  {item.index:>2}  {item.label}{backend}{current}{time_str}")
            _console.print()
            _console.print(
                "[dim]/sessions <number|id>[/dim] attach  "
                "[dim]/sessions new[/dim] create  "
                "[dim]/sessions delete <number|id>[/dim] remove"
            )
            return False

        should_restart = await self._attach_session(selected, switching=True)
        _console.print(f"[green]Attached session:[/green] {selected_id or selected.get('id')}")
        if not should_restart:
            self._print_restored_messages()
        return should_restart

    async def _create_new_session(self) -> bool:
        """Create a fresh session and attach it. Returns True if agent restart needed."""
        created = await create_chat_session(
            self.client,
            source="repl",
            label="REPL session",
            agent_backend=self.agent_backend,
        )
        should_restart = await self._attach_session(created, switching=True)
        _console.print(f"[green]New session:[/green] {created['id']}")
        return should_restart

    async def _delete_session(self, query: str) -> None:
        """Delete a session by number or ID prefix."""
        sessions = await list_chat_sessions(self.client, source="repl")
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

    # -- project resolution --------------------------------------------------

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
                        return True

        # 3. No match — bootstrap a new project for this CWD.
        return await self._bootstrap_project()

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

        # -- git identity setup (first-time only) ---
        await self._ensure_git_identity()

        return await self._create_project(name, repo_path)

    async def _ensure_git_identity(self) -> None:
        """Prompt for git identity mode if not yet configured."""
        settings = await self.client.settings.get()
        if "git_user_mode" in settings:
            return  # already configured

        if not sys.stdin.isatty():
            # non-interactive — use default
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

    # -- agent lifecycle (spawn_agent_process context manager) ---------------

    def _resolve_acp_command(self) -> tuple[str, list[str]]:
        """Return (executable, args) for the ACP agent process."""
        backend = get_backend(self.agent_backend)
        if not backend.get("supports_acp", True):
            raise AgentError(
                f"Agent backend {self.agent_backend!r} does not support ACP. "
                "Set a different orchestrator agent or use an ACP-capable backend."
            )

        executable = backend.get("executable")
        fallback = [executable] if isinstance(executable, str) and executable else []
        acp_cmd: list[str] = backend.get("acp_command", fallback)
        if not acp_cmd:
            raise AgentError(f"No ACP command configured for backend {self.agent_backend!r}")

        # Verify the executable is available
        exe = acp_cmd[0]
        if shutil.which(exe) is None:
            hint = ""
            if exe == "npx":
                hint = " Install Node.js first: https://nodejs.org/"
            raise AgentError(f"ACP executable {exe!r} not found on PATH.{hint}")

        return acp_cmd[0], acp_cmd[1:]

    async def run(self, *, prompt: str | None = None) -> None:
        """Run the full orchestrator lifecycle, restarting on agent switch."""
        while True:
            self._restart_requested = False
            self._is_primed = False
            await self._run_agent_session(prompt=prompt)
            if not self._restart_requested:
                break
            # On restart, don't re-send the original prompt
            prompt = None
            _console.print()
            _console.print(f"[bold cyan]Switching to {self.agent_backend}...[/bold cyan]")

    async def _run_agent_session(self, *, prompt: str | None = None) -> None:
        """Single agent session lifecycle inside spawn_agent_process context."""
        # Resolve the ACP command
        try:
            exe, exe_args = self._resolve_acp_command()
        except AgentError as exc:
            _console.print(f"[red]{exc}[/red]")
            return

        # Prepare MCP server config
        session_id = self._mcp_session_id or uuid4().hex[:8]
        db_path = str(default_db_path())
        mcp_content = build_mcp_manifest(
            session_id=session_id,
            db_path=db_path,
            access_tier="admin",
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

        # Prepare environment
        backend = get_backend(self.agent_backend)
        env = build_agent_environment(
            session_id=session_id,
            task_id=None,
            backend_env_vars=backend.get("env_vars", {}),
        )

        # Spawn ACP agent process (context manager owns the lifecycle)
        self._acp_client = _OrchestratorACPClient()

        async def _handshake(conn_inner):
            """Run ACP initialize + new_session."""
            timeout_s = _acp_handshake_timeout_seconds(self.agent_backend)
            client_caps = ClientCapabilities(terminal=False)
            await asyncio.wait_for(
                conn_inner.initialize(
                    protocol_version=acp.PROTOCOL_VERSION,
                    client_capabilities=client_caps,
                    client_info=Implementation(
                        name=_ACP_CLIENT_NAME,
                        title=_ACP_CLIENT_TITLE,
                        version=_ACP_CLIENT_VERSION,
                    ),
                ),
                timeout=timeout_s,
            )
            logger.info("ACP initialize completed")
            mcp_server = McpServerStdio(
                name="kagan",
                command="kagan",
                args=[
                    "mcp",
                    "--session-id",
                    session_id,
                    "--db",
                    db_path,
                    "--admin",
                    *(
                        ["--project-id", self.client.active_project_id]
                        if self.client.active_project_id
                        else []
                    ),
                ],
                env=[],
            )
            sess = await asyncio.wait_for(
                conn_inner.new_session(cwd=str(cwd), mcp_servers=[mcp_server]),
                timeout=timeout_s,
            )
            self._acp_session_id = sess.session_id
            logger.info("ACP session created session_id={}", self._acp_session_id)

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

                # Run handshake with live wave animation
                ready_event = asyncio.Event()
                handshake_error: Exception | None = None

                async def _do_handshake():
                    nonlocal handshake_error
                    try:
                        await _handshake(conn)
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

                # Run single-shot or REPL inside the context
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
            # Clean up .mcp.json
            if mcp_path.exists():
                with contextlib.suppress(OSError):
                    mcp_path.unlink()

    async def _send(self, text: str) -> None:
        """Send a user message to the orchestrator agent and stream the response."""
        if self._acp_conn is None or self._acp_session_id is None:
            _console.print("[red]No agent connected. Try restarting.[/red]")
            return

        # Prepend accumulated DB-change context (invisible to user)
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
            original_sigint = signal.getsignal(signal.SIGINT)
            loop = asyncio.get_running_loop()
            try:
                signal.signal(
                    signal.SIGINT,
                    lambda *_: loop.call_soon_threadsafe(prompt_task.cancel),
                )
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
                signal.signal(signal.SIGINT, original_sigint)

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

        # Auto-generate session title after first turn
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
        await self._persist_session()

    async def _repl_loop(self) -> None:
        """Interactive REPL loop — runs inside spawn_agent_process context."""
        _console.print(
            "[dim]Type [bold]/help[/bold] for commands, [bold]/flow[/bold] for guided mode, "
            "[bold]Ctrl-C[/bold] to interrupt, "
            "[bold]Ctrl-D[/bold] to exit.[/dim]\n"
        )
        try:
            while True:
                try:
                    line = await _get_prompt_session().prompt_async(_build_prompt_message())
                except EOFError:
                    break
                except KeyboardInterrupt:
                    continue

                stripped = line.strip()
                if not stripped:
                    continue

                # Slash command dispatch
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
            if not self._restart_requested:
                _console.print("\n[dim]Session ended.[/dim]")

    async def _handle_slash(self, text: str) -> bool:
        """Handle a slash command. Returns True if exit requested."""

        result = resolve_slash_input(
            text,
            session_label="Orchestrator",
            session_key="orchestrator",
            runtime_session_id=self._acp_session_id,
            current_backend=self.agent_backend,
            available_backends=list_registered_agent_backends(),
        )
        if not result.handled:
            return False

        if result.clear_requested:
            click.clear()

        # REPL text fallback for TUI-native actions
        if result.help_overlay_requested:
            self._print_help_documentation()

        if result.agent_picker_requested:
            backends = list_registered_agent_backends()
            for line in format_agent_backend_list(backends, current_backend=self.agent_backend):
                _console.print(line)

        for line in build_slash_presentation_lines(result):
            if line.tone == "error":
                _console.print(f"[red]{line.text}[/red]")
            else:
                _console.print(line.text)
        if result.selected_agent is not None:
            return await self._switch_agent(result.selected_agent)

        if result.sessions_requested:
            return await self._open_sessions(result.sessions_query)

        if result.delete_session_query is not None:
            await self._delete_session(result.delete_session_query)
            return False

        if result.new_session_requested:
            return await self._create_new_session()

        if result.tool_requested:
            self._show_tool_report(result.tool_query)
            return False

        return bool(result.close_requested)

    def _print_help_documentation(self) -> None:
        usage_panel = Panel.fit(
            "[bold]Usage:[/bold] /<command> [args]\n[dim]Kagan chat slash-command reference.[/dim]",
            title="kagan chat",
            border_style="cyan",
            padding=(0, 1),
        )

        command_table = Table(show_header=True, header_style="bold", box=None, pad_edge=False)
        command_table.add_column("Command", style="bold cyan", no_wrap=True)
        command_table.add_column("Description", style="default")
        for spec in SLASH_COMMAND_REGISTRY.specs():
            command_table.add_row(f"/{spec.name}", spec.description)

        commands_panel = Panel(
            command_table,
            title="Commands",
            border_style="green",
            padding=(0, 1),
            expand=False,
        )

        quick_refs = " ".join(f"/{spec.name}" for spec in SLASH_COMMAND_REGISTRY.specs())
        quick_refs_panel = Panel.fit(
            f"[dim]{quick_refs}[/dim]",
            title="Quick refs",
            border_style="magenta",
            padding=(0, 1),
        )

        _console.print(usage_panel)
        _console.print(commands_panel)
        _console.print(quick_refs_panel)
        _console.print("Documentation: https://docs.kagan.sh/")
        _console.print("CLI reference: https://docs.kagan.sh/reference/cli/")

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
        """Request agent switch and persist to settings. Returns True to exit REPL loop."""
        if new_backend == self.agent_backend:
            _console.print(f"[dim]Already using {new_backend}.[/dim]")
            return False

        self.agent_backend = new_backend
        _TOOLBAR_STATE.agent_backend = new_backend
        self._restart_requested = True
        await self.client.settings.set({"default_agent_backend": new_backend})
        await self._persist_session()
        return True  # break REPL loop → run() will restart with new backend
