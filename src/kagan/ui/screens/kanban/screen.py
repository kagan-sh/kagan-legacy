"""Main Kanban board screen."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from textual import getters, on
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.css.query import NoMatches
from textual.widgets import Static

from kagan.constants import (
    COLUMN_ORDER,
    MIN_SCREEN_HEIGHT,
    MIN_SCREEN_WIDTH,
)
from kagan.core.models.enums import CardIndicator, TaskStatus, TaskType
from kagan.git_utils import list_local_branches
from kagan.keybindings import KANBAN_BINDINGS
from kagan.ui.modals import (
    BaseBranchModal,
    ConfirmModal,
    ModalAction,
    TaskDetailsModal,
)
from kagan.ui.modals.description_editor import DescriptionEditorModal
from kagan.ui.screen_result import await_screen_result
from kagan.ui.screens.base import KaganScreen
from kagan.ui.screens.kanban import focus
from kagan.ui.screens.kanban.board_controller import KanbanBoardController
from kagan.ui.screens.kanban.review_controller import KanbanReviewController
from kagan.ui.screens.kanban.session_controller import KanbanSessionController
from kagan.ui.screens.kanban.state import KanbanUiState
from kagan.ui.screens.planner import PlannerScreen
from kagan.ui.utils import copy_with_notification
from kagan.ui.widgets.column import KanbanColumn
from kagan.ui.widgets.header import KaganHeader
from kagan.ui.widgets.keybinding_hint import KanbanHintBar
from kagan.ui.widgets.offline_banner import OfflineBanner
from kagan.ui.widgets.peek_overlay import PeekOverlay
from kagan.ui.widgets.search_bar import SearchBar

if TYPE_CHECKING:
    from textual import events
    from textual.app import ComposeResult
    from textual.timer import Timer

    from kagan.adapters.db.schema import Task
    from kagan.ui.widgets.card import TaskCard

SIZE_WARNING_MESSAGE = (
    f"Terminal too small\n\n"
    f"Minimum size: {MIN_SCREEN_WIDTH}x{MIN_SCREEN_HEIGHT}\n"
    f"Please resize your terminal"
)
BRANCH_LOOKUP_TIMEOUT_SECONDS = 1.0


class KanbanScreen(KaganScreen):
    """Main Kanban board screen with 4 columns."""

    BINDINGS = KANBAN_BINDINGS

    header = getters.query_one(KaganHeader)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tasks: list[Task] = []
        self._ui_state = KanbanUiState()
        self._refresh_timer: Timer | None = None
        self._task_hashes: dict[str, int] = {}
        self._agent_offline: bool = False
        self._merge_failed_tasks: set[str] = set()
        self._search_request_id: int = 0
        self._board = KanbanBoardController(self)
        self._review = KanbanReviewController(self)
        self._session = KanbanSessionController(self)

    _TASK_REQUIRED_ACTIONS = frozenset(
        {
            "edit_task",
            "delete_task",
            "delete_task_direct",
            "view_details",
            "open_session",
            "move_forward",
            "move_backward",
            "duplicate_task",
            "merge",
            "merge_direct",
            "view_diff",
            "open_review",
            "start_agent",
            "stop_agent",
        }
    )

    _AGENT_REQUIRED_ACTIONS = frozenset(
        {
            "start_agent",
            "open_planner",
        }
    )

    def _validate_action(self, action: str) -> tuple[bool, str | None]:
        """Validate if an action can be performed (inlined from ActionValidator)."""
        if self._agent_offline and action in self._AGENT_REQUIRED_ACTIONS:
            return (False, "Agent unavailable (offline mode)")

        card = focus.get_focused_card(self)
        task = card.task_model if card else None

        if not task:
            if action in self._TASK_REQUIRED_ACTIONS:
                return (False, "No task selected")
            return (True, None)

        status = task.status
        task_type = task.task_type

        if action == "edit_task":
            if status == TaskStatus.DONE:
                return (False, "Done tasks cannot be edited. Use [y] to duplicate.")
            return (True, None)

        if action in ("move_forward", "move_backward"):
            if status == TaskStatus.DONE:
                return (False, "Done tasks cannot be moved. Use [y] to duplicate.")
            return (True, None)

        if action in ("merge", "merge_direct", "view_diff", "open_review", "rebase"):
            if status != TaskStatus.REVIEW:
                return (False, f"Only available for REVIEW tasks (current: {status.value})")
            return (True, None)

        if action == "start_agent":
            if task_type != TaskType.AUTO:
                return (False, "Only available for AUTO tasks")
            return (True, None)

        if action == "stop_agent":
            if task_type != TaskType.AUTO:
                return (False, "Only available for AUTO tasks")
            if not self._is_runtime_running(task.id):
                return (False, "No agent running for this task")
            return (True, None)

        return (True, None)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        is_valid, _ = self._validate_action(action)
        return True if is_valid else None

    def _runtime_view(self, task_id: str):
        return self.ctx.runtime_service.get(task_id)

    def _is_runtime_running(self, task_id: str) -> bool:
        runtime_view = self._runtime_view(task_id)
        return runtime_view.is_running if runtime_view is not None else False

    def _runtime_run_count(self, task_id: str) -> int:
        runtime_view = self._runtime_view(task_id)
        return runtime_view.run_count if runtime_view is not None else 0

    def compose(self) -> ComposeResult:
        yield KaganHeader(task_count=0)
        yield SearchBar(id="search-bar")
        with Container(classes="board-container"):
            with Horizontal(classes="board"):
                for status in COLUMN_ORDER:
                    yield KanbanColumn(status=status, tasks=[])
        with Container(classes="size-warning"):
            yield Static(SIZE_WARNING_MESSAGE, classes="size-warning-text")
        yield Static("", id="review-queue-hint", classes="review-queue-hint")
        yield PeekOverlay(id="peek-overlay")
        yield KanbanHintBar(id="kanban-hint-bar")

    async def on_mount(self) -> None:
        self._board.check_screen_size()
        self._board.check_agent_health()
        await self.sync_header_context(self.header)
        await self._board.refresh_board()
        focus.focus_first_card(self)
        self.kagan_app.task_changed_signal.subscribe(self, self._on_task_changed)
        self._board.sync_agent_states()
        from kagan.ui.widgets.header import _get_git_branch

        if self.ctx.active_repo_id is None:
            self.header.update_branch("")
            return
        branch = await _get_git_branch(self.kagan_app.project_root)
        self.header.update_branch(branch)

    def on_unmount(self) -> None:
        self._board.cleanup_on_unmount()

    async def _on_task_changed(self, _task_id: str) -> None:
        if not self.is_mounted:
            return
        self._board.schedule_refresh()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        """Update UI immediately on focus change (hints first for instant feedback)."""
        self._board.update_keybinding_hints()
        self.refresh_bindings()

    def on_resize(self, event: events.Resize) -> None:
        self._board.check_screen_size()

    async def on_screen_resume(self) -> None:
        await self._board.refresh_board()
        self._board.sync_agent_states()

    async def reset_for_repo_change(self) -> None:
        await self._board.reset_for_repo_change()

    @on(OfflineBanner.Reconnect)
    def on_offline_banner_reconnect(self, event: OfflineBanner.Reconnect) -> None:
        """Handle reconnect from offline banner - refresh agent health check."""
        self.ctx.agent_health.refresh()
        if self.ctx.agent_health.is_available():
            self._agent_offline = False

            for banner in self.query(OfflineBanner):
                banner.remove()
            self.notify("Agent is now available", severity="information")
        else:
            self.notify("Agent still unavailable", severity="warning")

    def action_focus_left(self) -> None:
        focus.focus_horizontal(self, -1)

    def action_focus_right(self) -> None:
        focus.focus_horizontal(self, 1)

    def action_focus_up(self) -> None:
        focus.focus_vertical(self, -1)

    def action_focus_down(self) -> None:
        focus.focus_vertical(self, 1)

    def action_deselect(self) -> None:
        try:
            overlay = self.query_one("#peek-overlay", PeekOverlay)
            if overlay.has_class("visible"):
                overlay.hide()
                return
        except NoMatches:
            pass
        try:
            search_bar = self.query_one("#search-bar", SearchBar)
            if search_bar.is_visible:
                search_bar.hide()
                self._ui_state.filtered_tasks = None
                self.run_worker(self._board.refresh_board())
                return
        except NoMatches:
            pass
        self.app.set_focus(None)

    def action_quit(self) -> None:
        self.app.exit()

    def action_interrupt(self) -> None:
        self.app.exit()

    async def action_toggle_peek(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            return
        try:
            overlay = self.query_one("#peek-overlay", PeekOverlay)
        except NoMatches:
            return
        if not overlay.toggle():
            return

        task = card.task_model
        task_type = task.task_type

        if task_type == TaskType.AUTO:
            if self._is_runtime_running(task.id):
                run_count = self._runtime_run_count(task.id)
                run_label = f" (Run {run_count})" if run_count > 0 else ""
                status = f"🟢 Running{run_label}"
            else:
                status = "⚪ Idle"
        else:
            is_active = await self.ctx.session_service.session_exists(task.id)
            status = "🟢 Session Active" if is_active else "⚪ No Active Session"

        scratchpad = await self.ctx.task_service.get_scratchpad(task.id)
        content = scratchpad if scratchpad else "(No scratchpad)"

        overlay.update_content(task.short_id, task.title, status, content)
        x_pos = min(card.region.x + card.region.width + 2, self.size.width - 55)
        y_pos = max(1, card.region.y)
        overlay.show_at(x_pos, y_pos)

    def on_key(self, event: events.Key) -> None:
        feedback_actions = {
            "delete_task_direct",
            "merge_direct",
            "rebase",
            "edit_task",
            "view_details",
            "open_session",
            "start_agent",
            "stop_agent",
            "view_diff",
            "open_review",
        }
        key_action_map = {
            b.key: b.action
            for b in KANBAN_BINDINGS
            if isinstance(b, Binding) and b.action in feedback_actions
        }
        if event.key in key_action_map:
            _, reason = self._validate_action(key_action_map[event.key])
            if reason:
                self.notify(reason, severity="warning")

    def action_toggle_search(self) -> None:
        try:
            search_bar = self.query_one("#search-bar", SearchBar)
            if search_bar.is_visible:
                search_bar.hide()
                self._ui_state.filtered_tasks = None
                self.run_worker(self._board.refresh_board())
            else:
                search_bar.show()
        except NoMatches:
            pass

    @on(SearchBar.QueryChanged)
    def on_search_query_changed(self, event: SearchBar.QueryChanged) -> None:
        self._search_request_id += 1
        request_id = self._search_request_id
        query = event.query.strip()
        self.run_worker(
            self._apply_search_query(query, request_id),
            group="kanban-search",
            exclusive=True,
            exit_on_error=False,
        )

    async def _apply_search_query(self, query: str, request_id: int) -> None:
        filtered_tasks = None if not query else await self.ctx.task_service.search(query)
        if request_id != self._search_request_id or not self.is_mounted:
            return
        self._ui_state.filtered_tasks = filtered_tasks
        await self._board.refresh_board()

    def action_new_task(self) -> None:
        self.run_worker(self._open_task_details_modal(), group="task-modal-new")

    def action_new_auto_task(self) -> None:
        self.run_worker(
            self._open_task_details_modal(initial_type=TaskType.AUTO),
            group="task-modal-new-auto",
        )

    async def _open_task_details_modal(
        self,
        *,
        task: Task | None = None,
        start_editing: bool = False,
        initial_type: TaskType | None = None,
    ) -> None:
        editing_task_id = task.id if task is not None else None
        result = await await_screen_result(
            self.app,
            TaskDetailsModal(
                task=task,
                start_editing=start_editing,
                initial_type=initial_type,
            ),
        )
        await self._handle_task_details_result(result, editing_task_id=editing_task_id)

    async def _handle_task_details_result(
        self,
        result: ModalAction | dict | None,
        *,
        editing_task_id: str | None,
    ) -> None:
        if isinstance(result, dict):
            await self._save_task_modal_changes(result, editing_task_id=editing_task_id)
            return
        if result != ModalAction.DELETE or editing_task_id is None:
            return
        task = await self.ctx.task_service.get_task(editing_task_id)
        if task is not None:
            await self._confirm_and_delete_task(task)

    async def _save_task_modal_changes(
        self,
        result: dict,
        *,
        editing_task_id: str | None,
    ) -> None:
        if editing_task_id is None:
            task = await self.ctx.task_service.create_task(
                str(result.get("title", "")),
                str(result.get("description", "")),
                created_by=None,
            )
            update_fields = {
                key: value for key, value in result.items() if key not in ("title", "description")
            }
            if update_fields:
                await self.ctx.task_service.update_fields(task.id, **update_fields)
            await self._board.refresh_board()
            self.notify(f"Created task: {task.title}")
            return

        await self.ctx.task_service.update_fields(editing_task_id, **result)
        await self._board.refresh_board()
        self.notify("Task updated")

    def action_edit_task(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            return
        task = card.task_model
        self.run_worker(
            self._open_task_details_modal(task=task, start_editing=True),
            group=f"task-modal-edit-{task.id}",
        )

    def action_delete_task(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            return
        task = card.task_model
        self.run_worker(
            self._confirm_and_delete_task(task),
            group=f"delete-task-{task.id}",
        )

    def action_delete_task_direct(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            return
        task = card.task_model
        self.run_worker(
            self._confirm_and_delete_task(task),
            group=f"delete-task-direct-{task.id}",
        )

    async def _confirm_and_delete_task(self, task: Task) -> None:
        self._ui_state.pending_delete_task = task
        confirmed = await await_screen_result(
            self.app, ConfirmModal(title="Delete Task?", message=f'"{task.title}"')
        )
        pending_task = self._ui_state.pending_delete_task
        self._ui_state.pending_delete_task = None

        if not confirmed or pending_task is None:
            return
        if self.ctx.merge_service:
            await self.ctx.merge_service.delete_task(pending_task)
        await self._board.refresh_board()
        self.notify(f"Deleted task: {pending_task.title}")
        focus.focus_first_card(self)

    def action_merge_direct(self) -> None:
        self.run_worker(self._review.action_merge_direct(), group="review-merge-direct")

    def action_rebase(self) -> None:
        self.run_worker(self._review.action_rebase(), group="review-rebase")

    def action_move_forward(self) -> None:
        self.run_worker(self._review.move_task(forward=True), group="review-move-forward")

    def action_move_backward(self) -> None:
        self.run_worker(self._review.move_task(forward=False), group="review-move-backward")

    def action_duplicate_task(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            self.notify("No task selected", severity="warning")
            return
        task = card.task_model
        self.run_worker(
            self._run_duplicate_task_flow(task),
            group=f"duplicate-task-{task.id}",
        )

    async def _run_duplicate_task_flow(self, source_task: Task) -> None:
        from kagan.ui.modals.duplicate_task import DuplicateTaskModal

        result = await await_screen_result(self.app, DuplicateTaskModal(source_task=source_task))
        if not result:
            return
        task = await self.ctx.task_service.create_task(
            str(result.get("title", "")),
            str(result.get("description", "")),
            created_by=None,
        )
        update_fields = {
            key: value for key, value in result.items() if key not in ("title", "description")
        }
        if update_fields:
            await self.ctx.task_service.update_fields(task.id, **update_fields)
        await self._board.refresh_board()
        self.notify(f"Created duplicate: #{task.short_id}")
        focus.focus_column(self, TaskStatus.BACKLOG)

    def action_copy_task_id(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            self.notify("No task selected", severity="warning")
            return
        copy_with_notification(self.app, f"#{card.task_model.short_id}", "Task ID")

    def action_view_details(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            return
        task = card.task_model
        self.run_worker(
            self._open_task_details_modal(task=task),
            group=f"task-modal-view-{task.id}",
        )

    def action_expand_description(self) -> None:
        """Expand description in full-screen editor (read-only from Kanban)."""
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            self.notify("No task selected", severity="warning")
            return
        description = card.task_model.description or ""
        modal = DescriptionEditorModal(
            description=description, readonly=True, title="View Description"
        )
        self.app.push_screen(modal)

    def action_open_session(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            return
        self.run_worker(
            self._session.open_session_flow(card.task_model),
            group=f"open-session-{card.task_model.id}",
        )

    def action_start_agent(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            return
        self.run_worker(
            self._session.start_agent_flow(card.task_model),
            group=f"start-agent-{card.task_model.id}",
        )

    async def action_stop_agent(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            return
        task = card.task_model

        self.notify("Stopping agent...", severity="information")

        result = self.ctx.automation_service.stop_task(task.id)
        stopped = await result if hasattr(result, "__await__") else bool(result)
        if not stopped:
            self.notify("No agent running for this task", severity="warning")
            return

        self._board.set_card_indicator(task.id, CardIndicator.IDLE, is_active=False)
        self.notify(f"Agent stopped: {task.id[:8]}", severity="information")

    def action_open_planner(self) -> None:
        self.app.push_screen(PlannerScreen(agent_factory=self.kagan_app._agent_factory))

    def action_switch_global_agent(self) -> None:
        """Open global agent picker."""
        self.run_worker(
            self._switch_global_agent_flow(),
            exclusive=True,
            exit_on_error=False,
        )

    async def _switch_global_agent_flow(self) -> None:
        from kagan.ui.modals import GlobalAgentPickerModal

        current_agent = self.kagan_app.config.general.default_worker_agent
        selected = await await_screen_result(
            self.app, GlobalAgentPickerModal(current_agent=current_agent)
        )
        if not selected:
            return
        await self._session.apply_global_agent_selection(selected)

    async def action_open_settings(self) -> None:
        self.run_worker(
            self._open_settings_flow(),
            group="open-settings",
            exclusive=True,
            exit_on_error=False,
        )

    async def _open_settings_flow(self) -> None:
        from kagan.ui.modals import SettingsModal

        config = self.kagan_app.config
        config_path = self.kagan_app.config_path
        result = await await_screen_result(
            self.app,
            SettingsModal(config, config_path),
        )
        self._on_settings_result(result)

    def _on_settings_result(self, result: bool | None) -> None:
        if not result:
            return
        config_path = self.kagan_app.config_path
        self.kagan_app.config = self.kagan_app.config.load(config_path)
        self.header.update_agent_from_config(self.kagan_app.config)
        self.notify("Settings saved")

    def action_merge(self) -> None:
        self.run_worker(self._review.action_merge(), group="review-merge")

    def action_view_diff(self) -> None:
        self.run_worker(self._review.action_view_diff(), group="review-view-diff")

    def action_open_review(self) -> None:
        self.run_worker(self._review.action_open_review(), group="review-open")

    def action_set_task_branch(self) -> None:
        self.run_worker(
            self._set_task_branch_flow(),
            group="set-task-branch",
            exclusive=True,
            exit_on_error=False,
        )

    async def _set_task_branch_flow(self) -> None:
        card = focus.get_focused_card(self)
        if not card or not card.task_model:
            self.notify("No task focused", severity="warning")
            return

        task = card.task_model

        branches = await self._load_branch_candidates()

        modal = BaseBranchModal(
            branches=branches,
            current_value=task.base_branch or "",
            title="Set Task Branch",
            description=f"Set base branch for: {task.title[:40]}",
        )
        branch = await await_screen_result(self.app, modal)
        if branch is not None:
            await self._update_task_branch(task, branch)

    async def _update_task_branch(self, task: Task, branch: str) -> None:
        await self.ctx.task_service.update_fields(task.id, base_branch=branch or None)
        await self._board.refresh_board()
        self.notify(f"Branch set to: {branch or '(default)'}")

    def action_set_default_branch(self) -> None:
        self.run_worker(
            self._set_default_branch_flow(),
            group="set-default-branch",
            exclusive=True,
            exit_on_error=False,
        )

    async def _set_default_branch_flow(self) -> None:
        config = self.kagan_app.config

        branches = await self._load_branch_candidates()

        modal = BaseBranchModal(
            branches=branches,
            current_value=config.general.default_base_branch,
            title="Set Default Branch",
            description="Set global default branch for new workspaces:",
        )
        branch = await await_screen_result(self.app, modal)
        if branch is not None:
            config.general.default_base_branch = branch or "main"
            self.notify(f"Default branch set to: {branch or 'main'}")

    async def _load_branch_candidates(self) -> list[str]:
        try:
            return await asyncio.wait_for(
                list_local_branches(self.kagan_app.project_root),
                timeout=BRANCH_LOOKUP_TIMEOUT_SECONDS,
            )
        except TimeoutError:
            self.notify(
                "Branch lookup timed out. Enter branch manually.",
                severity="warning",
            )
            return []

    def on_task_card_selected(self, message: TaskCard.Selected) -> None:
        self.action_view_details()
