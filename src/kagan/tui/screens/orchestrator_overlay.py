"""OrchestratorOverlay — app-level modal overlay for orchestrator + agent chat.

Bound globally to ``o`` (and ``ctrl+space``).  Mirrors Claude Code's
"background agents — ↓ to manage" UX.

State machine
-------------
- ORCHESTRATOR mode  : talks to the project's orchestrator ChatSession.
- ATTACHED mode      : re-streams a worker/reviewer agent Session via
                       GET /api/v1/sessions/{id}/replay and
                       SSE /api/v1/sessions/{id}/events.

ESC behaviour
-------------
- While ATTACHED  → detach back to ORCHESTRATOR (first Esc).
- While ORCHESTRATOR → close overlay (second Esc).
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, cast

from loguru import logger
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.screen import ModalScreen
from textual.widgets import Input, Static

from kagan.core.enums import SessionKind
from kagan.tui.keybindings import ORCHESTRATOR_OVERLAY_BINDINGS
from kagan.tui.screens._chat_runner import (
    send_chat_message,
)
from kagan.tui.widgets.chat import ChatPanel
from kagan.tui.widgets.running_agents_bar import RunningAgentsBar

if TYPE_CHECKING:
    from textual.app import ComposeResult

    from kagan.tui.app import KaganApp

_ORCHESTRATOR_TITLE = "Orchestrator"


class OrchestratorOverlay(ModalScreen[None]):
    """App-level orchestrator/agent chat overlay.

    Parameters
    ----------
    task_id:
        If set and no active session exists, the overlay pre-fills the chat
        input with ``@task:<id> `` so the user has context.
    poll_interval:
        Agents-bar poll interval.  Set to 0 in tests.
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
        height: 1;
        width: 100%;
        padding: 0 1;
        background: $surface;
        color: $text-muted;
        border-bottom: solid $border;
        overflow: hidden;
        text-overflow: ellipsis;
    }
    #orch-chat {
        height: 1fr;
        width: 100%;
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

        # Track attach state
        self._attached_session_id: str | None = None
        self._attached_role: str | None = None
        self._attached_task_id: str | None = None

        # Orchestrator history
        self._orchestrator_history: list[tuple[str, str]] = []

        # Stream worker for attached mode
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
            yield ChatPanel(id="orch-chat", classes="")
            yield RunningAgentsBar(
                id="orch-agents-bar",
                on_select=self._on_agent_selected,
                poll_interval=self._poll_interval,
            )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def on_mount(self) -> None:
        await self._load_orchestrator_state()

        # Pre-fill @task:<id> prefix if provided
        if self._task_id is not None and self._attached_session_id is None:
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

    async def attach(
        self,
        session_id: str | None,
        role: str | None = None,
        task_id: str | None = None,
    ) -> None:
        """Switch between orchestrator mode and an agent session.

        Pass ``session_id=None`` to return to orchestrator mode.
        """
        if session_id == self._attached_session_id:
            return

        # Cancel any running SSE worker
        await self._cancel_sse()

        self._attached_session_id = session_id
        self._attached_role = role
        self._attached_task_id = task_id

        panel = self._chat_panel()
        if panel is None:
            return

        if session_id is None:
            # Return to orchestrator mode
            self._update_breadcrumb(_ORCHESTRATOR_TITLE)
            await self._load_orchestrator_state()
            return

        # Attach to agent session
        await self._do_attach(session_id, role, task_id, panel)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _chat_panel(self) -> ChatPanel | None:
        try:
            return self.query_one("#orch-chat", ChatPanel)
        except NoMatches:
            return None

    def _focus_input(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#chat-overlay-input", Input).focus()

    def _update_breadcrumb(self, text: str) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#orch-breadcrumb", Static).update(text)

    async def _load_orchestrator_state(self) -> None:
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        self._orchestrator_history = self.kagan_app.orchestrator_sessions.active_history()

        panel = self._chat_panel()
        if panel is None:
            return

        panel.set_mode_title(_ORCHESTRATOR_TITLE)
        panel.set_session_kind(SessionKind.ORCHESTRATOR)
        panel.hydrate_current_session_history(self._orchestrator_history)
        self._update_breadcrumb(_ORCHESTRATOR_TITLE)

    async def _do_attach(
        self, session_id: str, role: str | None, task_id: str | None, panel: ChatPanel
    ) -> None:
        """Wire the panel to an agent session."""
        # Persist attach state in the DB
        with contextlib.suppress(Exception):
            active_key = self.kagan_app.orchestrator_sessions.active_key()
            if active_key:
                await self.kagan_app.core.attach_chat(active_key, session_id, agent_role=role)

        # Clear existing messages
        panel.clear_messages()

        # Update breadcrumb
        role_label = (role or "Agent").capitalize()
        self._update_breadcrumb(f"{role_label} · attached")
        panel.set_mode_title(f"{role_label} · attached")

        # Subscribe to agent session events
        self._sse_task = asyncio.create_task(
            self._stream_agent_session(session_id, task_id, panel),
            name=f"orch-overlay-sse-{session_id[:8]}",
        )

    async def _stream_agent_session(
        self, session_id: str, task_id: str | None, panel: ChatPanel
    ) -> None:
        """Stream events from an agent Session into the panel.

        Replays recent events then subscribes to new ones.  Uses the core
        task-event stream filtered by session_id.  task_id is needed for the
        stream subscription; if unknown we skip the live tail.
        """
        from kagan.tui.screens._chat_runner import (
            stream_chunk_kind,
            stream_chunk_text,
        )
        from kagan.tui.widgets.streaming import UserInputWidget

        output = panel.stream_output()
        output.clear()

        # Replay: list_recent with session_id filter (needs task_id from DB)
        # First resolve task_id if not supplied
        resolved_task_id = task_id
        if resolved_task_id is None:
            try:
                rows = await self.kagan_app.core.list_running_agents()
                match_row = next((r for r in rows if r.session_id == session_id), None)
                if match_row is not None:
                    resolved_task_id = match_row.task_id
            except Exception:
                pass

        if resolved_task_id is not None:
            try:
                replay_events = await self.kagan_app.core.tasks.events.list_recent(
                    resolved_task_id, limit=200, session_id=session_id
                )
            except Exception:
                replay_events = []

            for event in replay_events:
                payload = event.payload or {}
                match event.event_type:
                    case "output_chunk":
                        text = stream_chunk_text(payload)
                        kind = stream_chunk_kind(payload)
                        if text and kind in {"assistant", "thought", "note", "user"}:
                            if kind == "user":
                                output.append_widget(UserInputWidget(text))
                            else:
                                output.append_chunk(text, kind=kind, merge=True)
                    case "agent_completed":
                        output.post_note("Agent completed")
                    case "agent_failed":
                        output.post_note(stream_chunk_text(payload) or "Agent failed")
                    case _:
                        pass

            # Live stream — filter by session_id
            # TODO: Replace with server SSE GET /api/v1/sessions/{id}/events once
            #       a TUI-side HTTP streaming helper is available.  For now we use
            #       the core task event stream with session_id filtering.
            try:
                async for event in self.kagan_app.core.tasks.events.stream(
                    resolved_task_id, replay=False
                ):
                    if event.session_id != session_id:
                        continue
                    payload = event.payload or {}
                    match event.event_type:
                        case "output_chunk":
                            text = stream_chunk_text(payload)
                            kind = stream_chunk_kind(payload)
                            if text and kind in {"assistant", "thought", "note", "user"}:
                                if kind == "user":
                                    output.append_widget(UserInputWidget(text))
                                else:
                                    output.append_chunk(text, kind=kind)
                        case "agent_completed":
                            role_label = (self._attached_role or "Agent").capitalize()
                            self._update_breadcrumb(f"{role_label} · done")
                            output.post_note("Agent completed")
                            break
                        case "agent_failed":
                            role_label = (self._attached_role or "Agent").capitalize()
                            self._update_breadcrumb(f"{role_label} · failed")
                            output.post_note(stream_chunk_text(payload) or "Agent failed")
                            break
                        case _:
                            pass
            except asyncio.CancelledError:
                raise
            except Exception:
                output.post_note("Stream ended")

    async def _cancel_sse(self) -> None:
        if self._sse_task is not None:
            self._sse_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sse_task
            self._sse_task = None

    def _on_agent_selected(self, session_id: str, role: str | None, task_id: str) -> None:
        self.run_worker(self.attach(session_id, role, task_id=task_id), exit_on_error=False)

    # ------------------------------------------------------------------
    # Key / event handlers
    # ------------------------------------------------------------------

    def action_handle_esc(self) -> None:
        if self._attached_session_id is not None:
            # First Esc: detach back to orchestrator
            self.run_worker(self.attach(None), exit_on_error=False)
        else:
            # Second Esc: close overlay
            self.dismiss()

    def on_running_agents_bar_focus_input(self, _: RunningAgentsBar.FocusInput) -> None:
        self._focus_input()

    def on_running_agents_bar_agent_selected(self, message: RunningAgentsBar.AgentSelected) -> None:
        self._on_agent_selected(message.session_id, message.agent_role, message.task_id)

    # Handle chat submit
    def on_chat_panel_submit_requested(self, message: ChatPanel.SubmitRequested) -> None:
        if self._attached_session_id is not None:
            # Route to the attached agent session instead of the orchestrator.
            if self._chat_message_task is not None and not self._chat_message_task.done():
                self._chat_message_task.cancel()
            self._chat_message_task = asyncio.create_task(
                self._send_attached_message(self._attached_session_id, message.text),
                name="orch-overlay-send-attached",
            )
            return

        if self._chat_message_task is not None and not self._chat_message_task.done():
            self._chat_message_task.cancel()

        self._chat_message_task = asyncio.create_task(
            self._send_orchestrator_message(message.text),
            name="orch-overlay-send",
        )

    async def _send_attached_message(self, session_id: str, text: str) -> None:
        """Route a typed message to the attached agent session.

        Injects the text as a user-turn event into the agent's event stream so
        it is visible in the live overlay and any future replay.  If the session
        has already finished, shows an inline notice instead.
        """
        from kagan.core.errors import KaganError

        panel = self._chat_panel()
        try:
            await self.kagan_app.core.send_message_to_session(session_id, text)
        except KaganError as exc:
            # Session no longer accepts input (e.g. COMPLETED or FAILED).
            role_label = (self._attached_role or "Agent").capitalize()
            notice = f"{role_label} session has finished — Esc to detach"
            if panel:
                panel.add_system_message(notice)
            logger.debug("send_attached_message rejected: {}", exc)
        except Exception as exc:
            if panel:
                panel.add_system_message(f"Send error: {exc}")
            logger.opt(exception=True).warning("_send_attached_message failed")

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
        """Down arrow from the overlay focuses the agents bar."""
        try:
            lv = self.query_one("#agents-list")
            lv.focus()
        except NoMatches:
            pass
