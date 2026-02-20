"""Main Kanban board screen."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from time import monotonic
from typing import TYPE_CHECKING, Any

from sqlalchemy.exc import OperationalError
from textual import getters, on
from textual.binding import Binding
from textual.containers import Container, Horizontal
from textual.css.query import NoMatches
from textual.reactive import var
from textual.widgets import Static

from kagan.core.adapters.db.repositories.base import RepositoryClosing
from kagan.core.constants import (
    COLUMN_ORDER,
    MIN_SCREEN_HEIGHT,
    MIN_SCREEN_WIDTH,
)
from kagan.core.domain.enums import TaskStatus, TaskType
from kagan.core.git_utils import get_current_branch
from kagan.tui.keybindings import KANBAN_BINDINGS
from kagan.tui.ui.modals.description_editor import DescriptionEditorModal
from kagan.tui.ui.screen_result import await_screen_result
from kagan.tui.ui.screens.base import KaganScreen
from kagan.tui.ui.screens.kanban.commands import (
    KANBAN_ACTIONS,
    KanbanActionId,
    KanbanCommandProvider,
    get_kanban_action,
)
from kagan.tui.ui.screens.kanban.runtime import (
    KanbanBoardController,
    KanbanReviewController,
    KanbanSessionController,
    KanbanTaskController,
    KanbanUiState,
)
from kagan.tui.ui.utils import copy_with_notification, state_attr
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay
from kagan.tui.ui.widgets.column import KanbanColumn
from kagan.tui.ui.widgets.header import KaganHeader
from kagan.tui.ui.widgets.keybinding_hint import KanbanHintBar
from kagan.tui.ui.widgets.offline_banner import OfflineBanner
from kagan.tui.ui.widgets.peek_overlay import PeekOverlay
from kagan.tui.ui.widgets.search_bar import SearchBar

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from textual import events
    from textual.app import ComposeResult
    from textual.timer import Timer

    from kagan.tui.ui.types import TaskView
    from kagan.tui.ui.widgets.card import TaskCard

SIZE_WARNING_MESSAGE = (
    f"Terminal too small\n\n"
    f"Minimum size: {MIN_SCREEN_WIDTH}x{MIN_SCREEN_HEIGHT}\n"
    f"Please resize your terminal"
)
DEFAULT_REPO_SYNC_ACTION_ID = "sync_issues"

KANBAN_DONE_BLOCKED_ACTIONS = frozenset(
    {
        KanbanActionId.EDIT_TASK,
        KanbanActionId.MOVE_FORWARD,
        KanbanActionId.MOVE_BACKWARD,
    }
)
KANBAN_REVIEW_ONLY_ACTIONS = frozenset(
    {
        KanbanActionId.MERGE,
        KanbanActionId.MERGE_DIRECT,
        KanbanActionId.VIEW_DIFF,
        KanbanActionId.OPEN_REVIEW,
        KanbanActionId.REBASE,
    }
)
KANBAN_AUTO_ONLY_ACTIONS = frozenset(
    {
        KanbanActionId.START_AGENT,
        KanbanActionId.STOP_AGENT,
    }
)
KANBAN_ACTIONS_WITH_KEY_FEEDBACK = frozenset(
    {
        KanbanActionId.DELETE_TASK_DIRECT,
        KanbanActionId.MERGE_DIRECT,
        KanbanActionId.REBASE,
        KanbanActionId.EDIT_TASK,
        KanbanActionId.VIEW_DETAILS,
        KanbanActionId.OPEN_SESSION,
        KanbanActionId.START_AGENT,
        KanbanActionId.STOP_AGENT,
        KanbanActionId.VIEW_DIFF,
        KanbanActionId.OPEN_REVIEW,
    }
)


def _as_kanban_action_id(action: str | KanbanActionId | None) -> KanbanActionId | None:
    if action is None:
        return None
    try:
        return KanbanActionId(action)
    except ValueError:
        return None


class KanbanScreen(KaganScreen):
    """Main Kanban board screen with 4 columns."""

    COMMANDS = {KanbanCommandProvider}
    BINDINGS = KANBAN_BINDINGS
    search_visible: var[bool] = var(False, init=False)

    header = getters.query_one(KaganHeader)

    BRANCH_SYNC_INTERVAL_SECONDS: float = 5.0

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._tasks: list[TaskView] = []
        self._last_focused_task_id: str | None = None
        self._ui_state = KanbanUiState()
        self._refresh_timer: Timer | None = None
        self._board_sync_timer: Timer | None = None
        self._board_sync_interval_seconds: float | None = None
        self._board_fast_ticks_remaining: int = 0
        self._task_hashes: dict[str, int] = {}
        self._agent_offline: bool = False
        self._merge_failed_tasks: set[str] = set()
        self._search_request_id: int = 0
        self._branch_sync_timer: Timer | None = None
        self._board = KanbanBoardController(self)
        self._review = KanbanReviewController(self)
        self._session = KanbanSessionController(self)
        self._task_controller = KanbanTaskController(self)
        self._plugin_ui_catalog: dict[str, Any] | None = None
        self._plugin_ui_catalog_fetched_at: float = 0.0
        self._plugin_ui_catalog_lock = asyncio.Lock()

    _TASK_REQUIRED_ACTIONS = frozenset(item.action for item in KANBAN_ACTIONS if item.requires_task)
    _AGENT_REQUIRED_ACTIONS = frozenset(
        item.action for item in KANBAN_ACTIONS if item.requires_agent
    )

    def _validate_action(self, action: str | KanbanActionId) -> tuple[bool, str | None]:
        action_id = _as_kanban_action_id(action)
        if self._agent_offline and action_id in self._AGENT_REQUIRED_ACTIONS:
            return (False, "Agent unavailable (offline mode)")

        card = self.get_focused_card()
        task = card.task_model if card else None

        if not task:
            if action_id in self._TASK_REQUIRED_ACTIONS:
                return (False, "No task selected")
            return (True, None)

        status = task.status
        task_type = task.task_type

        if action_id in KANBAN_DONE_BLOCKED_ACTIONS and status is TaskStatus.DONE:
            message = "Done tasks cannot be edited. Use [y] to duplicate."
            if action_id in {KanbanActionId.MOVE_FORWARD, KanbanActionId.MOVE_BACKWARD}:
                message = "Done tasks cannot be moved. Use [y] to duplicate."
            return (False, message)

        if action_id in KANBAN_REVIEW_ONLY_ACTIONS:
            if status != TaskStatus.REVIEW:
                return (False, f"Only available for REVIEW tasks (current: {status.value})")
            return (True, None)

        if action_id in KANBAN_AUTO_ONLY_ACTIONS:
            if task_type is not TaskType.AUTO:
                return (False, "Only available for AUTO tasks")
            if action_id is KanbanActionId.STOP_AGENT and not self._is_runtime_running(task.id):
                return (False, "No agent running for this task")
            return (True, None)

        return (True, None)

    def check_action(self, action: str, parameters: tuple[object, ...]) -> bool | None:
        is_valid, _ = self._validate_action(action)
        return True if is_valid else None

    def _runtime_view(self, task_id: str):
        return self.ctx.api.get_runtime_view(task_id)

    @staticmethod
    def _runtime_attr(runtime_view: object | None, name: str, default: Any = None) -> Any:
        return state_attr(runtime_view, name, default)

    def _is_runtime_running(self, task_id: str) -> bool:
        runtime_view = self._runtime_view(task_id)
        return bool(self._runtime_attr(runtime_view, "is_running", False))

    def _runtime_run_count(self, task_id: str) -> int:
        runtime_view = self._runtime_view(task_id)
        run_count = self._runtime_attr(runtime_view, "run_count", 0)
        if isinstance(run_count, int) and not isinstance(run_count, bool):
            return run_count
        return 0

    def get_columns(self) -> list[KanbanColumn]:
        return [
            self.query_one(f"#column-{status.value.lower()}", KanbanColumn)
            for status in COLUMN_ORDER
        ]

    def get_focused_card(self) -> TaskCard | None:
        from kagan.tui.ui.widgets.card import TaskCard

        focused = self.app.focused
        if isinstance(focused, TaskCard):
            return focused
        if focused is None:
            return None
        for ancestor in focused.ancestors:
            if isinstance(ancestor, TaskCard):
                return ancestor
        return None

    @property
    def last_focused_task_id(self) -> str | None:
        return self._last_focused_task_id

    def _remember_focused_task(self) -> None:
        card = self.get_focused_card()
        if card is None or card.task_model is None:
            return
        self._last_focused_task_id = card.task_model.id

    def focus_first_card(self) -> None:
        for column in self.get_columns():
            if column.focus_first_card():
                return

    def focus_column(self, status: TaskStatus) -> None:
        column = self.query_one(f"#column-{status.value.lower()}", KanbanColumn)
        column.focus_first_card()

    def focus_horizontal(self, direction: int) -> None:
        card = self.get_focused_card()
        columns = self.get_columns()
        if not card or not card.task_model:
            self.focus_first_card()
            return

        column_index = next(
            (
                index
                for index, status in enumerate(COLUMN_ORDER)
                if status == card.task_model.status
            ),
            -1,
        )
        card_index = columns[column_index].get_focused_card_index() or 0
        target_column_index = column_index + direction
        while 0 <= target_column_index < len(COLUMN_ORDER):
            cards = columns[target_column_index].get_cards()
            if cards:
                columns[target_column_index].focus_card(min(card_index, len(cards) - 1))
                return
            target_column_index += direction

    def focus_vertical(self, direction: int) -> None:
        card = self.get_focused_card()
        if not card or not card.task_model:
            self.focus_first_card()
            return

        status = card.task_model.status
        status_str = status.value if isinstance(status, TaskStatus) else status
        column = self.query_one(f"#column-{status_str.lower()}", KanbanColumn)
        index = column.get_focused_card_index()
        cards = column.get_cards()
        if index is None:
            return
        new_index = index + direction
        if 0 <= new_index < len(cards):
            column.focus_card(new_index)

    def compose(self) -> ComposeResult:
        yield KaganHeader(task_count=0)
        yield SearchBar(id="search-bar").data_bind(is_visible=KanbanScreen.search_visible)
        with Container(classes="board-container"):
            with Horizontal(classes="board"):
                for status in COLUMN_ORDER:
                    yield KanbanColumn(status=status, tasks=[])
            yield ChatOverlay(agent_factory=self.kagan_app._agent_factory, id="chat-overlay")
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
        self.focus_first_card()
        self.kagan_app.task_changed_signal.subscribe(self, self._on_task_changed)
        self._board.start_background_sync()
        self._board.sync_agent_states()
        if self.ctx.active_repo_id is None:
            self.header.update_branch("")
        else:
            branch = await get_current_branch(self.kagan_app.project_root)
            self.header.update_branch(branch)
        self._start_branch_sync()
        # Start on the board when tasks exist; use fullscreen intro only on empty boards.
        try:
            overlay = self.query_one("#chat-overlay", ChatOverlay)
            if await self._should_show_startup_intro():
                overlay.show(fullscreen=True)
        except NoMatches:
            pass
        self.sync_empty_placeholders_for_overlay()

    def on_unmount(self) -> None:
        self._stop_branch_sync()
        with suppress(Exception):
            self.kagan_app.task_changed_signal.unsubscribe(self)
        self.invalidate_search_requests(cancel_workers=True)
        self._board.cleanup_on_unmount()

    async def on_screen_suspend(self) -> None:
        self._stop_branch_sync()
        self._board.stop_background_sync()

    async def _on_task_changed(self, _task_id: str) -> None:
        if not self.is_mounted:
            return
        self._board.schedule_refresh()

    def on_descendant_focus(self, event: events.DescendantFocus) -> None:
        del event
        self._remember_focused_task()
        self._board.update_keybinding_hints()
        self.refresh_bindings()

    def on_resize(self, event: events.Resize) -> None:
        self._board.check_screen_size()
        self.call_after_refresh(self.sync_empty_placeholders_for_overlay)

    async def on_screen_resume(self) -> None:
        self._start_branch_sync()
        self._board.start_background_sync()
        await self._refresh_plugin_ui_catalog(force=True)
        await self._board.refresh_board()
        self._board.sync_agent_states()

    async def reset_for_repo_change(self) -> None:
        await self._board.reset_for_repo_change()

    async def prepare_for_orchestrator_return(self) -> None:
        """Ensure board reflects orchestrator-created tasks when overlay returns focus."""
        self._clear_search_state(cancel_workers=True)
        await self._board.refresh_board()
        self._board.sync_agent_states()

    @on(OfflineBanner.Reconnect)
    def on_offline_banner_reconnect(self, event: OfflineBanner.Reconnect) -> None:
        """Handle reconnect from offline banner - refresh agent health check."""
        self.ctx.api.refresh_agent_health()
        if self.ctx.api.is_agent_available():
            self._agent_offline = False

            for banner in self.query(OfflineBanner):
                banner.remove()
            self.notify("Agent is now available", severity="information")
        else:
            self.notify("Agent still unavailable", severity="warning")

    def action_focus_left(self) -> None:
        self.focus_horizontal(-1)

    def action_focus_right(self) -> None:
        self.focus_horizontal(1)

    def action_focus_up(self) -> None:
        self.focus_vertical(-1)

    def action_focus_down(self) -> None:
        self.focus_vertical(1)

    def action_deselect(self) -> None:
        try:
            overlay = self.query_one("#chat-overlay", ChatOverlay)
            if overlay.has_class("visible"):
                overlay.hide()
                return
        except NoMatches:
            pass
        try:
            overlay = self.query_one("#peek-overlay", PeekOverlay)
            if overlay.has_class("visible"):
                overlay.hide()
                return
        except NoMatches:
            pass
        if self.search_visible:
            self._clear_search_state(cancel_workers=True)
            self.run_worker(self._board.refresh_board())
            return
        self._last_focused_task_id = None
        self.app.set_focus(None)

    def action_quit(self) -> None:
        self.app.exit()

    def action_interrupt(self) -> None:
        # Ctrl+C is handled by chat-focused widgets; board-level interrupt is a no-op.
        return

    def action_toggle_peek(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.TOGGLE_PEEK)

    @staticmethod
    def _task_value(task: object | None, key: str) -> object:
        if task is None:
            return None
        if isinstance(task, dict):
            return task.get(key)
        return getattr(task, key, None)

    @classmethod
    def _task_id_value(cls, task: object | None) -> str | None:
        raw_task_id = cls._task_value(task, "id") or cls._task_value(task, "task_id")
        task_id = str(raw_task_id or "").strip()
        return task_id or None

    @classmethod
    def _task_type_value(cls, task: object | None) -> TaskType | None:
        raw_task_type = cls._task_value(task, "task_type")
        if isinstance(raw_task_type, TaskType):
            return raw_task_type
        if isinstance(raw_task_type, str):
            normalized = raw_task_type.strip().lower()
        else:
            enum_value = getattr(raw_task_type, "value", None)
            normalized = enum_value.strip().lower() if isinstance(enum_value, str) else ""
        for task_type in TaskType:
            if normalized == task_type.value:
                return task_type
        return None

    @classmethod
    def _task_status_value(cls, task: object | None) -> TaskStatus | None:
        raw_status = cls._task_value(task, "status")
        if isinstance(raw_status, TaskStatus):
            return raw_status
        if isinstance(raw_status, str):
            normalized = raw_status.strip().lower()
        else:
            enum_value = getattr(raw_status, "value", None)
            normalized = enum_value.strip().lower() if isinstance(enum_value, str) else ""
        for status in TaskStatus:
            if normalized == status.value:
                return status
        return None

    def _chat_task(self) -> object | None:
        """Get focused task object for chat (fallback: first board task)."""
        card = self.get_focused_card()
        if card and card.task_model:
            return card.task_model
        if self._tasks:
            return self._tasks[0]
        return None

    async def _should_show_startup_intro(self) -> bool:
        """Return True when startup should open the fullscreen orchestrator intro."""
        if self._tasks:
            return False

        project_id = self.ctx.active_project_id
        if not project_id:
            return True

        # Startup can race with initial board hydration; verify persisted tasks directly.
        try:
            return not bool(await self.ctx.api.list_tasks(project_id=project_id))
        except (ConnectionError, RepositoryClosing, OperationalError):
            return True
        except ValueError as exc:
            if str(exc) == "Connection closed":
                return True
            raise

    def _chat_task_id(self) -> str | None:
        """Get task id for chat (focused card or first task)."""
        return self._task_id_value(self._chat_task())

    def sync_empty_placeholders_for_overlay(self) -> None:
        """Keep empty-column placeholders centered in visible board area."""
        offset_y = 0
        with suppress(NoMatches):
            overlay = self.query_one("#chat-overlay", ChatOverlay)
            if overlay.has_class("visible") and not overlay.has_class("fullscreen"):
                overlay_height = overlay.region.height or overlay.size.height
                if overlay_height > 0:
                    offset_y = -(overlay_height // 2)
        for status in COLUMN_ORDER:
            with suppress(NoMatches):
                column = self.query_one(f"#column-{status.value.lower()}", KanbanColumn)
                column.set_empty_placeholder_offset(offset_y)

    def action_toggle_chat_overlay(self) -> None:
        """Toggle docked orchestrator overlay (switch fullscreen -> docked)."""
        try:
            overlay = self.query_one("#chat-overlay", ChatOverlay)
        except NoMatches:
            return
        if overlay.has_class("visible"):
            if overlay.has_class("fullscreen"):
                overlay.show(fullscreen=False)
                return
            overlay.hide()
            return
        task = self._chat_task()
        if task is not None:
            overlay.show_for_task(task, fullscreen=False)
            return
        overlay.show(fullscreen=False)

    def action_toggle_orchestrator_dock(self) -> None:
        """Alias with explicit orchestrator wording for docked toggle behavior."""
        self.action_toggle_chat_overlay()

    async def _run_toggle_chat_overlay(self) -> None:
        """Async wrapper for docked orchestrator toggle behavior."""
        self.action_toggle_chat_overlay()

    def action_open_chat_fullscreen(self) -> None:
        """Toggle fullscreen orchestrator overlay (switch docked -> fullscreen)."""
        try:
            overlay = self.query_one("#chat-overlay", ChatOverlay)
        except NoMatches:
            return
        if overlay.has_class("visible") and overlay.has_class("fullscreen"):
            overlay.hide()
            return
        if overlay.has_class("visible"):
            overlay.show(fullscreen=True)
            return
        task = self._chat_task()
        if task is not None:
            overlay.show_for_task(task, fullscreen=True)
            return
        overlay.show(fullscreen=True)

    def action_toggle_orchestrator_fullscreen(self) -> None:
        """Alias with explicit orchestrator wording for fullscreen toggle."""
        self.action_open_chat_fullscreen()

    async def _toggle_peek_flow(self, task: TaskView) -> None:
        card = self.get_focused_card()
        if not card or not card.task_model:
            return
        try:
            overlay = self.query_one("#peek-overlay", PeekOverlay)
        except NoMatches:
            return
        if not overlay.toggle():
            return

        if task.task_type == TaskType.AUTO:
            if self._is_runtime_running(task.id):
                run_count = self._runtime_run_count(task.id)
                run_label = f" (Run {run_count})" if run_count > 0 else ""
                status = f"🟢 Running{run_label}"
            else:
                status = "⚪ Idle"
        else:
            is_active = await self.ctx.api.session_exists(task.id)
            status = "🟢 Session Active" if is_active else "⚪ No Active Session"

        scratchpad = await self.ctx.api.get_scratchpad(task.id)
        content = scratchpad if scratchpad else "(No scratchpad)"

        overlay.update_content(task.short_id, task.title, status, content)
        x_pos = min(card.region.x + card.region.width + 2, self.size.width - 55)
        y_pos = max(1, card.region.y)
        overlay.show_at(x_pos, y_pos)

    def on_key(self, event: events.Key) -> None:
        try:
            overlay = self.query_one("#chat-overlay", ChatOverlay)
            if overlay.has_class("visible"):
                focused = self.app.focused
                focus_inside_overlay = bool(
                    focused is not None and (focused is overlay or overlay in focused.ancestors)
                )
                # Keep fullscreen overlay modal, but allow board shortcuts while docked.
                if overlay.has_class("fullscreen") and not focus_inside_overlay:
                    if event.key == "escape":
                        overlay.hide()
                        overlay._run_overlay_worker(
                            overlay._cancel_active_prompt,
                            group="chat-overlay-cancel",
                            exclusive=True,
                        )
                    elif event.key == "ctrl+c":
                        overlay.handle_ctrl_c()
                    event.stop()
                    return
                if focus_inside_overlay:
                    return
        except NoMatches:
            pass
        if event.key == "enter" and not self.search_visible:
            if self._dispatch_kanban_action(KanbanActionId.OPEN_SESSION):
                event.stop()
                return

        key_action_map = {
            binding.key: action_id
            for binding in KANBAN_BINDINGS
            if isinstance(binding, Binding)
            and (action_id := _as_kanban_action_id(binding.action))
            in KANBAN_ACTIONS_WITH_KEY_FEEDBACK
        }
        action_id = key_action_map.get(event.key)
        if action_id is None:
            return
        _, reason = self._validate_action(action_id)
        if reason:
            self.notify(reason, severity="warning")

    def action_toggle_search(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.TOGGLE_SEARCH)

    async def _toggle_search_flow(self) -> None:
        if self.search_visible:
            self._clear_search_state(cancel_workers=True)
            await self._board.refresh_board()
            return
        self.search_visible = True

    @on(SearchBar.QueryChanged)
    def on_search_query_changed(self, event: SearchBar.QueryChanged) -> None:
        if not self.search_visible:
            return
        request_id = self._next_search_request_id()
        query = event.query.strip()
        self.run_worker(
            self._apply_search_query(query, request_id),
            group="kanban-search",
            exclusive=True,
            exit_on_error=False,
        )

    async def _apply_search_query(self, query: str, request_id: int) -> None:
        try:
            filtered_tasks = None if not query else await self.ctx.api.search_tasks(query)
        except asyncio.CancelledError:
            return
        if request_id != self._search_request_id or not self.is_mounted or not self.search_visible:
            return
        self._ui_state.filtered_tasks = filtered_tasks
        await self._board.refresh_board()

    def _next_search_request_id(self) -> int:
        self._search_request_id += 1
        return self._search_request_id

    def invalidate_search_requests(self, *, cancel_workers: bool = False) -> None:
        self._search_request_id += 1
        if not cancel_workers:
            return
        for worker in self.workers:
            if worker.node == self and worker.group == "kanban-search" and not worker.is_finished:
                worker.cancel()

    def _clear_search_state(self, *, cancel_workers: bool) -> None:
        self.invalidate_search_requests(cancel_workers=cancel_workers)
        self.search_visible = False
        self._ui_state.filtered_tasks = None

    def _focused_task(self, *, notify_on_missing: bool = False) -> TaskView | None:
        card = self.get_focused_card()
        if card and card.task_model:
            self._last_focused_task_id = card.task_model.id
            return card.task_model
        if self._last_focused_task_id is not None:
            fallback = next(
                (task for task in self._tasks if task.id == self._last_focused_task_id),
                None,
            )
            if fallback is not None:
                return fallback
        if notify_on_missing:
            self.notify("No task selected", severity="warning")
        return None

    def _is_worker_group_active(self, group: str) -> bool:
        return any(
            worker.node == self and worker.group == group and not worker.is_finished
            for worker in self.workers
        )

    def _run_worker_for_action(
        self, action: str | KanbanActionId, operation: Awaitable[None]
    ) -> None:
        spec = get_kanban_action(action)
        if spec is None:
            self.run_worker(operation)
            return

        if spec.worker_group is not None:
            self.run_worker(
                operation,
                group=spec.worker_group,
                exclusive=spec.exclusive,
                exit_on_error=spec.exit_on_error,
            )
            return

        self.run_worker(
            operation,
            exclusive=spec.exclusive,
            exit_on_error=spec.exit_on_error,
        )

    def _dispatch_kanban_action(
        self,
        action: str | KanbanActionId,
        *,
        notify_on_missing_task: bool = False,
    ) -> bool:
        action_id = _as_kanban_action_id(action)
        action_value = action_id if action_id is not None else str(action)
        spec = get_kanban_action(action_value)
        if (
            action_id == KanbanActionId.OPEN_SESSION
            and spec is not None
            and spec.worker_group is not None
            and self._is_worker_group_active(spec.worker_group)
        ):
            return True
        operation = self._resolve_kanban_action_operation(
            action,
            notify_on_missing_task=notify_on_missing_task,
        )
        if operation is None:
            return False
        self._run_worker_for_action(action_value, operation)
        return True

    def run_kanban_action(self, action: str) -> None:
        """Dispatch a Kanban action through the shared action table."""
        notify_on_missing = action == KanbanActionId.DUPLICATE_TASK
        if self._dispatch_kanban_action(action, notify_on_missing_task=notify_on_missing):
            return
        action_method = getattr(self, f"action_{action}", None)
        if action_method is None:
            return
        result = action_method()
        if asyncio.iscoroutine(result):
            self.run_worker(result)

    def _resolve_kanban_action_operation(
        self,
        action: str | KanbanActionId,
        *,
        notify_on_missing_task: bool = False,
    ) -> Awaitable[None] | None:
        action_id = _as_kanban_action_id(action)
        action_value = action_id if action_id is not None else str(action)
        spec = get_kanban_action(action_value)
        task: TaskView | None = None
        if spec is not None and spec.requires_task:
            task = self._focused_task(notify_on_missing=notify_on_missing_task)
            if task is None:
                return None

        if task is not None:
            task_operation = self._resolve_task_action_operation(action_id, task)
            if task_operation is not None:
                return task_operation
        return self._resolve_global_action_operation(action_id)

    def _resolve_task_action_operation(
        self, action: KanbanActionId | None, task: TaskView
    ) -> Awaitable[None] | None:
        if action is None:
            return None
        task_operations: dict[KanbanActionId, Callable[[TaskView], Awaitable[None]]] = {
            KanbanActionId.EDIT_TASK: lambda selected: self._open_task_details_modal(
                task=selected,
                start_editing=True,
            ),
            KanbanActionId.DELETE_TASK_DIRECT: self._confirm_and_delete_task,
            KanbanActionId.DUPLICATE_TASK: self._run_duplicate_task_flow,
            KanbanActionId.VIEW_DETAILS: lambda selected: self._open_task_details_modal(
                task=selected
            ),
            KanbanActionId.TOGGLE_PEEK: self._toggle_peek_flow,
            KanbanActionId.OPEN_SESSION: self._open_session_flow,
            KanbanActionId.START_AGENT: self._start_agent_for_task,
            KanbanActionId.STOP_AGENT: self._stop_agent_flow,
            KanbanActionId.SET_TASK_BRANCH: self._set_task_branch_flow,
            KanbanActionId.MERGE_DIRECT: lambda _selected: self._review.action_merge_direct(),
            KanbanActionId.REBASE: lambda _selected: self._review.action_rebase(),
            KanbanActionId.MOVE_FORWARD: lambda _selected: self._review.move_task(forward=True),
            KanbanActionId.MOVE_BACKWARD: lambda _selected: self._review.move_task(forward=False),
            KanbanActionId.VIEW_DIFF: lambda _selected: self._review.action_view_diff(),
            KanbanActionId.OPEN_REVIEW: lambda _selected: self._review.action_open_review(),
        }
        operation_factory = task_operations.get(action)
        if operation_factory is None:
            return None
        return operation_factory(task)

    def _resolve_global_action_operation(
        self, action: KanbanActionId | None
    ) -> Awaitable[None] | None:
        if action is None:
            return None
        global_operations: dict[KanbanActionId, Callable[[], Awaitable[None]]] = {
            KanbanActionId.NEW_TASK: self._open_task_details_modal,
            KanbanActionId.NEW_AUTO_TASK: lambda: self._open_task_details_modal(
                initial_type=TaskType.AUTO
            ),
            KanbanActionId.TOGGLE_SEARCH: self._toggle_search_flow,
            KanbanActionId.SWITCH_GLOBAL_AGENT: self._switch_global_agent_flow,
            KanbanActionId.OPEN_SETTINGS: self._open_settings_flow,
            KanbanActionId.TOGGLE_CHAT: lambda: self._run_toggle_chat_overlay(),
        }
        operation_factory = global_operations.get(action)
        if operation_factory is None:
            return None
        return operation_factory()

    def action_new_task(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.NEW_TASK)

    def action_new_auto_task(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.NEW_AUTO_TASK)

    async def _open_task_details_modal(
        self,
        *,
        task: TaskView | None = None,
        start_editing: bool = False,
        initial_type: TaskType | None = None,
    ) -> None:
        await self._task_controller.open_task_details_modal(
            task=task,
            start_editing=start_editing,
            initial_type=initial_type,
        )

    async def _handle_task_details_result(
        self,
        result: object | dict | None,
        *,
        editing_task_id: str | None,
    ) -> None:
        await self._task_controller.handle_task_details_result(
            result,
            editing_task_id=editing_task_id,
        )

    async def _save_task_modal_changes(
        self,
        result: dict,
        *,
        editing_task_id: str | None,
    ) -> None:
        await self._task_controller.save_task_modal_changes(result, editing_task_id=editing_task_id)

    async def _create_task_from_payload(self, payload: dict) -> TaskView:
        return await self._task_controller.create_task_from_payload(payload)

    def _extract_non_content_update_fields(self, payload: dict) -> dict:
        return self._task_controller.extract_non_content_update_fields(payload)

    async def _handle_task_type_transition(
        self, task: TaskView, update_fields: dict[str, object]
    ) -> bool:
        return await self._task_controller.handle_task_type_transition(task, update_fields)

    def action_edit_task(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.EDIT_TASK)

    def action_delete_task_direct(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.DELETE_TASK_DIRECT)

    async def _confirm_and_delete_task(self, task: TaskView) -> None:
        await self._task_controller.confirm_and_delete_task(task)

    def action_merge_direct(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.MERGE_DIRECT)

    def action_rebase(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.REBASE)

    def action_move_forward(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.MOVE_FORWARD)

    def action_move_backward(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.MOVE_BACKWARD)

    def action_duplicate_task(self) -> None:
        self._dispatch_kanban_action(
            KanbanActionId.DUPLICATE_TASK,
            notify_on_missing_task=True,
        )

    async def _run_duplicate_task_flow(self, source_task: TaskView) -> None:
        await self._task_controller.run_duplicate_task_flow(source_task)

    def action_copy_task_id(self) -> None:
        task = self._focused_task(notify_on_missing=True)
        if task is None:
            return
        copy_with_notification(self.app, f"#{task.short_id}", "Task ID")

    def action_view_details(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.VIEW_DETAILS)

    def action_expand_description(self) -> None:
        """Expand description in full-screen editor (read-only from Kanban)."""
        card = self.get_focused_card()
        if not card or not card.task_model:
            self.notify("No task selected", severity="warning")
            return
        description = card.task_model.description or ""
        modal = DescriptionEditorModal(
            description=description, readonly=True, title="View Description"
        )
        self.app.push_screen(modal)

    def action_open_session(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.OPEN_SESSION)

    async def _open_orchestrator_for_task(self, task: object, *, fullscreen: bool = True) -> None:
        try:
            overlay = self.query_one("#chat-overlay", ChatOverlay)
        except NoMatches:
            return
        overlay.show_for_task(task, fullscreen=fullscreen)

    async def _open_session_flow(self, task: TaskView) -> None:
        """Open a focused task using mode-aware session routing."""
        await self._session.open_session_flow(task)

    async def _start_agent_for_task(self, task: TaskView | object) -> None:
        task_id = self._task_id_value(task)
        if not task_id:
            self.notify("No task selected", severity="warning")
            return
        task_for_start: TaskView | object = task
        if isinstance(task_for_start, dict):
            refreshed_task = await self.ctx.api.get_task(task_id)
            if refreshed_task is None:
                self.notify("Unable to load task before starting agent", severity="warning")
                return
            task_for_start = refreshed_task
        await self._session.start_agent_flow(task_for_start)

    def action_start_agent(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.START_AGENT)

    async def action_stop_agent(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.STOP_AGENT)

    async def _stop_agent_flow(self, task: TaskView) -> None:
        await self._task_controller.stop_agent_flow(task)

    def action_switch_global_agent(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.SWITCH_GLOBAL_AGENT)

    async def _switch_global_agent_flow(self) -> None:
        from kagan.tui.ui.modals import GlobalAgentPickerModal

        current_agent = self.kagan_app.config.general.default_worker_agent
        selected = await await_screen_result(
            self.app, GlobalAgentPickerModal(current_agent=current_agent)
        )
        if not selected:
            return
        await self._session.apply_global_agent_selection(selected)

    async def action_open_settings(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.OPEN_SETTINGS)

    async def _open_settings_flow(self) -> None:
        from kagan.tui.ui.modals import SettingsModal

        config = self.kagan_app.config
        result = await await_screen_result(
            self.app,
            SettingsModal(config, self.ctx.api),
        )
        self._on_settings_result(result)

    def _on_settings_result(self, result: bool | None) -> None:
        if not result:
            return
        config_path = self.kagan_app.config_path
        self.kagan_app.config = self.kagan_app.config.load(config_path)
        self.ctx.config = self.kagan_app.config
        self.header.update_agent_from_config(self.kagan_app.config)
        self.notify("Settings saved")

    def action_view_diff(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.VIEW_DIFF)

    def action_open_review(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.OPEN_REVIEW)

    def action_set_task_branch(self) -> None:
        self._dispatch_kanban_action(KanbanActionId.SET_TASK_BRANCH)

    def action_repo_sync(self) -> None:
        """Invoke the default repo sync plugin action from the catalog."""
        self.run_worker(self._invoke_catalog_action(DEFAULT_REPO_SYNC_ACTION_ID))

    async def _invoke_catalog_action(self, action_id: str) -> None:
        """Look up a plugin action by action_id in the catalog and invoke it."""
        catalog = await self._refresh_plugin_ui_catalog()
        actions = catalog.get("actions", [])
        if not isinstance(actions, list):
            self.notify("Plugin actions unavailable", severity="warning")
            return
        action = next(
            (
                item
                for item in actions
                if isinstance(item, dict) and item.get("action_id") == action_id
            ),
            None,
        )
        if action is None:
            self.notify(f"Action '{action_id}' not available", severity="warning")
            return
        plugin_id = action.get("plugin_id", "")
        if not plugin_id:
            self.notify("Action has no plugin_id", severity="warning")
            return
        await self.invoke_plugin_ui_action(plugin_id, action_id)

    async def _refresh_plugin_ui_catalog(self, *, force: bool = False) -> dict[str, Any]:
        if not force and self._plugin_ui_catalog is not None:
            if monotonic() - self._plugin_ui_catalog_fetched_at < 2.0:
                return dict(self._plugin_ui_catalog)

        async with self._plugin_ui_catalog_lock:
            if not force and self._plugin_ui_catalog is not None:
                if monotonic() - self._plugin_ui_catalog_fetched_at < 2.0:
                    return dict(self._plugin_ui_catalog)

            project = await self._get_active_project()
            if project is None:
                self._plugin_ui_catalog = {
                    "schema_version": "1",
                    "actions": [],
                    "forms": [],
                    "badges": [],
                }
                self._plugin_ui_catalog_fetched_at = monotonic()
                return dict(self._plugin_ui_catalog)

            try:
                catalog = await self.ctx.api.plugin_ui_catalog(
                    project_id=project.id,
                    repo_id=self.ctx.active_repo_id,
                )
            except Exception:
                catalog = {"schema_version": "1", "actions": [], "forms": [], "badges": []}

            if not isinstance(catalog, dict):
                catalog = {"schema_version": "1", "actions": [], "forms": [], "badges": []}

            self._plugin_ui_catalog = dict(catalog)
            self._plugin_ui_catalog_fetched_at = monotonic()
            return dict(self._plugin_ui_catalog)

    async def get_plugin_ui_actions(self, *, surface: str) -> list[dict[str, Any]]:
        catalog = await self._refresh_plugin_ui_catalog()
        actions = catalog.get("actions", [])
        if not isinstance(actions, list):
            return []
        return [
            action
            for action in actions
            if isinstance(action, dict) and action.get("surface") == surface
        ]

    def run_plugin_ui_action(self, plugin_id: str, action_id: str) -> None:
        """Dispatch a plugin UI action in a worker-safe context."""
        self.run_worker(
            self.invoke_plugin_ui_action(plugin_id, action_id),
            group=f"plugin-ui-action-{plugin_id}-{action_id}",
            exclusive=True,
            exit_on_error=False,
        )

    async def invoke_plugin_ui_action(self, plugin_id: str, action_id: str) -> None:
        project = await self._get_active_project()
        if project is None:
            self.notify("No active project", severity="warning")
            return
        project_id = project.id

        catalog = await self._refresh_plugin_ui_catalog()
        actions = catalog.get("actions", [])
        forms = catalog.get("forms", [])
        if not isinstance(actions, list) or not isinstance(forms, list):
            self.notify("Plugin actions unavailable", severity="warning")
            return

        action = next(
            (
                item
                for item in actions
                if isinstance(item, dict)
                and item.get("plugin_id") == plugin_id
                and item.get("action_id") == action_id
            ),
            None,
        )
        if action is None:
            self.notify("Plugin action not available", severity="warning")
            return

        repo_id = self.ctx.active_repo_id
        inputs: dict[str, Any] = {}

        # For task-scoped actions, inject the focused task's ID automatically.
        surface = str(action.get("surface") or "").strip()
        if surface == "kanban.task_actions":
            task = self._focused_task(notify_on_missing=True)
            if task is None:
                return
            inputs["task_id"] = task.id

        form_id = action.get("form_id")
        if isinstance(form_id, str) and form_id.strip():
            form = next(
                (
                    item
                    for item in forms
                    if isinstance(item, dict)
                    and item.get("plugin_id") == plugin_id
                    and item.get("form_id") == form_id
                ),
                None,
            )
            if form is not None:
                from kagan.tui.ui.modals import PluginFormModal

                initial_values: dict[str, Any] = {}
                if repo_id:
                    initial_values["repo_id"] = repo_id
                payload = await await_screen_result(
                    self.app,
                    PluginFormModal(form=form, initial_values=initial_values),
                )
                if payload is None:
                    return
                if isinstance(payload, dict):
                    inputs.update(payload)
                    selected_repo_id = inputs.get("repo_id")
                    if isinstance(selected_repo_id, str) and selected_repo_id.strip():
                        repo_id = selected_repo_id.strip()
                        inputs.pop("repo_id", None)

        label = str(action.get("label") or "").strip()
        if label:
            self.notify(f"{label}...", severity="information")

        try:
            result = await self.ctx.api.plugin_ui_invoke(
                project_id=project_id,
                repo_id=repo_id,
                plugin_id=plugin_id,
                action_id=action_id,
                inputs=inputs or None,
            )
        except Exception as exc:
            self.notify(str(exc), severity="error")
            return

        if not isinstance(result, dict):
            self.notify("Unexpected plugin action response", severity="error")
            return

        ok = bool(result.get("ok", False))
        message = str(result.get("message") or ("OK" if ok else "Action failed"))
        code = str(result.get("code") or "")
        hint: str | None = None
        data = result.get("data")
        if isinstance(data, dict):
            hint_value = data.get("hint")
            if isinstance(hint_value, str) and hint_value.strip():
                hint = hint_value.strip()
        if hint and hint not in message:
            message = f"{message} ({hint})"
        severity = "information" if ok else ("warning" if "NOT_CONNECTED" in code else "error")
        self.notify(message, severity=severity)

        refresh = result.get("refresh") if isinstance(result.get("refresh"), dict) else {}
        if isinstance(refresh, dict) and refresh.get("tasks") is True:
            await self._board.refresh_board()
        if isinstance(refresh, dict) and refresh.get("repo") is True:
            await self.sync_header_context(self.header)

    async def _set_task_branch_flow(self, task: TaskView) -> None:
        await self._task_controller.set_task_branch_flow(task)

    async def _update_task_branch(self, task: TaskView, branch: str) -> None:
        await self._task_controller.update_task_branch(task, branch)

    def _start_branch_sync(self) -> None:
        """Start periodic git branch polling for auto-sync."""
        if self._branch_sync_timer is not None:
            return
        self._branch_sync_timer = self.set_interval(
            self.BRANCH_SYNC_INTERVAL_SECONDS,
            self._schedule_branch_sync,
        )

    def _stop_branch_sync(self) -> None:
        """Stop periodic git branch polling."""
        if self._branch_sync_timer is None:
            return
        self._branch_sync_timer.stop()
        self._branch_sync_timer = None

    def _schedule_branch_sync(self) -> None:
        """Schedule a background worker for branch sync."""
        if not self.is_mounted or not self.app.is_running:
            return
        self.run_worker(
            self.auto_sync_branch(self.header),
            group="kanban-branch-sync",
            exclusive=True,
            exit_on_error=False,
        )
