from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

from kagan.core.constants import NOTIFICATION_TITLE_MAX_LENGTH
from kagan.core.domain.enums import (
    CardIndicator,
    RejectionAction,
    ReviewResult,
    TaskStatus,
    TaskType,
)
from kagan.core.services.jobs import JobStatus
from kagan.core.time import utc_now
from kagan.tui.ui.screen_result import await_screen_result
from kagan.tui.ui.utils import state_attr, state_bool, state_int, state_tuple

if TYPE_CHECKING:
    from kagan.core.services.runtime import AutoOutputReadiness
    from kagan.tui.ui.screens.kanban.screen import KanbanScreen
    from kagan.tui.ui.types import TaskView
    from kagan.tui.ui.widgets.card import TaskCard


log = logging.getLogger(__name__)


class KanbanReviewController:
    def __init__(self, screen: KanbanScreen) -> None:
        self.screen = screen

    @staticmethod
    def _state_attr(state: object | None, name: str, default: Any = None) -> Any:
        return state_attr(state, name, default)

    @staticmethod
    def _state_bool(state: object | None, name: str) -> bool:
        return state_bool(state, name)

    @staticmethod
    def _state_tuple(state: object | None, name: str) -> tuple[str, ...]:
        return state_tuple(state, name)

    @staticmethod
    def _state_int(state: object | None, name: str, default: int = 0) -> int:
        return state_int(state, name, default)

    @classmethod
    def _stream_target(cls, state: object | None, name: str) -> object | None:
        candidate = cls._state_attr(state, name)
        if callable(getattr(candidate, "set_message_target", None)):
            return candidate
        return None

    async def _resolve_base_branch(self, task: TaskView) -> str | None:
        try:
            return await self.screen.ctx.api.resolve_task_base_branch(task)
        except ValueError as exc:
            self.screen.notify(str(exc), severity="error")
            return None
        except RuntimeError as exc:
            self.screen.notify(str(exc), severity="error")
            return None

    def get_review_task(self, card: TaskCard | None) -> TaskView | None:
        if not card or not card.task_model:
            return None
        if card.task_model.status != TaskStatus.REVIEW:
            self.screen.notify(
                "Task is not in REVIEW. Move task to REVIEW before performing review actions.",
                severity="warning",
            )
            return None
        return card.task_model

    async def action_merge_direct(self) -> None:
        task = self.get_review_task(self.screen.get_focused_card())
        if not task:
            return
        if await self.screen.ctx.api.has_no_changes(task):
            await self.confirm_close_no_changes(task)
            return
        await self.execute_merge(
            task,
            success_msg=f"Merged: {task.title}",
            track_failures=True,
        )

    async def action_rebase(self) -> None:
        task = self.get_review_task(self.screen.get_focused_card())
        if not task:
            return
        base = await self._resolve_base_branch(task)
        if base is None:
            return
        self.screen.notify("Rebasing... (this may take a few seconds)", severity="information")
        (
            success,
            message,
            conflict_files,
        ) = await self.screen.ctx.api.rebase_workspace(task.id, base)
        if success:
            self.screen.notify(f"Rebased: {task.title}", severity="information")
        elif conflict_files:
            await self.handle_rebase_conflict(task, base, conflict_files)
        else:
            self.screen.notify(f"Rebase failed: {message}", severity="error")

    async def handle_rebase_conflict(
        self, task: TaskView, base_branch: str, conflict_files: list[str]
    ) -> None:
        from kagan.core.agents.prompt_builders import build_conflict_resolution_instructions

        await self.screen.ctx.api.abort_workspace_rebase(task.id)

        workspaces = await self.screen.ctx.api.list_workspaces(task_id=task.id)
        branch_name = workspaces[0].branch_name if workspaces else f"task-{task.short_id}"
        instructions = build_conflict_resolution_instructions(
            source_branch=branch_name,
            target_branch=base_branch,
            conflict_files=conflict_files,
        )

        timestamp = utc_now().strftime("%Y-%m-%d %H:%M")
        separator = f"\n\n---\n_Rebase conflict detected ({timestamp}):_\n\n"
        current_desc = task.description or ""
        new_desc = current_desc + separator + instructions
        await self.screen.ctx.api.update_task(task.id, description=new_desc)

        await self.screen.ctx.api.move_task(task.id, TaskStatus.IN_PROGRESS)

        if task.task_type == TaskType.AUTO:
            refreshed = await self.screen.ctx.api.get_task(task.id)
            if refreshed:
                submitted = await self.screen.ctx.api.submit_job(
                    refreshed.id,
                    "start_agent",
                )
                terminal = await self.screen._session.wait_for_job_terminal(
                    submitted.job_id,
                    task_id=refreshed.id,
                )
                payload = self.screen._session.job_result_payload(terminal)
                failed = payload is not None and not bool(payload.get("success", False))
                cancelled_or_failed = terminal is not None and terminal.status in {
                    JobStatus.FAILED,
                    JobStatus.CANCELLED,
                }
                if failed or cancelled_or_failed:
                    self.screen.notify(
                        self.screen._session.job_message(
                            terminal, "Failed to restart AUTO agent after conflict"
                        ),
                        severity="warning",
                    )
                elif payload is None:
                    self.screen.notify(
                        self.screen._session.START_JOB_PENDING_MESSAGE,
                        severity="information",
                    )

        self.screen._merge_failed_tasks.add(task.id)

        await self.screen._board.refresh_and_sync()
        n_files = len(conflict_files)
        self.screen.notify(
            f"Rebase conflict: {n_files} file(s). Task moved to IN_PROGRESS.",
            severity="warning",
        )

    async def move_task(self, forward: bool) -> None:
        card = self.screen.get_focused_card()
        if not card or not card.task_model:
            return
        task = card.task_model
        status = task.status
        task_type = task.task_type

        new_status = TaskStatus.next_status(status) if forward else TaskStatus.prev_status(status)
        if new_status:
            if status == TaskStatus.IN_PROGRESS and task_type == TaskType.AUTO:
                await self.on_auto_move_confirmed(task, new_status)
                return

            if status == TaskStatus.REVIEW and new_status == TaskStatus.DONE:
                if await self.screen.ctx.api.has_no_changes(task):
                    await self.confirm_close_no_changes(task)
                    return
                await self.on_merge_confirmed(task)
                return

            if (
                status == TaskStatus.IN_PROGRESS
                and task_type == TaskType.PAIR
                and new_status == TaskStatus.REVIEW
            ):
                await self.on_advance_confirmed(task)
                return

            if (
                task_type == TaskType.AUTO
                and status == TaskStatus.IN_PROGRESS
                and new_status != TaskStatus.REVIEW
            ):
                self.screen._board.set_card_indicator(task.id, CardIndicator.IDLE, is_active=False)

            await self.screen.ctx.api.move_task(task.id, new_status)
            await self.screen._board.refresh_board()
            self.screen.notify(f"Moved #{task.id} to {new_status.value}")
            self.screen.focus_column(new_status)
        else:
            self.screen.notify(
                f"Already in {'final' if forward else 'first'} status",
                severity="warning",
            )

    async def on_merge_confirmed(self, task: TaskView) -> None:
        from kagan.tui.ui.modals import ConfirmModal

        self.screen._ui_state.pending_merge_task = task
        title = task.title[:NOTIFICATION_TITLE_MAX_LENGTH]
        confirmed = await await_screen_result(
            self.screen.app,
            ConfirmModal(
                title="Complete Task?",
                message=f"Merge '{title}' and move to DONE?",
            ),
        )
        pending_task = self.screen._ui_state.pending_merge_task
        self.screen._ui_state.pending_merge_task = None
        if not confirmed or pending_task is None:
            return
        await self.execute_merge(
            pending_task,
            success_msg=f"Merged and completed: {pending_task.title}",
            track_failures=True,
        )

    async def on_close_confirmed(self, task: TaskView) -> None:
        from kagan.tui.ui.modals import ConfirmModal

        self.screen._ui_state.pending_close_task = task
        title = task.title[:NOTIFICATION_TITLE_MAX_LENGTH]
        confirmed = await await_screen_result(
            self.screen.app,
            ConfirmModal(
                title="No Changes Detected",
                message=f"Mark '{title}' as DONE and archive the workspace?",
            ),
        )
        pending_task = self.screen._ui_state.pending_close_task
        self.screen._ui_state.pending_close_task = None
        if not confirmed or pending_task is None:
            return
        success, message = await self.screen.ctx.api.close_exploratory(pending_task)
        if success:
            await self.screen._board.refresh_board()
            self.screen.notify(f"Closed (no changes): {pending_task.title}")
            return
        self.screen.notify(message, severity="error")

    async def on_advance_confirmed(self, task: TaskView) -> None:
        from kagan.tui.ui.modals import ConfirmModal

        self.screen._ui_state.pending_advance_task = task
        title = task.title[:NOTIFICATION_TITLE_MAX_LENGTH]
        confirmed = await await_screen_result(
            self.screen.app,
            ConfirmModal(title="Advance to Review?", message=f"Move '{title}' to REVIEW?"),
        )
        pending_task = self.screen._ui_state.pending_advance_task
        self.screen._ui_state.pending_advance_task = None
        if not confirmed or pending_task is None:
            return
        await self.screen.ctx.api.update_task(pending_task.id, status=TaskStatus.REVIEW)
        await self.screen._board.refresh_board()
        self.screen.notify(f"Moved #{pending_task.id} to REVIEW")
        self.screen.focus_column(TaskStatus.REVIEW)

    async def on_auto_move_confirmed(self, task: TaskView, new_status: TaskStatus) -> None:
        """Handle auto move confirmed event."""
        from kagan.tui.ui.modals import ConfirmModal

        self.screen._ui_state.pending_auto_move_task = task
        self.screen._ui_state.pending_auto_move_status = new_status
        title = task.title[:NOTIFICATION_TITLE_MAX_LENGTH]
        destination = new_status.value.upper()
        confirmed = await await_screen_result(
            self.screen.app,
            ConfirmModal(
                title="Stop Agent and Move Task?",
                message=f"Stop agent, keep worktree/logs, and move '{title}' to {destination}?",
            ),
        )
        pending_task = self.screen._ui_state.pending_auto_move_task
        pending_status = self.screen._ui_state.pending_auto_move_status
        self.screen._ui_state.pending_auto_move_task = None
        self.screen._ui_state.pending_auto_move_status = None
        if not confirmed or pending_task is None or pending_status is None:
            return

        submitted = await self.screen.ctx.api.submit_job(
            pending_task.id,
            "stop_agent",
        )
        terminal = await self.screen._session.wait_for_job_terminal(
            submitted.job_id,
            task_id=pending_task.id,
        )
        payload = self.screen._session.job_result_payload(terminal)
        if payload is None:
            self.screen.notify(
                self.screen._session.STOP_JOB_PENDING_MESSAGE,
                severity="information",
            )
            return
        elif terminal is not None and terminal.status in {JobStatus.FAILED, JobStatus.CANCELLED}:
            self.screen.notify(
                self.screen._session.job_message(terminal, "No running agent for this task"),
                severity="warning",
            )
            return
        runtime = payload.get("runtime") if isinstance(payload, dict) else None
        runtime_running = isinstance(runtime, dict) and bool(runtime.get("is_running", False))
        if runtime_running or self.screen.ctx.api.is_automation_running(pending_task.id):
            self.screen.notify(self.screen._session.job_message(terminal, "Agent stop queued"))
            return
        was_running = bool(payload.get("success", False)) if payload is not None else False
        self.screen._board.set_card_indicator(pending_task.id, CardIndicator.IDLE, is_active=False)

        await self.screen.ctx.api.move_task(pending_task.id, pending_status)
        await self.screen._board.refresh_board()
        if was_running:
            self.screen.notify(
                f"Moved #{pending_task.id} to {pending_status.value} (agent stopped)"
            )
        else:
            self.screen.notify(f"Moved #{pending_task.id} to {pending_status.value}")
        self.screen.focus_column(pending_status)

    async def action_merge(self) -> None:
        task = self.get_review_task(self.screen.get_focused_card())
        if not task:
            return
        if await self.screen.ctx.api.has_no_changes(task):
            await self.confirm_close_no_changes(task)
            return
        await self.execute_merge(task, success_msg=f"Merged and completed: {task.title}")

    async def action_view_diff(self) -> None:
        from kagan.tui.ui.modals import DiffModal

        task = self.get_review_task(self.screen.get_focused_card())
        if not task:
            return
        title = f"Diff: {task.short_id} {task.title[:NOTIFICATION_TITLE_MAX_LENGTH]}"
        workspaces = await self.screen.ctx.api.list_workspaces(task_id=task.id)

        if not workspaces:
            base = await self._resolve_base_branch(task)
            if base is None:
                return
            diff_text = await self.screen.ctx.api.get_workspace_diff(task.id, base_branch=base)
            result = await await_screen_result(
                self.screen.app, DiffModal(title=title, diff_text=diff_text, task=task)
            )
            await self.on_diff_result(task, result)
            return

        try:
            diffs = await self.screen.ctx.api.get_all_diffs(workspaces[0].id)
        except RuntimeError:
            base = await self._resolve_base_branch(task)
            if base is None:
                return
            diff_text = await self.screen.ctx.api.get_workspace_diff(task.id, base_branch=base)
            result = await await_screen_result(
                self.screen.app, DiffModal(title=title, diff_text=diff_text, task=task)
            )
            await self.on_diff_result(task, result)
            return

        result = await await_screen_result(
            self.screen.app,
            DiffModal(title=title, diffs=diffs, task=task),
        )
        await self.on_diff_result(task, result)

    async def on_diff_result(self, task: TaskView, result: str | None) -> None:
        if result == ReviewResult.APPROVE:
            if await self.screen.ctx.api.has_no_changes(task):
                await self.confirm_close_no_changes(task)
                return
            await self.execute_merge(task, success_msg=f"Merged: {task.title}")
        elif result == ReviewResult.REJECT:
            await self.handle_reject_with_feedback(task)

    async def action_open_review(self) -> None:
        task = self.get_review_task(self.screen.get_focused_card())
        if not task:
            return
        await self.open_task_output_for_task(task)

    async def open_task_output_for_task(
        self,
        task: TaskView,
        *,
        read_only: bool = False,
        initial_tab: str | None = None,
        include_running_output: bool = False,
        auto_output_readiness: AutoOutputReadiness | None = None,
        auto_start_requested: bool = False,
    ) -> None:
        """Open the dedicated task output screen with stats + chat overlay."""
        from kagan.tui.ui.screens import TaskOutputScreen

        del initial_tab, include_running_output, auto_output_readiness
        resolved_base_branch = await self._resolve_base_branch(task)
        if resolved_base_branch is None:
            return

        await await_screen_result(
            self.screen.app,
            TaskOutputScreen(
                task=task,
                base_branch=resolved_base_branch,
                auto_start_requested=auto_start_requested and not read_only,
            ),
        )
        await self.screen._board.refresh_board()
        self.screen._board.sync_agent_states()

    async def on_review_result(self, task_id: str, result: str | None) -> None:
        task = await self.screen.ctx.api.get_task(task_id)
        if not task:
            return

        if result == "rebase_conflict":
            base = await self._resolve_base_branch(task)
            if base is None:
                return
            (
                _success,
                _msg,
                conflict_files,
            ) = await self.screen.ctx.api.rebase_workspace(task.id, base)
            await self.handle_rebase_conflict(task, base, conflict_files)
            return

        if task.status != TaskStatus.REVIEW:
            return
        if result == ReviewResult.APPROVE:
            if await self.screen.ctx.api.has_no_changes(task):
                await self.confirm_close_no_changes(task)
                return
            await self.execute_merge(
                task,
                success_msg=f"Merged and completed: {task.title}",
                track_failures=True,
            )
        elif result == ReviewResult.EXPLORATORY:
            await self.confirm_close_no_changes(task)
        elif result == ReviewResult.REJECT:
            await self.handle_reject_with_feedback(task)

    async def execute_merge(
        self,
        task: TaskView,
        *,
        success_msg: str,
        track_failures: bool = False,
    ) -> bool:
        self.screen.notify("Merging... (this may take a few seconds)", severity="information")
        try:
            success, message = await self.screen.ctx.api.merge_task_direct(task)
        except RuntimeError as exc:
            log.error("Merge failed for task %s: %s", task.id, exc)
            if track_failures:
                self.screen._merge_failed_tasks.add(task.id)
                self.screen._board.sync_agent_states()
            self.screen.notify(f"Merge error: {exc}", severity="error")
            return False
        except (OSError, ConnectionError) as exc:  # quality-allow-broad-except
            log.error("Merge transport error for task %s: %s", task.id, exc)
            if track_failures:
                self.screen._merge_failed_tasks.add(task.id)
                self.screen._board.sync_agent_states()
            self.screen.notify(f"Merge connection error: {exc}", severity="error")
            return False
        if success:
            if track_failures:
                self.screen._merge_failed_tasks.discard(task.id)
            await self.screen._board.refresh_board()
            self.screen.notify(success_msg, severity="information")
        else:
            if track_failures:
                self.screen._merge_failed_tasks.add(task.id)
                self.screen._board.sync_agent_states()
            self.screen.notify(self.format_merge_failure(task, message), severity="error")
        return success

    @staticmethod
    def format_merge_failure(task: TaskView, message: str) -> str:
        """Format merge failure."""
        if task.task_type == TaskType.AUTO:
            return f"Merge failed (AUTO): {message}"
        return f"Merge failed (PAIR): {message}"

    async def confirm_close_no_changes(self, task: TaskView) -> None:
        await self.on_close_confirmed(task)

    async def handle_reject_with_feedback(self, task: TaskView) -> None:
        from kagan.tui.ui.modals import RejectionInputModal

        result = await await_screen_result(self.screen.app, RejectionInputModal(task.title))
        await self.apply_rejection_result(task, result)

    async def apply_rejection_result(self, task: TaskView, result: tuple[str, str] | None) -> None:
        if result is None:
            await self.screen.ctx.api.apply_rejection_feedback(
                task,
                None,
                RejectionAction.BACKLOG,
            )
            resolved_action = RejectionAction.BACKLOG
        else:
            feedback, action = result
            await self.screen.ctx.api.apply_rejection_feedback(task, feedback, action)
            resolved_action = (
                RejectionAction.BACKLOG
                if action == RejectionAction.BACKLOG
                else RejectionAction.IN_PROGRESS
            )
        await self.screen._board.refresh_board()
        if resolved_action == RejectionAction.BACKLOG:
            self.screen.notify(f"Moved to BACKLOG: {task.title}")
        else:
            self.screen.notify(f"Returned to IN_PROGRESS: {task.title}")
            refreshed = await self.screen.ctx.api.get_task(task.id)
            if refreshed is not None and refreshed.task_type == TaskType.AUTO:
                await self.screen._session.start_agent_flow(refreshed)
