"""OrchestratorOverlay — app-level modal overlay for unified session chat.

Bound globally to ``o`` (and ``ctrl+space``).

The overlay hosts a ChatPanel and a SessionList.  Any session type can be
selected:

- **Orchestrator** — loads chat history from ``orchestrator_sessions``.
- **General** — loads chat history from ``chat_sessions.get_with_history()``.
- **Task** — replays recent events read-only; live streaming and sending
  messages are disabled.

ESC behaviour
-------------
- Always closes the overlay (no attach/detach state machine).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, cast

from loguru import logger
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Input, ListView, Static

from kagan.core.enums import SessionKind
from kagan.tui.keybindings import ORCHESTRATOR_OVERLAY_BINDINGS
from kagan.tui.screens._chat_runner import (
    present_agent_event,
    render_agent_event_to_output,
    send_chat_message,
)
from kagan.tui.widgets.chat import ChatPanel
from kagan.tui.widgets.session_list import SessionList

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.core._session_items import SessionItem
    from kagan.tui.app import KaganApp
    from kagan.tui.widgets.streaming import StreamingOutput

_ORCHESTRATOR_TITLE = "Orchestrator"


class OrchestratorOverlay(ModalScreen[None]):
    """App-level session chat overlay.

    Parameters
    ----------
    task_id:
        If set and no active session exists, the overlay pre-fills the chat
        input with ``@task:<id> `` so the user has context.
    poll_interval:
        Session-list poll interval.  Set to 0 in tests.
    """

    BINDINGS = ORCHESTRATOR_OVERLAY_BINDINGS

    DEFAULT_CSS = """
    OrchestratorOverlay {
        align: center middle;
        background: $background 80%;
    }
    #orch-container {
        width: 90%;
        height: 85%;
        max-width: 120;
        border: round $primary;
        background: $background;
        layout: vertical;
    }
    #orch-breadcrumb {
        height: 2;
        width: 100%;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
        border-bottom: solid $border;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    OrchestratorOverlay #chat-panel {
        dock: none;
        height: 1fr;
        width: 100%;
        max-height: 100%;
        offset-y: 0;
        border-top: none;
        display: block;
    }
    """

    def __init__(
        self,
        *,
        task_id: str | None = None,
        poll_interval: float = 2.0,
    ) -> None:
        super().__init__()
        self._task_id = task_id
        self._poll_interval = poll_interval

        # Currently selected session (None = orchestrator default)
        self._selected_session_id: str | None = None
        self._selected_item: SessionItem | None = None

        # Orchestrator history cache
        self._orchestrator_history: list[tuple[str, str]] = []

        # Stream worker for task replay
        self._sse_task: asyncio.Task[None] | None = None

        # In-flight message send
        self._send_task: asyncio.Task[None] | None = None

        # Chat session switch token (prevents stale callbacks)
        self._session_switch_token = 0

        self._chat_message_task: asyncio.Task[None] | None = None

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="orch-container"):
            yield Static(_ORCHESTRATOR_TITLE, id="orch-breadcrumb")
            yield ChatPanel(id="chat-panel", classes="")
            yield SessionList(
                id="orch-session-list",
                poll_interval=self._poll_interval,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_mount(self) -> None:
        await self._select_orchestrator()

        # Pre-fill @task:<id> prefix if provided
        if self._task_id is not None and self._selected_session_id is None:
            with contextlib.suppress(NoMatches):
                inp = self.query_one("#chat-overlay-input", Input)
                inp.value = f"@task:{self._task_id[:8]} "

        self.call_after_refresh(self._focus_input)

    async def on_unmount(self) -> None:
        await self._cancel_sse()
        if self._chat_message_task is not None:
            self._chat_message_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._chat_message_task

    def on_show(self) -> None:
        self.call_after_refresh(self._focus_input)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def kagan_app(self) -> KaganApp:
        return cast("KaganApp", self.app)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _chat_panel(self) -> ChatPanel | None:
        try:
            return self.query_one("#chat-panel", ChatPanel)
        except NoMatches:
            return None

    def _session_list(self) -> SessionList | None:
        try:
            return self.query_one("#orch-session-list", SessionList)
        except NoMatches:
            return None

    def _focus_input(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-input", Input).focus()

    def _update_breadcrumb(self, text: str) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#orch-breadcrumb", Static).update(text)

    async def _select_orchestrator(self) -> None:
        """Default to orchestrator mode."""
        await self._cancel_sse()
        self._selected_session_id = None
        self._selected_item = None
        self._update_breadcrumb(_ORCHESTRATOR_TITLE)
        await self._load_orchestrator_state()

    async def _select_session(self, item: SessionItem) -> None:
        """Switch the overlay to show the given session."""
        if self._selected_session_id == item.id:
            return

        await self._cancel_sse()
        self._selected_session_id = item.id
        self._selected_item = item

        panel = self._chat_panel()
        if panel is None:
            return

        match item.type:
            case "orchestrator":
                self._update_breadcrumb(item.title)
                await self._load_orchestrator_state()
            case "general":
                self._update_breadcrumb(item.title)
                await self._load_general_state(item)
            case "task":
                role_label = (item.role or "Agent").capitalize()
                self._update_breadcrumb(f"{item.title[:40]} · {role_label}")
                panel.set_mode_title(f"{role_label}")
                panel.set_session_kind(
                    SessionKind.REVIEW if item.role == "reviewer" else SessionKind.DETACHED
                )
                panel.clear_messages()
                await self._replay_task_session(item, panel)
            case _:
                self._update_breadcrumb(item.title)
                panel.clear_messages()
                panel.add_system_message(f"Unknown session type: {item.type}")

    async def _load_orchestrator_state(self) -> None:
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        self._orchestrator_history = self.kagan_app.orchestrator_sessions.active_history()

        panel = self._chat_panel()
        if panel is None:
            return

        panel.styles.dock = "none"
        panel.styles.layer = "default"
        panel.styles.offset = ("0", "0")
        panel.styles.height = "1fr"
        panel.styles.max_height = "1fr"
        panel.set_visible(True)
        panel.set_footer_mode("overlay")
        panel.set_mode_title(_ORCHESTRATOR_TITLE)
        panel.set_session_kind(SessionKind.ORCHESTRATOR)
        panel.hydrate_current_session_history(self._orchestrator_history)
        self._update_breadcrumb(_ORCHESTRATOR_TITLE)

    async def _load_general_state(self, item: SessionItem) -> None:
        panel = self._chat_panel()
        if panel is None:
            return

        history: list[tuple[str, str]] = []
        if item.chat_session_id:
            try:
                pair = await self.kagan_app.core.chat_sessions.get_with_history(
                    item.chat_session_id
                )
                if pair is not None:
                    _chat_session, messages = pair
                    history = [(m.role, m.content) for m in messages]
            except Exception:
                logger.opt(exception=True).debug("_load_general_state failed")

        panel.styles.dock = "none"
        panel.styles.layer = "default"
        panel.styles.offset = ("0", "0")
        panel.styles.height = "1fr"
        panel.styles.max_height = "1fr"
        panel.set_visible(True)
        panel.set_footer_mode("overlay")
        panel.set_mode_title(item.title)
        panel.set_session_kind(SessionKind.ORCHESTRATOR)
        panel.hydrate_current_session_history(history)

    async def _replay_task_session(self, item: SessionItem, panel: ChatPanel) -> None:
        """Replay recent events for a task session (read-only, no live stream)."""
        output = panel.stream_output()
        output.clear()

        task_id = item.task_id
        session_id = item.session_id
        if task_id is None or session_id is None:
            panel.add_system_message("Task session missing task or session id")
            return

        try:
            replay_events = await self.kagan_app.core.tasks.events.list_recent(
                task_id, limit=200, session_id=session_id
            )
        except Exception:
            replay_events = []

        for event in replay_events:
            match event.event_type:
                case "output_chunk":
                    self._render_agent_event(
                        event.event_type, event.payload or {}, output, merge=True
                    )
                case "agent_completed":
                    self._render_agent_event(
                        event.event_type, event.payload or {}, output, merge=True
                    )
                case "agent_failed":
                    self._render_agent_event(
                        event.event_type, event.payload or {}, output, merge=True
                    )
                case _:
                    pass

    async def _cancel_sse(self) -> None:
        if self._sse_task is not None:
            self._sse_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sse_task
            self._sse_task = None

    # ------------------------------------------------------------------
    # Key / event handlers
    # ------------------------------------------------------------------

    def action_handle_esc(self) -> None:
        self.dismiss()

    def action_cycle_agent_next(self) -> None:
        """Ctrl+Down: rotate through sessions."""
        self._cycle_session(direction=1)

    def action_cycle_agent_prev(self) -> None:
        """Ctrl+Up: rotate backwards through sessions."""
        self._cycle_session(direction=-1)

    def _cycle_session(self, *, direction: int) -> None:
        session_list = self._session_list()
        if session_list is None:
            return
        items = list(session_list._items)
        if not items:
            return

        # States: -1=orchestrator, 0=items[0], 1=items[1], …
        current_idx = -1
        if self._selected_session_id is not None:
            for i, item in enumerate(items):
                if item.id == self._selected_session_id:
                    current_idx = i
                    break

        next_idx = (current_idx + direction) % (len(items) + 1)
        if next_idx == -1:
            next_idx = len(items) - 1
        if next_idx == len(items):
            next_idx = -1

        if next_idx == -1:
            self.run_worker(self._select_orchestrator(), exit_on_error=False)
        else:
            item = items[next_idx]
            try:
                lv = session_list.query_one("#session-list", ListView)
                lv.index = next_idx
                lv.focus()
            except Exception:
                pass
            self.run_worker(self._select_session(item), exit_on_error=False)

    def on_session_list_focus_input(self, _: SessionList.FocusInput) -> None:
        self._focus_input()

    def on_session_list_session_selected(self, message: SessionList.SessionSelected) -> None:
        self.run_worker(self._select_session(message.item), exit_on_error=False)

    def on_session_list_session_stop_requested(
        self, message: SessionList.SessionStopRequested
    ) -> None:
        self.run_worker(self._stop_session(message.item), exit_on_error=False)

    def on_session_list_session_close_requested(
        self, message: SessionList.SessionCloseRequested
    ) -> None:
        self.run_worker(self._close_session(message.item), exit_on_error=False)

    async def _stop_session(self, item: SessionItem) -> None:
        if not item.capabilities.can_stop:
            return
        try:
            if item.type == "task" and item.session_id:
                await self.kagan_app.core.tasks.sessions.stop(item.session_id)
            elif item.chat_session_id:
                # Chat sessions don't have a dedicated stop API yet;
                # closing is the closest action.
                pass
        except Exception as exc:
            logger.warning("Failed to stop session {}: {}", item.id, exc)
        session_list = self._session_list()
        if session_list is not None:
            await session_list.refresh_items()

    async def _close_session(self, item: SessionItem) -> None:
        if not item.capabilities.can_close:
            return
        try:
            if item.chat_session_id:
                await self.kagan_app.core.chat_sessions.delete(item.chat_session_id)
            elif item.session_id:
                await self.kagan_app.core.tasks.sessions.stop(item.session_id)
        except Exception as exc:
            logger.warning("Failed to close session {}: {}", item.id, exc)
        session_list = self._session_list()
        if session_list is not None:
            await session_list.refresh_items()

    # Handle chat submit
    def on_chat_panel_submit_requested(self, message: ChatPanel.SubmitRequested) -> None:
        if self._selected_item is not None and self._selected_item.type == "task":
            # Task sessions are read-only in the overlay
            panel = self._chat_panel()
            if panel is not None:
                panel.add_system_message("Task sessions are read-only")
            return

        if self._chat_message_task is not None and not self._chat_message_task.done():
            self._chat_message_task.cancel()

        if self._selected_item is not None and self._selected_item.type == "general":
            self._chat_message_task = asyncio.create_task(
                self._send_general_message(message.text),
                name="orch-overlay-send-general",
            )
            return

        self._chat_message_task = asyncio.create_task(
            self._send_orchestrator_message(message.text),
            name="orch-overlay-send",
        )

    async def _send_general_message(self, text: str) -> None:
        from kagan.core.errors import KaganError

        panel = self._chat_panel()
        if panel is None or self._selected_item is None:
            return

        chat_session_id = self._selected_item.chat_session_id
        if chat_session_id is None:
            panel.add_system_message("No chat session available")
            return

        try:
            await self.kagan_app.core.chat_sessions.append_message(chat_session_id, "user", text)
            panel.add_user_message(text)
            # TODO: wire general chat to an LLM backend for replies
            panel.add_system_message("General chat reply not yet implemented")
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            panel.set_runtime_status("error")
            panel.add_system_message(f"Chat error: {exc}")

    async def _send_orchestrator_message(self, text: str) -> None:
        from kagan.core.errors import KaganError

        panel = self._chat_panel()
        if panel is None:
            return

        try:
            self._orchestrator_history = await send_chat_message(
                core=self.kagan_app.core,
                panel=panel,
                text=text,
                history=self._orchestrator_history,
            )
            await self.kagan_app.orchestrator_sessions.persist_active(
                history=self._orchestrator_history,
                rendered_messages=panel.export_rendered_messages(),
                agent_backend=panel.preferred_agent_backend(),
            )
        except asyncio.CancelledError:
            panel.set_runtime_status("ready")
            raise
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            panel.set_runtime_status("error")
            panel.add_system_message(f"Orchestrator error: {exc}")

    def on_chat_panel_close_requested(self, _: ChatPanel.CloseRequested) -> None:
        self.action_handle_esc()

    def on_key_down(self) -> None:
        """Down arrow from the overlay focuses the session list."""
        try:
            lv = self.query_one("#session-list")
            lv.focus()
        except NoMatches:
            pass

    def _render_agent_event(
        self,
        event_type: str,
        payload: dict,
        output: StreamingOutput,
        *,
        merge: bool,
    ) -> None:
        render_agent_event_to_output(output, present_agent_event(event_type, payload), merge=merge)
