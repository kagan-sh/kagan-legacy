"""ACP client for orchestrator mode — streaming output, tool tracking, animation."""

from __future__ import annotations

import asyncio
import contextlib
import io
import shutil
import sys
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from acp.schema import (
    AgentMessageChunk,
    AgentThoughtChunk,
    ToolCallProgress,
    ToolCallStart,
    UsageUpdate,
)
from loguru import logger
from prompt_toolkit.application.run_in_terminal import run_in_terminal
from rich.markup import escape as _rich_escape
from rich.measure import Measurement
from rich.text import Text

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable

from kagan.cli.chat._approval_panel import build_approval_panel, get_rich_spinner_name
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


def _rejected_permission_response() -> Any:
    from acp.schema import DeniedOutcome, RequestPermissionResponse

    return RequestPermissionResponse(outcome=DeniedOutcome(outcome="cancelled"))


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


def _tool_action_key(tool_call: Any) -> str:
    """Return a stable string that identifies the tool action for session-allow tracking."""
    title = getattr(tool_call, "title", None) or getattr(tool_call, "name", None) or "tool"
    return str(title).strip().casefold()


# ---------------------------------------------------------------------------
# Grouped tool-call display
# ---------------------------------------------------------------------------


class _GroupedToolDisplay:
    """Accumulate parallel tool calls and render them as grouped status lines.

    Groups calls by tool name.  Shows: ``tool_name x N -- done D/N . Xs``.
    """

    def __init__(self) -> None:
        # tool_name -> list of (status, started_at, ended_at)
        self._calls: dict[str, list[dict[str, Any]]] = defaultdict(list)
        self._key_to_name: dict[str, str] = {}

    def start(self, tool_key: str, tool_name: str, started_at: float) -> None:
        self._key_to_name[tool_key] = tool_name
        self._calls[tool_name].append(
            {"key": tool_key, "status": "running", "started": started_at, "ended": None}
        )

    def complete(self, tool_key: str, status: str, ended_at: float) -> None:
        name = self._key_to_name.get(tool_key)
        if name is None:
            return
        for entry in self._calls.get(name, []):
            if entry["key"] == tool_key and entry["status"] == "running":
                entry["status"] = status
                entry["ended"] = ended_at
                break

    def render_lines(self) -> list[str]:
        """Return one display line per tool name."""
        lines = []
        now = time.monotonic()
        for name, entries in self._calls.items():
            total = len(entries)
            done = sum(1 for e in entries if e["status"] in ("completed", "failed"))
            error = sum(1 for e in entries if e["status"] == "failed")
            elapsed = max(
                (now - e["started"]) for e in entries if e["started"] is not None
            )
            elapsed_text = f"{elapsed:.1f}s"

            if total == 1:
                entry = entries[0]
                if entry["status"] == "running":
                    icon = "●"
                    style = "dim"
                elif entry["status"] == "completed":
                    icon = "✓"
                    style = "green"
                else:
                    icon = "✗"
                    style = "red"
                line = f"  [{style}]{icon} {_rich_escape(name)} · {elapsed_text}[/{style}]"
            else:
                if error > 0:
                    status_text = f"done {done}/{total} · {error} err · {elapsed_text}"
                    style = "red"
                elif done == total:
                    status_text = f"done {total}/{total} · {elapsed_text}"
                    style = "green"
                else:
                    status_text = f"done {done}/{total} · {elapsed_text}"
                    style = "dim"
                icon = "✓" if done == total and error == 0 else "●"
                line = (
                    f"  [{style}]{icon} {_rich_escape(name)} x{total}"
                    f" -- {status_text}[/{style}]"
                )
            lines.append(line)
        return lines

    def clear(self) -> None:
        self._calls.clear()
        self._key_to_name.clear()


# ---------------------------------------------------------------------------
# Arrow-key approval panel — prompt_toolkit Application
# ---------------------------------------------------------------------------


def _render_panel_ansi(
    tool_call: Any,
    *,
    permission_options: list[Any],
    selected_index: int,
    feedback_draft: str,
    queue_position: int,
    queue_depth: int,
) -> str:
    """Render the Rich approval panel to an ANSI escape-code string."""
    from rich.console import Console

    buf = io.StringIO()
    cols = shutil.get_terminal_size((80, 24)).columns
    tmp = Console(file=buf, highlight=False, width=cols, force_terminal=True)
    tmp.print(
        build_approval_panel(
            tool_call,
            options=permission_options,
            selected_index=selected_index,
            feedback_draft=feedback_draft,
            queue_depth=queue_depth,
            queue_position=queue_position,
        )
    )
    return buf.getvalue()


