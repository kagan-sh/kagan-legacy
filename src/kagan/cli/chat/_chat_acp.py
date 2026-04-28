"""ACP client for orchestrator mode — streaming output, tool tracking, animation."""

import asyncio
import contextlib
import sys
import time
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from typing import Any

from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ToolCallProgress,
    ToolCallStart,
    UsageUpdate,
)
from rich.markup import escape as _rich_escape
from rich.measure import Measurement
from rich.text import Text

from kagan.cli.chat._streaming import OutputFlushManager, ResponseChunkBuffer
from kagan.cli.chat.repl import WAVE_FRAMES, _console, _env_flag_enabled
from kagan.cli.chat.tool_runs import ToolRunTracker
from kagan.core import ACPClientBase


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


@dataclass(frozen=True, slots=True)
class _SendResult:
    was_cancelled: bool = False


_PERMISSION_KIND_LABELS = {
    "allow_once": "allow once",
    "allow_always": "allow always",
    "reject_once": "deny",
    "reject_always": "deny always",
}
_PERMISSION_KIND_ALIASES = {
    "allow_once": {"allow once", "once", "allow_once"},
    "allow_always": {"allow always", "always", "allow_always"},
    "reject_once": {"deny", "reject", "no", "reject once", "reject_once"},
    "reject_always": {"deny always", "reject always", "reject_always"},
}


def _stdio_is_interactive() -> bool:
    return sys.stdin.isatty() and sys.stdout.isatty()


def _cancelled_permission_response() -> Any:
    from acp.schema import DeniedOutcome, RequestPermissionResponse

    return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))


def _selected_permission_response(option: Any) -> Any:
    from acp.schema import AllowedOutcome, RequestPermissionResponse

    return RequestPermissionResponse(
        outcome=AllowedOutcome(outcome="selected", option_id=option.option_id)
    )


def _permission_choice_matches(value: str, option: Any, index: int) -> bool:
    normalized = value.casefold().strip()
    kind = str(getattr(option, "kind", "")).casefold()
    aliases = {
        str(index),
        kind,
        str(getattr(option, "name", "")).casefold(),
        str(getattr(option, "option_id", "")).casefold(),
        *_PERMISSION_KIND_ALIASES.get(kind, set()),
    }
    return normalized in {alias for alias in aliases if alias}


def _format_permission_tool(tool_call: Any) -> str:
    title = getattr(tool_call, "title", None) or getattr(tool_call, "name", None)
    kind = getattr(tool_call, "kind", None)
    if title and kind:
        return f"{title} ({kind})"
    if title:
        return str(title)
    return "tool call"


def _prompt_for_permission_option(options: list[Any], tool_call: Any) -> Any | None:
    _console.print()
    _console.print("[bold yellow]Permission requested[/bold yellow]")
    _console.print(f"[dim]{_rich_escape(_format_permission_tool(tool_call))}[/dim]")
    for index, option in enumerate(options, start=1):
        kind = str(getattr(option, "kind", ""))
        label = _PERMISSION_KIND_LABELS.get(kind, kind.replace("_", " "))
        name = str(getattr(option, "name", "") or label)
        _console.print(f"  {index}. {name} [dim]({label})[/dim]")

    try:
        value = input("Select permission option [deny]: ").strip()
    except (EOFError, KeyboardInterrupt):
        _console.print("[yellow]Permission denied.[/yellow]")
        return None

    if not value:
        return None
    for index, option in enumerate(options, start=1):
        if _permission_choice_matches(value, option, index):
            return option
    _console.print("[yellow]Unrecognized permission choice; denying.[/yellow]")
    return None


class _OrchestratorACPClient(ACPClientBase):
    def __init__(self) -> None:
        self._conn: Any = None
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
        del session_id
        permission_options = [
            option
            for option in list(options or ())
            if getattr(option, "kind", None)
            in {"allow_once", "allow_always", "reject_once", "reject_always"}
        ]
        if not permission_options:
            return _cancelled_permission_response()

        self._output_flusher.flush(force=True)
        if not _stdio_is_interactive():
            _console.print("[yellow]Permission request denied in non-interactive mode.[/yellow]")
            return _cancelled_permission_response()

        selected = _prompt_for_permission_option(permission_options, tool_call)
        if selected is None:
            return _cancelled_permission_response()
        return _selected_permission_response(selected)
