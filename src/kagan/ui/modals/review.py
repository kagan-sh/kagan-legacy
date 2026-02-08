"""Modal for reviewing task changes."""

from __future__ import annotations

import asyncio
import contextlib
from typing import TYPE_CHECKING

from sqlalchemy.exc import OperationalError
from textual import on
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.css.query import NoMatches
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Label,
    LoadingIndicator,
    RichLog,
    Rule,
    Static,
    TabbedContent,
    TabPane,
)

from kagan.acp import messages
from kagan.adapters.db.repositories.base import RepositoryClosing
from kagan.agents.agent_factory import AgentFactory, create_agent
from kagan.constants import MODAL_TITLE_MAX_LENGTH
from kagan.core.models.enums import StreamPhase, TaskStatus, TaskType
from kagan.keybindings import REVIEW_BINDINGS
from kagan.ui.modals.base import KaganModalScreen
from kagan.ui.modals.review_actions import ReviewActionsMixin
from kagan.ui.modals.review_diff import ReviewDiffMixin
from kagan.ui.modals.review_prompt import ReviewPromptMixin
from kagan.ui.modals.review_prompt import extract_review_decision as extract_review_decision_message
from kagan.ui.modals.review_queue import ReviewQueueMixin
from kagan.ui.modals.review_state import ReviewStateMixin
from kagan.ui.modals.review_stream import ReviewStreamMixin
from kagan.ui.utils.agent_exit import parse_agent_exit_code as parse_agent_exit_code_message
from kagan.ui.utils.agent_stream_router import AgentStreamRouter
from kagan.ui.widgets import ChatPanel

_SHUTDOWN_ERRORS = (RepositoryClosing, OperationalError)

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.timer import Timer
    from textual.worker import Worker

    from kagan.acp import Agent
    from kagan.adapters.db.repositories import ExecutionRepository
    from kagan.adapters.db.schema import Task
    from kagan.config import AgentConfig
    from kagan.services.diffs import FileDiff
    from kagan.services.workspaces import WorkspaceService


def parse_agent_exit_code(message: str) -> int | None:
    """Compatibility wrapper around shared agent-exit parser."""
    return parse_agent_exit_code_message(message)


def extract_review_decision(text: str) -> str | None:
    """Compatibility wrapper around review decision parser."""
    return extract_review_decision_message(text)


