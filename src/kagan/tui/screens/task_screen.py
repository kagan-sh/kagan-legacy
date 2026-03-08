import asyncio
import contextlib
import re
from typing import TYPE_CHECKING, Any, cast

from textual import events
from textual.app import ComposeResult
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
from kagan.core.enums import SessionEventType, TaskStatus, WorkMode
from kagan.core.errors import (
    KaganError,
    MergeConflictError,
    NotFoundError,
    PreflightError,
    SessionError,
    WorktreeError,
)
from kagan.core.models import Task
from kagan.tui.keybindings import TASK_SCREEN_BINDINGS
from kagan.tui.orchestrator_sessions import is_orchestrator_session_key
from kagan.tui.screens.confirm import ConfirmModal
from kagan.tui.screens.kanban_chat import (
    acp_payload,
    apply_task_chat_event,
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
from kagan.tui.widgets.streaming import StreamingOutput
from kagan.tui.widgets.task_action_bar import TaskActionBar
from kagan.tui.widgets.task_detail_pane import TaskDetailPane
from kagan.tui.widgets.task_diff_pane import TaskDiffPane

if TYPE_CHECKING:
    from textual.timer import Timer

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

    @property
    def kagan_app(self) -> "KaganApp":
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

            yield StreamingOutput(id="ts-stream", classes="ts-stream ts-hidden-stream")
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

        if (
            self._task_model is not None
            and self._task_model.status is TaskStatus.IN_PROGRESS
            and self._task_model.execution_mode is WorkMode.AUTO
        ):
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
        # If chat overlay is fullscreen, exit fullscreen first (like Ctrl+T)
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
        active = self._active_tab()
        if active == "detail":
            if self._task_model is not None and self._task_model.status is TaskStatus.REVIEW:
                if self._task_model.review_approved:
                    self.action_merge()
                else:
                    self.action_approve()
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
            if self._task_model is not None and self._task_model.review_approved:
                self.action_merge()
            else:
                self.action_approve()
            return

        if self._task_model is not None and self._task_model.status is TaskStatus.REVIEW:
            if self._task_model.review_approved:
                self.action_merge()
            else:
                self.action_approve()
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
            [*self.kagan_app.orchestrator_sessions.options(), *self._task_session_options()],
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
        """Cycle to next chat session."""
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

        merged_description = task_model.description.strip()
        follow_up = f"User follow-up:\n{text}".strip()
        updated_description = (
            f"{merged_description}\n\n{follow_up}" if merged_description else follow_up
        )
        self._task_model = await self.kagan_app.core.tasks.update(
            self._task_id,
            description=updated_description,
        )

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
        return (
            settings.get("default_agent_backend") or settings.get("default_agent") or "claude-code"
        )

    async def _hydrate_workspace_panels(self) -> None:
        if self._task_id is None:
            return

        workspace = await self.kagan_app.core.worktrees.get(self._task_id)
        diff_pane = self.query_one(TaskDiffPane)
        bar_w = diff_pane.get_workspace_bar()
        diff_view = diff_pane.get_diff_view()

        if workspace is None:
            merged_fallback = await self._merged_commit_diff_fallback()
            if merged_fallback is None:
                bar_w.update("No worktree provisioned")
                bar_w.remove_class("loading")
                bar_w.add_class("ts-no-workspace")
                diff_view.set_diff("")
                return

            diff_text, stats, repo_path, short_sha, target_branch = merged_fallback
            files = self._changed_files(diff_text)
            n_files = int(stats.get("files", 0))
            ins = int(stats.get("insertions", 0))
            dels = int(stats.get("deletions", 0))

            bar_w.update(
                " | ".join(
                    [
                        f"Merged {short_sha} -> {target_branch}",
                        f"{n_files} files",
                        f"+{ins} -{dels}",
                        f"{len(files)} changed",
                    ]
                )
                + f"\n{repo_path}"
            )
            bar_w.remove_class("loading")
            bar_w.remove_class("ts-no-workspace")

            diff_view.set_diff(diff_text)
            if files:
                diff_view.set_selected_file(files[0])
            return

        diff_text = ""
        with contextlib.suppress(SessionError, WorktreeError):
            diff_text = await self.kagan_app.core.worktrees.diff(self._task_id)
        stats: dict[str, Any] = {"files": 0, "insertions": 0, "deletions": 0}
        with contextlib.suppress(SessionError, WorktreeError):
            stats = await self.kagan_app.core.worktrees.diff_stats(self._task_id)

        files = self._changed_files(diff_text)
        n_files = int(stats.get("files", 0))
        ins = int(stats.get("insertions", 0))
        dels = int(stats.get("deletions", 0))

        bar_w.update(
            " | ".join(
                [
                    "Workspace",
                    f"{n_files} files",
                    f"+{ins} -{dels}",
                    f"{len(files)} changed",
                ]
            )
            + f"\n{workspace.worktree_path}"
        )
        bar_w.remove_class("loading")
        bar_w.remove_class("ts-no-workspace")

        if self._active_tab() == "diff":
            selected_path = diff_view.current_file_path()
            diff_view.set_diff(diff_text)
            if selected_path is not None and selected_path in files:
                diff_view.set_selected_file(selected_path)

    @staticmethod
    def _changed_files(diff_text: str) -> list[str]:
        files: list[str] = []
        for line in diff_text.splitlines():
            if not line.startswith("diff --git a/"):
                continue
            parts = line.split(" b/", maxsplit=1)
            if len(parts) != 2:
                continue
            files.append(parts[1].strip())
        seen: set[str] = set()
        unique: list[str] = []
        for item in files:
            if item in seen:
                continue
            seen.add(item)
            unique.append(item)
        return unique

    @staticmethod
    def _workspace_snapshot_text(
        worktree_path: str,
        files: list[str],
        stats: dict[str, Any],
    ) -> str:
        n_files = int(stats.get("files", 0))
        ins = int(stats.get("insertions", 0))
        dels = int(stats.get("deletions", 0))
        return (
            f"Workspace · {n_files} files · +{ins} / -{dels} · {len(files)} changed\n"
            f"{worktree_path}"
        )

    @staticmethod
    def _merged_snapshot_text(
        repo_path: str,
        short_sha: str,
        target_branch: str,
        files: list[str],
        stats: dict[str, Any],
    ) -> str:
        n_files = int(stats.get("files", 0))
        ins = int(stats.get("insertions", 0))
        dels = int(stats.get("deletions", 0))
        return (
            f"Merged {short_sha} -> {target_branch} · {n_files} files · +{ins} / -{dels} · "
            f"{len(files)} changed\n{repo_path}"
        )

    async def _merged_commit_diff_fallback(
        self,
    ) -> tuple[str, dict[str, int], str, str, str] | None:
        if self._task_id is None:
            return None

        task = self._task_model
        if task is None:
            with contextlib.suppress(KaganError, OSError, RuntimeError, ValueError):
                task = await self.kagan_app.core.tasks.get(self._task_id)
        if task is None or task.status is not TaskStatus.DONE:
            return None

        merge_event = await self.kagan_app.core.tasks.events.latest(
            self._task_id,
            event_type=SessionEventType.MERGE_COMPLETED,
        )
        if merge_event is None:
            return None

        payload = merge_event.payload or {}
        commit_sha = str(payload.get("commit_sha") or "").strip()
        if not commit_sha:
            return None

        repo_path, default_branch = await self._task_repo_path(task.project_id)
        if repo_path is None:
            return None

        diff_text = ""
        with contextlib.suppress(WorktreeError):
            diff_text = await git.show_commit_diff(repo_path, commit_sha=commit_sha)
        if not diff_text.strip():
            return None

        files, insertions, deletions = self._diff_totals(diff_text)
        target_branch = str(
            payload.get("target_branch") or task.base_branch or default_branch or "main"
        )
        target_branch = target_branch.strip() or "main"
        return (
            diff_text,
            {"files": files, "insertions": insertions, "deletions": deletions},
            repo_path,
            commit_sha[:8],
            target_branch,
        )

    async def _task_repo_path(self, project_id: str) -> tuple[str | None, str]:
        repos = await self.kagan_app.core.projects.repos(project_id)
        if not repos:
            return None, "main"
        repo = repos[0]
        return repo.path, repo.default_branch

    def _ensure_stream_worker(self) -> None:
        if self._stream_task is not None and not self._stream_task.done():
            return
        if self._task_id is None:
            return
        self._stream_task = asyncio.create_task(self._stream_events(self._task_id))

    def _maybe_apply_chat_event(
        self, overlay_chat: ChatPanel, event_type: SessionEventType, payload: dict[str, Any]
    ) -> None:
        """Apply chat event if in task chat mode."""
        if self._chat_mode == "task":
            apply_task_chat_event(overlay_chat, event_type, payload)

    async def _stream_events(self, task_id: str) -> None:
        output = self._output_stream()
        overlay_chat = self._overlay_panel()
        try:
            async for event in self.kagan_app.core.tasks.events.stream(
                task_id,
                replay_limit=TASK_SCREEN_REPLAY_EVENT_LIMIT,
            ):
                payload = event.payload or {}
                match event.event_type:
                    case SessionEventType.OUTPUT_CHUNK:
                        self._render_stream_chunk(output, payload)
                        self._maybe_apply_chat_event(overlay_chat, event.event_type, payload)
                    case SessionEventType.TOOL_CALL_START:
                        output.upsert_tool_call(
                            tool_call_id(payload),
                            tool_call_title(payload),
                            status=tool_call_status(payload, default="running"),
                            args=tool_call_args(payload),
                            result=tool_call_result(payload),
                            kind=tool_call_kind(payload),
                        )
                        self._maybe_apply_chat_event(overlay_chat, event.event_type, payload)
                    case SessionEventType.TOOL_CALL_UPDATE:
                        output.update_tool_status(
                            tool_call_id(payload),
                            tool_call_status(payload, default="updated"),
                            result=tool_call_result(payload),
                        )
                        self._maybe_apply_chat_event(overlay_chat, event.event_type, payload)
                    case SessionEventType.AGENT_STATUS:
                        self._maybe_apply_chat_event(overlay_chat, event.event_type, payload)
                        output.post_note(self._payload_text(payload) or "Agent status update")
                    case SessionEventType.PLAN_UPDATE:
                        output.post_note(self._payload_text(payload) or "Plan updated")
                    case SessionEventType.TASK_STATUS_CHANGED:
                        output.post_note(self._payload_text(payload) or "Task status changed")
                        self._queue_stream_refresh(runtime=True)
                    case SessionEventType.AGENT_COMPLETED:
                        self._running = False
                        self._set_status("Completed")
                        self._maybe_apply_chat_event(overlay_chat, event.event_type, payload)
                        output.post_note("Agent completed")
                    case SessionEventType.AGENT_FAILED:
                        self._running = False
                        self._set_status("Failed")
                        self._maybe_apply_chat_event(overlay_chat, event.event_type, payload)
                        output.post_note(self._payload_text(payload) or "Agent failed")
                    case SessionEventType.MERGE_COMPLETED:
                        output.post_note(self._payload_text(payload) or "Merge completed")
                    case SessionEventType.MERGE_FAILED:
                        output.post_note(self._payload_text(payload) or "Merge failed")
                if event.event_type in {
                    SessionEventType.OUTPUT_CHUNK,
                    SessionEventType.TOOL_CALL_START,
                    SessionEventType.TOOL_CALL_UPDATE,
                    SessionEventType.AGENT_COMPLETED,
                    SessionEventType.AGENT_FAILED,
                    SessionEventType.TASK_STATUS_CHANGED,
                }:
                    self._queue_stream_refresh(workspace=True, review=True)
        except asyncio.CancelledError:
            pass
        except (KaganError, NoMatches, AttributeError, OSError, RuntimeError) as exc:
            self._running = False
            self._set_status("Failed")
            output.post_note(f"Stream ended unexpectedly: {exc}")

    def _output_stream(self) -> StreamingOutput:
        return self.query_one("#ts-stream", StreamingOutput)

    def _render_stream_chunk(self, output: StreamingOutput, payload: dict[str, Any]) -> None:
        text = stream_chunk_text(payload)
        kind = stream_chunk_kind(payload)
        if not text:
            return
        if kind in {"assistant", "thought", "note", "user"}:
            output.append_chunk(text, kind=cast("Any", kind), merge=True)
            return
        output.append_text(text)

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
        if self._running:
            text = f"Stream: {source_label}{advisory} · LIVE"
            stream_title = f"{source_label} STREAM · LIVE"
        else:
            text = f"Stream: {source_label} · IDLE"
            stream_title = f"{source_label} STREAM"

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
                "Ctrl+P command palette: AI review (advisory)" if show_hint else ""
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
        """Run AI review (advisory — does not approve or merge)."""
        if self._task_id is None or self._task_model is None:
            return
        backend = await self._resolve_backend(self._task_model)
        await self.kagan_app.core.tasks.run(self._task_id, agent_backend=backend)
        self._running = True
        self._set_stream_source("reviewer")
        self._set_status("AI Reviewing (Advisory)")
        self.app.notify("AI review started (advisory only)", severity="information")
        self._ensure_stream_worker()

    def action_open_repo_picker(self) -> None:
        self.run_worker(self._open_repo_picker_flow(), exit_on_error=False)

    async def action_switch_session(self) -> None:
        """Open session picker to switch sessions."""
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
        """Load the task model or set error status and return None."""
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
        badge = "APPROVED" if task.review_approved else task.status.value.upper()
        current_status = f"Ready | {badge}"
        with contextlib.suppress(NoMatches):
            self.query_one("#ts-detail-status", Static).update(current_status)
        return current_status

    async def _render_criteria_checkboxes(self, task: Task) -> None:
        criteria_container = self.query_one("#ts-detail-criteria-list", Vertical)
        criteria_status = self.query_one("#ts-detail-criteria-status", Static)

        criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
        signature = tuple(criteria)

        if criteria:
            if signature != self._review_criteria_signature:
                await criteria_container.remove_children()
                for i, criterion in enumerate(criteria):
                    checkbox = Checkbox(
                        criterion,
                        id=f"ts-detail-criterion-{i}",
                        classes="ts-detail-criterion",
                    )
                    checkbox.styles.width = "100%"
                    checkbox.styles.height = "auto"
                    await criteria_container.mount(checkbox)
                self._review_criteria_signature = signature
            self._sync_criteria_status_widget(criteria_status)
        else:
            if self._review_criteria_signature != signature:
                await criteria_container.remove_children()
                self._review_criteria_signature = signature
            criteria_status.update("")

    async def _render_changed_files(self, task: Task) -> None:
        try:
            diff_text = await self.kagan_app.core.worktrees.diff(self._task_id)
        except (SessionError, WorktreeError):
            diff_text = ""
        if not diff_text:
            merged_fallback = await self._merged_commit_diff_fallback()
            if merged_fallback is not None:
                diff_text = merged_fallback[0]

        files, insertions, deletions = self._diff_totals(diff_text)
        with contextlib.suppress(NoMatches):
            self.query_one("#ts-detail-changes-summary", Static).update(
                f"Changes - {files} files  +{insertions} -{deletions}"
            )

        if diff_text and task.status is TaskStatus.REVIEW:
            with contextlib.suppress(NoMatches):
                badge = "APPROVED" if task.review_approved else task.status.value.upper()
                self.query_one("#ts-detail-status", Static).update(f"Ready | {badge}")

    async def _load_review_context(self) -> None:
        """Load and render the review context for the current task."""
        task = await self._load_task_or_fail()
        if task is None:
            return

        current_status = await self._render_task_summary(task)
        await self._render_criteria_checkboxes(task)
        await self._render_changed_files(task)
        self._set_status(current_status)
        self._sync_merge_readiness()

    def _sync_merge_readiness(self) -> None:
        """Update the merge readiness checklist in the Review tab."""
        task = self._task_model
        with contextlib.suppress(NoMatches):
            widget = self.query_one("#ts-merge-readiness", Static)
            if task is None or task.status is not TaskStatus.REVIEW:
                widget.update("")
                return

            lines: list[str] = []
            if task.review_approved:
                lines.append("  ✓ Approved")
            else:
                criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
                if criteria:
                    lines.append("  ✗ Not approved  →  a to approve")
                else:
                    lines.append("  ✗ Not approved (no criteria)  →  a for options")

            if self._last_merge_blocker:
                lines.append(f"  ✗ {self._last_merge_blocker}")
            else:
                lines.append("  ✓ No merge blockers")

            widget.update("Merge Readiness\n" + "\n".join(lines))

    @staticmethod
    def _parse_file_diff_summary(diff_text: str) -> list[tuple[str, int, int]]:
        """Parse unified diff into per-file (path, insertions, deletions) tuples."""
        entries: list[tuple[str, int, int]] = []
        current_file: str | None = None
        ins = 0
        dels = 0
        for line in diff_text.splitlines():
            if line.startswith("diff --git a/"):
                if current_file is not None:
                    entries.append((current_file, ins, dels))
                parts = line.split(" b/", maxsplit=1)
                current_file = parts[1].strip() if len(parts) == 2 else None
                ins = 0
                dels = 0
            elif current_file is not None:
                if line.startswith("+++") or line.startswith("---"):
                    continue
                if line.startswith("+"):
                    ins += 1
                elif line.startswith("-"):
                    dels += 1
        if current_file is not None:
            entries.append((current_file, ins, dels))
        return entries

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
        if checked == total:
            status.update(f"All {total} criteria verified")
            status.add_class("ts-criteria-complete")
        else:
            status.update(f"{checked}/{total} verified")
            status.remove_class("ts-criteria-complete")

    def _diff_totals(self, diff_text: str) -> tuple[int, int, int]:
        files = len(
            {match.group(1) for match in re.finditer(r"^diff --git a/(.+?) b/", diff_text, re.M)}
        )
        insertions = 0
        deletions = 0
        for line in diff_text.splitlines():
            if line.startswith("+++") or line.startswith("---"):
                continue
            if line.startswith("+"):
                insertions += 1
            elif line.startswith("-"):
                deletions += 1
        return files, insertions, deletions

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
        action_bar.active_tab = self._active_tab()
        action_bar.task_data = task
        action_bar.task_running = self._running
        criteria = (
            [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
            if task is not None
            else []
        )
        action_bar.has_criteria = bool(criteria)

    def _sync_overlay_layout_class(self) -> None:
        panel = self._overlay_panel()
        tabs = self.query_one("#ts-tabs", TabbedContent)
        visible = panel.has_class("visible")
        fullscreen = visible and panel.has_class("fullscreen")
        if visible:
            if fullscreen:
                panel.styles.layer = "overlay"
                panel.styles.dock = "bottom"
                panel.styles.width = "100%"
                panel.styles.height = "1fr"
                panel.styles.max_height = "1fr"
                panel.styles.min_height = "0"
                tabs.styles.height = "1fr"
            elif self._overlay_layout_mode == "vertical":
                panel.styles.layer = "default"
                panel.styles.dock = "right"
                panel.styles.width = "44%"
                panel.styles.height = "1fr"
                panel.styles.max_height = "1fr"
                panel.styles.min_height = "0"
                tabs.styles.height = "1fr"
            else:
                panel.styles.layer = "default"
                panel.styles.dock = "bottom"
                panel.styles.width = "100%"
                panel.styles.height = "50%"
                panel.styles.max_height = "50%"
                panel.styles.min_height = "8"
                tabs.styles.height = "1fr"
        else:
            tabs.styles.height = "1fr"
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
        """Configure the chat overlay panel with common setup logic.

        Args:
            visible: Whether the panel should be visible
            fullscreen: Whether the panel should be fullscreen
            mode: Either "task" or "orchestrator" mode
            layout_mode: Layout mode ("vertical" or "horizontal"), defaults to current
            focus: Whether to focus the input field
        """
        panel = self._overlay_panel()
        panel.set_visible(visible)
        panel.set_fullscreen(fullscreen)

        if layout_mode is not None:
            self._overlay_layout_mode = layout_mode

        if mode == "orchestrator":
            panel.set_mode_title("Orchestrator")
            panel.set_session_kind("orchestrator")
        else:
            panel.set_mode_title("Task Chat")
            panel.set_session_kind("auto")
            panel.set_sessions(
                [*self.kagan_app.orchestrator_sessions.options(), *self._task_session_options()],
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
            [*self.kagan_app.orchestrator_sessions.options(), *self._task_session_options()],
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
