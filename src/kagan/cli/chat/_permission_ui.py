"""PermissionUI — engine-driven permission flow for the CLI REPL.

Owns the full permission UX surface for ``kg chat``:

* :class:`PermissionUI` — the controller-facing entry point. Consumes a
  :class:`PermissionRequest` event from :class:`kagan.core.chat.ChatEngine`
  and dispatches the user's decision via
  ``engine.resolve_permission(session_id, future_id, outcome=..., feedback=...)``.
* The single-approval modal (``_run_interactive_modal`` / ``_run_legacy_input`` /
  ``_run_approval_panel_async``) and ANSI render helpers
  (``_render_panel_ansi`` / ``_show_panel_in_pager``).
* The session-allow cache (``_session_approvals`` / ``get_session_approvals``)
  and pure formatters (``_format_permission_tool``, ``_tool_action_key``,
  ``_stdio_is_interactive``, ``_permission_choice_matches``).
* The ``(outcome, feedback)`` decision tuple (``_DecisionTuple``) and the
  modal-result mapper (``_map_decision_from_approval``).
* :class:`_WaveIndicator` and :class:`_SendResult` — small dataclasses still
  used by the controller and the batch queue.

Phase 6 of refactor R1 collapses ``_chat_acp.py`` and ``_permission_ui.py``
into one module. Tests that previously did
``import kagan.cli.chat._chat_acp as chat_acp_module`` should now import from
this module instead.
"""

from __future__ import annotations

import io
import shutil
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kagan.core.permission import PermissionRequest

from loguru import logger
from prompt_toolkit.application.run_in_terminal import run_in_terminal
from rich.markup import escape as _rich_escape

from kagan.cli.chat._approval_panel import build_approval_panel, no_color
from kagan.cli.chat._approval_types import (
    _DecisionTuple,
    _modal_active,
    _SendResult,
    _session_approvals,
    _SessionApprovals,
    _tool_action_key,
    _WaveIndicator,
    get_session_approvals,
)
from kagan.cli.chat._renderer import (
    CLIRenderer,
    _GroupedToolDisplay,
    _modal_depth,
    print_via_terminal,
)
from kagan.cli.chat.repl import _console

# ---------------------------------------------------------------------------
# Pure helpers
# ---------------------------------------------------------------------------


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


def _get_modal_depth() -> int:  # pragma: no cover — diagnostic helper
    return _modal_depth()


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
        state["selected"] = (state["selected"] + direction) % 5
        state["feedback_mode"] = state["selected"] == 4

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
        selected = state["selected"]
        if selected == 2:
            _session_approvals.grant_all()
            msg = "[dim green]✓ all tools trusted for this session[/dim green]"
            from kagan.cli.chat.repl import _console as _c

            _c.print(msg)
            _exit_with(event.app, 0, "")
        else:
            _exit_with(event.app, selected, fb)

    @kb.add("escape", eager=True)
    @kb.add("c-c", eager=True)
    @kb.add("c-d", eager=True)
    def _cancel(event) -> None:
        _exit_with(event.app, 3, "")

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
            if idx == 4:
                state["feedback_mode"] = True
            elif idx == 2:
                state["feedback_mode"] = False
                _session_approvals.grant_all()
                msg = "[dim green]✓ all tools trusted for this session[/dim green]"
                from kagan.cli.chat.repl import _console as _c

                _c.print(msg)
                _exit_with(event.app, 0, "")
            else:
                state["feedback_mode"] = False
                _exit_with(event.app, idx, "")

    for n in range(1, 6):
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
            if raw in {"1", "2", "3", "4", "5"}:
                selected_index = int(raw) - 1
                if selected_index == 2:
                    _session_approvals.grant_all()
                    _console.print("[dim green]✓ all tools trusted for this session[/dim green]")
                    selected_index = 0
                elif selected_index == 4:
                    _console.print(
                        "[dim]Type rejection reason (Enter confirm, empty cancel):[/dim]"
                    )
                    try:
                        feedback_draft = input().strip()
                    except (EOFError, KeyboardInterrupt):
                        feedback_draft = ""
                break
            if raw in {"q", "n", "reject", "deny"}:
                selected_index = 3
                break
            if raw in {"y", "a", "approve"}:
                selected_index = 0
                break
    except (EOFError, KeyboardInterrupt):
        selected_index = 3

    return selected_index, feedback_draft


# ---------------------------------------------------------------------------
# Result mapping — modal index/feedback → PermissionDecision
# ---------------------------------------------------------------------------
# Result mapping — modal index/feedback → PermissionDecision
# ---------------------------------------------------------------------------