class ReviewModal(
    ReviewActionsMixin,
    ReviewDiffMixin,
    ReviewPromptMixin,
    ReviewQueueMixin,
    ReviewStateMixin,
    ReviewStreamMixin,
    KaganModalScreen[str | None],
):
    """Modal for reviewing task changes."""

    BINDINGS = REVIEW_BINDINGS
    _agent: Agent | None
    _live_output_agent: Agent | None
    _live_review_agent: Agent | None
    _live_output_attached: bool
    _live_output_wait_noted: bool
    _live_review_attached: bool

    def __init__(
        self,
        task: Task,
        worktree_manager: WorkspaceService,
        agent_config: AgentConfig,
        base_branch: str = "main",
        agent_factory: AgentFactory = create_agent,
        execution_service: ExecutionRepository | None = None,
        execution_id: str | None = None,
        run_count: int = 0,
        running_agent: Agent | None = None,
        review_agent: Agent | None = None,
        is_reviewing: bool = False,
        is_running: bool = False,
        read_only: bool = False,
        initial_tab: str = "review-summary",
        **kwargs,
    ) -> None:
        super().__init__(**kwargs)
        self._task_model = task
        self._worktree = worktree_manager
        self._agent_config = agent_config
        self._base_branch = base_branch
        self._agent_factory = agent_factory
        self._execution_service = execution_service
        self._agent: Agent | None = None
        self._execution_id = execution_id
        self._run_count = run_count
        self._live_output_agent = running_agent
        self._live_review_agent = review_agent
        self._is_reviewing = is_reviewing
        self._is_running = is_running
        self._read_only = read_only
        self._initial_tab = initial_tab
        self._live_output_attached = False
        self._live_output_wait_noted = False
        self._live_review_attached = False
        self._review_log_loaded = False
        self._phase: StreamPhase = StreamPhase.IDLE
        self._diff_stats: str = ""
        self._diff_text: str = ""
        self._file_diffs: dict[str, FileDiff] = {}
        self._no_changes: bool = False
        self._anim_timer: Timer | None = None
        self._anim_frame: int = 0
        self._prompt_worker: Worker[None] | None = None
        self._review_queue_pending = False
        self._implementation_queue_pending = False
        self._hydrated = False
        self._agent_stream = AgentStreamRouter(
            get_output=self._get_stream_output,
            on_update=self._on_stream_update,
            on_complete=self._on_stream_complete,
            on_fail=self._on_stream_fail,
        )

    def compose(self) -> ComposeResult:
        with Vertical(id="review-modal-container"):
            yield Label(
                f"Review: {self._task_model.title[:MODAL_TITLE_MAX_LENGTH]}",
                id="review-title",
                classes="modal-title",
            )
            yield Label(
                f"Branch: task-{self._task_model.short_id} → {self._base_branch}",
                id="branch-info",
                classes="branch-info",
            )
            yield Rule()

            yield LoadingIndicator(id="review-loading", classes="review-loading")

            with TabbedContent(id="review-tabs", classes="hidden"):
                with TabPane("Summary", id="review-summary"):
                    with VerticalScroll(id="review-summary-scroll"):
                        yield Label("Overview", classes="section-title")
                        with Horizontal(id="review-stats", classes="hidden"):
                            yield Static(id="stat-additions", classes="stat-card")
                            yield Static(id="stat-deletions", classes="stat-card")
                            yield Static(id="stat-files", classes="stat-card")

                        yield Label("Commits", classes="section-title")
                        yield DataTable(id="commits-table")

                        yield Label("Changes", classes="section-title")
                        yield Static(id="diff-stats")

                        if self._task_model.description.strip():
                            yield Label("Description", classes="section-title")
                            yield Static(
                                self._task_model.description.strip(),
                                id="review-description",
                            )

                with TabPane("Diff", id="review-diff"):
                    with Horizontal(id="diff-pane"):
                        yield DataTable(id="diff-files", classes="hidden")
                        yield RichLog(id="diff-log", wrap=False, markup=True, auto_scroll=False)

                with TabPane("AI Review", id="review-ai"):
                    with Vertical(id="ai-review-section", classes="hidden"):
                        with Horizontal(id="ai-review-header"):
                            yield Label("AI Review", classes="section-title")
                            yield Static("", classes="spacer")
                            yield Static(
                                "Decision: Pending",
                                id="decision-badge",
                                classes="decision-badge decision-pending",
                            )
                            yield Static(
                                "○ Ready", id="phase-badge", classes="phase-badge phase-idle"
                            )
                        yield ChatPanel(
                            None,
                            allow_input=True,
                            input_placeholder="Send a follow-up message...",
                            output_id="ai-review-output",
                            id="ai-review-chat",
                            classes="hidden",
                        )
                with TabPane("Agent Output", id="review-agent-output"):
                    yield ChatPanel(
                        self._execution_id,
                        allow_input=True,
                        input_placeholder="Queue implementation follow-up...",
                        output_id="review-agent-output",
                        id="review-agent-output-chat",
                    )

            yield Rule()

            with Horizontal(classes="button-row hidden"):
                with Horizontal(classes="button-group button-group-start"):
                    if self._task_model.task_type == TaskType.PAIR:
                        yield Button("Attach", variant="default", id="attach-btn")
                    yield Button("Rebase (R)", variant="default", id="rebase-btn")
                    yield Button("Review (g)", id="generate-btn", variant="primary")
                    yield Button("Cancel", id="cancel-btn", variant="warning", classes="hidden")
                yield Static("", classes="spacer")
                with Horizontal(classes="button-group button-group-end"):
                    yield Button("Approve (Enter)", variant="success", id="approve-btn")
                    yield Button("Reject (r)", variant="error", id="reject-btn")

        yield Footer(show_command_palette=False)

    async def on_mount(self) -> None:
        """Render shell immediately, then hydrate heavy content in background."""
        self._show_shell()
        self._bind_task_updates()
        # Attach live streams as soon as the modal mounts so AUTO Enter opens into
        # an already streaming output pane.
        with contextlib.suppress(Exception):
            await self._attach_live_output_stream_if_available(wait_for_agent=False)
        with contextlib.suppress(Exception):
            await self._attach_live_review_stream_if_available()
        self.run_worker(self._hydrate_content, exclusive=True, exit_on_error=False)

    def _show_shell(self) -> None:
        """Make modal interactive before loading expensive data."""
        with contextlib.suppress(NoMatches):
            self.query_one("#review-loading", LoadingIndicator).remove()
        self.query_one("#review-tabs").remove_class("hidden")
        self.query_one("#ai-review-section").remove_class("hidden")
        if (
            not self._read_only
            and self._task_model.task_type == TaskType.PAIR
            and self._task_model.status == TaskStatus.REVIEW
            and self.ctx.config.general.auto_review
        ):
            self.query_one("#ai-review-chat", ChatPanel).remove_class("hidden")
        if not self._read_only:
            self.query_one(".button-row").remove_class("hidden")
        self._set_active_tab(self._initial_tab)
        self._sync_agent_output_queue_visibility()
        self._sync_review_queue_visibility()

    def _bind_task_updates(self) -> None:
        self.kagan_app.task_changed_signal.subscribe(self, self._on_task_changed)

    async def _hydrate_content(self) -> None:
        """Load commits, diffs and history without blocking initial paint."""
        from kagan.debug_log import log

        workspaces = []
        try:
            workspaces = await self._worktree.list_workspaces(task_id=self._task_model.id)
            if workspaces:
                actual_branch = workspaces[0].branch_name
                branch_info = self.query_one("#branch-info", Label)
                branch_info.update(f"Branch: {actual_branch} → {self._base_branch}")

            commits_task = self._worktree.get_commit_log(self._task_model.id, self._base_branch)
            diff_stats_task = self._worktree.get_diff_stats(self._task_model.id, self._base_branch)
            diff_task = self._worktree.get_diff(self._task_model.id, self._base_branch)
            commits, diff_stats, self._diff_text = await asyncio.gather(
                commits_task,
                diff_stats_task,
                diff_task,
            )

            self._populate_commits(commits)
            self.query_one("#diff-stats", Static).update(diff_stats or "[dim](No changes)[/dim]")
            self._diff_stats = diff_stats or ""
            self._no_changes = not commits and not self._diff_stats
            await self._populate_diff_pane(workspaces)
        except Exception as exc:
            log.error(
                "[ReviewModal] Failed to hydrate diff/commit data",
                task_id=self._task_model.id[:8],
                error=str(exc),
            )
            self._diff_text = ""
            self._diff_stats = ""
            self._no_changes = False
            with contextlib.suppress(NoMatches):
                self.query_one("#diff-stats", Static).update(
                    "[dim](Unable to load diff data)[/dim]"
                )

        if self._no_changes:
            self.query_one("#approve-btn", Button).label = "Close task"

        history_results = await asyncio.gather(
            self._load_agent_output_history(),
            self._configure_follow_up_chat(),
            self._configure_agent_output_chat(),
            return_exceptions=True,
        )
        for result in history_results:
            if isinstance(result, Exception):
                log.error(
                    "[ReviewModal] Failed to hydrate output/chat state",
                    task_id=self._task_model.id[:8],
                    error=str(result),
                )

        queue_results = await asyncio.gather(
            self._refresh_review_queue_state(),
            self._refresh_implementation_queue_state(),
            return_exceptions=True,
        )
        for result in queue_results:
            if isinstance(result, Exception):
                log.error(
                    "[ReviewModal] Failed to refresh queue state",
                    task_id=self._task_model.id[:8],
                    error=str(result),
                )

        if self._read_only:
            self.query_one("#generate-btn", Button).add_class("hidden")
            self.query_one("#cancel-btn", Button).add_class("hidden")

        if self._execution_service is not None:
            with contextlib.suppress(Exception):
                await self._load_prior_review()
        with contextlib.suppress(Exception):
            await self._attach_live_output_stream_if_available()
        with contextlib.suppress(Exception):
            await self._attach_live_review_stream_if_available()
        auto_started = False
        with contextlib.suppress(Exception):
            auto_started = await self._maybe_auto_start_pair_review()
        self._hydrated = True
        if auto_started:
            self._set_active_tab("review-ai")

    async def _on_task_changed(self, task_id: str) -> None:
        if not self.is_mounted or task_id != self._task_model.id:
            return
        self.run_worker(self._refresh_runtime_state, exclusive=True, exit_on_error=False)

    @on(DataTable.RowHighlighted, "#diff-files")
    def on_diff_file_highlighted(self, event: DataTable.RowHighlighted) -> None:
        self._show_file_diff(str(event.row_key))

    @on(Button.Pressed, "#generate-btn")
    async def on_generate_btn(self) -> None:
        await self.action_generate_review()

    @on(Button.Pressed, "#cancel-btn")
    async def on_cancel_btn(self) -> None:
        await self.action_cancel_review()

    @on(Button.Pressed, "#rebase-btn")
    async def on_rebase_btn(self) -> None:
        await self.action_rebase()

    @on(Button.Pressed, "#attach-btn")
    async def on_attach_btn(self) -> None:
        await self.action_attach_session()

    @on(Button.Pressed, "#approve-btn")
    def on_approve_btn(self) -> None:
        self.action_approve()

    @on(Button.Pressed, "#reject-btn")
    def on_reject_btn(self) -> None:
        self.action_reject()

    async def _on_stream_update(self, message: messages.AgentUpdate) -> None:
        if self._phase == StreamPhase.THINKING:
            self._set_phase(StreamPhase.STREAMING)
        output = self._get_stream_output()
        await output.post_response(message.text)

    async def _on_stream_complete(self, _: messages.AgentComplete) -> None:
        if self._agent is not None:
            self._agent = None
        if self._live_output_attached and self._agent is None:
            self._live_output_attached = False
        if self._live_review_attached and self._agent is None:
            self._live_review_attached = False
        self._sync_decision_from_output()
        self._set_phase(StreamPhase.COMPLETE)
        await asyncio.gather(
            self._refresh_review_queue_state(),
            self._refresh_implementation_queue_state(),
        )
        await self._refresh_runtime_state()
        if not self._read_only and self._review_queue_pending:
            await self._start_review_follow_up_if_needed()

    async def _on_stream_fail(self, message: messages.AgentFail) -> None:
        output = self._get_stream_output()
        exit_code = parse_agent_exit_code(message.message)
        if exit_code == -15:
            await output.post_note(
                "Agent stream ended by cancellation (SIGTERM).",
                classes="dismissed",
            )
            self._sync_decision_from_output()
            if extract_review_decision(output.get_text_content()):
                self._set_phase(StreamPhase.COMPLETE)
            else:
                self._set_phase(StreamPhase.IDLE)
            if self._agent is not None:
                self._agent = None
            if self._live_output_attached and self._agent is None:
                self._live_output_attached = False
            if self._live_review_attached and self._agent is None:
                self._live_review_attached = False
            await asyncio.gather(
                self._refresh_review_queue_state(),
                self._refresh_implementation_queue_state(),
            )
            await self._refresh_runtime_state()
            return

        await output.post_note(f"Error: {message.message}", classes="error")
        if self._agent is not None:
            self._agent = None
        if self._live_output_attached and self._agent is None:
            self._live_output_attached = False
        if self._live_review_attached and self._agent is None:
            self._live_review_attached = False
        self._set_phase(StreamPhase.IDLE)
        await asyncio.gather(
            self._refresh_review_queue_state(),
            self._refresh_implementation_queue_state(),
        )
        await self._refresh_runtime_state()

    @on(messages.AgentMessage)
    async def on_agent_message(self, message: messages.AgentMessage) -> None:
        await self._agent_stream.dispatch(message)

    async def _refresh_runtime_state(self) -> None:
        if not self.is_mounted:
            return
        try:
            latest = await self.ctx.task_service.get_task(self._task_model.id)
        except _SHUTDOWN_ERRORS:
            return
        if latest is not None:
            previous_status = self._task_model.status
            self._task_model = latest
            if previous_status == TaskStatus.IN_PROGRESS and latest.status == TaskStatus.REVIEW:
                self._read_only = False
                self.query_one(".button-row").remove_class("hidden")
                self.query_one("#generate-btn", Button).remove_class("hidden")
                self.query_one("#cancel-btn", Button).add_class("hidden")
                self._set_phase(StreamPhase.IDLE)
                self._set_active_tab("review-ai")

        runtime_view = self.ctx.runtime_service.get(self._task_model.id)
        self._is_running = runtime_view.is_running if runtime_view is not None else False
        self._is_reviewing = runtime_view.is_reviewing if runtime_view is not None else False
        if runtime_view is not None and runtime_view.execution_id is not None:
            self._execution_id = runtime_view.execution_id
        self._live_output_agent = runtime_view.running_agent if runtime_view is not None else None
        self._live_review_agent = runtime_view.review_agent if runtime_view is not None else None

        await self._attach_live_output_stream_if_available()
        await self._attach_live_review_stream_if_available()
        try:
            await asyncio.gather(
                self._refresh_review_queue_state(),
                self._refresh_implementation_queue_state(),
            )
            if self._hydrated and self._task_model.status == TaskStatus.REVIEW:
                await self._load_prior_review()
        except _SHUTDOWN_ERRORS:
            return

    async def on_unmount(self) -> None:
        """Cleanup agent and animation on close."""
        with contextlib.suppress(Exception):
            self.kagan_app.task_changed_signal.unsubscribe(self)
        self._stop_animation()
        if self._prompt_worker is not None and not self._prompt_worker.is_finished:
            self._prompt_worker.cancel()
        if self._agent:
            await self._agent.stop()
        if self._live_output_agent:
            self._live_output_agent.set_message_target(None)
        if self._live_review_agent:
            self._live_review_agent.set_message_target(None)
