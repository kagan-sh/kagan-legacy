"""ReviewModal action methods — extracted mixin."""

from __future__ import annotations

import asyncio
import contextlib
import re
from typing import TYPE_CHECKING, Any, Literal

from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import (
    Button,
    DataTable,
    LoadingIndicator,
    RichLog,
    Static,
    TabbedContent,
)

from kagan.core.constants import MODAL_TITLE_MAX_LENGTH
from kagan.core.domain.enums import StreamPhase, TaskStatus, TaskType
from kagan.core.services.jobs import JobRecord, JobStatus
from kagan.tui.ui.utils.helpers import colorize_diff_line, copy_with_notification

if TYPE_CHECKING:
    from kagan.core.services.workspaces import RepoDiff

DIFF_MODAL_APPROVE_RESULT: str = "approve"
DIFF_MODAL_REJECT_RESULT: str = "reject"


class ReviewActionsMixin:
    """Mixin providing action methods for ReviewModal.

    Expects the host class to supply:
    - ctx, _task_model, _base_branch, _phase, _read_only, _agent,
      _prompt_worker, _live_review_attached, _live_output_attached,
      _is_running, _diff_text, _diff_stats, _file_diffs,
      _pr_comments_loaded, _review_queue_pending, _no_changes
    - Methods: _state_set_decision, _state_set_phase,
      _stream_review_output_panel, _prompt_generate_review,
      _refresh_runtime_state, notify, dismiss, run_worker,
      query_one, app
    """

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    async def _actions_wait_for_job_terminal(
        self,
        job_id: str,
        *,
        task_id: str,
        timeout_seconds: float = 0.6,
    ) -> JobRecord | None:
        try:
            return await self.ctx.api.wait_job(  # type: ignore[attr-defined]
                job_id,
                task_id=task_id,
                timeout_seconds=timeout_seconds,
            )
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):  # quality-allow-broad-except
                await self.ctx.api.cancel_job(job_id, task_id=task_id)  # type: ignore[attr-defined]
            raise

    @staticmethod
    def _actions_job_result_payload(
        record: JobRecord | None,
    ) -> dict[str, Any] | None:
        if record is None or not isinstance(record.result, dict):
            return None
        return record.result

    @classmethod
    def _actions_job_message(cls, record: JobRecord | None, default: str) -> str:
        payload = cls._actions_job_result_payload(record)
        if payload is not None:
            payload_message = payload.get("message")
            if isinstance(payload_message, str) and payload_message.strip():
                return payload_message
        if record is not None and record.message:
            return record.message
        return default

    def _actions_job_result_message(
        self,
        terminal: JobRecord | None,
        *,
        failure_msg: str,
        success_msg: str,
        pending_msg: str,
    ) -> tuple[str, Literal["warning", "information"]]:
        """Return (message, severity) for job result."""
        payload = self._actions_job_result_payload(terminal)
        if payload is not None and not bool(payload.get("success", False)):
            return (
                self._actions_job_message(terminal, failure_msg),
                "warning",
            )
        if terminal is not None and terminal.status in {
            JobStatus.FAILED,
            JobStatus.CANCELLED,
        }:
            return (
                self._actions_job_message(terminal, failure_msg),
                "warning",
            )
        if payload is None:
            return (pending_msg, "information")
        return (
            self._actions_job_message(terminal, success_msg),
            "information",
        )

    def action_show_summary(self) -> None:
        """Switch to the summary tab."""
        self._actions_set_active_tab("review-summary")

    def action_show_diff(self) -> None:
        """Switch to the diff tab."""
        self._actions_set_active_tab("review-diff")

    def action_show_ai_review(self) -> None:
        """Switch to the review output tab."""
        self._actions_set_active_tab("review-ai")

    def action_show_agent_output(self) -> None:
        """Switch to the agent output tab."""
        self._actions_set_active_tab("review-agent-output")

    def action_show_pr_comments(self) -> None:
        """Switch to the PR comments tab and lazy-load if needed."""
        self._actions_set_active_tab("review-pr-comments")
        if not self._pr_comments_loaded:  # type: ignore[attr-defined]
            self._pr_comments_loaded = True  # type: ignore[attr-defined]
            self.run_worker(  # type: ignore[attr-defined]
                self._load_pr_comments,
                exclusive=True,
                exit_on_error=False,
            )

    def _actions_set_active_tab(self, tab_id: str) -> None:
        tabs = self.query_one("#review-tabs", TabbedContent)  # type: ignore[attr-defined]
        tabs.active = tab_id

    @staticmethod
    def _actions_parse_diff_modal_result(
        result: object,
    ) -> str | None:
        if result == DIFF_MODAL_APPROVE_RESULT:
            return DIFF_MODAL_APPROVE_RESULT
        if result == DIFF_MODAL_REJECT_RESULT:
            return DIFF_MODAL_REJECT_RESULT
        return None

    def _diff_populate_commits(self, commits: list[str]) -> None:
        table = self.query_one("#commits-table", DataTable)  # type: ignore[attr-defined]
        table.clear()
        if not table.columns:
            table.add_columns("Repo", "Hash", "Message")
        table.cursor_type = "row"
        table.zebra_stripes = True

        if not commits:
            table.add_row("—", "—", "No commits found")
            return

        for line in commits:
            repo, sha, message = self._diff_parse_commit_line(line)
            table.add_row(repo or "—", sha or "—", message or "—")

    async def _diff_populate_pane(self, workspaces: list) -> None:  # type: ignore[type-arg]
        if workspaces:
            try:
                diffs = await self.ctx.api.get_all_diffs(workspaces[0].id)  # type: ignore[attr-defined]
            except RuntimeError:
                diffs = None
            if diffs is not None:
                self._diff_populate_file_table(diffs)
                total_additions = sum(diff.total_additions for diff in diffs)
                total_deletions = sum(diff.total_deletions for diff in diffs)
                total_files = sum(len(diff.files) for diff in diffs)
                self._diff_set_stats(total_additions, total_deletions, total_files)
                return

        total_additions, total_deletions, total_files = self._diff_parse_totals(
            self._diff_stats  # type: ignore[attr-defined]
        )
        self._diff_set_stats(total_additions, total_deletions, total_files)
        self._diff_render_text(self._diff_text)  # type: ignore[attr-defined]

    def _diff_populate_file_table(self, diffs: list[RepoDiff]) -> None:
        table = self.query_one("#diff-files", DataTable)  # type: ignore[attr-defined]
        table.clear()
        if not table.columns:
            table.add_columns("File", "+", "-")
        table.cursor_type = "row"
        table.zebra_stripes = True

        self._file_diffs.clear()  # type: ignore[attr-defined]
        multi_repo = len(diffs) > 1
        for diff in diffs:
            for file in diff.files:
                key = f"{diff.repo_name}:{file.path}"
                self._file_diffs[key] = file  # type: ignore[attr-defined]
                label = f"{diff.repo_name}/{file.path}" if multi_repo else file.path
                table.add_row(label, str(file.additions), str(file.deletions), key=key)

        if not self._file_diffs:  # type: ignore[attr-defined]
            table.add_class("hidden")
            self._diff_render_text(self._diff_text)  # type: ignore[attr-defined]
            return

        table.remove_class("hidden")
        first_key = next(iter(self._file_diffs))  # type: ignore[attr-defined]
        self._diff_show_file(first_key)

    def _diff_show_file(self, key: str) -> None:
        file_diff = self._file_diffs.get(key)  # type: ignore[attr-defined]
        if file_diff is None:
            self._diff_render_text(self._diff_text)  # type: ignore[attr-defined]
            return
        self._diff_render_text(file_diff.diff_content)

    def _diff_render_text(self, diff_text: str) -> None:
        diff_log = self.query_one("#diff-log", RichLog)  # type: ignore[attr-defined]
        diff_log.clear()
        for line in diff_text.splitlines() or ["(No diff available)"]:
            diff_log.write(colorize_diff_line(line))
        diff_log.scroll_home(animate=False, immediate=True)

    def _diff_set_stats(self, additions: int, deletions: int, files: int) -> None:
        self.query_one("#review-stats", Horizontal).remove_class("hidden")  # type: ignore[attr-defined]
        self.query_one("#stat-additions", Static).update(  # type: ignore[attr-defined]
            f"+ {additions} Additions"
        )
        self.query_one("#stat-deletions", Static).update(  # type: ignore[attr-defined]
            f"- {deletions} Deletions"
        )
        self.query_one("#stat-files", Static).update(  # type: ignore[attr-defined]
            f"{files} Files Changed"
        )

    def _diff_parse_totals(self, diff_stats: str) -> tuple[int, int, int]:
        if not diff_stats:
            return 0, 0, 0
        pattern = re.compile(r"\+(\d+)\s+-(\d+)\s+\((\d+)\s+file")
        total_line = ""
        for line in diff_stats.splitlines():
            if line.lower().startswith("total:"):
                total_line = line
                break
        if total_line:
            match = pattern.search(total_line)
            if match:
                return (
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3)),
                )
        additions = deletions = files = 0
        for line in diff_stats.splitlines():
            match = pattern.search(line)
            if match:
                additions += int(match.group(1))
                deletions += int(match.group(2))
                files += int(match.group(3))
        return additions, deletions, files

    def _diff_parse_commit_line(self, line: str) -> tuple[str, str, str]:
        repo = ""
        rest = line.strip()
        if rest.startswith("["):
            end = rest.find("]")
            if end != -1:
                repo = rest[1:end]
                rest = rest[end + 1 :].strip()
        parts = rest.split(" ", 1)
        sha = parts[0] if parts else ""
        message = parts[1] if len(parts) > 1 else ""
        return repo, sha, message

    async def _diff_open_modal(self) -> None:
        from kagan.tui.ui.modals import DiffModal

        workspaces = await self.ctx.api.list_workspaces(  # type: ignore[attr-defined]
            task_id=self._task_model.id  # type: ignore[attr-defined]
        )
        title = (
            f"Diff: {self._task_model.short_id}"  # type: ignore[attr-defined]
            f" {self._task_model.title[:MODAL_TITLE_MAX_LENGTH]}"  # type: ignore[attr-defined]
        )

        if not workspaces:
            diff_text = self._diff_text or await self.ctx.api.get_workspace_diff(  # type: ignore[attr-defined]
                self._task_model.id,  # type: ignore[attr-defined]
                base_branch=self._base_branch,  # type: ignore[attr-defined]
            )
            result = await self.app.push_screen(  # type: ignore[attr-defined]
                DiffModal(
                    title=title,
                    diff_text=diff_text,
                    task=self._task_model,  # type: ignore[attr-defined]
                )
            )
        else:
            try:
                diffs = await self.ctx.api.get_all_diffs(workspaces[0].id)  # type: ignore[attr-defined]
            except RuntimeError:
                diff_text = self._diff_text or await self.ctx.api.get_workspace_diff(  # type: ignore[attr-defined]
                    self._task_model.id,  # type: ignore[attr-defined]
                    base_branch=self._base_branch,  # type: ignore[attr-defined]
                )
                result = await self.app.push_screen(  # type: ignore[attr-defined]
                    DiffModal(
                        title=title,
                        diff_text=diff_text,
                        task=self._task_model,  # type: ignore[attr-defined]
                    )
                )
            else:
                result = await self.app.push_screen(  # type: ignore[attr-defined]
                    DiffModal(
                        title=title,
                        diffs=diffs,
                        task=self._task_model,  # type: ignore[attr-defined]
                    )
                )

        modal_result = self._actions_parse_diff_modal_result(result)
        if modal_result == DIFF_MODAL_APPROVE_RESULT:
            self.action_approve()  # type: ignore[attr-defined]
        elif modal_result == DIFF_MODAL_REJECT_RESULT:
            self.action_reject()  # type: ignore[attr-defined]

    async def action_attach_session(self) -> None:
        """Attach to the running PAIR session."""
        if self._task_model.task_type != TaskType.PAIR:  # type: ignore[attr-defined]
            return
        if not await self.ctx.api.session_exists(self._task_model.id):  # type: ignore[attr-defined]
            self.notify("No active session for this task", severity="warning")  # type: ignore[attr-defined]
            return
        with self.app.suspend():  # type: ignore[attr-defined]
            await self.ctx.api.attach_session(self._task_model.id)  # type: ignore[attr-defined]

    async def action_generate_review(self) -> None:
        """Generate or regenerate AI review."""
        from kagan.core.debug_log import log

        if self._read_only:  # type: ignore[attr-defined]
            self.notify("Read-only history view", severity="warning")  # type: ignore[attr-defined]
            return
        if self._live_review_attached:  # type: ignore[attr-defined]
            self.notify("Review is already running", severity="information")  # type: ignore[attr-defined]
            return

        log.info(f"[ReviewModal] Starting AI review (phase={self._phase})")  # type: ignore[attr-defined]

        if self._phase == StreamPhase.COMPLETE:  # type: ignore[attr-defined]
            await self.action_regenerate_review()
            return
        if self._phase != StreamPhase.IDLE:  # type: ignore[attr-defined]
            return

        self._state_set_decision(None)  # type: ignore[attr-defined]
        self._state_set_phase(StreamPhase.THINKING)  # type: ignore[attr-defined]
        chat_panel = self._stream_review_output_panel()  # type: ignore[attr-defined]
        chat_panel.remove_class("hidden")
        output = chat_panel.output
        await self._prompt_generate_review(output)  # type: ignore[attr-defined]

    async def action_regenerate_review(self) -> None:
        """Regenerate AI review."""
        if self._phase != StreamPhase.COMPLETE:  # type: ignore[attr-defined]
            return

        if self._agent:  # type: ignore[attr-defined]
            await self._agent.stop()  # type: ignore[attr-defined]
            self._agent = None  # type: ignore[attr-defined]

        output = self._stream_review_output_panel().output  # type: ignore[attr-defined]
        await output.clear()
        self._state_set_decision(None)  # type: ignore[attr-defined]
        self._state_set_phase(StreamPhase.THINKING)  # type: ignore[attr-defined]
        await self._prompt_generate_review(output)  # type: ignore[attr-defined]

    async def action_cancel_review(self) -> None:
        if self._live_review_attached and self._agent is None:  # type: ignore[attr-defined]
            self.notify("Review is managed by automation", severity="warning")  # type: ignore[attr-defined]
            return
        if self._phase not in (StreamPhase.THINKING, StreamPhase.STREAMING):  # type: ignore[attr-defined]
            return

        if self._prompt_worker is not None and not self._prompt_worker.is_finished:  # type: ignore[attr-defined]
            self._prompt_worker.cancel()  # type: ignore[attr-defined]
        if self._agent:  # type: ignore[attr-defined]
            await self._agent.stop()  # type: ignore[attr-defined]
            self._agent = None  # type: ignore[attr-defined]

        output = self._stream_review_output_panel().output  # type: ignore[attr-defined]
        await output.post_note("Review cancelled", classes="dismissed")
        self._state_set_phase(StreamPhase.IDLE)  # type: ignore[attr-defined]

    async def action_view_diff(self) -> None:
        """Open the diff modal for the current task."""
        await self._diff_open_modal()

    async def action_start_agent_output(self) -> None:
        """Start AUTO execution from Task Output > Agent Output tab."""
        latest = await self.ctx.api.get_task(self._task_model.id)  # type: ignore[attr-defined]
        if latest is None:
            self.notify("Task no longer exists", severity="error")  # type: ignore[attr-defined]
            return
        self._task_model = latest  # type: ignore[attr-defined]
        if latest.task_type != TaskType.AUTO or latest.status != TaskStatus.IN_PROGRESS:
            self.notify(  # type: ignore[attr-defined]
                "Start is available only for AUTO tasks in IN_PROGRESS",
                severity="warning",
            )
            return
        if self._is_running:  # type: ignore[attr-defined]
            self.notify("Agent is already running", severity="information")  # type: ignore[attr-defined]
            return

        submitted = await self.ctx.api.submit_job(latest.id, "start_agent")  # type: ignore[attr-defined]
        terminal = await self._actions_wait_for_job_terminal(submitted.job_id, task_id=latest.id)
        msg, severity = self._actions_job_result_message(
            terminal,
            failure_msg="Failed to start agent",
            success_msg="Agent start requested",
            pending_msg=self.START_JOB_PENDING_MESSAGE,  # type: ignore[attr-defined]
        )
        self.notify(msg, severity=severity)  # type: ignore[attr-defined]
        await self._refresh_runtime_state()  # type: ignore[attr-defined]

    async def action_stop_agent_output(self) -> None:
        """Stop AUTO execution from Task Output > Agent Output tab."""
        latest = await self.ctx.api.get_task(self._task_model.id)  # type: ignore[attr-defined]
        if latest is None:
            self.notify("Task no longer exists", severity="error")  # type: ignore[attr-defined]
            return
        self._task_model = latest  # type: ignore[attr-defined]
        if latest.task_type != TaskType.AUTO or latest.status != TaskStatus.IN_PROGRESS:
            self.notify(  # type: ignore[attr-defined]
                "Stop is available only for AUTO tasks in IN_PROGRESS",
                severity="warning",
            )
            return

        submitted = await self.ctx.api.submit_job(latest.id, "stop_agent")  # type: ignore[attr-defined]
        terminal = await self._actions_wait_for_job_terminal(submitted.job_id, task_id=latest.id)
        msg, severity = self._actions_job_result_message(
            terminal,
            failure_msg="No running agent to stop",
            success_msg="Agent stop requested",
            pending_msg=self.STOP_JOB_PENDING_MESSAGE,  # type: ignore[attr-defined]
        )
        self.notify(msg, severity=severity)  # type: ignore[attr-defined]
        await self._refresh_runtime_state()  # type: ignore[attr-defined]

    async def action_rebase(self) -> None:
        """Rebase the task branch onto the base branch."""
        if self._read_only:  # type: ignore[attr-defined]
            self.notify("Read-only history view", severity="warning")  # type: ignore[attr-defined]
            return
        self.notify("Rebasing...", severity="information")  # type: ignore[attr-defined]
        success, message, conflict_files = await self.ctx.api.rebase_workspace(  # type: ignore[attr-defined]
            self._task_model.id,
            self._base_branch,  # type: ignore[attr-defined]
        )
        if success:
            self._diff_text = await self.ctx.api.get_workspace_diff(  # type: ignore[attr-defined]
                self._task_model.id,  # type: ignore[attr-defined]
                base_branch=self._base_branch,  # type: ignore[attr-defined]
            )
            self._diff_render_text(self._diff_text)  # type: ignore[attr-defined]
            diff_stats = await self.ctx.api.get_workspace_diff_stats(  # type: ignore[attr-defined]
                self._task_model.id,  # type: ignore[attr-defined]
                base_branch=self._base_branch,  # type: ignore[attr-defined]
            )
            self.query_one("#diff-stats", Static).update(  # type: ignore[attr-defined]
                diff_stats or "[dim](No changes)[/dim]"
            )
            self.notify("Rebase successful", severity="information")  # type: ignore[attr-defined]
        elif conflict_files:
            self.dismiss("rebase_conflict")  # type: ignore[attr-defined]
        else:
            self.notify(f"Rebase failed: {message}", severity="error")  # type: ignore[attr-defined]

    async def _load_pr_comments(self) -> None:
        """Lazy-load PR review comments from GitHub."""
        from kagan.core.plugins.github.contract import (
            GITHUB_CAPABILITY,
            GITHUB_METHOD_GET_PR_REVIEW_COMMENTS,
        )

        scroll = self.query_one("#pr-comments-scroll", VerticalScroll)  # type: ignore[attr-defined]
        loading = self.query_one("#pr-comments-loading", LoadingIndicator)  # type: ignore[attr-defined]
        loading.remove_class("hidden")

        try:
            result = await self.ctx.api.invoke_plugin(  # type: ignore[attr-defined]
                GITHUB_CAPABILITY,
                GITHUB_METHOD_GET_PR_REVIEW_COMMENTS,
                {
                    "project_id": self._task_model.project_id,  # type: ignore[attr-defined]
                    "task_id": self._task_model.id,  # type: ignore[attr-defined]
                },
            )
        except Exception as exc:
            loading.add_class("hidden")
            await scroll.mount(Static(f"[dim]Failed to load PR comments: {exc}[/dim]"))
            return

        loading.add_class("hidden")

        if not result.get("success"):
            msg = result.get("message", "No linked PR found")
            await scroll.mount(Static(f"[dim]{msg}[/dim]"))
            return

        comments = result.get("comments", [])
        pr_number = result.get("pr_number", "?")

        if not comments:
            await scroll.mount(Static(f"[dim]No review comments on PR #{pr_number}[/dim]"))
            return

        # Update tab title with count
        with contextlib.suppress(NoMatches):
            tabs = self.query_one("#review-tabs", TabbedContent)  # type: ignore[attr-defined]
            tab = tabs.get_tab("review-pr-comments")
            tab.label = f"PR Comments ({len(comments)})"

        widgets: list[Vertical] = []
        for comment in comments:
            user = comment.get("user", {}).get("login", "unknown")
            body = comment.get("body", "").strip()
            path = comment.get("path", "")
            line = comment.get("line") or comment.get("original_line") or ""
            loc = f" {path}:{line}" if path else ""
            header = f"[bold]{user}[/bold]{loc}"
            block = f"{header}\n{body}\n"
            item = Vertical(
                Static(block, markup=True),
                Button(
                    "Resolve with AI",
                    variant="default",
                    classes="pr-comment-resolve-btn",
                ),
                classes="pr-comment-item",
            )
            widgets.append(item)

        await scroll.mount_all(widgets)

    def action_approve(self) -> None:
        """Approve the review."""
        if self._read_only:  # type: ignore[attr-defined]
            self.notify("Read-only history view", severity="warning")  # type: ignore[attr-defined]
            return
        if self._phase in (StreamPhase.THINKING, StreamPhase.STREAMING):  # type: ignore[attr-defined]
            self.notify(  # type: ignore[attr-defined]
                "Wait for review to complete before approval",
                severity="warning",
            )
            return
        if self._review_queue_pending:  # type: ignore[attr-defined]
            self.notify(  # type: ignore[attr-defined]
                "Process queued review messages before approval",
                severity="warning",
            )
            return
        if self._no_changes:  # type: ignore[attr-defined]
            self.dismiss("exploratory")  # type: ignore[attr-defined]
        else:
            self.dismiss("approve")  # type: ignore[attr-defined]

    def action_reject(self) -> None:
        """Reject the review."""
        if self._read_only:  # type: ignore[attr-defined]
            self.notify("Read-only history view", severity="warning")  # type: ignore[attr-defined]
            return
        self.dismiss("reject")  # type: ignore[attr-defined]

    async def action_close_or_cancel(self) -> None:
        """Cancel review if in progress, otherwise close."""
        if self._phase in (StreamPhase.THINKING, StreamPhase.STREAMING):  # type: ignore[attr-defined]
            if self._agent is None and (  # type: ignore[attr-defined]
                self._live_review_attached or self._live_output_attached  # type: ignore[attr-defined]
            ):
                self.dismiss(None)  # type: ignore[attr-defined]
                return
            await self.action_cancel_review()
        else:
            self.dismiss(None)  # type: ignore[attr-defined]

    def action_copy(self) -> None:
        """Copy review content to clipboard."""
        output = self._stream_review_output_panel().output  # type: ignore[attr-defined]
        review_text = output._agent_response._markdown if output._agent_response else ""

        content_parts = [f"# Review: {self._task_model.title}"]  # type: ignore[attr-defined]
        if self._diff_stats:  # type: ignore[attr-defined]
            content_parts.append(f"\n## Changes\n{self._diff_stats}")  # type: ignore[attr-defined]
        if review_text:
            content_parts.append(f"\n## AI Review\n{review_text}")

        copy_with_notification(
            self.app,
            "\n".join(content_parts),
            "Review",  # type: ignore[attr-defined]
        )


__all__ = [
    "DIFF_MODAL_APPROVE_RESULT",
    "DIFF_MODAL_REJECT_RESULT",
    "ReviewActionsMixin",
]