def _show_panel_in_pager(
    tool_call: Any,
    *,
    permission_options: list[Any],
    selected_index: int,
) -> None:
    """Show a full pager with the approval panel content (Ctrl-E handler)."""
    from rich.console import Console

    cols = shutil.get_terminal_size((80, 24)).columns
    buf = io.StringIO()
    tmp = Console(file=buf, highlight=False, width=cols, force_terminal=True)
    tmp.print(
        build_approval_panel(
            tool_call,
            options=permission_options,
            selected_index=selected_index,
            feedback_draft="",
            queue_depth=1,
            queue_position=1,
        )
    )
    with _console.pager(styles=True):
        _console.print(buf.getvalue(), end="")


async def _run_approval_panel_async(
    tool_call: Any,
    *,
    permission_options: list[Any],
    queue_position: int = 1,
    queue_depth: int = 1,
) -> tuple[int, str]:
    """Show an interactive arrow-key approval panel.

    Returns (selected_index, feedback_draft).
    Falls back to the legacy input() loop on any failure (e.g. dumb TTY).
    """
    try:
        return await _run_interactive_modal(
            tool_call,
            permission_options=permission_options,
            queue_position=queue_position,
            queue_depth=queue_depth,
        )
    except Exception:
        logger.debug("Arrow-key approval modal failed; falling back to legacy input loop")
        return _run_legacy_input(
            tool_call,
            permission_options=permission_options,
            queue_position=queue_position,
            queue_depth=queue_depth,
        )


async def _run_interactive_modal(
    tool_call: Any,
    *,
    permission_options: list[Any],
    queue_position: int,
    queue_depth: int,
) -> tuple[int, str]:
    """Build and run a transient prompt_toolkit Application for the approval panel.

    The Application renders the Rich panel as ANSI text and handles key events.
    It does not interfere with the outer PromptSession — it runs as a separate
    event-loop Application that the outer session is not aware of.
    """
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl

    # Mutable state captured by the closures below.
    state: dict[str, Any] = {
        "selected": 0,
        "feedback": "",
        "feedback_mode": False,
    }

    # Buffer for option-4 inline feedback text.
    feedback_buffer = Buffer(name="approval_feedback", multiline=False)

    def _panel_text() -> ANSI:
        draft = feedback_buffer.text if state["feedback_mode"] else state["feedback"]
        ansi = _render_panel_ansi(
            tool_call,
            permission_options=permission_options,
            selected_index=state["selected"],
            feedback_draft=draft,
            queue_position=queue_position,
            queue_depth=queue_depth,
        )
        return ANSI(ansi)

    panel_window = Window(
        content=FormattedTextControl(text=_panel_text),
        dont_extend_height=True,
    )
    # Height-0 Window keeps the feedback buffer alive without taking screen space.
    feedback_window = Window(
        content=BufferControl(buffer=feedback_buffer, focusable=True),
        height=0,
    )

    layout = Layout(HSplit([panel_window, feedback_window]))
    kb = KeyBindings()

    def _exit_with(app: Any, idx: int, fb: str) -> None:
        app.exit(result=(idx, fb))

    def _move(direction: int) -> None:
        if state["feedback_mode"]:
            state["feedback"] = feedback_buffer.text
            feedback_buffer.set_document(Document(), bypass_readonly=True)
        state["selected"] = (state["selected"] + direction) % 4
        state["feedback_mode"] = state["selected"] == 3

    @kb.add("up", eager=True)
    def _up(event) -> None:
        _move(-1)

    @kb.add("down", eager=True)
    def _down(event) -> None:
        _move(1)

    @kb.add("enter", eager=True)
    def _enter(event) -> None:
        if state["feedback_mode"] and not feedback_buffer.text.strip():
            return  # keep editing — empty Enter in feedback mode is a no-op
        fb = feedback_buffer.text.strip() if state["feedback_mode"] else state["feedback"]
        _exit_with(event.app, state["selected"], fb)

    @kb.add("escape", eager=True)
    @kb.add("c-c", eager=True)
    @kb.add("c-d", eager=True)
    def _cancel(event) -> None:
        _exit_with(event.app, 2, "")  # slot 2 = reject_once

    @kb.add("c-e", eager=True)
    def _expand(event) -> None:
        async def _pager() -> None:
            await asyncio.to_thread(
                _show_panel_in_pager,
                tool_call,
                permission_options=permission_options,
                selected_index=state["selected"],
            )

        event.app.create_background_task(_pager())

    def _make_num_handler(num: int) -> None:
        @kb.add(str(num), eager=True)
        def _num(event) -> None:
            idx = num - 1
            state["selected"] = idx
            if idx == 3:
                state["feedback_mode"] = True
                # option 4 selected — stay open for feedback input
            else:
                state["feedback_mode"] = False
                _exit_with(event.app, idx, "")

    for n in range(1, 5):
        _make_num_handler(n)

    app: Application[tuple[int, str]] = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )

    result = await app.run_async()
    if result is None:
        return 2, ""
    return result


