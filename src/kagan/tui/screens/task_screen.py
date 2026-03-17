from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, Any, cast

from textual import events, on
from textual.containers import Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.screen import Screen
from textual.widgets import (
    Checkbox,
    Input,
    Label,
    Select,
    Static,
    TabbedContent,
    TabPane,
    TextArea,
)

from kagan.core import git
from kagan.core.enums import SessionEventType, TaskStatus
from kagan.core.errors import (
    KaganError,
    MergeConflictError,
    NotFoundError,
    PreflightError,
    SessionError,
    WorktreeError,
)
from kagan.tui._chat_helpers import (
    TitleGenerationSession,
    build_session_options,
    kick_title_generation,
    send_task_message,
)
from kagan.tui.keybindings import TASK_SCREEN_BINDINGS
from kagan.tui.orchestrator_sessions import is_orchestrator_session_key
from kagan.tui.screens.confirm import ConfirmModal
from kagan.tui.screens.kanban_chat import (
    acp_payload,
    stream_chunk_kind,
    stream_chunk_text,
    tool_call_args,
    tool_call_id,
    tool_call_kind,
    tool_call_result,
    tool_call_status,
    tool_call_title,
)
from kagan.tui.screens.kanban_chat import (
    send_orchestrator_message as send_chat_message,
)
from kagan.tui.screens.rejection_input import RejectionInputModal
from kagan.tui.screens.task_commands import TaskScreenCommandProvider
from kagan.tui.widgets.chat import ChatPanel
from kagan.tui.widgets.diff import DiffFileTree
from kagan.tui.widgets.header import KaganHeader
from kagan.tui.widgets.streaming import OutputChunk, StreamingOutput, ToolCallView, UserInputWidget
from kagan.tui.widgets.task_action_bar import TaskActionBar
from kagan.tui.widgets.task_detail_pane import TaskDetailPane
from kagan.tui.widgets.task_diff_pane import TaskDiffPane
from kagan.tui.widgets.task_event_handler import TaskEventHandler
from kagan.tui.widgets.task_review_helpers import (
    build_merge_readiness_text,
    render_ai_verdict_summary,
    render_criteria_checkboxes,
)
from kagan.tui.widgets.task_workspace_helpers import (
    diff_totals,
    hydrate_workspace_panels,
    merged_commit_diff_fallback,
    resolve_latest_merge_event,
)

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer
    from textual.widget import Widget

    from kagan.core.models import Task
    from kagan.tui.app import KaganApp


TASK_WORKER_SESSION_KEY = "task-worker"
TASK_REVIEWER_SESSION_KEY = "task-reviewer"
TASK_SCREEN_REPLAY_EVENT_LIMIT = 400


