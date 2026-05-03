"""ACP client for orchestrator mode — streaming output, tool tracking, animation.

Phase 5b refactor: rendering state (``StreamingMarkdownRegion``,
``_GroupedToolDisplay``, ``ToolRunTracker``, the usage snapshot, terminal
printing) lives in ``cli/chat/_renderer.py`` as ``CLIRenderer``. The permission
flow lives in ``cli/chat/_permission_ui.py`` as ``PermissionUI``.

This module retains:
- The module-level helper functions (``_run_interactive_modal``,
  ``_run_legacy_input``, ``_run_approval_panel_async``, ``_map_approval_result``,
  ``_session_approvals``, the ``_*_permission_response`` constructors,
  ``_format_permission_tool``, ``_tool_action_key``, ``_stdio_is_interactive``,
  ``_render_panel_ansi``, ``_show_panel_in_pager``, ``_modal_active``,
  ``_MODAL_DEPTH``). Existing tests reach into these via monkeypatch and
  ``_BatchApprovalQueue`` imports them as plain symbols, so they stay
  defined in this module rather than being moved to ``_permission_ui``.
- ``_OrchestratorACPClient`` itself, now a thin wrapper that constructs
  ``CLIRenderer`` + ``PermissionUI`` and dispatches ``session_update`` /
  ``request_permission`` calls through them. Phase 5c will delete this class
  entirely and have the controller drive the engine + helpers directly.
"""

from __future__ import annotations

import io
import shutil
import sys
import time
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

from kagan.cli.chat._approval_panel import build_approval_panel, get_rich_spinner_name, no_color

# Re-export the modal-depth helpers so external imports keep working. The
# canonical implementation now lives in ``_renderer`` so the renderer and
# the permission flow share a single counter.
from kagan.cli.chat._renderer import (
    CLIRenderer,
    _GroupedToolDisplay,
    _modal_active,
    _modal_depth,
    print_via_terminal,
)
from kagan.cli.chat.repl import WAVE_FRAMES, _console, _env_flag_enabled
from kagan.core import ACPClientBase

if TYPE_CHECKING:
    from collections.abc import Callable


