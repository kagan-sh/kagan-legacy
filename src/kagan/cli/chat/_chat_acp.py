"""CLI chat ACP residue — module-level helpers and singletons.

Phase 5c rewires the controller onto :class:`kagan.core.chat.ChatEngine` +
:class:`kagan.core.chat.LongLivedACPFactory` and deletes
``_OrchestratorACPClient``. The ACP-translation layer (mapping a
``PermissionDecision`` back to an ACP ``RequestPermissionResponse``) now
lives entirely in :class:`kagan.cli.chat.acp._CaptureACPClient`.

What remains here:

* ``_WaveIndicator`` / ``_SendResult`` — small dataclasses still used by the
  controller and shared across modules.
* ``_run_interactive_modal`` / ``_run_legacy_input`` /
  ``_run_approval_panel_async`` — the single-approval modal helpers. Tests
  monkey-patch these via ``chat_acp_module``; the batch queue imports them
  directly.
* ``_session_approvals`` / ``get_session_approvals`` — module-level singleton
  tracking session-granted tool approvals. Same lifetime as the REPL.
* Pure helpers: ``_format_permission_tool``, ``_tool_action_key``,
  ``_stdio_is_interactive``, ``_render_panel_ansi``, ``_show_panel_in_pager``,
  ``_permission_choice_matches``, ``_map_decision_from_approval``,
  ``_modal_active`` (re-exported from ``_renderer``).

The four ``_*_permission_response`` ACP-shape constructors that previously
lived here are gone. Decisions are now :class:`PermissionDecision`-shaped
``(outcome, feedback)`` tuples; ACP translation is the factory's job.
"""

from __future__ import annotations

import io
import shutil
import sys
import time
from dataclasses import dataclass, field
from typing import Any

from loguru import logger
from prompt_toolkit.application.run_in_terminal import run_in_terminal
from rich.markup import escape as _rich_escape
from rich.measure import Measurement
from rich.text import Text

from kagan.cli.chat._approval_panel import build_approval_panel, no_color
from kagan.cli.chat._renderer import (
    CLIRenderer,
    _GroupedToolDisplay,
    _modal_active,
    _modal_depth,
    print_via_terminal,
)
from kagan.cli.chat.repl import WAVE_FRAMES, _console


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
    """Return a stable string that identifies the tool action for session-allow tracking.

    Accepts both ACP tool-call objects (with ``title`` / ``name`` attrs) and
    plain dicts (used by the engine's :class:`PermissionRequest` event).
    """
    if isinstance(tool_call, dict):
        title = tool_call.get("title") or tool_call.get("name") or "tool"
        return str(title).strip().casefold()
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
    """Build and run a transient prompt_toolkit Application for the approval panel."""
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
            return
        fb = feedback_buffer.text.strip() if state["feedback_mode"] else state["feedback"]
        _exit_with(event.app, state["selected"], fb)

    @kb.add("escape", eager=True)
    @kb.add("c-c", eager=True)
    @kb.add("c-d", eager=True)
    def _cancel(event) -> None:
        _exit_with(event.app, 2, "")

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
# Session-allow cache (module-level singleton)
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


# ---------------------------------------------------------------------------
# Result mapping — modal index/feedback → PermissionDecision
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class _DecisionTuple:
    """``(outcome, feedback)`` shape — mirrors ``PermissionDecision``."""

    outcome: str  # one of: allow_once, allow_always, deny, deny_feedback
    feedback: str | None = None


def _map_decision_from_approval(
    selected_index: int,
    feedback: str,
    *,
    action_key: str,
) -> _DecisionTuple:
    """Convert (selected_index, feedback) into a decision.

    Slot mapping:
      0 -> allow_once
      1 -> allow_always (also grants session approval for action_key)
      2 -> deny
      3 -> deny_feedback (or deny if feedback is empty)
    """
    slot = min(selected_index, 3)
    if slot == 0:
        return _DecisionTuple(outcome="allow_once")
    if slot == 1:
        _session_approvals.grant(action_key)
        msg = (
            f"[dim green]✓ approved · will not ask again for"
            f" [bold]{_rich_escape(action_key)}[/bold] this session[/dim green]"
        )
        _console.print(msg)
        return _DecisionTuple(outcome="allow_always")
    if slot == 3 and feedback:
        logger.info("Rejection feedback from user: {}", feedback)
        return _DecisionTuple(outcome="deny_feedback", feedback=feedback)
    return _DecisionTuple(outcome="deny")


__all__ = [
    "CLIRenderer",
    "_DecisionTuple",
    "_GroupedToolDisplay",
    "_SendResult",
    "_SessionApprovals",
    "_WaveIndicator",
    "_format_permission_tool",
    "_get_modal_depth",
    "_map_decision_from_approval",
    "_modal_active",
    "_permission_choice_matches",
    "_render_panel_ansi",
    "_run_approval_panel_async",
    "_run_interactive_modal",
    "_run_legacy_input",
    "_session_approvals",
    "_show_panel_in_pager",
    "_stdio_is_interactive",
    "_tool_action_key",
    "get_session_approvals",
    "print_via_terminal",
]