class TaskScreen(Screen[None]):
    BINDINGS = TASK_SCREEN_BINDINGS
    COMMANDS = {TaskScreenCommandProvider}

    def __init__(self, task_id: str | None = None) -> None:
        super().__init__(id="task-screen")
        self._task_id = task_id
        self._task_model: Task | None = None
        self._running = False
        self._status_override: str | None = None
        self._stream_task: asyncio.Task[None] | None = None
        self._runtime_poll_timer: Timer | None = None
        self._stream_refresh_timer: Timer | None = None
        self._pending_runtime_refresh = False
        self._pending_workspace_refresh = False
        self._pending_review_refresh = False
        self._simulated_session = False
        self._chat_mode = "task"
        self._overlay_layout_mode = "vertical"
        self._chat_orchestrator_history: list[tuple[str, str]] = []
        self._chat_session_switch_token = 0
        self._chat_message_task: asyncio.Task[None] | None = None
        self._review_criteria_signature: tuple[str, ...] | None = None
        self._review_file_entries_signature: tuple[tuple[str, int, int], ...] | None = None
        self._stream_source: str | None = None
        self._last_merge_blocker: str | None = None
        self._oldest_event_ts: str | None = None
        self._replay_count: int = 0
        self._worker_session_id: str | None = None
        self._reviewer_session_id: str | None = None
        self._pending_reviewer_session_id = False

    @property
    def kagan_app(self) -> KaganApp:
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        yield KaganHeader()
        with Vertical(id="task-screen-root"):
            yield Label("Task", id="ts-title", classes="ts-title")
            yield Label("Branch: -", id="ts-branch", classes="ts-branch")
            yield Label("Idle", id="ts-status", classes="ts-status")

            with TabbedContent(id="ts-tabs", initial="detail"):
                with TabPane("Detail", id="detail"):
                    yield TaskDetailPane(id="ts-overview-pane")

                with TabPane("Diff", id="diff"):
                    yield TaskDiffPane(id="ts-diff-pane")

            yield ChatPanel(id="ts-chat-overlay", classes="chat-overlay")

        yield TaskActionBar(id="ts-actions")

    async def on_mount(self) -> None:
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        if self._task_id is None:
            app_task_id = getattr(self.kagan_app, "_active_task_id", None)
            self._task_id = app_task_id if isinstance(app_task_id, str) else None

        if self._task_id is None:
            self._configure_overlay_chat()
            self._refresh_header()
            self._refresh_header_labels()
            self._set_status("Idle")
            self._select_initial_tab()
            self._sync_action_bar()
            self._sync_overlay_layout_class()
            self._sync_stream_source_indicator()
            self.run_worker(
                self._refresh_header_context(),
                group="task-screen-header-context",
                exclusive=True,
                exit_on_error=False,
            )
            self.call_after_refresh(self.refresh_bindings)
            return

        with contextlib.suppress(NotFoundError):
            self._task_model = await self.kagan_app.core.tasks.get(self._task_id)
        self._configure_overlay_chat()
        self._refresh_header()
        self._refresh_header_labels()
        self._select_initial_tab()
        await self._hydrate_workspace_panels()
        await self._load_review_context()
        self._ensure_stream_worker()
        self._sync_action_bar()
        self._sync_overlay_layout_class()
        self.run_worker(
            self._refresh_header_context(),
            group="task-screen-header-context",
            exclusive=True,
            exit_on_error=False,
        )
        self.query_one("#ts-overview-scroll", VerticalScroll).focus()
        self.call_after_refresh(self.refresh_bindings)

        if self._task_model is not None and self._task_model.status is TaskStatus.IN_PROGRESS:
            self._running = True
            self.call_after_refresh(
                lambda: self.run_worker(self.action_open_task_overlay(), exit_on_error=False)
            )
        self._sync_stream_source_indicator()
        self._runtime_poll_timer = self.set_interval(1.0, self._schedule_runtime_refresh)

    def on_unmount(self) -> None:
        if self._stream_task is not None:
            self._stream_task.cancel()
            self._stream_task = None
        if self._runtime_poll_timer is not None:
            self._runtime_poll_timer.stop()
            self._runtime_poll_timer = None
        if self._stream_refresh_timer is not None:
            self._stream_refresh_timer.stop()
            self._stream_refresh_timer = None
        self._pending_runtime_refresh = False
        self._pending_workspace_refresh = False
        self._pending_review_refresh = False

    def on_show(self) -> None:
        self._sync_overlay_layout_class()
        self._sync_action_bar()
        self.refresh_bindings()

    def action_back(self) -> None:
        panel = self._overlay_panel()
        # If chat overlay is fullscreen, exit fullscreen first (same as split-cycle shortcut)
        if panel.has_class("visible") and panel.has_class("fullscreen"):
            panel.set_fullscreen(False)
            self._overlay_layout_mode = "vertical"
            self._sync_overlay_layout_class()
            return
        # If chat overlay is visible (not fullscreen), close it
        if panel.has_class("visible"):
            panel.set_visible(False)
            panel.set_fullscreen(False)
            self._overlay_layout_mode = "vertical"
            self._sync_overlay_layout_class()
            return
        # Otherwise, go back to kanban
        self.app.pop_screen()

    def action_tab_detail(self) -> None:
        self._switch_tab("detail")

    def action_tab_diff(self) -> None:
        self._switch_tab("diff")

    def action_tab_overview(self) -> None:
        self.action_tab_detail()

    def action_tab_changes(self) -> None:
        self.action_tab_diff()

    def _switch_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#ts-tabs", TabbedContent)
        self.set_focus(None)
        tabs.active = tab_id
        self.call_after_refresh(lambda: self._focus_tab_after_switch(tab_id))
        self._sync_action_bar()
        self.refresh_bindings()

    def action_switch_tab(self, tab_id: str) -> None:
        self._switch_tab(tab_id)

    def on_tabbed_content_tab_activated(self) -> None:
        self._sync_action_bar()
        self.refresh_bindings()
        if self._active_tab() == "diff":
            self._schedule_runtime_refresh()

    def _focus_tab_after_switch(self, tab_id: str) -> None:
        if tab_id == "diff":
            with contextlib.suppress(NoMatches):
                self.set_focus(self.query_one(DiffFileTree))
                return

        if tab_id == "detail":
            for node in self.query(".ts-detail-criterion"):
                if isinstance(node, Checkbox):
                    self.set_focus(node)
                    return

    async def action_primary_action(self) -> None:
        if self._overlay_panel().has_class("visible") and self._focused_widget_accepts_text():
            return

        task = self._task_model

        def _approve_or_merge() -> None:
            if task is not None and task.review_approved:
                self.action_merge()
            else:
                self.action_approve()

        active = self._active_tab()
        if active == "detail":
            if task is not None and task.status is TaskStatus.REVIEW:
                _approve_or_merge()
                return
            self._switch_tab("diff")
            if self._running:
                self._set_status("Running")
                return
            self._running = True
            self._set_stream_source("worker")
            self._set_status("Running")
            self._output_stream().append_text("[started]")
            await self._start_or_attach_session()
            return

        if active == "diff":
            _approve_or_merge()
            return

        if task is not None and task.status is TaskStatus.REVIEW:
            _approve_or_merge()
            return
        if self._running:
            self._set_status("Running")
            return
        self._running = True
        self._set_stream_source("worker")
        self._set_status("Running")
        self._output_stream().append_text("[started]")
        await self._start_or_attach_session()

    async def action_cancel_run(self) -> None:
        self._running = False
        self._set_status("Stopped")
        self._output_stream().append_text("[stopped]")
        if self._task_id is not None and not self._simulated_session:
            with contextlib.suppress(KaganError, OSError, RuntimeError):
                await self.kagan_app.core.tasks.cancel(self._task_id)

    def action_edit_task(self) -> None:
        self.run_worker(self._edit_task_flow(), exit_on_error=False)

    async def _edit_task_flow(self) -> None:
        if self._task_id is None:
            return
        if self._task_model is None:
            with contextlib.suppress(NotFoundError):
                self._task_model = await self.kagan_app.core.tasks.get(self._task_id)
        if self._task_model is None:
            return

        from kagan.tui.screens.task_editor_modal import TaskEditorModal

        await self.app.push_screen_wait(TaskEditorModal(task=self._task_model))
        await self._refresh_runtime_state()

    def action_delete_task(self) -> None:
        self.run_worker(self._delete_task_flow(), exit_on_error=False)

    async def _delete_task_flow(self) -> None:
        if self._task_id is None:
            return
        if self._task_model is None:
            with contextlib.suppress(NotFoundError):
                self._task_model = await self.kagan_app.core.tasks.get(self._task_id)
        task = self._task_model
        if task is None:
            return

        from kagan.tui.screens.task_editor_modal import TaskDeleteConfirmModal

        worktree = await self.kagan_app.core.worktrees.get(task.id)
        confirmed = await self.app.push_screen_wait(
            TaskDeleteConfirmModal(
                task,
                has_worktree=worktree is not None,
                has_active_session=False,
            )
        )
        if confirmed is not True:
            return
        await self.kagan_app.core.tasks.delete(task.id)
        self.action_back()

    async def action_open_orchestrator_chat(self) -> None:
        panel = self._overlay_panel()
        was_visible = panel.has_class("visible")
        layout_mode = "vertical" if not was_visible else None
        self._configure_overlay_chat(
            visible=True,
            fullscreen=False,
            mode="orchestrator",
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
            mode="task",
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
        panel.set_session_kind("auto")
        panel.set_sessions(
            build_session_options(self.kagan_app, self._task_session_options()),
            self._active_task_session_key(),
        )
        if self._task_id is not None:
            panel.set_mode_title(f"Task #{self._task_id[:8]}")
            self._ensure_stream_worker()
        panel.query_one("#chat-overlay-input", Input).focus()
        self._chat_mode = "task"
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
        if self._chat_mode == "orchestrator":
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

        if self._chat_mode == "orchestrator":
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
        next_mode = "orchestrator" if self._chat_mode == "task" else "task"
        self.run_worker(
            self._cycle_chat_session(next_mode=next_mode, fullscreen=fullscreen),
            exit_on_error=False,
        )

    def action_cycle_chat_session(self) -> None:
        self.action_cycle_session()

    async def _cycle_chat_session(self, *, next_mode: str, fullscreen: bool) -> None:
        if next_mode == "orchestrator":
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
            self._chat_mode = "orchestrator"
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
        self._chat_mode = "task"
        panel = self._overlay_panel()
        panel.set_mode_title(
            f"Task #{self._task_id[:8]}" if self._task_id is not None else "Task Chat"
        )
        panel.set_session_kind(self._chat_session_kind(message.key))
        self._set_stream_source(self._stream_source_for_session_key(message.key))
        self._ensure_stream_worker()
        self._sync_overlay_layout_class()

    def on_chat_panel_new_session_requested(self, message: ChatPanel.NewSessionRequested) -> None:
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

    def on_chat_panel_agent_picker_requested(self, message: ChatPanel.AgentPickerRequested) -> None:
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

    def on_chat_panel_interrupt_requested(self, message: ChatPanel.InterruptRequested) -> None:
        sender_id = self._sender_id(message)
        if sender_id and sender_id != "ts-chat-overlay":
            return
        if self._chat_message_task is not None and not self._chat_message_task.done():
            self._chat_message_task.cancel()
            return
        self.run_worker(self.action_cancel_run(), exit_on_error=False)

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
        self._set_stream_source("worker")
        restart_error = await self._start_or_attach_session(
            backend_hint=panel.preferred_agent_backend()
        )
        if restart_error is None:
            return
        panel.set_runtime_status("error")
        panel.set_stream_action("Unable to restart task agent", confidence="needs-validation")
        panel.add_system_message(f"Unable to restart agent: {restart_error}")

    async def _start_or_attach_session(self, *, backend_hint: str | None = None) -> str | None:
        if self._effective_stream_source() == "worker":
            self._worker_session_id = None
            self._pending_reviewer_session_id = False
        if self._task_id is None:
            self._simulated_session = True
            self._output_stream().post_note("No task selected; running simulated output")
            return "No task selected"

        if self._task_model is None:
            self._task_model = await self.kagan_app.core.tasks.get(self._task_id)

        backend = backend_hint or await self._resolve_backend(self._task_model)
        try:
            await self._ensure_workspace()
            await self.kagan_app.core.tasks.run(self._task_id, agent_backend=backend)
            self._simulated_session = False
            self._output_stream().post_note(f"Session started with backend: {backend}")
            self._ensure_stream_worker()
            self._sync_stream_source_indicator()
            return None
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            self._simulated_session = True
            self._output_stream().post_note(f"Session unavailable, using local simulation: {exc}")
            self._sync_stream_source_indicator()
            return str(exc)

    async def _ensure_workspace(self) -> None:
        if self._task_id is None:
            return
        workspace = await self.kagan_app.core.worktrees.get(self._task_id)
        if workspace is None:
            await self.kagan_app.core.worktrees.create(self._task_id)

    async def _resolve_backend(self, task: Task) -> str:
        if task.agent_backend:
            return task.agent_backend
        settings = await self.kagan_app.core.settings.get()
        return settings.get("default_agent_backend") or "claude-code"

    async def _hydrate_workspace_panels(self) -> None:
        await hydrate_workspace_panels(
            task_id=self._task_id,
            active_tab=self._active_tab(),
            diff_pane=self.query_one(TaskDiffPane),
            get_workspace=self.kagan_app.core.worktrees.get,
            get_workspace_diff=self.kagan_app.core.worktrees.diff,
            get_workspace_stats=self.kagan_app.core.worktrees.diff_stats,
            resolve_merged_fallback=self._resolve_merged_commit_diff_fallback,
        )

    async def _resolve_merged_commit_diff_fallback(
        self,
    ) -> tuple[str, dict[str, int], str, str, str] | None:
        if self._task_id is None:
            return None
        return await merged_commit_diff_fallback(
            task_id=self._task_id,
            task=self._task_model,
            get_task=self.kagan_app.core.tasks.get,
            latest_merge_event=lambda task_id: resolve_latest_merge_event(
                self.kagan_app.core.tasks.events,
                task_id,
            ),
            resolve_repo_path=self._task_repo_path,
        )

    async def _task_repo_path(self, project_id: str) -> tuple[str | None, str]:
        from kagan.core.errors import KaganError

        try:
            repo = await self.kagan_app.core.projects.resolve_repo(
                project_id,
                selected_repo_id=self.kagan_app.selected_repo_id,
            )
        except KaganError:
            return None, "main"
        return repo.path, repo.default_branch

    def _ensure_stream_worker(self) -> None:
        if self._stream_task is not None and not self._stream_task.done():
            return
        if self._task_id is None:
            return
        self._stream_task = asyncio.create_task(self._stream_events(self._task_id))

    async def _stream_events(self, task_id: str) -> None:
        output = self._output_stream()
        overlay_chat = self._overlay_panel()
        detail_pane = self.query_one(TaskDetailPane)
        event_handler = TaskEventHandler(
            output=output,
            overlay_chat=overlay_chat,
            is_task_chat_mode=lambda: self._chat_mode == "task",
            active_session_id=self._active_stream_session_id,
            payload_text=self._payload_text,
            queue_refresh=self._queue_stream_refresh,
            set_running=self._set_running,
            set_status=self._set_status,
            set_usage=lambda context_used, context_size, cost_amount, cost_currency: (
                detail_pane.agent_status_panel.set_usage_info(
                    context_used, context_size, cost_amount, cost_currency
                )
            ),
        )
        self._replay_count = 0
        self._oldest_event_ts = None
        try:
            async for event in self.kagan_app.core.tasks.events.stream(
                task_id,
                replay_limit=TASK_SCREEN_REPLAY_EVENT_LIMIT,
            ):
                self._replay_count += 1
                if self._oldest_event_ts is None and event.created_at:
                    from kagan.wire.models import utc_iso

                    self._oldest_event_ts = utc_iso(event.created_at)
                if self._replay_count == TASK_SCREEN_REPLAY_EVENT_LIMIT:
                    output.show_load_more_bar()
                self._track_session_event(event.event_type, event.session_id)
                active_session_id = self._active_stream_session_id()
                if event.session_id and active_session_id and event.session_id != active_session_id:
                    continue
                payload = event.payload or {}
                handler = event_handler.event_handlers.get(event.event_type)
                if handler is not None:
                    handler(payload, event.session_id)
                if self._should_refresh_after_event(event.event_type):
                    self._queue_stream_refresh(workspace=True, review=True)
        except asyncio.CancelledError:
            pass
        except (KaganError, NoMatches, AttributeError, OSError, RuntimeError) as exc:
            self._running = False
            self._set_status("Failed")
            output.post_note(f"Stream ended unexpectedly: {exc}")

    def _set_running(self, running: bool) -> None:
        self._running = running

    @staticmethod
    def _should_refresh_after_event(event_type: SessionEventType) -> bool:
        return event_type in {
            SessionEventType.OUTPUT_CHUNK,
            SessionEventType.TOOL_CALL_START,
            SessionEventType.TOOL_CALL_UPDATE,
            SessionEventType.CRITERION_VERDICT,
            SessionEventType.AGENT_COMPLETED,
            SessionEventType.AGENT_FAILED,
            SessionEventType.TASK_STATUS_CHANGED,
            SessionEventType.AUTO_REVIEW_STARTED,
        }

    def _output_stream(self) -> StreamingOutput:
        return self._overlay_panel().stream_output()

    def _active_stream_session_id(self) -> str | None:
        source = self._effective_stream_source()
        if source == "reviewer":
            return self._reviewer_session_id
        return self._worker_session_id

    def _track_session_event(
        self, event_type: SessionEventType, event_session_id: str | None
    ) -> None:
        if event_type is SessionEventType.AUTO_REVIEW_STARTED:
            self._pending_reviewer_session_id = True
            return
        if event_session_id is None:
            return
        if self._pending_reviewer_session_id:
            self._reviewer_session_id = event_session_id
            self._pending_reviewer_session_id = False
            return
        if self._effective_stream_source() == "reviewer" and self._reviewer_session_id is None:
            self._reviewer_session_id = event_session_id
            return
        if self._worker_session_id is None:
            self._worker_session_id = event_session_id
            return
        if self._worker_session_id != event_session_id and self._reviewer_session_id is None:
            self._reviewer_session_id = event_session_id

    @on(StreamingOutput.LoadMore)
    async def _on_load_more(self) -> None:
        if self._task_id is None or self._oldest_event_ts is None:
            return
        output = self._output_stream()
        output.hide_load_more_bar()

        older_events = await self.kagan_app.core.tasks.events.list_before(
            self._task_id,
            before=self._oldest_event_ts,
            limit=200,
        )
        if not older_events:
            return

        if older_events[0].created_at:
            from kagan.wire.models import utc_iso

            self._oldest_event_ts = utc_iso(older_events[0].created_at) or self._oldest_event_ts

        active_session_id = self._active_stream_session_id()
        widgets: list[Widget] = []
        filtered_events = [
            event
            for event in older_events
            if not (
                event.session_id and active_session_id and event.session_id != active_session_id
            )
        ]
        for event in filtered_events:
            payload = event.payload or {}
            match event.event_type:
                case SessionEventType.OUTPUT_CHUNK:
                    text = stream_chunk_text(payload)
                    kind = stream_chunk_kind(payload)
                    if text and kind in {"assistant", "thought", "note", "user"}:
                        if kind == "user":
                            widgets.append(UserInputWidget(text))
                        else:
                            widgets.append(OutputChunk(text, kind=kind))
                case SessionEventType.TOOL_CALL_START:
                    widgets.append(
                        ToolCallView(
                            tool_call_title(payload),
                            status=tool_call_status(payload, default="running"),
                            args=tool_call_args(payload),
                            result=tool_call_result(payload),
                            tool_id=tool_call_id(payload),
                            kind=tool_call_kind(payload),
                        )
                    )
                case SessionEventType.AGENT_COMPLETED:
                    widgets.append(OutputChunk("Agent completed", kind="note"))
                case SessionEventType.AGENT_FAILED:
                    widgets.append(
                        OutputChunk(stream_chunk_text(payload) or "Agent failed", kind="note")
                    )
                case SessionEventType.TASK_STATUS_CHANGED:
                    widgets.append(
                        OutputChunk(
                            stream_chunk_text(payload) or "Task status changed", kind="note"
                        )
                    )
                case _:
                    continue

        if widgets:
            output.prepend_widgets(widgets)

        if len(filtered_events) >= 200:
            output.show_load_more_bar()

    def _payload_text(self, payload: Any) -> str:
        if payload is None:
            return ""
        if isinstance(payload, str):
            return payload
        if isinstance(payload, dict):
            text = stream_chunk_text(payload)
            if text:
                return text
            nested = acp_payload(payload)
            if nested:
                if "title" in nested:
                    return str(nested["title"])
                if "status" in nested and "sessionUpdate" in nested:
                    return str(nested["status"])
            if "message" in payload:
                return str(payload["message"])
            pieces = [f"{key}={value}" for key, value in payload.items()]
            return " ".join(pieces)
        return str(payload)

    def _set_status(self, value: str) -> None:
        self._status_override = value
        self.query_one("#ts-status", Static).update(value)
        with contextlib.suppress(NoMatches):
            self.query_one("#ts-detail-status", Static).update(value)
        self._sync_stream_source_indicator()

    def _set_stream_source(self, source: str | None) -> None:
        if source in {"worker", "reviewer"}:
            self._stream_source = source
        else:
            self._stream_source = None
        self._sync_stream_source_indicator()

    def _effective_stream_source(self) -> str:
        if self._stream_source in {"worker", "reviewer"}:
            return self._stream_source
        if self._task_model is not None and self._task_model.status is TaskStatus.REVIEW:
            return "reviewer"
        return "worker"

    def _sync_stream_source_indicator(self) -> None:
        source = self._effective_stream_source()
        source_label = "AI REVIEWER" if source == "reviewer" else "WORKER"
        advisory = " (Advisory)" if source == "reviewer" else ""
        backend = ""
        if self._task_model is not None:
            backend = getattr(self._task_model, "agent_backend", "") or ""
        backend_suffix = f" · {backend}" if backend else ""
        if self._running:
            text = f"Stream: {source_label}{advisory} · LIVE{backend_suffix}"
            stream_title = f"{source_label} STREAM · LIVE{backend_suffix}"
        else:
            text = f"Stream: {source_label} · IDLE{backend_suffix}"
            stream_title = f"{source_label} STREAM{backend_suffix}"

        with contextlib.suppress(NoMatches):
            source_widget = self.query_one("#ts-detail-stream-source", Static)
            source_widget.update(text)
            source_widget.set_class(source == "reviewer", "ts-source-reviewer")
            source_widget.set_class(source == "worker", "ts-source-worker")
            source_widget.set_class(self._running, "ts-source-live")

        with contextlib.suppress(NoMatches):
            stream = self._output_stream()
            stream.border_title = stream_title
            show_hint = (
                not self._running
                and source == "worker"
                and self._task_model is not None
                and self._task_model.status is TaskStatus.REVIEW
            )
            stream.border_subtitle = (
                "Ctrl+Shift+P quick actions: AI review (advisory)" if show_hint else ""
            )

    def _refresh_header_labels(self) -> None:
        task = self._task_model
        if task is None:
            self.query_one("#ts-title", Label).update("Task")
            self.query_one("#ts-branch", Label).update("Branch: -")
            status = self._status_override or "Idle"
            self.query_one("#ts-status", Static).update(status)
            self.query_one(TaskDetailPane).task_data = None
            self._sync_stream_source_indicator()
            return

        self.query_one("#ts-title", Label).update(f"{task.title}")
        branch = task.base_branch or "main"
        self.query_one("#ts-branch", Label).update(f"task-{task.id[:8]} \u2192 {branch}")
        status_label = task.status.value.replace("_", " ").title()
        if task.review_approved:
            status_label += " \u00b7 APPROVED"
        status = self._status_override or status_label
        self.query_one("#ts-status", Static).update(status)

        self.query_one(TaskDetailPane).task_data = task
        self._sync_stream_source_indicator()

    def _refresh_header(self) -> None:
        header = self.query_one(KaganHeader)
        project = self.kagan_app.project
        header.update_project(project.name if project is not None else "No project")
        header.update_repo(self.kagan_app.selected_repo_name or "")
        header.update_count(0 if self._task_model is None else 1)
        header.update_sessions(1 if self._running else 0)

    async def _refresh_header_context(self) -> None:
        header = self.query_one(KaganHeader)
        with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
            tasks = await self.kagan_app.core.tasks.list()
            active = sum(1 for task in tasks if task.status is TaskStatus.IN_PROGRESS)
            review = sum(1 for task in tasks if task.status is TaskStatus.REVIEW)
            done = sum(1 for task in tasks if task.status is TaskStatus.DONE)
            header.update_health_strip(active=active, review=review, done=done)

        with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
            repo_id = self.kagan_app.selected_repo_id
            project = self.kagan_app.project
            if repo_id and project is not None:
                repos = await self.kagan_app.core.projects.repos(project.id)
                repo = next((item for item in repos if item.id == repo_id), None)
                if repo is not None:
                    branch = await git.current_branch(repo.path)
                    if branch:
                        header.update_branch(branch)

    def _schedule_runtime_refresh(self) -> None:
        if not self.is_mounted:
            return
        self._queue_stream_refresh(runtime=True)

    def _queue_stream_refresh(
        self,
        *,
        runtime: bool = False,
        workspace: bool = False,
        review: bool = False,
    ) -> None:
        if not self.is_mounted:
            return
        self._pending_runtime_refresh = self._pending_runtime_refresh or runtime
        self._pending_workspace_refresh = self._pending_workspace_refresh or workspace
        self._pending_review_refresh = self._pending_review_refresh or review
        if self._stream_refresh_timer is not None:
            return
        self._stream_refresh_timer = self.set_timer(0.12, self._flush_stream_refresh)

    def _flush_stream_refresh(self) -> None:
        self._stream_refresh_timer = None
        runtime = self._pending_runtime_refresh
        workspace = self._pending_workspace_refresh
        review = self._pending_review_refresh
        self._pending_runtime_refresh = False
        self._pending_workspace_refresh = False
        self._pending_review_refresh = False
        if not self.is_mounted:
            return
        if runtime:
            self.run_worker(
                self._refresh_runtime_state,
                group="task-screen-runtime-refresh",
                exclusive=True,
                exit_on_error=False,
            )
        if workspace:
            self.run_worker(
                self._hydrate_workspace_panels,
                group="task-screen-hydrate-stream",
                exclusive=True,
                exit_on_error=False,
            )
        if review:
            self.run_worker(
                self._load_review_context,
                group="task-screen-review-hydrate-stream",
                exclusive=True,
                exit_on_error=False,
            )

    async def _refresh_runtime_state(self) -> None:
        if self._task_id is None:
            return
        with contextlib.suppress(KaganError):
            latest = await self.kagan_app.core.tasks.get(self._task_id)
            self._task_model = latest
            self._refresh_header()
            self._refresh_header_labels()
            self._sync_action_bar()
            await self._load_review_context()
            await self._hydrate_workspace_panels()

    def action_approve(self) -> None:
        self.run_worker(self._approve_only_flow(), exit_on_error=False)

    async def _approve_only_flow(self) -> None:
        if self._task_id is None or self._task_model is None:
            return
        if self._task_model.status is not TaskStatus.REVIEW:
            return

        criteria = [
            c.strip() for c in (self._task_model.acceptance_criteria or []) if c and c.strip()
        ]
        if not criteria:
            from kagan.tui.screens.review_no_criteria import ReviewNoCriteriaModal

            choice = await self.app.push_screen_wait(ReviewNoCriteriaModal())
            if choice == "add_criteria":
                await self._edit_task_flow_for_criteria()
                return
            if choice == "approve_manually":
                await self._manual_approve_flow()
                return
            if choice == "reject":
                await self._reject_flow()
                return
            return

        confirmed = await self.app.push_screen_wait(
            ConfirmModal(
                title="Approve Task?",
                message="Mark this task as approved. You can merge separately.",
                confirm_label="Approve",
            )
        )
        if confirmed is not True:
            return

        await self.kagan_app.core.reviews.approve(self._task_id)
        await self._refresh_runtime_state()
        self.app.notify("Task approved", severity="information")

    async def _edit_task_flow_for_criteria(self) -> None:
        """Open the task editor focused on the acceptance criteria field."""
        if self._task_id is None:
            return
        if self._task_model is None:
            with contextlib.suppress(NotFoundError):
                self._task_model = await self.kagan_app.core.tasks.get(self._task_id)
        if self._task_model is None:
            return

        from kagan.tui.screens.task_editor_modal import TaskEditorModal

        await self.app.push_screen_wait(
            TaskEditorModal(task=self._task_model, focus_field="task-acceptance-criteria")
        )
        await self._refresh_runtime_state()

    async def _manual_approve_flow(self) -> None:
        """Approve a task manually when no acceptance criteria are defined."""
        if self._task_id is None or self._task_model is None:
            return

        confirmed = await self.app.push_screen_wait(
            ConfirmModal(
                title="Manual Approval (No Criteria)",
                message=(
                    "This task has no acceptance criteria.\n"
                    "Manual approval is an exceptional path \u2014 "
                    "the review is entirely your judgment.\n\n"
                    "Are you sure you want to approve?"
                ),
                confirm_label="Approve Manually",
            )
        )
        if confirmed is not True:
            return

        await self.kagan_app.core.reviews.approve(self._task_id)
        await self._refresh_runtime_state()
        self.app.notify("Manually approved (no criteria)", severity="warning")

    def action_merge(self) -> None:
        self.run_worker(self._merge_flow(), exit_on_error=False)

    async def _merge_flow(self) -> None:
        if self._task_id is None or self._task_model is None:
            return
        if self._task_model.status is not TaskStatus.REVIEW:
            return
        if not self._task_model.review_approved:
            self.app.notify("Approve the task before merging", severity="warning")
            return

        confirmed = await self.app.push_screen_wait(
            ConfirmModal(
                title="Merge Task?",
                message="This will merge the task branch and move to DONE.",
                confirm_label="Merge",
            )
        )
        if confirmed is not True:
            self._set_status("Merge cancelled")
            return

        try:
            await self.kagan_app.core.reviews.merge(self._task_id)
        except PreflightError as exc:
            self._last_merge_blocker = "Preflight failed  →  fix and retry"
            self._set_status(str(exc))
            self._output_stream().post_note(str(exc))
            self._sync_merge_readiness()
            return
        except MergeConflictError as exc:
            self._last_merge_blocker = "Merge conflicts  →  b to rebase"
            message = self._conflict_message(exc.conflict_files, prefix="Merge has conflicts")
            self._set_status(message)
            self._output_stream().post_note(message)
            self._sync_merge_readiness()
            return
        except WorktreeError as exc:
            self._last_merge_blocker = f"Worktree error: {exc}"
            message = f"Unable to merge: {exc}"
            self._set_status(message)
            self._output_stream().post_note(message)
            self._sync_merge_readiness()
            return

        self._last_merge_blocker = None
        self.app.notify("Merged and moved to DONE", severity="information")
        self.action_back()

    def action_reject(self) -> None:
        self.run_worker(self._reject_flow(), exit_on_error=False)

    async def _reject_flow(self) -> None:
        if self._task_id is None or self._task_model is None:
            return
        if self._task_model.status is not TaskStatus.REVIEW:
            return
        feedback = await self.app.push_screen_wait(
            RejectionInputModal(task_label=f"Task {self._task_id}")
        )
        if feedback is None:
            self._set_status("Rejection cancelled")
            return
        move_to_backlog = False
        if feedback.startswith(RejectionInputModal.BACKLOG_SENTINEL):
            move_to_backlog = True
            _, _, feedback = feedback.partition(":")
        note = feedback or "Needs more work"
        await self.kagan_app.core.reviews.reject(self._task_id, feedback=note)
        if move_to_backlog:
            await self.kagan_app.core.tasks.set_status(self._task_id, TaskStatus.BACKLOG)
            self.app.notify("Moved back to BACKLOG", severity="warning")
        else:
            self.app.notify("Moved back to IN_PROGRESS", severity="warning")
        self.action_back()

    async def action_rebase(self) -> None:
        if self._task_id is None or self._task_model is None:
            return
        if self._task_model.status is not TaskStatus.REVIEW:
            return
        try:
            await self.kagan_app.core.reviews.rebase(self._task_id)
        except WorktreeError as exc:
            self._last_merge_blocker = "Rebase conflicts  →  resolve and retry"
            conflicts = await self.kagan_app.core.reviews.conflicts(self._task_id)
            conflict_files = cast("list[str]", conflicts.get("conflicted_files", []))
            message = self._conflict_message(conflict_files, prefix=str(exc))
            self._set_status(message)
            self._output_stream().post_note(message)
            self._sync_merge_readiness()
            return
        self._last_merge_blocker = None
        self.app.notify("Rebase completed", severity="information")
        await self._hydrate_workspace_panels()
        await self._load_review_context()

    async def action_run_review(self) -> None:
        if self._task_id is None or self._task_model is None:
            return
        criteria = [
            c.strip() for c in (self._task_model.acceptance_criteria or []) if c and c.strip()
        ]
        if not criteria:
            self.app.notify(
                "Cannot run AI review — no acceptance criteria defined",
                severity="warning",
            )
            return
        with contextlib.suppress(KaganError, OSError, RuntimeError):
            await self.kagan_app.core.reviews.clear_verdicts(self._task_id)
        backend = await self._resolve_backend(self._task_model)
        self._reviewer_session_id = None
        self._pending_reviewer_session_id = True
        await self.kagan_app.core.tasks.run(self._task_id, agent_backend=backend)
        self._running = True
        self._set_stream_source("reviewer")
        self._set_status("AI Reviewing...")
        self.app.notify("AI review started", severity="information")
        self._ensure_stream_worker()

    def action_open_repo_picker(self) -> None:
        self.run_worker(self._open_repo_picker_flow(), exit_on_error=False)

    async def action_switch_session(self) -> None:
        panel = self._overlay_panel()
        if not panel.has_class("visible"):
            await self.action_open_task_overlay()
            panel = self._overlay_panel()
        self._open_overlay_session_picker(panel)

    async def action_open_session_picker(self) -> None:
        await self.action_switch_session()

    def _open_overlay_session_picker(self, panel: ChatPanel, *, initial_query: str = "") -> None:
        modal = panel.create_session_picker_modal(initial_query=initial_query)

        def _on_select(selected_key: str | None) -> None:
            if selected_key is None:
                return
            selector = panel.query_one("#chat-overlay-session-select", Select)
            selector.value = selected_key

        self.app.push_screen(modal, callback=_on_select)

    async def _open_repo_picker_flow(self) -> None:
        await self.app.push_screen_wait("repo-picker-modal")
        await self._hydrate_workspace_panels()
        await self._load_review_context()

    async def _load_task_or_fail(self) -> Task | None:
        if self._task_id is None:
            return None

        try:
            task = await self.kagan_app.core.tasks.get(self._task_id)
            self._task_model = task
            return task
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            self._set_status(f"Unable to load task: {exc}")
            return None

    async def _render_task_summary(self, task: Task) -> str:
        if task.review_approved:
            badge = "APPROVED"
        elif task.status is TaskStatus.REVIEW and self._running:
            badge = "REVIEWING..."
        else:
            badge = task.status.value.upper()
        current_status = f"Ready | {badge}"
        with contextlib.suppress(NoMatches):
            self.query_one("#ts-detail-status", Static).update(current_status)
        return current_status

    async def _render_criteria_checkboxes(self, task: Task) -> None:
        self._review_criteria_signature = await render_criteria_checkboxes(
            task=task,
            criteria_container=self.query_one("#ts-detail-criteria-list", Vertical),
            criteria_status=self.query_one("#ts-detail-criteria-status", Static),
            previous_signature=self._review_criteria_signature,
            running=self._running,
            get_static=lambda selector: self.query_one(selector, Static),
            sync_criteria_status=self._sync_criteria_status_widget,
        )

    async def _render_changed_files(self, task: Task) -> None:
        try:
            diff_text = await self.kagan_app.core.worktrees.diff(self._task_id)
        except (SessionError, WorktreeError):
            diff_text = ""
        if not diff_text:
            merged_fallback = await self._resolve_merged_commit_diff_fallback()
            if merged_fallback is not None:
                diff_text = merged_fallback[0]

        files, insertions, deletions = diff_totals(diff_text)
        with contextlib.suppress(NoMatches):
            self.query_one("#ts-detail-changes-summary", Static).update(
                f"Changes - {files} files  +{insertions} -{deletions}"
            )

        if diff_text and task.status is TaskStatus.REVIEW:
            with contextlib.suppress(NoMatches):
                if task.review_approved:
                    badge = "APPROVED"
                elif self._running:
                    badge = "REVIEWING..."
                else:
                    badge = task.status.value.upper()
                self.query_one("#ts-detail-status", Static).update(f"Ready | {badge}")

    async def _load_review_context(self) -> None:
        task = await self._load_task_or_fail()
        if task is None:
            return

        current_status = await self._render_task_summary(task)
        await self._render_criteria_checkboxes(task)
        await self._render_changed_files(task)
        await self._load_resume_context(task)
        self._set_status(current_status)
        self._sync_merge_readiness()

    async def _load_resume_context(self, task: Task) -> None:
        pane = self.query_one(TaskDetailPane)
        if self._task_id is None:
            pane.set_resume_context([], task.status)
            return
        notes: list[str] = []
        with contextlib.suppress(KaganError, OSError, RuntimeError):
            entries = await self.kagan_app.core.tasks.list_notes(self._task_id)
            notes = [entry.content for entry in entries]
        pane.set_resume_context(notes, task.status)

    def _sync_merge_readiness(self) -> None:
        try:
            widget = self.query_one("#ts-merge-readiness", Static)
        except NoMatches:
            return
        widget.update(
            build_merge_readiness_text(
                self._task_model,
                last_merge_blocker=self._last_merge_blocker,
            )
        )

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if not event.checkbox.has_class("ts-detail-criterion"):
            return
        self._sync_criteria_status_widget(self.query_one("#ts-detail-criteria-status", Static))

    def _sync_criteria_status_widget(self, status: Static) -> None:
        checkboxes = [
            node for node in self.query(".ts-detail-criterion") if isinstance(node, Checkbox)
        ]
        total = len(checkboxes)
        if total == 0:
            status.update("")
            status.remove_class("ts-criteria-complete")
            return
        checked = sum(1 for checkbox in checkboxes if checkbox.value)
        task = self._task_model
        ai_summary = ""
        ai_state = ""
        if task is not None:
            ai_summary, ai_state = render_ai_verdict_summary(task, total, running=self._running)
        if checked == total:
            human_summary = f"All {total} criteria verified"
            status.add_class("ts-criteria-complete")
        else:
            human_summary = f"{checked}/{total} verified"
            status.remove_class("ts-criteria-complete")

        if ai_summary:
            status.update(f"{human_summary}\n{ai_summary}")
        else:
            status.update(human_summary)

        status.remove_class("ts-ai-pass", "ts-ai-fail")
        status.set_class(ai_state == "pass", "ts-ai-pass")
        status.set_class(ai_state == "fail", "ts-ai-fail")

    def on_diff_file_tree_file_selected(self, message: DiffFileTree.FileSelected) -> None:
        if message.entry is None:
            return
        with contextlib.suppress(NoMatches):
            current = self.query_one("#ts-workspace-bar", Static).content
            first_line = str(current).splitlines()[0] if str(current).strip() else "Workspace"
            self.query_one("#ts-workspace-bar", Static).update(
                f"{first_line}\nCurrent: {message.entry.path}"
            )

    async def on_key(self, event: events.Key) -> None:
        panel = self._overlay_panel()
        active = self._active_tab()

        if event.key == "ctrl+k":
            event.prevent_default()
            event.stop()
            await self.action_open_session_picker()
            return

        if event.key == "ctrl+f" and panel.has_class("visible"):
            event.prevent_default()
            event.stop()
            await self.action_expand_chat_overlay()
            return

        if event.key == "q":
            if panel.has_class("visible") or self._focused_widget_accepts_text():
                return
            event.prevent_default()
            event.stop()
            self.action_back()
            return

        if event.key == "escape":
            if panel.has_class("visible"):
                event.prevent_default()
                event.stop()
                panel.set_visible(False)
                panel.set_fullscreen(False)
                self._overlay_layout_mode = "vertical"
                self._sync_overlay_layout_class()
                return
            event.prevent_default()
            event.stop()
            self.action_back()
            return

        if self._focused_widget_accepts_text():
            if event.key == "enter" and panel.has_class("visible"):
                event.prevent_default()
                event.stop()
                panel.action_send_message()
                return
            return

        if panel.has_class("visible"):
            return

        if active != "diff":
            return

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        del parameters
        if action in {"primary_action", "cancel_run"}:
            with contextlib.suppress(NoMatches):
                if (
                    self._overlay_panel().has_class("visible")
                    and self._focused_widget_accepts_text()
                ):
                    return False
        return True

    def _focused_widget_accepts_text(self) -> bool:
        focused = self.focused
        return isinstance(focused, Input | TextArea)

    def _sync_action_bar(self) -> None:
        action_bar = self.query_one(TaskActionBar)
        task = self._task_model
        panel = self._overlay_panel()
        action_bar.active_tab = self._active_tab()
        action_bar.task_data = task
        action_bar.task_running = self._running
        action_bar.chat_visible = panel.has_class("visible")
        action_bar.chat_fullscreen = panel.has_class("visible") and panel.has_class("fullscreen")
        criteria = (
            [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
            if task is not None
            else []
        )
        action_bar.has_criteria = bool(criteria)

    def _sync_overlay_layout_class(self) -> None:
        panel = self._overlay_panel()
        visible = panel.has_class("visible")
        fullscreen = visible and panel.has_class("fullscreen")
        self.set_class(visible, "ts-chat-visible")
        self.set_class(fullscreen, "ts-chat-fullscreen")
        self.set_class(
            visible and not fullscreen and self._overlay_layout_mode == "vertical",
            "ts-chat-vertical",
        )
        self.set_class(
            visible and not fullscreen and self._overlay_layout_mode == "horizontal",
            "ts-chat-horizontal",
        )
        self._sync_action_bar()

    def _conflict_message(
        self, conflict_files: list[str], *, prefix: str = "Rebase has conflicts"
    ) -> str:
        if not conflict_files:
            return prefix
        joined = ", ".join(conflict_files[:3])
        more = "" if len(conflict_files) <= 3 else f" (+{len(conflict_files) - 3} more)"
        return f"{prefix}: {joined}{more}"

    def _active_tab(self) -> str:
        with contextlib.suppress(NoMatches, AttributeError):
            tabs = self.query_one("#ts-tabs", TabbedContent)
            active = getattr(tabs, "active", "")
            if isinstance(active, str) and active:
                return active
        return "detail"

    def _select_initial_tab(self) -> None:
        self.query_one("#ts-tabs", TabbedContent).active = "detail"

    def _configure_overlay_chat(
        self,
        *,
        visible: bool = False,
        fullscreen: bool = False,
        mode: str = "task",
        layout_mode: str | None = None,
        focus: bool = False,
    ) -> None:
        panel = self._overlay_panel()
        panel.set_visible(visible)
        panel.set_fullscreen(fullscreen)
        panel.set_overlay_shortcuts(split="Space", fullscreen="Ctrl+F", close="Esc")

        if layout_mode is not None:
            self._overlay_layout_mode = layout_mode

        if mode == "orchestrator":
            panel.set_mode_title("Orchestrator")
            panel.set_session_kind("orchestrator")
        else:
            panel.set_mode_title("Task Chat")
            panel.set_session_kind("auto")
            panel.set_sessions(
                build_session_options(self.kagan_app, self._task_session_options()),
                self._active_task_session_key(),
            )
            if self._task_id is not None:
                panel.set_mode_title(f"Task #{self._task_id[:8]}")

        if focus:
            panel.query_one("#chat-overlay-input", Input).focus()

        self._chat_mode = mode

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
        if source == "reviewer":
            return TASK_REVIEWER_SESSION_KEY
        return TASK_WORKER_SESSION_KEY

    @staticmethod
    def _stream_source_for_session_key(key: str) -> str | None:
        normalized = key.casefold()
        if "review" in normalized:
            return "reviewer"
        if "task" in normalized or "worker" in normalized:
            return "worker"
        return None

    @staticmethod
    def _chat_session_kind(key: str) -> str:
        return "review" if "review" in key.casefold() else "auto"

    def _overlay_panel(self) -> ChatPanel:
        return self.query_one("#ts-chat-overlay", ChatPanel)
