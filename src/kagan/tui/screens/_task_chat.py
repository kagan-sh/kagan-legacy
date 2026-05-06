from __future__ import annotations

import asyncio
import contextlib
from typing import Any, cast

from textual.widgets import Input

from kagan.core.enums import ChatMode, SessionKind, StreamSource
from kagan.core.errors import KaganError
from kagan.tui._chat_helpers import (
    TitleGenerationSession,
    build_session_options,
    kick_title_generation,
    send_task_message,
)
from kagan.tui.orchestrator_sessions import is_orchestrator_session_key
from kagan.tui.screens._chat_runner import (
    TASK_REVIEWER_SESSION_KEY,
    TASK_WORKER_SESSION_KEY,
    send_chat_message,
)
from kagan.tui.widgets.chat import ChatPanel


class _TaskChatMixin:
    _task_id: str | None
    async def action_open_orchestrator_chat(self) -> None:
        panel = self._overlay_panel()
        was_visible = panel.has_class("visible")
        layout_mode = "vertical" if not was_visible else None
        self._configure_overlay_chat(
            visible=True,
            fullscreen=False,
            mode=ChatMode.ORCHESTRATOR,
            layout_mode=layout_mode,
            focus=True,
        )
        await self._load_orchestrator_panel_state(panel)
        self._sync_overlay_layout_class()

    async def action_open_task_overlay(self) -> None:
        panel = self._overlay_panel()
        was_visible = panel.has_class("visible")
        layout_mode = "vertical" if not was_visible else None
        self._configure_overlay_chat(
            visible=True,
            fullscreen=False,
            mode=ChatMode.TASK,
            layout_mode=layout_mode,
            focus=True,
        )
        if self._task_id is not None:
            self._ensure_stream_worker()
        self._sync_overlay_layout_class()

    async def action_open_task_chat(self) -> None:
        panel = self._overlay_panel()
        panel.set_visible(True)
        panel.set_fullscreen(True)
        panel.set_mode_title("Task Chat")
        panel.set_session_kind(SessionKind.DETACHED)
        panel.set_sessions(
            build_session_options(self.kagan_app, self._task_session_options()),
            self._active_task_session_key(),
        )
        if self._task_id is not None:
            panel.set_mode_title(f"Task #{self._task_id[:8]}")
            self._ensure_stream_worker()
        panel.query_one("#chat-overlay-input", Input).focus()
        self._chat_mode = ChatMode.TASK
        self._sync_overlay_layout_class()

    async def action_fullscreen_chat(self) -> None:
        panel = self._overlay_panel()
        if panel.has_class("visible") and panel.has_class("fullscreen"):
            panel.set_visible(False)
            panel.set_fullscreen(False)
            self._overlay_layout_mode = "vertical"
            self._sync_overlay_layout_class()
            return
        if panel.has_class("visible"):
            panel.set_fullscreen(True)
            panel.query_one("#chat-overlay-input", Input).focus()
            self._sync_overlay_layout_class()
            return
        await self._open_chat_from_current_mode(fullscreen=True)

    async def action_expand_chat_overlay(self) -> None:
        panel = self._overlay_panel()
        if not panel.has_class("visible"):
            return
        panel.set_fullscreen(True)
        panel.query_one("#chat-overlay-input", Input).focus()
        self._sync_overlay_layout_class()

    async def action_toggle_chat(self) -> None:
        panel = self._overlay_panel()
        if panel.has_class("visible") and panel.has_class("fullscreen"):
            panel.set_fullscreen(False)
            self._overlay_layout_mode = "vertical"
            panel.query_one("#chat-overlay-input", Input).focus()
            self._sync_overlay_layout_class()
            return
        if not panel.has_class("visible"):
            self._overlay_layout_mode = "vertical"
            await self.action_open_task_overlay()
            return
        if self._overlay_layout_mode == "vertical":
            self._overlay_layout_mode = "horizontal"
            panel.query_one("#chat-overlay-input", Input).focus()
            self._sync_overlay_layout_class()
            return
        panel.set_visible(False)
        panel.set_fullscreen(False)
        self._overlay_layout_mode = "vertical"
        self._sync_overlay_layout_class()

    async def _open_chat_from_current_mode(self, *, fullscreen: bool) -> None:
        if self._chat_mode == ChatMode.ORCHESTRATOR:
            await self.action_open_orchestrator_chat()
            if fullscreen:
                panel = self._overlay_panel()
                panel.set_fullscreen(True)
                panel.query_one("#chat-overlay-input", Input).focus()
                self._sync_overlay_layout_class()
            return
        if fullscreen:
            await self.action_open_task_chat()
            return
        await self.action_open_task_overlay()

    @staticmethod
    def _sender_id(message: Any) -> str:
        sender = cast("Any", getattr(message, "control", getattr(message, "sender", None)))
        sender_id = getattr(sender, "id", "")
        return sender_id if isinstance(sender_id, str) else ""

    async def on_chat_panel_submit_requested(self, message: ChatPanel.SubmitRequested) -> None:
        sender_id = self._sender_id(message)
        if sender_id and sender_id != "ts-chat-overlay":
            return

        if self._chat_message_task is not None and not self._chat_message_task.done():
            self._chat_message_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._chat_message_task

        if self._chat_mode == ChatMode.ORCHESTRATOR:
            self._chat_message_task = asyncio.create_task(
                self._send_orchestrator_message(message.text),
                name="task-screen-orchestrator-send",
            )
            return

        self._chat_message_task = asyncio.create_task(
            self._send_task_message(message.text),
            name="task-screen-task-send",
        )

    def action_cycle_session(self) -> None:
        panel = self._overlay_panel()
        fullscreen = panel.has_class("visible") and panel.has_class("fullscreen")
        next_mode = ChatMode.ORCHESTRATOR if self._chat_mode == ChatMode.TASK else ChatMode.TASK
        self.run_worker(
            self._cycle_chat_session(next_mode=next_mode, fullscreen=fullscreen),
            exit_on_error=False,
        )

    def action_cycle_chat_session(self) -> None:
        self.action_cycle_session()

    async def _cycle_chat_session(self, *, next_mode: str, fullscreen: bool) -> None:
        if next_mode == ChatMode.ORCHESTRATOR:
            await self.action_open_orchestrator_chat()
        elif fullscreen:
            await self.action_open_task_chat()
        else:
            await self.action_open_task_overlay()

        panel = self._overlay_panel()
        panel.set_fullscreen(fullscreen)
        panel.query_one("#chat-overlay-input", Input).focus()
        self._sync_overlay_layout_class()

    def on_chat_panel_session_changed(self, message: ChatPanel.SessionChanged) -> None:
        sender_id = self._sender_id(message)
        if sender_id and sender_id != "ts-chat-overlay":
            return
        if is_orchestrator_session_key(message.key):
            self._chat_mode = ChatMode.ORCHESTRATOR
            self._overlay_panel().set_mode_title("Orchestrator")
            self._chat_orchestrator_history = self.kagan_app.orchestrator_sessions.history_for_key(
                message.key
            )
            self._overlay_panel().hydrate_current_session_history(self._chat_orchestrator_history)
            self._chat_session_switch_token += 1
            token = self._chat_session_switch_token
            self.run_worker(
                self._switch_orchestrator_session(self._overlay_panel(), message.key, token=token),
                exit_on_error=False,
            )
            self._sync_overlay_layout_class()
            return
        self._chat_mode = ChatMode.TASK
        panel = self._overlay_panel()
        panel.set_mode_title(
            f"Task #{self._task_id[:8]}" if self._task_id is not None else "Task Chat"
        )
        panel.set_session_kind(self._chat_session_kind(message.key))
        self._set_stream_source(self._stream_source_for_session_key(message.key))
        self._ensure_stream_worker()
        self._sync_overlay_layout_class()

    def on_chat_panel_new_session_requested(
        self, message: ChatPanel.NewSessionRequested
    ) -> None:
        sender_id = self._sender_id(message)
        if sender_id and sender_id != "ts-chat-overlay":
            return
        panel = self._overlay_panel()
        self.run_worker(self._create_new_orchestrator_session(panel), exit_on_error=False)

    def on_chat_panel_session_picker_requested(
        self, message: ChatPanel.SessionPickerRequested
    ) -> None:
        sender_id = self._sender_id(message)
        if sender_id and sender_id != "ts-chat-overlay":
            return

        panel = self._overlay_panel()
        self._open_overlay_session_picker(panel, initial_query=message.initial_query)

    def on_chat_panel_file_picker_requested(
        self, message: ChatPanel.FilePickerRequested
    ) -> None:
        sender_id = self._sender_id(message)
        if sender_id and sender_id != "ts-chat-overlay":
            return

        panel = self._overlay_panel()
        modal = panel.create_file_picker_modal(initial_query=message.initial_query)
        self.app.push_screen(modal, callback=panel.handle_file_picker_selected)

    def on_chat_panel_agent_picker_requested(
        self, message: ChatPanel.AgentPickerRequested
    ) -> None:
        sender_id = self._sender_id(message)
        if sender_id and sender_id != "ts-chat-overlay":
            return
        panel = self._overlay_panel()

        def _on_agent_selected(selected: str | None) -> None:
            if selected is None:
                return
            panel._agent_hint = selected
            panel.add_system_message(f"Default agent set to {selected}")

        self.app.push_screen("agent-picker-modal", callback=_on_agent_selected)

    def on_chat_panel_close_requested(self, message: ChatPanel.CloseRequested) -> None:
        sender_id = self._sender_id(message)
        if sender_id == "ts-chat-overlay":
            panel = self._overlay_panel()
            panel.set_visible(False)
            panel.set_fullscreen(False)
            self._overlay_layout_mode = "vertical"
            self._sync_overlay_layout_class()
            return

    def on_chat_panel_interrupt_requested(
        self, message: ChatPanel.InterruptRequested
    ) -> None:
        sender_id = self._sender_id(message)
        if sender_id and sender_id != "ts-chat-overlay":
            return
        panel = self._overlay_panel()
        if self._chat_message_task is not None and not self._chat_message_task.done():
            self._chat_message_task.cancel()
            panel.post_message(ChatPanel.InterruptCompleted())
            return

        async def _cancel_and_complete() -> None:
            await self.action_cancel_run()
            panel.post_message(ChatPanel.InterruptCompleted())

        self.run_worker(_cancel_and_complete(), exit_on_error=False)

    async def _send_orchestrator_message(self, text: str) -> None:
        panel = self._overlay_panel()
        should_title = self.kagan_app.orchestrator_sessions.should_generate_title()
        try:
            self._chat_orchestrator_history = await send_chat_message(
                core=self.kagan_app.core,
                panel=panel,
                text=text,
                history=self._chat_orchestrator_history,
            )
            await self.kagan_app.orchestrator_sessions.persist_active(
                history=self._chat_orchestrator_history,
                rendered_messages=panel.export_rendered_messages(),
                agent_backend=panel.preferred_agent_backend(),
            )
            # Auto-generate a session title after the first turn
            if should_title and self._chat_orchestrator_history:
                asyncio.create_task(
                    kick_title_generation(
                        TitleGenerationSession(
                            orchestrator_sessions=self.kagan_app.orchestrator_sessions,
                            panel=panel,
                            user_message=text,
                            history=self._chat_orchestrator_history,
                            session_options=build_session_options(
                                self.kagan_app,
                                self._task_session_options(),
                            ),
                            is_mounted=lambda: self.is_mounted,
                        ),
                        self.kagan_app.core,
                    ),
                    name="task-chat-title-gen",
                )
        except asyncio.CancelledError:
            panel.set_runtime_status("ready")
            panel.set_stream_action("Waiting for prompt", confidence="certain")
            raise
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            panel.set_runtime_status("error")
            panel.set_stream_action("Orchestrator error", confidence="needs-validation")
            panel.add_system_message(f"Orchestrator error: {exc}")

    async def _send_task_message(self, text: str) -> None:
        panel = self._overlay_panel()
        if self._task_id is None:
            panel.add_system_message("No task selected")
            return

        await self.action_cancel_run()

        if self._task_model is None:
            self._task_model = await self.kagan_app.core.tasks.get(self._task_id)

        task_model = self._task_model
        if task_model is None:
            panel.add_system_message("Unable to load task")
            return

        self._task_model = await send_task_message(self.kagan_app.core, task_model, text)

        panel.set_runtime_status("initializing")
        panel.set_stream_action("Restarting task agent...", confidence="assumption")
        self._set_stream_source(StreamSource.WORKER)
        restart_error = await self._start_or_attach_session(
            backend_hint=panel.preferred_agent_backend()
        )
        if restart_error is None:
            return
        panel.set_runtime_status("error")
        panel.set_stream_action("Unable to restart task agent", confidence="needs-validation")
        panel.add_system_message(f"Unable to restart agent: {restart_error}")

    async def _switch_orchestrator_session(
        self,
        panel: ChatPanel,
        key: str,
        *,
        token: int | None = None,
    ) -> None:
        if token is not None and token != self._chat_session_switch_token:
            return
        await self.kagan_app.orchestrator_sessions.persist_active(
            history=self._chat_orchestrator_history,
            rendered_messages=panel.export_rendered_messages(),
            agent_backend=panel.preferred_agent_backend(),
        )
        if token is not None and token != self._chat_session_switch_token:
            return
        await self._load_orchestrator_panel_state(panel, requested_key=key)

    async def _create_new_orchestrator_session(self, panel: ChatPanel) -> None:
        await self.kagan_app.orchestrator_sessions.persist_active(
            history=self._chat_orchestrator_history,
            rendered_messages=panel.export_rendered_messages(),
            agent_backend=panel.preferred_agent_backend(),
        )
        next_key = await self.kagan_app.orchestrator_sessions.create_new(
            agent_backend=panel.preferred_agent_backend()
        )
        await self._load_orchestrator_panel_state(panel, requested_key=next_key)
        panel.add_system_message("New session started.")

    async def _load_orchestrator_panel_state(
        self,
        panel: ChatPanel,
        *,
        requested_key: str | None = None,
    ) -> None:
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        if requested_key is not None and is_orchestrator_session_key(requested_key):
            self._chat_orchestrator_history = await self.kagan_app.orchestrator_sessions.switch(
                requested_key
            )
        else:
            self._chat_orchestrator_history = self.kagan_app.orchestrator_sessions.active_history()

        active_key = self.kagan_app.orchestrator_sessions.active_key()
        panel.set_sessions(
            build_session_options(self.kagan_app, self._task_session_options()),
            active_key,
        )
        panel.hydrate_current_session_history(self._chat_orchestrator_history)
        session_backend = self.kagan_app.orchestrator_sessions.agent_backend_for_key(active_key)
        if session_backend is not None:
            panel.set_preferred_agent_backend(session_backend)

    def _task_session_options(self) -> list[tuple[str, str]]:
        return [
            ("Task", TASK_WORKER_SESSION_KEY),
            ("Review", TASK_REVIEWER_SESSION_KEY),
        ]

    def _active_task_session_key(self) -> str:
        source = self._effective_stream_source()
        if source == StreamSource.REVIEWER:
            return TASK_REVIEWER_SESSION_KEY
        return TASK_WORKER_SESSION_KEY

    @staticmethod
    def _stream_source_for_session_key(key: str) -> str | None:
        normalized = key.casefold()
        if "review" in normalized:
            return StreamSource.REVIEWER
        if "task" in normalized or "worker" in normalized:
            return StreamSource.WORKER
        return None

    @staticmethod
    def _chat_session_kind(key: str) -> str:
        return SessionKind.REVIEW if "review" in key.casefold() else SessionKind.DETACHED