# Backward-compatible alias for the module-level modal-depth integer.
# Tests and ``_approval_batch`` import ``_modal_active`` from here; keep
# ``_MODAL_DEPTH`` resolvable as a module attribute for any callers that
# inspect it directly.
def _get_modal_depth() -> int:  # pragma: no cover — diagnostic helper
    return _modal_depth()


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
# Single-approval panel rendering + key handling
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
    tmp = Console(file=buf, highlight=False, width=cols, force_terminal=True, no_color=no_color())
    tmp.print(
        build_approval_panel(
            tool_call,
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
    selected_index: int,
) -> None:
    """Show a full pager with the approval panel content (Ctrl-E handler)."""
    from rich.console import Console

    cols = shutil.get_terminal_size((80, 24)).columns
    buf = io.StringIO()
    tmp = Console(file=buf, highlight=False, width=cols, force_terminal=True, no_color=no_color())
    tmp.print(
        build_approval_panel(
            tool_call,
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
        logger.warning(
            "Arrow-key approval modal failed; falling back to legacy input loop",
            exc_info=True,
        )
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

    state: dict[str, Any] = {
        "selected": 0,
        "feedback": "",
        "feedback_mode": False,
    }

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
            await run_in_terminal(
                lambda: _show_panel_in_pager(
                    tool_call,
                    selected_index=state["selected"],
                )
            )

        event.app.create_background_task(_pager())

    def _make_num_handler(num: int) -> None:
        @kb.add(str(num), eager=True)
        def _num(event) -> None:
            idx = num - 1
            state["selected"] = idx
            if idx == 3:
                state["feedback_mode"] = True
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

    with _modal_active():
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


# ---------------------------------------------------------------------------
# Session-allow cache (module-level singleton — owned conceptually by
# ``PermissionUI`` but kept addressable here for cross-module imports and
# existing tests).
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# _OrchestratorACPClient — thin shell over CLIRenderer + PermissionUI
# ---------------------------------------------------------------------------


class _OrchestratorACPClient(ACPClientBase):
    def __init__(self, *, yolo: bool = False) -> None:
        from kagan.cli.chat._permission_ui import PermissionUI

        self._conn: Any = None
        self._streaming = False
        show_thoughts = _env_flag_enabled("KAGAN_CHAT_SHOW_THOUGHTS", default=False)
        self._renderer = CLIRenderer(_console, show_thoughts=show_thoughts)
        self._permission_ui = PermissionUI(yolo=yolo, renderer=self._renderer)
        self._spinner_name = get_rich_spinner_name()

    # ------------------------------------------------------------------
    # Backward-compatible attribute surface — the controller and a handful
    # of other call sites still poke at these directly. Phase 5c will
    # replace these with explicit accessor calls on the renderer.
    # ------------------------------------------------------------------

    @property
    def last_usage(self) -> Any:
        return self._renderer.last_usage

    @last_usage.setter
    def last_usage(self, value: Any) -> None:
        self._renderer.last_usage = value

    @property
    def _md_region(self) -> Any:
        return self._renderer._md_region

    @property
    def _tool_runs(self) -> Any:
        return self._renderer._tool_runs

    @property
    def _grouped_tools(self) -> Any:
        return self._renderer._grouped_tools

    @property
    def _response_chunks(self) -> Any:
        return self._renderer._response_chunks

    @property
    def _yolo(self) -> bool:
        return self._permission_ui._yolo

    @property
    def _show_thoughts(self) -> bool:
        return self._renderer._show_thoughts

    @property
    def _batch_queue(self) -> Any:
        return self._permission_ui._batch_queue

    # ------------------------------------------------------------------
    # Turn lifecycle
    # ------------------------------------------------------------------

    def start_turn(self) -> None:
        self._renderer.start_turn()
        self._permission_ui.reset_batch_queue()

    def finish_turn(self) -> str:
        return self._renderer.finish_turn()

    def tool_report(self, query: str | None) -> tuple[str, bool]:
        return self._renderer.tool_report(query)

    def _print_via_terminal(self, fn: Callable[[], None]) -> None:
        print_via_terminal(fn)

    # ------------------------------------------------------------------
    # ACP session_update — thin dispatcher into the renderer
    # ------------------------------------------------------------------

    async def session_update(self, session_id: str, update: Any, **kwargs: Any) -> None:
        del session_id, kwargs
        if isinstance(update, AgentMessageChunk):
            content = getattr(update, "content", None)
            if content and getattr(content, "type", None) == "text":
                text = getattr(content, "text", "") or ""
                if text:
                    self._streaming = True
                    self._renderer.on_assistant_chunk(text)
        elif isinstance(update, AgentThoughtChunk):
            content = getattr(update, "content", None)
            if content and getattr(content, "type", None) == "text":
                text = getattr(content, "text", "") or ""
                if text:
                    self._renderer.on_assistant_chunk(text, thought=True)
        elif isinstance(update, ToolCallStart):
            self._renderer.on_tool_call_start(update)
        elif isinstance(update, ToolCallProgress):
            self._renderer.on_tool_call_progress(update)
        elif isinstance(update, UsageUpdate):
            self._renderer.on_usage_update(update)

    async def request_permission(self, options: Any, session_id: str, tool_call: Any, **_kw: Any):
        return await self._permission_ui.handle_request(options, session_id, tool_call)

    def cancel_batch_queue(self) -> None:
        """Cancel all pending batch approval futures (called from SIGINT handler)."""
        self._permission_ui.cancel_batch_queue()


__all__ = [
    "CLIRenderer",
    "_GroupedToolDisplay",
    "_OrchestratorACPClient",
    "_SendResult",
    "_SessionApprovals",
    "_WaveIndicator",
    "_cancelled_permission_response",
    "_format_permission_tool",
    "_get_modal_depth",
    "_map_approval_result",
    "_modal_active",
    "_permission_choice_matches",
    "_prompt_for_permission_option_async",
    "_rejected_permission_response",
    "_render_panel_ansi",
    "_run_approval_panel_async",
    "_run_interactive_modal",
    "_run_legacy_input",
    "_selected_permission_response",
    "_session_approvals",
    "_show_panel_in_pager",
    "_stdio_is_interactive",
    "_tool_action_key",
    "get_session_approvals",
    "print_via_terminal",
]
