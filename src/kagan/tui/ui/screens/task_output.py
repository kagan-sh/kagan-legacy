"""Dedicated AUTO task output screen with split stats and live chat overlay."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from textual import on
from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Label, Rule, Static

from kagan.core.constants import MODAL_TITLE_MAX_LENGTH
from kagan.core.domain.enums import TaskStatus, TaskType
from kagan.core.services.jobs import JobStatus
from kagan.tui.keybindings import TASK_OUTPUT_BINDINGS
from kagan.tui.ui.screens.base import KaganScreen
from kagan.tui.ui.utils.job_results import job_message, job_result_payload
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay
from kagan.tui.ui.widgets.diff_browser import DiffBrowserWidget

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

    from kagan.tui.ui.types import TaskView


class TaskOutputScreen(KaganScreen):
    """Show task stats on top and the standard orchestrator overlay on the lower half."""

    BINDINGS = TASK_OUTPUT_BINDINGS
    DOCKED_OVERLAY_BASE_HEIGHT: int = 8
    DOCKED_OVERLAY_MAX_HEIGHT_RATIO: float = 0.5
    DOCKED_OVERLAY_MIN_HEIGHT: int = 3
    START_JOB_PENDING_MESSAGE = "Agent start requested; waiting for scheduler."
    STOP_JOB_PENDING_MESSAGE = "Agent stop requested; waiting for scheduler."

    def __init__(
        self,
        task: TaskView,
        base_branch: str = "main",
        *,
        auto_start_requested: bool = False,
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._task_model = task
        self._base_branch = base_branch
        self._auto_start_requested = auto_start_requested
        self._runtime_poll_timer: Timer | None = None

    @staticmethod
    def _state_attr(state: object | None, name: str, default: Any = None) -> Any:
        if state is None:
            return default
        if isinstance(state, dict):
            return state.get(name, default)
        return getattr(state, name, default)

    @classmethod
    def _state_bool(cls, state: object | None, name: str) -> bool:
        value = cls._state_attr(state, name, False)
        if isinstance(value, bool):
            return value
        return bool(value)

    def compose(self) -> ComposeResult:
        with Vertical(id="task-output-screen-root"):
            with Vertical(id="task-output-top"):
                yield Label(
                    f"Task Output: {self._task_model.title[:MODAL_TITLE_MAX_LENGTH]}",
                    id="task-output-title",
                    classes="modal-title",
                )
                yield Label(
                    f"Branch: task-{self._task_model.short_id} -> {self._base_branch}",
                    id="task-output-branch",
                    classes="branch-info",
                )
                yield Label("", id="task-output-status", classes="task-output-status")
                yield Rule()
                yield Static(
                    "[dim]Loading workspace diff…[/dim]",
                    id="task-output-diff-placeholder",
                )
            yield TaskOutputChatOverlay(
                agent_factory=self.kagan_app._agent_factory,
                id="task-output-chat-overlay",
            )

    async def on_mount(self) -> None:
        self._refresh_header_labels()
        if not self._initialize_overlay():
            self.call_after_refresh(self._initialize_overlay)
        self._runtime_poll_timer = self.set_interval(1.0, self._schedule_runtime_refresh)
        self.run_worker(
            self._hydrate_top_panel(),
            group="task-output-hydrate",
            exclusive=True,
            exit_on_error=False,
        )
        if self._auto_start_requested and self._task_model.task_type is TaskType.AUTO:
            self.run_worker(
                self._auto_start_if_needed(),
                group="task-output-auto-start",
                exclusive=True,
                exit_on_error=False,
            )
        self._schedule_runtime_refresh()

    async def on_unmount(self) -> None:
        if self._runtime_poll_timer is not None:
            self._runtime_poll_timer.stop()
            self._runtime_poll_timer = None
        with contextlib.suppress(NoMatches):
            overlay = self._overlay()
            overlay.hide()
            overlay.set_target_scope(None)

    def _overlay(self) -> ChatOverlay:
        return self.query_one("#task-output-chat-overlay", ChatOverlay)

    def _initialize_overlay(self) -> bool:
        with contextlib.suppress(NoMatches):
            overlay = self._overlay()
            overlay.set_target_scope(self._task_model.id)
            overlay.show_for_task(self._task_model, fullscreen=False)
            self._sync_overlay_layout_class()
            return True
        return False

    def _refresh_header_labels(self) -> None:
        with contextlib.suppress(NoMatches):
            self.query_one("#task-output-title", Label).update(
                f"Task Output: {self._task_model.title[:MODAL_TITLE_MAX_LENGTH]}"
            )
        with contextlib.suppress(NoMatches):
            self.query_one("#task-output-branch", Label).update(
                f"Branch: task-{self._task_model.short_id} -> {self._base_branch}"
            )

    async def _hydrate_top_panel(self) -> None:
        placeholder = None
        with contextlib.suppress(NoMatches):
            placeholder = self.query_one("#task-output-diff-placeholder", Static)

        try:
            workspaces = await self.ctx.api.list_workspaces(task_id=self._task_model.id)
        except RuntimeError:
            workspaces = []

        first = workspaces[0] if workspaces else None
        workspace_id = str(self._state_attr(first, "id", "")).strip()

        if not workspace_id:
            if placeholder is not None:
                placeholder.update("[dim](No workspace yet)[/dim]")
            return

        if placeholder is not None:
            placeholder.display = False

        with contextlib.suppress(NoMatches):
            top = self.query_one("#task-output-top", Vertical)
            await top.mount(
                DiffBrowserWidget(
                    workspace_id,
                    load_all_diffs=self._load_all_workspace_diffs,
                )
            )

    async def _load_all_workspace_diffs(self, workspace_id: str) -> list[Any]:
        return await self.ctx.api.get_all_diffs(workspace_id)

    @on(DiffBrowserWidget.ActionRequested)
    async def _on_diff_action_requested(self, event: DiffBrowserWidget.ActionRequested) -> None:
        event.stop()
        if event.action == "approve":
            self.notify("Diff approved", severity="information")
        elif event.action == "reject":
            self.notify("Diff rejected", severity="warning")
        elif event.action == "merge":
            await self._handle_diff_merge()

    async def _handle_diff_merge(self) -> None:
        try:
            workspaces = await self.ctx.api.list_workspaces(task_id=self._task_model.id)
        except RuntimeError:
            self.notify("Merge failed: unable to load workspace", severity="error")
            return
        if not workspaces:
            self.notify("No workspace to merge", severity="warning")
            return
        from kagan.tui.ui.modals import MergeDialog

        await self.app.push_screen(MergeDialog(workspaces[0].id, []))

    def _schedule_runtime_refresh(self) -> None:
        if not self.is_mounted:
            return
        self.run_worker(
            self._refresh_runtime_state(),
            group="task-output-runtime-refresh",
            exclusive=True,
            exit_on_error=False,
        )

    async def _refresh_runtime_state(self) -> None:
        with contextlib.suppress(Exception):
            await self.ctx.api.reconcile_running_tasks([self._task_model.id])
        latest = await self.ctx.api.get_task(self._task_model.id)
        if latest is None:
            self.notify("Task no longer exists. Returning to board.", severity="warning")
            self.dismiss(None)
            return
        self._task_model = latest
        self._refresh_header_labels()

        runtime_view = self.ctx.api.get_runtime_view(self._task_model.id)
        if self._state_bool(runtime_view, "is_reviewing"):
            runtime_text = "reviewing"
        elif self._state_bool(runtime_view, "is_running"):
            runtime_text = "running"
        elif self._state_bool(runtime_view, "is_blocked"):
            runtime_text = "blocked"
        elif self._state_bool(runtime_view, "is_pending"):
            runtime_text = "pending"
        else:
            runtime_text = "idle"
        with contextlib.suppress(NoMatches):
            self.query_one("#task-output-status", Label).update(
                f"Task: {self._task_model.status.value.upper()} | Runtime: {runtime_text}"
            )

    def action_cycle_chat_session(self) -> None:
        overlay = self._overlay()
        if overlay.has_class("visible"):
            overlay.cycle_chat_session()

    def _sync_overlay_layout_class(self) -> None:
        overlay = self._overlay()
        self.set_class(
            overlay.has_class("visible") and overlay.has_class("fullscreen"),
            "task-output-terminal-fullscreen",
        )

    def _estimated_docked_overlay_height(self) -> int:
        viewport_height = 0
        with contextlib.suppress(Exception):
            viewport_height = int(self.size.height)
        if viewport_height <= 0:
            with contextlib.suppress(Exception):
                viewport_height = int(self.app.size.height)
        if viewport_height <= 0:
            return 0
        target_height = max(
            self.DOCKED_OVERLAY_BASE_HEIGHT,
            int(viewport_height * self.DOCKED_OVERLAY_MAX_HEIGHT_RATIO),
        )
        max_allowed_height = max(1, viewport_height - 1)
        return max(1, min(target_height, max_allowed_height))

    def _apply_overlay_height_constraints(
        self,
        overlay: ChatOverlay,
        *,
        fullscreen: bool,
        docked_height: int | None = None,
    ) -> None:
        if fullscreen:
            overlay.styles.height = "1fr"
            overlay.styles.max_height = "1fr"
            overlay.styles.min_height = "0"
            return
        resolved = max(1, int(docked_height or self._estimated_docked_overlay_height() or 1))
        min_height = min(self.DOCKED_OVERLAY_MIN_HEIGHT, resolved)
        overlay.styles.height = str(resolved)
        overlay.styles.max_height = str(resolved)
        overlay.styles.min_height = str(min_height)

    def prepare_for_docked_overlay_open(self) -> None:
        overlay_height = self._estimated_docked_overlay_height()
        if overlay_height <= 0:
            return
        with contextlib.suppress(NoMatches):
            overlay = self._overlay()
            self._apply_overlay_height_constraints(
                overlay,
                fullscreen=False,
                docked_height=overlay_height,
            )

    def on_chat_overlay_visibility_changed(self, visible: bool, fullscreen: bool) -> None:
        if not self.is_mounted:
            return
        with contextlib.suppress(NoMatches):
            overlay = self._overlay()
            if visible:
                overlay_height = self._estimated_docked_overlay_height() if not fullscreen else None
                self._apply_overlay_height_constraints(
                    overlay,
                    fullscreen=fullscreen,
                    docked_height=overlay_height,
                )
        self._sync_overlay_layout_class()

    def action_toggle_chat_overlay(self) -> None:
        overlay = self._overlay()
        if overlay.has_class("visible"):
            if overlay.has_class("fullscreen"):
                overlay.show_for_task(self._task_model, fullscreen=False)
                self._sync_overlay_layout_class()
                return
            overlay.hide()
            self._sync_overlay_layout_class()
            return
        overlay.show_for_task(self._task_model, fullscreen=False)
        self._sync_overlay_layout_class()

    def action_open_chat_fullscreen(self) -> None:
        overlay = self._overlay()
        if overlay.has_class("visible") and overlay.has_class("fullscreen"):
            overlay.hide()
            self._sync_overlay_layout_class()
            return
        if overlay.has_class("visible"):
            overlay.show_for_task(self._task_model, fullscreen=True)
            self._sync_overlay_layout_class()
            return
        overlay.show_for_task(self._task_model, fullscreen=True)
        self._sync_overlay_layout_class()

    async def action_start_agent_output(self) -> None:
        if self._task_model.task_type is not TaskType.AUTO:
            return
        if self._task_model.status is not TaskStatus.IN_PROGRESS:
            self.notify("Start is available only for AUTO tasks in IN_PROGRESS", severity="warning")
            return
        await self._submit_runtime_action(
            action="start_agent",
            pending_msg=self.START_JOB_PENDING_MESSAGE,
            failure_msg="Failed to start agent",
            success_msg="Starting agent...",
        )

    async def _auto_start_if_needed(self) -> None:
        with contextlib.suppress(Exception):
            await self.ctx.api.reconcile_running_tasks([self._task_model.id])
        runtime_view = self.ctx.api.get_runtime_view(self._task_model.id)
        if self._state_bool(runtime_view, "is_running") or self._state_bool(
            runtime_view, "is_pending"
        ):
            return
        await self.action_start_agent_output()

    async def action_stop_agent_output(self) -> None:
        if self._task_model.task_type is not TaskType.AUTO:
            return
        if self._task_model.status is not TaskStatus.IN_PROGRESS:
            self.notify("Stop is available only for AUTO tasks in IN_PROGRESS", severity="warning")
            return
        await self._submit_runtime_action(
            action="stop_agent",
            pending_msg=self.STOP_JOB_PENDING_MESSAGE,
            failure_msg="Failed to stop agent",
            success_msg="Stopping agent...",
        )

    async def _submit_runtime_action(
        self,
        *,
        action: str,
        pending_msg: str,
        failure_msg: str,
        success_msg: str,
    ) -> None:
        submitted = await self.ctx.api.submit_job(self._task_model.id, action)
        terminal = await self.ctx.api.wait_job(
            submitted.job_id,
            task_id=self._task_model.id,
            timeout_seconds=0.6,
        )
        payload = job_result_payload(terminal)
        if payload is None:
            self.notify(pending_msg, severity="information")
        elif terminal is not None and terminal.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
            self.notify(job_message(terminal, failure_msg), severity="warning")
        else:
            self.notify(success_msg, severity="information")
        await self._refresh_runtime_state()

    def action_close(self) -> None:
        self.dismiss(None)


class TaskOutputChatOverlay(ChatOverlay):
    """Task Output variant: Escape closes the Task Output screen."""

    _TASK_STREAM_CONNECTING_MESSAGE = "Connecting to agent output stream in a task..."

    def show_for_task(self, task: object, *, fullscreen: bool = False) -> None:
        """Prime output stream UI before async session sync begins."""
        self._show_output()
        super().show_for_task(task, fullscreen=fullscreen)
        self._run_overlay_worker(
            self._post_task_stream_connecting_note_if_needed(),
            group="task-output-stream-connect-note",
            exclusive=True,
        )

    async def _post_task_stream_connecting_note_if_needed(self) -> None:
        existing_output = self.output.get_text_content().lower()
        if self._TASK_STREAM_CONNECTING_MESSAGE.lower() in existing_output:
            return
        await self.output.post_note(self._TASK_STREAM_CONNECTING_MESSAGE, classes="info")

    async def _activate(self) -> None:
        """Prioritize AUTO stream attach; warm the orchestrator agent in background."""
        self._update_status("ready", self._ready_hint(self._active_target()))
        self._focus_chat_input()
        self.call_after_refresh(self._focus_chat_input)
        await self._refresh_chat_targets()
        self._discover_local_skills()
        self._run_overlay_worker(
            self._ensure_agent(),
            group="chat-overlay-activate-agent",
            exclusive=True,
        )

    def action_escape_overlay(self) -> None:
        if not self.has_class("visible"):
            return
        close_action = getattr(self.screen, "action_close", None)
        if callable(close_action):
            close_action()
            return
        super().action_escape_overlay()
