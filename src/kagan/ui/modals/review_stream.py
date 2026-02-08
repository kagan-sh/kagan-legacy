"""Agent stream lifecycle for the review modal."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.core.models.enums import StreamPhase, TaskStatus, TaskType
from kagan.ui.widgets import ChatPanel, StreamingOutput

if TYPE_CHECKING:
    from kagan.acp import Agent
    from kagan.ui.modals.review import ReviewModal


class ReviewStreamMixin:
    """Load history, attach live streams, and handle agent events."""

    _LIVE_ATTACH_TIMEOUT_SECONDS = 1.5
    _live_output_agent: Agent | None
    _live_output_wait_noted: bool
    _live_output_attached: bool
    _live_review_attached: bool
    _is_running: bool
    _is_reviewing: bool

    async def _resolve_execution_id(self: ReviewModal) -> str | None:
        if self._execution_id is not None:
            return self._execution_id
        if self._execution_service is None:
            return None
        execution = await self._execution_service.get_latest_execution_for_task(self._task_model.id)
        if execution is None:
            return None
        self._execution_id = execution.id
        return self._execution_id

    def _get_agent_output_panel(self: ReviewModal) -> ChatPanel:
        return self.query_one("#review-agent-output-chat", ChatPanel)

    def _get_chat_panel(self: ReviewModal) -> ChatPanel:
        return self.query_one("#ai-review-chat", ChatPanel)

    def _get_stream_output(self: ReviewModal) -> StreamingOutput:
        if self._live_review_attached or self._agent is not None:
            return self._get_chat_panel().output
        if self._live_output_attached or self._initial_tab == "review-agent-output":
            return self._get_agent_output_panel().output
        return self._get_chat_panel().output

    async def _load_agent_output_history(self: ReviewModal) -> None:
        execution_id = await self._resolve_execution_id()
        panel = self._get_agent_output_panel()
        if execution_id is None:
            if not self._is_running:
                await panel.output.post_note("No execution logs available", classes="warning")
            return

        entries = await self.ctx.execution_service.get_execution_log_entries(execution_id)
        if not entries:
            if not self._is_running:
                await panel.output.post_note("No execution logs available", classes="warning")
            return

        has_review_result = False
        execution = await self.ctx.execution_service.get_execution(execution_id)
        if execution and execution.metadata_:
            has_review_result = "review_result" in execution.metadata_

        review_entries = entries[-1:] if has_review_result and len(entries) > 1 else []
        impl_entries = entries[:-1] if review_entries else entries
        rendered_impl_output = False
        for entry in impl_entries:
            if not entry.logs:
                continue
            panel.set_execution_id(None)
            for line in entry.logs.splitlines():
                rendered_impl_output = await panel._render_log_line(line) or rendered_impl_output

        if impl_entries and not rendered_impl_output:
            await panel.output.post_note(
                "Execution history is present but contains no displayable output yet.",
                classes="warning",
            )

        if review_entries:
            chat_panel = self._get_chat_panel()
            chat_panel.remove_class("hidden")
            for entry in review_entries:
                if not entry.logs:
                    continue
                for line in entry.logs.splitlines():
                    await chat_panel._render_log_line(line)
            self._review_log_loaded = True
            self._sync_decision_from_output()
            self._set_phase(StreamPhase.COMPLETE)

    async def _attach_live_review_stream_if_available(self: ReviewModal) -> None:
        if self._live_review_attached:
            return
        if not self._is_reviewing or self._live_review_agent is None:
            return
        chat_panel = self._get_chat_panel()
        chat_panel.remove_class("hidden")
        # Mark attached before replay so buffered messages route to the review pane.
        self._live_review_attached = True
        self._live_review_agent.set_message_target(self)
        await chat_panel.output.post_note("Connected to live review stream", classes="info")
        self._set_phase(StreamPhase.STREAMING)

    async def _attach_live_output_stream_if_available(
        self: ReviewModal,
        *,
        wait_for_agent: bool = True,
    ) -> None:
        if self._live_output_attached:
            return
        if self._is_reviewing or not self._is_running:
            return
        if self._live_output_agent is None:
            if not wait_for_agent:
                return
            agent = await self.ctx.automation_service.wait_for_running_agent(
                self._task_model.id,
                timeout=self._LIVE_ATTACH_TIMEOUT_SECONDS,
            )
            if agent is None:
                if not self._live_output_wait_noted:
                    await self._get_agent_output_panel().output.post_note(
                        "Waiting for live agent stream...",
                        classes="warning",
                    )
                    self._live_output_wait_noted = True
                return
            self._live_output_agent = agent
        panel = self._get_agent_output_panel()
        # Mark attached before replay so buffered messages route to the output pane.
        self._live_output_attached = True
        self._live_output_agent.set_message_target(self)
        self._live_output_wait_noted = False
        await panel.output.post_note("Connected to live agent stream", classes="info")

    async def _maybe_auto_start_pair_review(self: ReviewModal) -> bool:
        if self._read_only or self._live_review_attached or self._review_log_loaded:
            return False
        if self._task_model.task_type != TaskType.PAIR:
            return False
        if self._task_model.status != TaskStatus.REVIEW:
            return False
        if self._phase != StreamPhase.IDLE:
            return False
        if not self.ctx.config.general.auto_review:
            return False
        await self.action_generate_review()
        return True

    async def _load_prior_review(self: ReviewModal) -> None:
        """Load auto-review results from execution metadata if available."""
        if self._execution_service is None:
            return
        if self._review_log_loaded:
            return
        execution_id = await self._resolve_execution_id()
        if execution_id is None:
            return
        execution = await self._execution_service.get_execution(execution_id)
        if execution is None or not execution.metadata_:
            return
        review_result = execution.metadata_.get("review_result")
        if review_result is None:
            return

        status = review_result.get("status", "")
        summary = review_result.get("summary", "")

        chat_panel = self._get_chat_panel()
        chat_panel.remove_class("hidden")
        output = chat_panel.output

        if status == "approved":
            await output.post_note("Auto-review passed", classes="success")
        else:
            await output.post_note("Auto-review flagged issues", classes="warning")

        if summary:
            await output.post_response(summary)

        if status == "approved":
            self._set_decision("approved")
        elif status == "rejected":
            self._set_decision("rejected")

        self._set_phase(StreamPhase.COMPLETE)
