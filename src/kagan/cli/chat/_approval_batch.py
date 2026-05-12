"""Batched approval queue for concurrent tool-permission requests in kg chat.

When multiple permission requests arrive within the debounce window
(default 100 ms), they are collected into a single combined panel.  Each
caller receives an ``asyncio.Future`` which is resolved once the user has
worked through the panel; the queue *also* dispatches the decision via
``engine.resolve_permission(session_id, future_id, outcome=..., feedback=...)``
so the assistant turn unblocks.

N=1 path: if only one item arrives before the debounce fires, the caller's
Future resolves once the single-approval modal returns.

Batch path (N>=2): a single combined panel lists all pending items with
per-item options 1-4 and bulk options 5 (approve all) / 6 (reject all).

Phase 5c: the queue dispatches via ``ChatEngine.resolve_permission`` and
no longer constructs ACP responses. ACP-shape translation lives in
``_CaptureACPClient.request_permission``.
"""

from __future__ import annotations

import asyncio
import io
import os
import shutil
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger
from prompt_toolkit.application.run_in_terminal import run_in_terminal

from kagan.cli.chat._approval_panel import no_color, strip_tool_prefix
from kagan.cli.chat._theme import APPROVAL

if TYPE_CHECKING:
    from kagan.cli.chat._approval_types import _DecisionTuple

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
    """One pending approval request waiting in the batch queue.

    ``future`` resolves to ``None`` (meaning the queue has dispatched the
    decision via ``engine.resolve_permission``). The caller awaits it purely
    as a "decided" signal; the actual decision was already routed through the
    engine. It's kept as a Future (rather than a bare Event) so that
    ``cancel_all`` can short-circuit pending awaits on SIGINT.
    """

    options: list[Any]
    tool_call: Any
    future_id: str
    session_id: str
    future: asyncio.Future[None] = field(repr=False)


# ---------------------------------------------------------------------------
# Batch panel rendering helpers (unchanged)
# ---------------------------------------------------------------------------

_BATCH_OPTION_LABELS: list[tuple[str, str]] = [
    ("Approve once", "allow_once"),
    ("Approve tool for session", "allow_always"),
    ("Allow all for session", "allow_all_session"),
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
    resolved: dict[int, str] | None = None,
) -> str:
    from rich.console import Console, Group
    from rich.panel import Panel
    from rich.text import Text

    resolved = resolved or {}
    buf = io.StringIO()
    cols = shutil.get_terminal_size((80, 24)).columns
    tmp = Console(file=buf, highlight=False, width=cols, force_terminal=True, no_color=no_color())

    n = len(items)
    pending = sum(1 for i in range(n) if i not in resolved)
    lines: list[Any] = []

    lines.append(Text.from_markup(f"[yellow]{pending} of {n} tool calls pending:[/yellow]"))
    lines.append(Text(""))

    for i, item in enumerate(items):
        raw_tc = item.tool_call
        raw = (
            (raw_tc.get("title") or raw_tc.get("name") if isinstance(raw_tc, dict) else None)
            or getattr(raw_tc, "title", None)
            or getattr(raw_tc, "name", None)
            or "tool call"
        )
        name = strip_tool_prefix(str(raw))
        disposition = resolved.get(i)
        if disposition == "approved":
            lines.append(Text(f"✓ {name}", style="dim green"))
        elif disposition == "rejected":
            lines.append(Text(f"✗ {name}", style="dim red"))
        elif i == focused_item:
            lines.append(Text(f"→ {name}", style=APPROVAL.focused))
        else:
            lines.append(Text(f"  {name}", style=APPROVAL.dim))

    lines.append(Text(""))

    for idx, (label, _kind) in enumerate(_BATCH_OPTION_LABELS):
        num = idx + 1
        is_selected = idx == selected_option
        is_feedback_slot = idx == 4
        if is_selected:
            if is_feedback_slot and feedback_draft:
                cursor_display = f"→ [{num}] Reject: {feedback_draft}█"
                lines.append(Text(cursor_display, style=APPROVAL.cursor))
            else:
                lines.append(Text(f"→ [{num}] {label}", style=APPROVAL.focused))
        else:
            lines.append(Text(f"  [{num}] {label}", style=APPROVAL.dim))

    lines.append(Text(""))

    if selected_option == 4 and feedback_draft:
        hint = "  Type feedback  Enter submit  Esc cancel"
    else:
        hint = "  ▲/▼ option  Tab/S-Tab item  1-7 choose  ↵ confirm  Ctrl-E expand  Esc reject all"
    lines.append(Text(hint, style=APPROVAL.hint))

    title = f"[bold]approval ({n} tools)[/bold]"
    panel = Panel(
        Group(*lines),
        border_style=APPROVAL.border,
        title=title,
        title_align="left",
        padding=(0, 1),
    )
    tmp.print(panel)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Interactive batch modal (unchanged)
