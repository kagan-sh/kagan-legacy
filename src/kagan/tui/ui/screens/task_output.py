"""Dedicated AUTO task output screen with split stats and live chat overlay."""

from __future__ import annotations

import contextlib
from typing import TYPE_CHECKING, Any

from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Label, Rule, Static

from kagan.core.constants import MODAL_TITLE_MAX_LENGTH
from kagan.core.domain.enums import TaskType
from kagan.core.services.jobs import JobStatus
from kagan.tui.keybindings import TASK_OUTPUT_BINDINGS
from kagan.tui.ui.screens.base import KaganScreen
from kagan.tui.ui.utils.job_results import job_message, job_result_payload
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer

    from kagan.tui.ui.types import TaskView


class TaskOutputScreen(KaganScreen):
    """Show task stats on top and the standard orchestrator overlay on the lower half."""

    BINDINGS = TASK_OUTPUT_BINDINGS

    _OUTPUT_LAYOUT_SPLIT = "split"
    _OUTPUT_LAYOUT_FULLSCREEN = "fullscreen"
    START_JOB_PENDING_MESSAGE = "Agent start requested; waiting for scheduler."
    STOP_JOB_PENDING_MESSAGE = "Agent stop requested; waiting for scheduler."

    def __init__(self, task: TaskView, base_branch: str = "main", **kwargs) -> None:
        super().__init__(**kwargs)
        self._task_model = task
        self._base_branch = base_branch
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
                yield Static("[dim]Loading diff stats...[/dim]", id="task-output-diff-stats")
                yield Static("[dim]Loading changed files...[/dim]", id="task-output-files")
            yield TaskOutputChatOverlay(
                agent_factory=self.kagan_app._agent_factory,
                id="task-output-chat-overlay",
            )

    async def on_mount(self) -> None:
        self._refresh_header_labels()
        overlay = self._overlay()
        overlay.set_target_scope(self._task_model.id)
        overlay.show_for_task(self._task_model, fullscreen=False)
        self._sync_overlay_layout_class()
        self._runtime_poll_timer = self.set_interval(1.0, self._schedule_runtime_refresh)
        self.run_worker(
            self._hydrate_top_panel(),
            group="task-output-hydrate",
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
        stats_text = ""
        try:
            stats_text = await self.ctx.api.get_workspace_diff_stats(
                self._task_model.id,
                base_branch=self._base_branch,
            )
        except RuntimeError:
            stats_text = ""
        with contextlib.suppress(NoMatches):
            self.query_one("#task-output-diff-stats", Static).update(
                f"[bold]Diff Stats:[/bold]\n{stats_text}" if stats_text else "[dim](No diff)[/dim]"
            )

        files_text = await self._load_changed_files_text()
        with contextlib.suppress(NoMatches):
            self.query_one("#task-output-files", Static).update(files_text)

    async def _load_changed_files_text(self) -> str:
        try:
            workspaces = await self.ctx.api.list_workspaces(task_id=self._task_model.id)
        except RuntimeError:
            return "[dim](Unable to load changed files)[/dim]"
        if not workspaces:
            return "[dim](No workspace yet)[/dim]"

        workspace_id = str(self._state_attr(workspaces[0], "id", "")).strip()
        if not workspace_id:
            return "[dim](No workspace yet)[/dim]"

        try:
            repo_diffs = await self.ctx.api.get_all_diffs(workspace_id)
        except RuntimeError:
            return "[dim](Unable to load changed files)[/dim]"

        lines: list[str] = []
        for repo_diff in repo_diffs or []:
            file_diffs = self._state_attr(repo_diff, "files", [])
            if not isinstance(file_diffs, list):
                continue
            for file_diff in file_diffs:
                path = str(self._state_attr(file_diff, "path", "")).strip()
                if not path:
                    continue
                additions = self._state_attr(file_diff, "additions", 0)
                deletions = self._state_attr(file_diff, "deletions", 0)
                lines.append(f"- {path} (+{additions}/-{deletions})")
        if not lines:
            return "[dim](No changed files)[/dim]"

        max_lines = 12
        visible = lines[:max_lines]
        remaining = len(lines) - len(visible)
        if remaining > 0:
            visible.append(f"[dim]... {remaining} more file(s)[/dim]")
        return "[bold]Files Changed:[/bold]\n" + "\n".join(visible)

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

    def action_cycle_output_layout(self) -> None:
        """Backward-compatible alias for fullscreen toggle."""
        self.action_open_chat_fullscreen()

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
        await self._submit_runtime_action(
            action="start_agent",
            pending_msg=self.START_JOB_PENDING_MESSAGE,
            failure_msg="Failed to start agent",
            success_msg="Starting agent...",
        )

    async def action_stop_agent_output(self) -> None:
        if self._task_model.task_type is not TaskType.AUTO:
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

    def action_escape_overlay(self) -> None:
        if not self.has_class("visible"):
            return
        close_action = getattr(self.screen, "action_close", None)
        if callable(close_action):
            close_action()
            return
        super().action_escape_overlay()