def _map_decision_from_approval(
    selected_index: int,
    feedback: str,
    *,
    action_key: str,
) -> _DecisionTuple:
    """Convert (selected_index, feedback) into a decision.

    Slot mapping (slot 2 is handled before this call — grant_all + allow_once):
      0 -> allow_once
      1 -> allow_always (also grants session approval for action_key)
      2 -> (intercepted upstream — grant_all; never reaches here; treated as allow_once)
      3 -> deny
      4 -> deny_feedback (or deny if feedback is empty)
    """
    slot = min(selected_index, 4)
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
    if slot == 4 and feedback:
        logger.info("Rejection feedback from user: {}", feedback)
        return _DecisionTuple(outcome="deny_feedback", feedback=feedback)
    return _DecisionTuple(outcome="deny")


# ---------------------------------------------------------------------------
# PermissionUI — controller-facing entry point
# ---------------------------------------------------------------------------


class PermissionUI:
    """Owns the modal + cache + batch queue for one chat session.

    ``renderer`` is held so the queue can finalize the streaming Markdown
    region before opening a modal. ``engine`` is the :class:`ChatEngine`
    receiving every decision — supplied lazily via :meth:`bind_engine` so
    construction order in the controller stays simple.
    """

    def __init__(
        self,
        *,
        renderer: CLIRenderer | None = None,
        engine: Any = None,
    ) -> None:
        from kagan.cli.chat._approval_batch import _BatchApprovalQueue

        self._renderer = renderer
        self._engine = engine
        self._batch_queue = _BatchApprovalQueue(engine)

    def bind_engine(self, engine: Any) -> None:
        """(Re)bind the engine reference and rebuild the batch queue.

        Called when the controller switches sessions / restarts the factory
        but keeps the same ``PermissionUI`` instance.
        """
        from kagan.cli.chat._approval_batch import _BatchApprovalQueue

        self._engine = engine
        self._batch_queue = _BatchApprovalQueue(engine)

    # ------------------------------------------------------------------
    # Hooks consumed by ``_BatchApprovalQueue`` for terminal printing.
    # ------------------------------------------------------------------

    def _print_via_terminal(self, fn: Any) -> None:
        print_via_terminal(fn)

    # ------------------------------------------------------------------
    # Entry point — called by the controller for each PermissionRequest event
    # ------------------------------------------------------------------

    async def handle_request(
        self,
        event: PermissionRequest,
        session_id: str,
    ) -> None:
        """Handle one engine permission event.

        Resolves the decision via :meth:`ChatEngine.resolve_permission`. The
        coroutine returns once the decision has been *dispatched* — fast for
        non-interactive denial paths; for interactive paths it returns once the
        modal flow finishes and the engine has been notified.
        """
        if self._engine is None:
            raise RuntimeError("PermissionUI.handle_request called before bind_engine")

        # Engine emits ``options`` as plain dicts; preserve dict shape so the
        # batch queue / single-approval helpers can render titles uniformly.
        permission_options = [
            opt
            for opt in (event.options or ())
            if (opt.get("kind") if isinstance(opt, dict) else getattr(opt, "kind", None))
            in {"allow_once", "allow_always", "reject_once", "reject_always"}
        ]
        if not permission_options:
            await self._engine.resolve_permission(session_id, event.future_id, outcome="deny")
            return

        tool_key = _tool_action_key(event.tool_call)
        if tool_key.startswith("mcp__kagan"):
            await self._engine.resolve_permission(session_id, event.future_id, outcome="allow_once")
            return

        if self._renderer is not None:
            self._renderer.finalize_pending_markdown()

        if not _stdio_is_interactive():

            def _print_denied() -> None:
                _console.print(
                    "[yellow]Permission request denied in non-interactive mode.[/yellow]"
                )

            self._print_via_terminal(_print_denied)
            await self._engine.resolve_permission(session_id, event.future_id, outcome="deny")
            return

        future = await self._batch_queue.enqueue(
            permission_options,
            event.tool_call,
            future_id=event.future_id,
            session_id=session_id,
        )
        # Wait for the queue to dispatch — the queue calls
        # ``engine.resolve_permission`` itself before resolving this future.
        await future

    def reset_batch_queue(self) -> None:
        """Clear queue state at turn start."""
        self._batch_queue.reset()

    def cancel_batch_queue(self) -> None:
        """Cancel all pending batch approval futures (SIGINT)."""
        self._batch_queue.cancel_all()


__all__ = [
    "CLIRenderer",
    "PermissionUI",
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