def _run_legacy_input(
    tool_call: Any,
    *,
    permission_options: list[Any],
    queue_position: int,
    queue_depth: int,
) -> tuple[int, str]:
    """Sync fallback: render panel then read choice via input()."""
    selected_index = 0
    feedback_draft = ""

    _console.print(
        build_approval_panel(
            tool_call,
            options=permission_options,
            selected_index=selected_index,
            feedback_draft=feedback_draft,
            queue_depth=queue_depth,
            queue_position=queue_position,
        )
    )

    try:
        while True:
            raw = input().strip()
            if not raw:
                break
            if raw in {"1", "2", "3", "4"}:
                selected_index = int(raw) - 1
                if selected_index == 3:
                    _console.print(
                        "[dim]Type rejection reason (Enter confirm, empty cancel):[/dim]"
                    )
                    try:
                        feedback_draft = input().strip()
                    except (EOFError, KeyboardInterrupt):
                        feedback_draft = ""
                break
            if raw in {"q", "n", "reject", "deny"}:
                selected_index = 2
                break
            if raw in {"y", "a", "approve"}:
                selected_index = 0
                break
    except (EOFError, KeyboardInterrupt):
        selected_index = 2

    return selected_index, feedback_draft


class _SessionApprovals:
    """Track tool actions approved for the lifetime of this REPL session."""

    def __init__(self) -> None:
        self._allowed: set[str] = set()

    def is_allowed(self, action_key: str) -> bool:
        return action_key in self._allowed

    def grant(self, action_key: str) -> None:
        self._allowed.add(action_key)

    def revoke(self, action_key: str) -> None:
        self._allowed.discard(action_key)

    def list_granted(self) -> list[str]:
        return sorted(self._allowed)


_session_approvals = _SessionApprovals()


def get_session_approvals() -> _SessionApprovals:
    """Return the module-level session approval tracker."""
    return _session_approvals


async def _prompt_for_permission_option_async(
    options: list[Any],
    tool_call: Any,
    *,
    queue_position: int = 1,
    queue_depth: int = 1,
) -> Any | None:
    """Show Rich panel approval prompt with arrow-key navigation.

    Returns selected ACP option or None (reject / cancel).
    """
    _allowed_kinds = {"allow_once", "allow_always", "reject_once", "reject_always"}
    permission_options = [o for o in options if getattr(o, "kind", None) in _allowed_kinds]
    if not permission_options:
        return None

    action_key = _tool_action_key(tool_call)
    if _session_approvals.is_allowed(action_key):
        for o in permission_options:
            if getattr(o, "kind", None) == "allow_once":
                return o
        return permission_options[0]

    selected_index, feedback = await _run_approval_panel_async(
        tool_call,
        permission_options=permission_options,
        queue_position=queue_position,
        queue_depth=queue_depth,
    )

    return _map_approval_result(
        selected_index,
        feedback,
        action_key=action_key,
        permission_options=permission_options,
    )


def _map_approval_result(
    selected_index: int,
    feedback: str,
    *,
    action_key: str,
    permission_options: list[Any],
) -> Any | None:
    """Convert (selected_index, feedback) into an ACP option or None (reject)."""
    _SLOT_KINDS = ["allow_once", "allow_always", "reject_once", "reject_feedback"]
    slot_kind = _SLOT_KINDS[min(selected_index, 3)]

    if slot_kind == "allow_always":
        _session_approvals.grant(action_key)
        msg = (
            f"[dim green]✓ approved · will not ask again for"
            f" [bold]{_rich_escape(action_key)}[/bold] this session[/dim green]"
        )
        _console.print(msg)
        for o in permission_options:
            if getattr(o, "kind", None) == "allow_always":
                return o
        for o in permission_options:
            if getattr(o, "kind", None) == "allow_once":
                return o
        return permission_options[0]

    if slot_kind == "allow_once":
        for o in permission_options:
            if getattr(o, "kind", None) == "allow_once":
                return o
        return permission_options[0]

    if slot_kind == "reject_feedback" and feedback:
        logger.info("Rejection feedback from user: {}", feedback)

    return None