# ---------------------------------------------------------------------------


async def _run_batch_modal_async(
    items: list[_PendingItem],
    *,
    _resolve_item: Any,
    _resolve_all: Any,
    _reject_all: Any,
) -> None:
    try:
        await _run_batch_interactive(
            items,
            resolve_item=_resolve_item,
            resolve_all=_resolve_all,
            reject_all=_reject_all,
        )
    except Exception:
        logger.warning(
            "Batch interactive modal failed; falling back to legacy batch input",
            exc_info=True,
        )
        _run_legacy_batch_input(
            items,
            resolve_item=_resolve_item,
            reject_all=_reject_all,
        )


def _find_next_unresolved(
    current: int, n: int, resolved: set[int], direction: int = 1
) -> int | None:
    for i in range(1, n + 1):
        candidate = (current + direction * i) % n
        if candidate not in resolved:
            return candidate
    return None


def _reset_item_focus(state: dict[str, Any], new_idx: int, fb_buf: Any) -> None:
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
    state["selected_option"] = idx
    if idx == 4:
        state["feedback_mode"] = True
    elif idx == 2:
        from kagan.cli.chat._approval_types import _session_approvals

        # Allow all for session: pre-approve this tool for the rest of the session.
        _session_approvals.grant_all()
        resolve_all("allow_once")
        app.exit(result=None)
    elif idx == 5:
        # Approve all remaining in this batch only (no session-wide trust).
        resolve_all("allow_once")
        app.exit(result=None)
    elif idx == 6:
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
        "resolved": {},
    }

    feedback_buffer = Buffer(name="batch_approval_feedback", multiline=False)

    def _panel_text() -> ANSI:
        draft = feedback_buffer.text if state["feedback_mode"] else state["feedback"]
        ansi = _build_batch_panel_ansi(
            items,
            focused_item=state["focused_item"],
            selected_option=state["selected_option"],
            feedback_draft=draft,
            resolved=state["resolved"],
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
        state["selected_option"] = (state["selected_option"] + direction) % 7
        state["feedback_mode"] = state["selected_option"] == 4

    def _confirm_current(app: Any) -> None:
        opt = state["selected_option"]
        item_idx = state["focused_item"]
        fb = feedback_buffer.text.strip() if state["feedback_mode"] else state["feedback"]
        if opt == 2:
            from kagan.cli.chat._approval_types import _session_approvals

            _session_approvals.grant_all()
            resolve_all("allow_once")
            app.exit(result=None)
            return
        if opt == 5:
            resolve_all("allow_once")
            app.exit(result=None)
            return
        if opt == 6:
            reject_all()
            app.exit(result=None)
            return
        resolve_item(item_idx, opt, fb)
        state["resolved"][item_idx] = "approved" if opt in (0, 1, 2) else "rejected"
        state["feedback"] = ""
        feedback_buffer.set_document(Document(), bypass_readonly=True)
        next_idx = _find_next_unresolved(item_idx, n, set(state["resolved"]))
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

    for n_key in range(1, 8):
        _make_num_handler(n_key)

    app: Application[None] = Application(
        layout=layout,
        key_bindings=kb,
        full_screen=False,
        mouse_support=False,
    )
    from kagan.cli.chat._approval_types import _modal_active

    with _modal_active():
        await app.run_async()


def _run_legacy_batch_input(
    items: list[_PendingItem],
    *,
    resolve_item: Any,
    reject_all: Any,
) -> None:
    from kagan.cli.chat.repl import _console

    for i, item in enumerate(items):
        raw_tc = item.tool_call
        title = (
            (raw_tc.get("title") if isinstance(raw_tc, dict) else None)
            or getattr(raw_tc, "title", None)
            or "tool"
        )
        _console.print(
            f"[bold yellow]approval ({i + 1}/{len(items)})[/bold yellow]: "
            f"{strip_tool_prefix(str(title))}"
        )
        try:
            raw = input(
                "  [1] approve once  [2] approve tool session  [3] allow all session  "
                "[4] reject  [6] approve all  [7] reject all  > "
            ).strip()
            if raw == "1":
                resolve_item(i, 0, "")
            elif raw == "2":
                resolve_item(i, 1, "")
            elif raw == "3":
                from kagan.cli.chat._approval_types import _session_approvals

                # "Allow all for session" — grant_all short-circuits future
                # permission checks, so resolve every remaining item as
                # allow_once and return (matching the interactive modal).
                _session_approvals.grant_all()
                for j in range(i, len(items)):
                    resolve_item(j, 0, "")
                return
            elif raw in {"6", "a"}:
                for j in range(i, len(items)):
                    resolve_item(j, 0, "")
                return
            elif raw in {"7", "d"}:
                reject_all()
                return
            else:
                resolve_item(i, 3, "")
        except (EOFError, KeyboardInterrupt):
            reject_all()
            return


# ---------------------------------------------------------------------------
# Batch queue
# ---------------------------------------------------------------------------


def _resolve_decision_via_engine(
    engine: Any,
    item: _PendingItem,
    decision: _DecisionTuple,
) -> None:
    """Push the decision to the engine and mark the local future done.

    Engine call is fire-and-forget — its only failure mode is "future_id
    unknown" which is already an idempotent no-op inside the engine.
    """
    try:
        coro = engine.resolve_permission(
            item.session_id,
            item.future_id,
            outcome=decision.outcome,
            feedback=decision.feedback,
        )
    except Exception:
        logger.exception("engine.resolve_permission raised; dropping decision")
        if not item.future.done():
            item.future.set_result(None)
        return
    asyncio.ensure_future(coro)
    if not item.future.done():
        item.future.set_result(None)


def _cancelled_decision() -> _DecisionTuple:
    from kagan.cli.chat._approval_types import _DecisionTuple as _DT

    return _DT(outcome="deny")


def _preresolve_session_approved(
    items: list[_PendingItem],
    *,
    engine: Any,
) -> tuple[set[int], list[_PendingItem], list[int]]:
    """Auto-resolve items whose tool was previously approved-for-session.

    Returns ``(resolved_indices, unresolved_items, unresolved_index_map)``.
    Resolved items are dispatched to the engine immediately.
    """
    from kagan.cli.chat._approval_types import (
        _DecisionTuple,
        _session_approvals,
        _tool_action_key,
    )

    resolved_indices: set[int] = set()
    unresolved_items: list[_PendingItem] = []
    unresolved_index_map: list[int] = []
    for original_idx, pending in enumerate(items):
        action_key = _tool_action_key(pending.tool_call)
        if not _session_approvals.is_allowed(action_key):
            unresolved_items.append(pending)
            unresolved_index_map.append(original_idx)
            continue
        _resolve_decision_via_engine(engine, pending, _DecisionTuple(outcome="allow_once"))
        resolved_indices.add(original_idx)
    return resolved_indices, unresolved_items, unresolved_index_map


class _BatchApprovalQueue:
    """Collect concurrent permission requests and present them as one panel.

    Phase 5c: the queue dispatches decisions via
    ``engine.resolve_permission(session_id, future_id, outcome, feedback)``
    instead of constructing ACP responses. Item Futures resolve to ``None``
    once dispatched — they exist only so callers can ``await`` for the
    "decided" event.

    Constructed by :class:`PermissionUI`; the ``engine`` ref is supplied at
    construction time so the queue stays self-contained.
    """

    def __init__(self, engine: Any) -> None:
        self._engine = engine
        self._pending: list[_PendingItem] = []
        self._debounce_task: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    def reset(self) -> None:
        """Clear queue state at turn start."""
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = None
        for item in self._pending:
            _resolve_decision_via_engine(self._engine, item, _cancelled_decision())
        self._pending.clear()

    def cancel_all(self) -> None:
        """Cancel all pending futures (SIGINT handler)."""
        if self._debounce_task is not None and not self._debounce_task.done():
            self._debounce_task.cancel()
        self._debounce_task = None
        for item in self._pending:
            _resolve_decision_via_engine(self._engine, item, _cancelled_decision())
        self._pending.clear()

    async def enqueue(
        self,
        options: list[Any],
        tool_call: Any,
        *,
        future_id: str,
        session_id: str,
    ) -> asyncio.Future[None]:
        """Add a request to the queue; return a Future that resolves once decided."""
        loop = asyncio.get_running_loop()
        fut: asyncio.Future[None] = loop.create_future()
        item = _PendingItem(
            options=options,
            tool_call=tool_call,
            future_id=future_id,
            session_id=session_id,
            future=fut,
        )

        async with self._lock:
            self._pending.append(item)
            cap = _batch_cap()
            if len(self._pending) >= cap:
                if self._debounce_task is not None and not self._debounce_task.done():
                    self._debounce_task.cancel()
                self._debounce_task = None
                asyncio.ensure_future(self._flush())
            elif self._debounce_task is None or self._debounce_task.done():
                self._debounce_task = asyncio.create_task(
                    self._debounce_then_flush(), name="batch-approval-debounce"
                )

        return fut

    async def _debounce_then_flush(self) -> None:
        await asyncio.sleep(_debounce_seconds())
        await self._flush()

    async def _flush(self) -> None:
        async with self._lock:
            items = list(self._pending)
            self._pending.clear()
            self._debounce_task = None

        if not items:
            return

        if len(items) == 1:
            await self._flush_single(items[0])
            return

        await self._flush_batch(items)

    async def _flush_single(self, item: _PendingItem) -> None:
        from kagan.cli.chat._approval_types import (
            _DecisionTuple,
            _session_approvals,
            _tool_action_key,
        )
        from kagan.cli.chat._permission_ui import (
            _map_decision_from_approval,
            _run_approval_panel_async,
        )

        action_key = _tool_action_key(item.tool_call)
        if _session_approvals.is_allowed(action_key):
            _resolve_decision_via_engine(self._engine, item, _DecisionTuple(outcome="allow_once"))
            return

        selected_index, feedback = await _run_approval_panel_async(
            item.tool_call,
            permission_options=item.options,
            queue_position=1,
            queue_depth=1,
        )
        decision = _map_decision_from_approval(selected_index, feedback, action_key=action_key)
        _resolve_decision_via_engine(self._engine, item, decision)

    async def _flush_batch(self, items: list[_PendingItem]) -> None:
        from kagan.cli.chat._approval_types import (
            _DecisionTuple,
            _session_approvals,
            _tool_action_key,
        )
        from kagan.cli.chat._permission_ui import (
            _map_decision_from_approval,
        )

        resolved_indices, unresolved_items, unresolved_index_map = _preresolve_session_approved(
            items, engine=self._engine
        )

        if not unresolved_items:
            return

        if len(unresolved_items) == 1:
            await self._flush_single(unresolved_items[0])
            return

        # Local map so ``_resolve_all`` / ``_reject_all`` can override
        # ``_resolve_item`` calls. Items are dispatched to the engine after
        # the modal exits.
        decisions: dict[int, _DecisionTuple] = {}

        def _resolve_item(unresolved_idx: int, opt_idx: int, feedback: str) -> None:
            original_idx = unresolved_index_map[unresolved_idx]
            item = items[original_idx]
            action_key = _tool_action_key(item.tool_call)
            # Slot 2 in the batch panel is "Allow all for session" — intercept
            # here (like the single-panel modal does) so the grant is applied
            # instead of falling through to deny via the unmapped slot.
            if opt_idx == 2:
                _session_approvals.grant_all()
                decisions[original_idx] = _DecisionTuple(outcome="allow_once")
                return
            decisions[original_idx] = _map_decision_from_approval(
                opt_idx, feedback, action_key=action_key
            )

        def _resolve_all(kind: str) -> None:
            for original_idx in unresolved_index_map:
                if original_idx in decisions:
                    continue
                outcome = "allow_always" if kind == "allow_always" else "allow_once"
                decisions[original_idx] = _DecisionTuple(outcome=outcome)

        def _reject_all_fn() -> None:
            for original_idx in unresolved_index_map:
                if original_idx not in decisions:
                    decisions[original_idx] = _DecisionTuple(outcome="deny")

        run_in_terminal(lambda: None)

        await _run_batch_modal_async(
            unresolved_items,
            _resolve_item=_resolve_item,
            _resolve_all=_resolve_all,
            _reject_all=_reject_all_fn,
        )

        # Dispatch every unresolved item; default to deny for any still missing.
        for original_idx in unresolved_index_map:
            if original_idx in resolved_indices:
                continue
            decision = decisions.get(original_idx) or _DecisionTuple(outcome="deny")
            _resolve_decision_via_engine(self._engine, items[original_idx], decision)
