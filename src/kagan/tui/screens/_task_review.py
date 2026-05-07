from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING, cast

from textual.containers import Vertical
from textual.css.query import NoMatches
from textual.widgets import Checkbox, Static

from kagan.core.enums import StreamSource, TaskStatus
from kagan.core.errors import (
    KaganError,
    MergeConflictError,
    NotFoundError,
    PreflightError,
    SessionError,
    WorktreeError,
)
from kagan.tui.screens.confirm import ConfirmModal
from kagan.tui.screens.rejection_input import RejectionInputModal
from kagan.tui.widgets.task_detail_pane import TaskDetailPane
from kagan.tui.widgets.task_review_helpers import (
    build_merge_readiness_text,
    render_ai_verdict_summary,
    render_criteria_checkboxes,
)
from kagan.tui.widgets.task_workspace_helpers import diff_totals

if TYPE_CHECKING:
    from kagan.core.models import Task


class _TaskReviewMixin:
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
        if not self._review_approved:
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
            self._last_merge_blocker = "Preflight failed  \u2192  fix and retry"
            self._set_status(str(exc))
            self.app.notify(str(exc), severity="error")
            self._sync_merge_readiness()
            return
        except MergeConflictError as exc:
            self._last_merge_blocker = "Merge conflicts  \u2192  b to rebase"
            message = self._conflict_message(exc.conflict_files, prefix="Merge has conflicts")
            self._set_status(message)
            self.app.notify(message, severity="error")
            self._sync_merge_readiness()
            return
        except WorktreeError as exc:
            self._last_merge_blocker = f"Worktree error: {exc}"
            message = f"Unable to merge: {exc}"
            self._set_status(message)
            self.app.notify(message, severity="error")
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
            self._last_merge_blocker = "Rebase conflicts  \u2192  resolve and retry"
            conflicts = await self.kagan_app.core.reviews.conflicts(self._task_id)
            conflict_files = cast("list[str]", conflicts.get("conflicted_files", []))
            message = self._conflict_message(conflict_files, prefix=str(exc))
            self._set_status(message)
            self.app.notify(message, severity="error")
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
                "Cannot run AI review \u2014 no acceptance criteria defined",
                severity="warning",
            )
            return
        with contextlib.suppress(KaganError, OSError, RuntimeError):
            await self.kagan_app.core.reviews.clear_verdicts(self._task_id)
        backend = await self._resolve_backend(self._task_model)
        await self.kagan_app.core.tasks.run(self._task_id, agent_backend=backend)
        self._running = True
        self._set_stream_source(StreamSource.REVIEWER)
        self._set_status("AI Reviewing...")
        self.app.notify(
            "AI review started \u2014 open AI Overlay (o) to follow progress",
            severity="information",
        )

    async def _load_task_or_fail(self) -> Task | None:
        if self._task_id is None:
            return None

        try:
            task = await self.kagan_app.core.tasks.get(self._task_id)
            self._task_model = task
            self._review_approved = await asyncio.to_thread(
                self.kagan_app.core.reviews.is_approved, self._task_id
            )
            return task
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            self._set_status(f"Unable to load task: {exc}")
            return None

    async def _render_task_summary(self, task: Task) -> str:
        if self._review_approved:
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
                if self._review_approved:
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
                human_approved=self._review_approved,
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

    def _conflict_message(
        self, conflict_files: list[str], *, prefix: str = "Rebase has conflicts"
    ) -> str:
        if not conflict_files:
            return prefix
        joined = ", ".join(conflict_files[:3])
        more = "" if len(conflict_files) <= 3 else f" (+{len(conflict_files) - 3} more)"
        return f"{prefix}: {joined}{more}"
