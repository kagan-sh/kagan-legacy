"""Batched approval queue for concurrent tool-permission requests in kg chat.

When multiple ``request_permission`` calls arrive within the debounce window
(default 100 ms), they are collected into a single combined panel.  Each caller
receives an ``asyncio.Future``; the batch responder resolves all of them once
the user has worked through the panel.

N=1 path: if only one item arrives before the debounce fires, the caller's
Future is resolved with the raw (options, tool_call) tuple — the upstream
``request_permission`` implementation falls through to the existing
single-approval panel unchanged.

Batch path (N>=2): a single combined panel lists all pending items with
per-item options 1-4 and bulk options 5 (approve all) / 6 (reject all).
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
from dataclasses import dataclass
from typing import Any

from loguru import logger
from prompt_toolkit.application.run_in_terminal import run_in_terminal

# ---------------------------------------------------------------------------
# Environment-configurable debounce + cap
# ---------------------------------------------------------------------------

_DEFAULT_DEBOUNCE_MS = 100
_DEFAULT_BATCH_CAP = 20


def _debounce_seconds() -> float:
    raw = os.environ.get("KAGAN_BATCH_APPROVAL_DEBOUNCE_MS", "")
    try:
        return max(0.0, float(raw)) / 1000.0
    except ValueError:
        return _DEFAULT_DEBOUNCE_MS / 1000.0


def _batch_cap() -> int:
    raw = os.environ.get("KAGAN_BATCH_APPROVAL_CAP", "")
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_BATCH_CAP


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class _PendingItem:
    """One pending approval request waiting in the batch queue."""

    options: list[Any]
    tool_call: Any
    future: asyncio.Future[Any]  # resolved with an ACP response object


# ---------------------------------------------------------------------------
# Batch panel rendering helpers
# ---------------------------------------------------------------------------

# Options 1-4 come from the existing single-approval panel.
# Options 5-6 are batch-only bulk actions.
_BATCH_OPTION_LABELS: list[tuple[str, str]] = [
    ("Approve once", "allow_once"),
    ("Approve for this session", "allow_always"),
    ("Reject", "reject_once"),
    ("Reject — tell the model what to do", "reject_feedback"),
    ("Approve all remaining", "approve_all"),
    ("Reject all remaining", "reject_all"),
]


def _build_batch_panel_ansi(
    items: list[_PendingItem],
    *,
    focused_item: int,
    selected_option: int,
    feedback_draft: str,
) -> str:
    """Render the combined batch approval panel to an ANSI string."""
    from rich.console import Console, Group
    from rich.markup import escape as _rich_escape
    from rich.panel import Panel
    from rich.text import Text

    buf = io.StringIO()
    cols = shutil.get_terminal_size((80, 24)).columns
    tmp = Console(file=buf, highlight=False, width=cols, force_terminal=True)

    n = len(items)
    lines: list[Any] = []

    # Item list header
    lines.append(Text(f"[yellow]{n} tool calls pending:[/yellow]", justify="left"))
    lines.append(Text(""))

    for i, item in enumerate(items):
        raw = (
            getattr(item.tool_call, "title", None)
            or getattr(item.tool_call, "name", None)
            or "tool call"
        )
        name = _strip_mcp_prefix(str(raw))
        if i == focused_item:
            lines.append(Text.from_markup(f"[cyan bold]→ {name}[/cyan bold]"))
        else:
            lines.append(Text.from_markup(f"[dim]  {_rich_escape(name)}[/dim]"))

    lines.append(Text(""))

    # Option menu for focused item
    for idx, (label, _kind) in enumerate(_BATCH_OPTION_LABELS):
        num = idx + 1
        is_selected = idx == selected_option
        is_feedback_slot = idx == 3
        if is_selected:
            if is_feedback_slot and feedback_draft:
                cursor_display = f"→ [{num}] Reject: {feedback_draft}█"
                lines.append(Text(cursor_display, style="cyan"))
            else:
                lines.append(Text(f"→ [{num}] {label}", style="cyan bold"))
        else:
            lines.append(Text(f"  [{num}] {label}", style="dim"))

    lines.append(Text(""))

    # Footer hint
    if selected_option == 3 and feedback_draft:
        hint = "  Type feedback  Enter submit  Esc cancel"
    else:
        hint = "  ▲/▼ option  Tab/S-Tab item  1-6 choose  ↵ confirm  Esc reject all"
    lines.append(Text(hint, style="dim"))

    title = f"[bold]approval ({n} tools)[/bold]"
    panel = Panel(
        Group(*lines),
        border_style="yellow",
        title=title,
        title_align="left",
        padding=(0, 1),
    )
    tmp.print(panel)
    return buf.getvalue()


def _strip_mcp_prefix(name: str) -> str:
    for prefix in ("mcp__kagan__", "mcp__"):
        if name.startswith(prefix):
            name = name[len(prefix):]
    return name.replace("_", " ").strip()


# ---------------------------------------------------------------------------
# Interactive batch modal
# ---------------------------------------------------------------------------


async def _run_batch_modal_async(
    items: list[_PendingItem],
    *,
    _resolve_item: Any,
    _resolve_all: Any,
    _reject_all: Any,
) -> None:
    """Run the interactive batch-approval prompt_toolkit Application.

    Calls _resolve_item(index, option_idx, feedback) for per-item decisions,
    _resolve_all(option_idx) for approve-all / reject-all.
    Falls back to legacy_batch_input on any failure.
    """
    try:
        await _run_batch_interactive(
            items,
            resolve_item=_resolve_item,
            resolve_all=_resolve_all,
            reject_all=_reject_all,
        )
    except Exception:
        logger.debug("Batch interactive modal failed; falling back to legacy batch input")
        _run_legacy_batch_input(
            items,
            resolve_item=_resolve_item,
            reject_all=_reject_all,
        )


def _find_next_unresolved(
    current: int, n: int, resolved: set[int], direction: int = 1
) -> int | None:
    """Return the next unresolved item index (wrapping), or None if all done."""
    for i in range(1, n + 1):
        candidate = (current + direction * i) % n
        if candidate not in resolved:
            return candidate
    return None


def _reset_item_focus(state: dict[str, Any], new_idx: int, fb_buf: Any) -> None:
    """Move focus to a new item and reset option state."""
    from prompt_toolkit.document import Document

    state["focused_item"] = new_idx
    state["selected_option"] = 0
    state["feedback_mode"] = False
    state["feedback"] = ""
    fb_buf.set_document(Document(), bypass_readonly=True)


def _handle_num_key(
    idx: int,
    *,
    state: dict[str, Any],
    fb_buf: Any,
    app: Any,
    resolve_all: Any,
    reject_all: Any,
    confirm_fn: Any,
) -> None:
    """Handle a digit key press (0-based idx) in the batch modal."""
    state["selected_option"] = idx
    if idx == 3:
        state["feedback_mode"] = True
    elif idx == 4:
        resolve_all("allow_once")
        app.exit(result=None)
    elif idx == 5:
        reject_all()
        app.exit(result=None)
    else:
        state["feedback_mode"] = False
        confirm_fn(app)


async def _run_batch_interactive(
    items: list[_PendingItem],
    *,
    resolve_item: Any,
    resolve_all: Any,
    reject_all: Any,
) -> None:
    """Build and run a transient prompt_toolkit Application for batch approval."""
    from prompt_toolkit.application import Application
    from prompt_toolkit.buffer import Buffer
    from prompt_toolkit.document import Document
    from prompt_toolkit.formatted_text import ANSI
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import BufferControl, FormattedTextControl

    n = len(items)
    state: dict[str, Any] = {
        "focused_item": 0,
        "selected_option": 0,
        "feedback": "",
        "feedback_mode": False,
        "resolved": [],
    }

    feedback_buffer = Buffer(name="batch_approval_feedback", multiline=False)

    def _panel_text() -> ANSI:
        draft = feedback_buffer.text if state["feedback_mode"] else state["feedback"]
        ansi = _build_batch_panel_ansi(
            items,
            focused_item=state["focused_item"],
            selected_option=state["selected_option"],
            feedback_draft=draft,
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

    def _move_option(direction: int) -> None:
        if state["feedback_mode"]:
            state["feedback"] = feedback_buffer.text
            feedback_buffer.set_document(Document(), bypass_readonly=True)
        state["selected_option"] = (state["selected_option"] + direction) % 6
        state["feedback_mode"] = state["selected_option"] == 3

    def _confirm_current(app: Any) -> None:
        opt = state["selected_option"]
        item_idx = state["focused_item"]
        fb = feedback_buffer.text.strip() if state["feedback_mode"] else state["feedback"]
        if opt == 4:
            resolve_all("allow_once")
            app.exit(result=None)
            return
        if opt == 5:
            reject_all()
            app.exit(result=None)
            return
        resolve_item(item_idx, opt, fb)
        state["resolved"].append(item_idx)
        state["feedback"] = ""
        feedback_buffer.set_document(Document(), bypass_readonly=True)
        resolved_set = set(state["resolved"])
        next_idx = _find_next_unresolved(item_idx, n, resolved_set)
        if next_idx is None:
            app.exit(result=None)
        else:
            _reset_item_focus(state, next_idx, feedback_buffer)

    def _move_item(direction: int) -> None:
        resolved_set = set(state["resolved"])
        next_idx = _find_next_unresolved(state["focused_item"], n, resolved_set, direction)
        if next_idx is not None:
            _reset_item_focus(state, next_idx, feedback_buffer)

    @kb.add("up", eager=True)
    def _up(event) -> None:
        _move_option(-1)

    @kb.add("down", eager=True)
    def _down(event) -> None:
        _move_option(1)

    @kb.add("tab", eager=True)
    def _tab(event) -> None:
        _move_item(1)

    @kb.add("s-tab", eager=True)
    def _stab(event) -> None:
        _move_item(-1)

    @kb.add("enter", eager=True)
    def _enter(event) -> None:
        if state["feedback_mode"] and not feedback_buffer.text.strip():
            return
        _confirm_current(event.app)

    @kb.add("escape", eager=True)
    @kb.add("c-c", eager=True)
    @kb.add("c-d", eager=True)
    def _cancel(event) -> None:
        reject_all()
        event.app.exit(result=None)

    def _make_num_handler(num: int) -> None:
        @kb.add(str(num), eager=True)
        def _num(event) -> None:
            _handle_num_key(
                num - 1,
                state=state,
                fb_buf=feedback_buffer,
                app=event.app,
                resolve_all=resolve_all,
                reject_all=reject_all,
                confirm_fn=_confirm_current,
            )

    for n_key in range(1, 7):
        _make_num_handler(n_key)

    app: Application[None] = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )
    await app.run_async()


def _run_legacy_batch_input(
    items: list[_PendingItem],
    *,
    resolve_item: Any,
    reject_all: Any,
) -> None:
    """Sync fallback: iterate items one by one via input()."""
    from kagan.cli.chat.repl import _console

    for i, item in enumerate(items):
        _console.print(
            f"[bold yellow]approval ({i+1}/{len(items)})[/bold yellow]: "
            f"{_strip_mcp_prefix(getattr(item.tool_call, 'title', None) or 'tool')}"
        )
        try:
            raw = input("  [1] approve  [3] reject  > ").strip()
            if raw in {"1", "2"}:
                resolve_item(i, 0, "")
            elif raw in {"5", "a"}:
                # approve all remaining
                for j in range(i, len(items)):
                    resolve_item(j, 0, "")
                return
            elif raw in {"6", "d"}:
                reject_all()
                return
            else:
                resolve_item(i, 2, "")
        except (EOFError, KeyboardInterrupt):
            reject_all()
            return


# ---------------------------------------------------------------------------
# Batch queue
# ---------------------------------------------------------------------------


class _BatchApprovalQueue:
    """Collect concurrent request_permission calls and present them as one panel.

    Usage::

        queue = _BatchApprovalQueue(acp_client)
        # In _OrchestratorACPClient.request_permission:
        future = await queue.enqueue(options, tool_call)
        response = await future   # blocks until batch resolves

    The queue arms a debounce timer on the first enqueue.  When the timer fires
    (or the cap is reached) it calls ``_flush()`` which renders the batch panel
    and resolves all pending Futures.
    """

    def __init__(self, client: Any) -> None:
        self._client = client  # _OrchestratorACPClient reference (for helpers)
        self._pending: list[_PendingItem] = []
        self._debounce_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        """Clear queue state at turn start (called from start_turn)."""
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = None
        # Resolve any lingering futures as cancelled
        for item in self._pending:
            if not item.future.done():
                from kagan.cli.chat._chat_acp import _cancelled_permission_response

                item.future.set_result(_cancelled_permission_response())
        self._pending.clear()

    def cancel_all(self) -> None:
        """Cancel all pending futures (SIGINT handler)."""
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = None
        from kagan.cli.chat._chat_acp import _cancelled_permission_response

        for item in self._pending:
            if not item.future.done():
                item.future.set_result(_cancelled_permission_response())
        self._pending.clear()

    async def enqueue(self, options: list[Any], tool_call: Any) -> asyncio.Future[Any]:
        """Add one permission request to the queue; return a Future for the response."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[Any] = loop.create_future()
        item = _PendingItem(options=options, tool_call=tool_call, future=fut)

        async with self._lock:
            self._pending.append(item)
            cap = _batch_cap()
            if len(self._pending) >= cap:
                # Cancel debounce timer and flush immediately
                if self._debounce_task is not None and not self._debounce_task.done():
                    self._debounce_task.cancel()
                self._debounce_task = None
                asyncio.ensure_future(self._flush())
            elif self._debounce_task is None or self._debounce_task.done():
                # Arm new debounce timer
                self._debounce_task = asyncio.create_task(
                    self._debounce_then_flush(), name="batch-approval-debounce"
                )

        return fut

    async def _debounce_then_flush(self) -> None:
        await asyncio.sleep(_debounce_seconds())
        await self._flush()

    async def _flush(self) -> None:
        """Take snapshot of pending items and render panel; resolve all Futures."""
        async with self._lock:
            items = list(self._pending)
            self._pending.clear()
            self._debounce_task = None

        if not items:
            return

        if len(items) == 1:
            # N=1: fall through to the single-approval panel unchanged.
            await self._flush_single(items[0])
            return

        await self._flush_batch(items)

    async def _flush_single(self, item: _PendingItem) -> None:
        """Resolve one item via the existing single-approval panel."""
        from kagan.cli.chat._chat_acp import (
            _map_approval_result,
            _rejected_permission_response,
            _run_approval_panel_async,
            _selected_permission_response,
            _session_approvals,
            _tool_action_key,
        )

        action_key = _tool_action_key(item.tool_call)
        if _session_approvals.is_allowed(action_key):
            for o in item.options:
                if getattr(o, "kind", None) == "allow_once":
                    item.future.set_result(_selected_permission_response(o))
                    return
            item.future.set_result(_selected_permission_response(item.options[0]))
            return

        selected_index, feedback = await _run_approval_panel_async(
            item.tool_call,
            permission_options=item.options,
            queue_position=1,
            queue_depth=1,
        )
        option = _map_approval_result(
            selected_index,
            feedback,
            action_key=action_key,
            permission_options=item.options,
        )
        if option is None:
            item.future.set_result(_rejected_permission_response())
        else:
            item.future.set_result(_selected_permission_response(option))

    async def _flush_batch(self, items: list[_PendingItem]) -> None:
        """Render combined batch panel and resolve all item Futures."""
        from kagan.cli.chat._chat_acp import (
            _map_approval_result,
            _rejected_permission_response,
            _selected_permission_response,
            _tool_action_key,
        )

        # We'll collect resolutions here then apply after the modal closes
        resolutions: dict[int, Any] = {}  # index -> ACP response

        def _resolve_item(item_idx: int, opt_idx: int, feedback: str) -> None:
            item = items[item_idx]
            action_key = _tool_action_key(item.tool_call)
            option = _map_approval_result(
                opt_idx,
                feedback,
                action_key=action_key,
                permission_options=item.options,
            )
            if option is None:
                resolutions[item_idx] = _rejected_permission_response()
            else:
                resolutions[item_idx] = _selected_permission_response(option)

        def _resolve_all(kind: str) -> None:
            for i, item in enumerate(items):
                if i not in resolutions:
                    for o in item.options:
                        if getattr(o, "kind", None) == kind:
                            resolutions[i] = _selected_permission_response(o)
                            break
                    else:
                        # fall back to first option
                        if item.options:
                            resolutions[i] = _selected_permission_response(item.options[0])
                        else:
                            resolutions[i] = _rejected_permission_response()

        def _reject_all_fn() -> None:
            for i, _item in enumerate(items):
                if i not in resolutions:
                    resolutions[i] = _rejected_permission_response()

        run_in_terminal(lambda: None)  # flush any pending terminal output

        await _run_batch_modal_async(
            items,
            _resolve_item=_resolve_item,
            _resolve_all=_resolve_all,
            _reject_all=_reject_all_fn,
        )

        # Apply resolutions; any still-missing items get rejected
        for i, item in enumerate(items):
            response = resolutions.get(i)
            if response is None:
                response = _rejected_permission_response()
            if not item.future.done():
                item.future.set_result(response)