class _OrchestratorACPClient(ACPClientBase):
    def __init__(self, *, yolo: bool = False) -> None:
        self._conn: Any = None
        self._streaming = False
        self._yolo = yolo
        self._show_thoughts = _env_flag_enabled("KAGAN_CHAT_SHOW_THOUGHTS", default=False)
        self._tool_runs = ToolRunTracker()
        self._grouped_tools = _GroupedToolDisplay()
        self._response_chunks = ResponseChunkBuffer()
        self._output_flusher = OutputFlushManager(_console)
        self._first_update_notified = False
        self._on_first_update: Callable[[], None] | None = None
        self.last_usage: Any = None
        self._spinner_name = get_rich_spinner_name()

    def start_turn(self, *, on_first_update: Callable[[], None] | None = None) -> None:
        self._output_flusher.shutdown()
        self._response_chunks.clear()
        self._output_flusher.clear()
        self._tool_runs.start_turn()
        self._grouped_tools.clear()
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

    def _print_via_terminal(self, fn: Callable[[], None]) -> None:
        """Print safely, using run_in_terminal when a real prompt_toolkit app is active."""
        try:
            from prompt_toolkit.application.current import get_app
            from prompt_toolkit.application.dummy import DummyApplication

            app = get_app()
            if app is not None and not isinstance(app, DummyApplication):
                run_in_terminal(fn)
                return
        except Exception:
            pass
        fn()

    def _handle_tool_progress(self, update: ToolCallProgress) -> None:
        """Handle ToolCallProgress events: update run record and print status."""
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
        if status not in ("completed", "failed"):
            return
        self._tool_runs.set_status(tool_key, status)
        run.ended_at = run.ended_at or time.monotonic()
        self._grouped_tools.complete(tool_key, status, run.ended_at)
        self._print_via_terminal(
            self._make_done_printer(title, key_arg, status, run.started_at, run.ended_at)
        )

    @staticmethod
    def _make_done_printer(
        title: str,
        key_arg: str | None,
        status: str,
        started_at: float,
        ended_at: float,
    ) -> Callable[[], None]:
        def _print() -> None:
            arg_suffix = f"({key_arg})" if key_arg else ""
            elapsed = max(0.0, ended_at - started_at)
            duration = f" [dim]{elapsed:.1f}s[/dim]" if elapsed >= 0.1 else ""
            if status == "completed":
                _console.print(
                    f"  [green]● {title}{arg_suffix}[/green]{duration}",
                    highlight=False,
                )
            else:
                _console.print(
                    f"  [red]● {title}{arg_suffix} failed[/red]",
                    highlight=False,
                )

        return _print

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

                        def _print_thought() -> None:
                            _console.print(
                                f"[dim]{_rich_escape(text)}[/dim]", end="", highlight=False
                            )
                            _console.file.flush()

                        self._print_via_terminal(_print_thought)
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
                self._grouped_tools.start(tool_key, title, run.started_at)

                def _print_start() -> None:
                    arg_suffix = f"({key_arg})" if key_arg else ""
                    _console.print(f"\n  [dim]● {title}{arg_suffix}[/dim]", highlight=False)

                self._print_via_terminal(_print_start)
        elif isinstance(update, ToolCallProgress):
            self._notify_first_update()
            self._output_flusher.flush(force=True)
            self._handle_tool_progress(update)
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

        if self._yolo:
            for option in permission_options:
                if getattr(option, "kind", None) == "allow_once":
                    _yolo_title = _format_permission_tool(tool_call)

                    def _print_yolo(_t: str = _yolo_title) -> None:
                        _console.print(
                            f"  [red]● yolo auto-approve:[/red]"
                            f" [dim]{_rich_escape(_t)}[/dim]",
                            highlight=False,
                        )

                    self._print_via_terminal(_print_yolo)
                    return _selected_permission_response(option)

        if not _stdio_is_interactive():

            def _print_denied() -> None:
                _console.print(
                    "[yellow]Permission request denied in non-interactive mode.[/yellow]"
                )

            self._print_via_terminal(_print_denied)
            return _cancelled_permission_response()

        selected = await _prompt_for_permission_option_async(permission_options, tool_call)
        if selected is None:
            return _rejected_permission_response()
        return _selected_permission_response(selected)
