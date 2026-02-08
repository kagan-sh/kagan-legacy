from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.constants import NOTIFICATION_TITLE_MAX_LENGTH
from kagan.core.models.enums import (
    CardIndicator,
    RejectionAction,
    ReviewResult,
    TaskStatus,
    TaskType,
)
from kagan.core.time import utc_now
from kagan.ui.screen_result import await_screen_result
from kagan.ui.screens.kanban import focus

if TYPE_CHECKING:
    from kagan.adapters.db.schema import Task
    from kagan.services.runtime import AutoOutputReadiness
    from kagan.ui.screens.kanban.screen import KanbanScreen
    from kagan.ui.widgets.card import TaskCard


class KanbanReviewController:
    def __init__(self, screen: KanbanScreen) -> None:
        self.screen = screen

    def get_review_task(self, card: TaskCard | None) -> Task | None:
        if not card or not card.task_model:
            return None
        if card.task_model.status != TaskStatus.REVIEW:
            self.screen.notify("Task is not in REVIEW", severity="warning")
            return None
        return card.task_model

    async def action_merge_direct(self) -> None:
        task = self.get_review_task(focus.get_focused_card(self.screen))
        if not task:
            return
        if self.screen.ctx.merge_service and await self.screen.ctx.merge_service.has_no_changes(
            task
        ):
            await self.confirm_close_no_changes(task)
            return
        await self.execute_merge(
            task,
            success_msg=f"Merged: {task.title}",
            track_failures=True,
        )

    async def action_rebase(self) -> None:
        task = self.get_review_task(focus.get_focused_card(self.screen))
        if not task:
            return
        base = task.base_branch or self.screen.ctx.config.general.default_base_branch
        self.screen.notify("Rebasing... (this may take a few seconds)", severity="information")
        success, message, conflict_files = await self.screen.ctx.workspace_service.rebase_onto_base(
            task.id, base
        )
        if success:
            self.screen.notify(f"Rebased: {task.title}", severity="information")
        elif conflict_files:
            await self.handle_rebase_conflict(task, base, conflict_files)
        else:
            self.screen.notify(f"Rebase failed: {message}", severity="error")

    async def handle_rebase_conflict(
        self, task: Task, base_branch: str, conflict_files: list[str]
    ) -> None:
        from kagan.agents.conflict_instructions import build_conflict_resolution_instructions

        await self.screen.ctx.workspace_service.abort_rebase(task.id)

        workspaces = await self.screen.ctx.workspace_service.list_workspaces(task_id=task.id)
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
        await self.screen.ctx.task_service.update_fields(task.id, description=new_desc)

        await self.screen.ctx.task_service.move(task.id, TaskStatus.IN_PROGRESS)

        if task.task_type == TaskType.AUTO:
            refreshed = await self.screen.ctx.task_service.get_task(task.id)
            if refreshed:
                await self.screen.ctx.automation_service.spawn_for_task(refreshed)

        self.screen._merge_failed_tasks.add(task.id)

        await self.screen._board.refresh_and_sync()
        n_files = len(conflict_files)
        self.screen.notify(
            f"Rebase conflict: {n_files} file(s). Task moved to IN_PROGRESS.",
            severity="warning",
        )

    async def move_task(self, forward: bool) -> None:
        card = focus.get_focused_card(self.screen)
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
                if (
                    self.screen.ctx.merge_service
                    and await self.screen.ctx.merge_service.has_no_changes(task)
                ):
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

            await self.screen.ctx.task_service.move(task.id, new_status)
            await self.screen._board.refresh_board()
            self.screen.notify(f"Moved #{task.id} to {new_status.value}")
            focus.focus_column(self.screen, new_status)
        else:
            self.screen.notify(
                f"Already in {'final' if forward else 'first'} status",
                severity="warning",
            )

    async def on_merge_confirmed(self, task: Task) -> None:
        from kagan.ui.modals import ConfirmModal

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

    async def on_close_confirmed(self, task: Task) -> None:
        from kagan.ui.modals import ConfirmModal

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
        success, message = (
            await self.screen.ctx.merge_service.close_exploratory(pending_task)
            if self.screen.ctx.merge_service
            else (False, "")
        )
        if success:
            await self.screen._board.refresh_board()
            self.screen.notify(f"Closed (no changes): {pending_task.title}")
            return
        self.screen.notify(message, severity="error")

    async def on_advance_confirmed(self, task: Task) -> None:
        from kagan.ui.modals import ConfirmModal

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
        await self.screen.ctx.task_service.update_fields(pending_task.id, status=TaskStatus.REVIEW)
        await self.screen._board.refresh_board()
        self.screen.notify(f"Moved #{pending_task.id} to REVIEW")
        focus.focus_column(self.screen, TaskStatus.REVIEW)

    async def on_auto_move_confirmed(self, task: Task, new_status: TaskStatus) -> None:
        from kagan.ui.modals import ConfirmModal

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

        was_running = await self.screen.ctx.automation_service.stop_task(pending_task.id)
        self.screen._board.set_card_indicator(pending_task.id, CardIndicator.IDLE, is_active=False)

        await self.screen.ctx.task_service.move(pending_task.id, pending_status)
        await self.screen._board.refresh_board()
        if was_running:
            self.screen.notify(
                f"Moved #{pending_task.id} to {pending_status.value} (agent stopped)"
            )
        else:
            self.screen.notify(f"Moved #{pending_task.id} to {pending_status.value}")
        focus.focus_column(self.screen, pending_status)

    async def action_merge(self) -> None:
        task = self.get_review_task(focus.get_focused_card(self.screen))
        if not task:
            return
        if self.screen.ctx.merge_service and await self.screen.ctx.merge_service.has_no_changes(
            task
        ):
            await self.confirm_close_no_changes(task)
            return
        await self.execute_merge(task, success_msg=f"Merged and completed: {task.title}")

    async def action_view_diff(self) -> None:
        from kagan.ui.modals import DiffModal

        task = self.get_review_task(focus.get_focused_card(self.screen))
        if not task:
            return
        title = f"Diff: {task.short_id} {task.title[:NOTIFICATION_TITLE_MAX_LENGTH]}"
        workspace_service = self.screen.ctx.workspace_service
        workspaces = await workspace_service.list_workspaces(task_id=task.id)

        if not workspaces or self.screen.ctx.diff_service is None:
            base = self.screen.kagan_app.config.general.default_base_branch
            diff_text = await workspace_service.get_diff(task.id, base_branch=base)  # type: ignore[misc]
            result = await await_screen_result(
                self.screen.app, DiffModal(title=title, diff_text=diff_text, task=task)
            )
            await self.on_diff_result(task, result)
            return

        diffs = await self.screen.ctx.diff_service.get_all_diffs(workspaces[0].id)
        result = await await_screen_result(
            self.screen.app, DiffModal(title=title, diffs=diffs, task=task)
        )
        await self.on_diff_result(task, result)

    async def on_diff_result(self, task: Task, result: str | None) -> None:
        if result == ReviewResult.APPROVE:
            if self.screen.ctx.merge_service and await self.screen.ctx.merge_service.has_no_changes(
                task
            ):
                await self.confirm_close_no_changes(task)
                return
            await self.execute_merge(task, success_msg=f"Merged: {task.title}")
        elif result == ReviewResult.REJECT:
            await self.handle_reject_with_feedback(task)

    async def action_open_review(self) -> None:
        task = self.get_review_task(focus.get_focused_card(self.screen))
        if not task:
            return
        await self.open_review_for_task(task)

    async def open_review_for_task(
        self,
        task: Task,
        *,
        read_only: bool = False,
        initial_tab: str | None = None,
        include_running_output: bool = False,
        auto_output_readiness: AutoOutputReadiness | None = None,
    ) -> None:
        from kagan.ui.modals import ReviewModal

        agent_config = task.get_agent_config(self.screen.kagan_app.config)
        task_id = task.id
        is_auto = task.task_type == TaskType.AUTO
        runtime_service = self.screen.ctx.runtime_service
        runtime_view = runtime_service.get(task.id) if is_auto else None

        if is_auto:
            execution_id = runtime_view.execution_id if runtime_view is not None else None
            run_count = runtime_view.run_count if runtime_view is not None else 0
            is_running = runtime_view.is_running if runtime_view is not None else False
            is_reviewing = runtime_view.is_reviewing if runtime_view is not None else False
            review_agent = runtime_view.review_agent if runtime_view is not None else None
        else:
            execution_id = None
            run_count = 0
            is_running = False
            is_reviewing = False
            review_agent = None

        running_agent = None
        if is_auto and include_running_output:
            running_agent = runtime_view.running_agent if runtime_view is not None else None
            if running_agent is None:
                running_agent = self.screen.ctx.automation_service.get_running_agent(task.id)
            if running_agent is not None:
                is_running = True
        if is_auto and auto_output_readiness is not None:
            if auto_output_readiness.execution_id is not None:
                execution_id = auto_output_readiness.execution_id
            is_running = auto_output_readiness.is_running
            if include_running_output and auto_output_readiness.running_agent is not None:
                running_agent = auto_output_readiness.running_agent
        if running_agent is not None:
            is_running = True

        if execution_id is None:
            latest = await self.screen.ctx.execution_service.get_latest_execution_for_task(task.id)
            if latest is not None:
                execution_id = latest.id
                if run_count == 0:
                    run_count = await self.screen.ctx.execution_service.count_executions_for_task(
                        task.id
                    )

        result = await await_screen_result(
            self.screen.app,
            ReviewModal(
                task=task,
                worktree_manager=self.screen.ctx.workspace_service,
                agent_config=agent_config,
                base_branch=self.screen.kagan_app.config.general.default_base_branch,
                agent_factory=self.screen.kagan_app._agent_factory,
                execution_service=self.screen.ctx.execution_service,
                execution_id=execution_id,
                run_count=run_count,
                running_agent=running_agent,
                review_agent=review_agent,
                is_reviewing=is_reviewing,
                is_running=is_running,
                read_only=read_only,
                initial_tab=initial_tab
                or (
                    "review-ai"
                    if is_auto and task.status == TaskStatus.REVIEW
                    else "review-summary"
                ),
            ),
        )
        await self.on_review_result(task_id, result)

    async def on_review_result(self, task_id: str, result: str | None) -> None:
        task = await self.screen.ctx.task_service.get_task(task_id)
        if not task:
            return

        if result == "rebase_conflict":
            base = task.base_branch or self.screen.ctx.config.general.default_base_branch
            (
                _success,
                _msg,
                conflict_files,
            ) = await self.screen.ctx.workspace_service.rebase_onto_base(task.id, base)
            await self.handle_rebase_conflict(task, base, conflict_files)
            return

        if task.status != TaskStatus.REVIEW:
            return
        if result == ReviewResult.APPROVE:
            if self.screen.ctx.merge_service and await self.screen.ctx.merge_service.has_no_changes(
                task
            ):
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
        task: Task,
        *,
        success_msg: str,
        track_failures: bool = False,
    ) -> bool:
        self.screen.notify("Merging... (this may take a few seconds)", severity="information")
        success, message = (
            await self.screen.ctx.merge_service.merge_task(task)
            if self.screen.ctx.merge_service
            else (False, "")
        )
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
    def format_merge_failure(task: Task, message: str) -> str:
        if task.task_type == TaskType.AUTO:
            return f"Merge failed (AUTO): {message}"
        return f"Merge failed (PAIR): {message}"

    async def confirm_close_no_changes(self, task: Task) -> None:
        await self.on_close_confirmed(task)

    async def handle_reject_with_feedback(self, task: Task) -> None:
        from kagan.ui.modals import RejectionInputModal

        result = await await_screen_result(self.screen.app, RejectionInputModal(task.title))
        await self.apply_rejection_result(task, result)

    async def apply_rejection_result(self, task: Task, result: tuple[str, str] | None) -> None:
        if self.screen.ctx.merge_service is None:
            return
        if result is None:
            await self.screen.ctx.merge_service.apply_rejection_feedback(
                task,
                None,
                RejectionAction.BACKLOG,
            )
            action = RejectionAction.BACKLOG
        else:
            feedback, action = result
            await self.screen.ctx.merge_service.apply_rejection_feedback(task, feedback, action)
        await self.screen._board.refresh_board()
        if action == RejectionAction.BACKLOG:
            self.screen.notify(f"Moved to BACKLOG: {task.title}")
        else:
            self.screen.notify(f"Returned to IN_PROGRESS: {task.title}")
