import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from textual import events, on
from textual.app import ComposeResult, SuspendNotSupported
from textual.containers import Container
from textual.css.query import NoMatches
from textual.reactive import reactive
from textual.screen import Screen
from textual.widgets import Static

from kagan.cli.chat import resolve_default_agent_backend
from kagan.core import resolve_launcher, resolve_spawn_command
from kagan.core.enums import Priority, TaskStatus
from kagan.core.errors import KaganError
from kagan.core.models import Task, Worktree
from kagan.runtime_env import build_sanitized_subprocess_environment
from kagan.tui._utils import is_enabled as _is_enabled
from kagan.tui.keybindings import (
    KANBAN_BINDINGS,
    get_global_shortcut_help_rows,
    get_key_for_action,
    get_keys_for_action,
)
from kagan.tui.screens.confirm import ConfirmModal
from kagan.tui.screens.github_import_modal import GitHubImportSummary
from kagan.tui.screens.kanban_commands import KanbanCommandProvider
from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
from kagan.tui.screens.task_editor_modal import TaskEditorModal
from kagan.tui.screens.tutorial import TutorialOverlay
from kagan.tui.widgets.board import BoardView
from kagan.tui.widgets.card import TaskCard
from kagan.tui.widgets.header import KaganHeader
from kagan.tui.widgets.hint_bar import KanbanHintBar
from kagan.tui.widgets.peek import PeekOverlay
from kagan.tui.widgets.search_bar import SearchBar
from kagan.tui.widgets.task_inspector import TaskInspector

if TYPE_CHECKING:
    from kagan.core.client import DBWatcher
    from kagan.tui.app import KaganApp


_TUTORIAL_SEEN_SETTING_KEY = "ui.tui_tutorial_seen"


MIN_SCREEN_WIDTH = 80
MIN_SCREEN_HEIGHT = 20
BRANCH_SYNC_INTERVAL = 5.0
PEEK_RIGHT_MARGIN = 52
PEEK_OFFSET_X = 2
PEEK_MIN_Y = 1

_SEARCH_STATUS_ALIASES: dict[str, TaskStatus] = {
    "backlog": TaskStatus.BACKLOG,
    "todo": TaskStatus.BACKLOG,
    "in_progress": TaskStatus.IN_PROGRESS,
    "inprogress": TaskStatus.IN_PROGRESS,
    "progress": TaskStatus.IN_PROGRESS,
    "review": TaskStatus.REVIEW,
    "done": TaskStatus.DONE,
    "completed": TaskStatus.DONE,
}
_SEARCH_PRIORITY_ALIASES: dict[str, str] = {
    "low": "low",
    "medium": "medium",
    "med": "medium",
    "high": "high",
    "critical": "high",
    "urgent": "high",
}
_SEARCH_SORT_ALIASES: dict[str, str] = {
    "default": "default",
    "created": "created",
    "priority": "priority",
    "recent": "recent",
}


@dataclass(frozen=True, slots=True)
class SearchQuery:
    """Parsed search query with optional filters."""

    text: str
    status: TaskStatus | None = None
    priority: str | None = None
    sort: str | None = None


@dataclass(frozen=True, slots=True)
class _TaskSessionSummary:
    has_history: bool = False
    has_active: bool = False
    active_launcher: str | None = None
    latest_launcher: str | None = None


@dataclass(frozen=True, slots=True)
class _BoardTaskView:
    id: str
    title: str
    description: str
    priority: Priority
    status: TaskStatus
    review_approved: bool
    acceptance_criteria: list[str]
    updated_at: object
    agent_backend: str | None = None
    base_branch: str | None = None
    github_issue_number: int | None = None
    github_pr_number: int | None = None
    task_type: object | None = None
    has_active_session: bool = False
    has_session_history: bool = False
    active_launcher: str | None = None
    latest_launcher: str | None = None


class KanbanScreen(Screen[None]):
    COMMANDS = {KanbanCommandProvider}
    BINDINGS = KANBAN_BINDINGS
    search_visible: reactive[bool] = reactive(False, init=False)

    def __init__(self) -> None:
        super().__init__(id="kanban-screen")
        self._all_tasks: list[Task] = []
        self._tasks: list[Task] = []
        self._selected_task_id: str | None = None
        self._search_query = ""
        self._search_status_filter: TaskStatus | None = None
        self._search_priority_filter: str | None = None
        self._search_sort_filter: str | None = None
        self._watcher: DBWatcher | None = None
        self._watcher_reload_task: asyncio.Task[None] | None = None
        self._branch_sync_task: asyncio.Task[None] | None = None
        self._inline_action_message: str | None = None
        self._session_summary_by_task: dict[str, _TaskSessionSummary] = {}
        self._review_approved_by_task: dict[str, bool] = {}
        self._github_import_hint_shown = False

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        yield KaganHeader()
        yield SearchBar(id="search-bar").data_bind(is_visible=KanbanScreen.search_visible)
        with Container(classes="board-container kanban-board-container"):
            with Container(classes="kanban-content-pane"):
                with Container(classes="kanban-main-pane"):
                    yield BoardView(id="board-container", classes="board kanban-board")
                    yield TaskInspector(id="task-inspector", classes="task-inspector")
                yield Static(
                    "",
                    id="review-queue-hint",
                    classes="review-queue-hint kanban-review-queue-hint",
                )
            yield TutorialOverlay(id="kanban-tutorial-overlay", classes="kanban-tutorial-overlay")
        with Container(classes="size-warning"):
            yield Static(self._size_warning_message(), classes="size-warning-text")
        yield PeekOverlay(id="peek-overlay", classes="task-peek-overlay")
        yield KanbanHintBar(id="kanban-hint-bar", classes="board-hint-bar")

    async def on_mount(self) -> None:
        self._refresh_header()
        self._set_tutorial_visible(False)
        self._check_screen_size()
        self._update_review_queue_hint()
        self.run_worker(
            self._bootstrap_initial_state(),
            group="kanban-bootstrap",
            exclusive=True,
            exit_on_error=False,
        )
        self.run_worker(
            self._maybe_show_first_boot_tutorial(),
            group="kanban-first-boot",
            exclusive=True,
            exit_on_error=False,
        )

    async def _maybe_show_first_boot_tutorial(self) -> None:
        settings = await self.kagan_app.core.settings.get()
        tutorial_seen = _is_enabled(settings.get(_TUTORIAL_SEEN_SETTING_KEY), default=False)
        if tutorial_seen:
            return

        self._set_tutorial_visible(True)
        await self.kagan_app.core.settings.set({_TUTORIAL_SEEN_SETTING_KEY: "true"})

    def _tutorial_overlay(self) -> TutorialOverlay:
        return self.query_one("#kanban-tutorial-overlay", TutorialOverlay)

    def _tutorial_visible(self) -> bool:
        with contextlib.suppress(NoMatches):
            return bool(self._tutorial_overlay().display)
        return False

    def _set_tutorial_visible(self, visible: bool) -> None:
        with contextlib.suppress(NoMatches):
            self._tutorial_overlay().set_visible(visible)

    async def _bootstrap_initial_state(self) -> None:
        board = self.query_one(BoardView)
        board.loading = True
        try:
            await self._reload_tasks()
            self.call_after_refresh(self._focus_default_widget)

            if not self._all_tasks and not self._github_import_hint_shown:
                self.app.notify(
                    "No tasks yet. Press Ctrl+Shift+P and run"
                    " 'github import' to import from GitHub.",
                    severity="information",
                )
                self._github_import_hint_shown = True

            from kagan.core.client import DBWatcher

            watcher = DBWatcher(self.kagan_app.core)
            await watcher.initialize()
            await watcher.subscribe()
            self._watcher = watcher
            self._watcher_reload_task = asyncio.create_task(
                self._watch_board_changes(),
                name="kanban-board-refresh",
            )
            self._branch_sync_task = asyncio.create_task(
                self._run_branch_sync_loop(),
                name="kanban-branch-sync",
            )
            with contextlib.suppress(KaganError, OSError, RuntimeError):
                await self._sync_branch()
        finally:
            board.loading = False

    async def _stop_branch_sync(self) -> None:
        if self._branch_sync_task is not None:
            self._branch_sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._branch_sync_task
            self._branch_sync_task = None

    async def on_unmount(self) -> None:
        if self._watcher_reload_task is not None:
            self._watcher_reload_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._watcher_reload_task
            self._watcher_reload_task = None
        await self._stop_branch_sync()
        if self._watcher is not None:
            await self._watcher.close()

    @staticmethod
    def _size_warning_message() -> str:
        return (
            "Terminal too small\n\n"
            f"Minimum size: {MIN_SCREEN_WIDTH}x{MIN_SCREEN_HEIGHT}\n"
            "Please resize your terminal"
        )

    def _check_screen_size(self) -> None:
        size = self.app.size
        too_small = size.width < MIN_SCREEN_WIDTH or size.height < MIN_SCREEN_HEIGHT
        self.set_class(too_small, "too-small")

    def _auto_focus_board(self) -> None:
        board = self.query_one(BoardView)
        cards = list(board.query("TaskCard"))
        if not cards:
            return
        # Try focusing the selected card first
        if board.selected_task_id is not None:
            for card in cards:
                task_data = getattr(card, "task_data", None)
                if task_data is not None and task_data.id == board.selected_task_id:
                    card.focus()
                    return
        # Fallback: focus the first available card
        cards[0].focus()

    def _focus_default_widget(self) -> None:
        self._auto_focus_board()

    def _selected_card(self) -> TaskCard | None:
        board = self.query_one(BoardView)
        selected_task_id = board.selected_task_id
        if selected_task_id is None:
            return None
        for card in board.query(TaskCard):
            if card.task_data.id == selected_task_id:
                return card
        return None

    async def _reload_tasks(self) -> None:
        if self.kagan_app.project is None:
            tasks = []
        else:
            tasks = await self.kagan_app.core.tasks.list(repo_id=self.kagan_app.selected_repo_id)
        if not self.is_mounted:
            return
        self._all_tasks = sorted(
            tasks,
            key=lambda task: (str(getattr(task, "created_at", "") or ""), task.id),
        )
        self._session_summary_by_task = await self._collect_session_summaries(self._all_tasks)
        self._review_approved_by_task = await self._collect_review_approvals(self._all_tasks)
        self._apply_filter()

    async def _collect_session_summaries(self, tasks: list[Task]) -> dict[str, _TaskSessionSummary]:
        if not tasks:
            return {}

        task_ids = [task.id for task in tasks]
        summaries_data = await self.kagan_app.core.tasks.sessions.active_session_summaries(task_ids)

        # SessionSummary is now a typed Pydantic model — field access replaces .get()
        return {
            task_id: _TaskSessionSummary(
                has_history=summary.has_history,
                has_active=summary.has_active,
                active_launcher=summary.active_launcher,
                latest_launcher=summary.latest_launcher,
            )
            for task_id, summary in summaries_data.items()
        }

    async def _collect_review_approvals(self, tasks: list[Task]) -> dict[str, bool]:
        """Fetch review approval state for all tasks that are in REVIEW status."""
        review_tasks = [t for t in tasks if t.status is TaskStatus.REVIEW]
        if not review_tasks:
            return {}
        results = await asyncio.gather(
            *(
                asyncio.to_thread(self.kagan_app.core.reviews.is_approved, t.id)
                for t in review_tasks
            ),
            return_exceptions=True,
        )
        return {
            t.id: bool(result) if not isinstance(result, BaseException) else False
            for t, result in zip(review_tasks, results, strict=True)
        }

    def _board_tasks(self, tasks: list[Task]) -> list[_BoardTaskView]:
        views: list[_BoardTaskView] = []
        for task in tasks:
            summary = self._session_summary_by_task.get(task.id, _TaskSessionSummary())
            views.append(
                _BoardTaskView(
                    id=task.id,
                    title=task.title,
                    description=task.description,
                    priority=task.priority,
                    status=task.status,
                    review_approved=self._review_approved_by_task.get(task.id, False),
                    acceptance_criteria=list(task.acceptance_criteria),
                    updated_at=task.updated_at,
                    agent_backend=task.agent_backend,
                    base_branch=task.base_branch,
                    github_issue_number=getattr(task, "github_issue_number", None),
                    github_pr_number=getattr(task, "github_pr_number", None),
                    task_type=getattr(task, "task_type", None),
                    has_active_session=summary.has_active,
                    has_session_history=summary.has_history,
                    active_launcher=summary.active_launcher,
                    latest_launcher=summary.latest_launcher,
                )
            )
        return views

    async def _watch_board_changes(self) -> None:
        if self._watcher is None:
            return
        try:
            while True:
                await self._watcher.wait_for_change()
                if not self.is_mounted:
                    return
                await self._reload_tasks()
        except asyncio.CancelledError:
            return

    def _apply_filter(self) -> None:
        q = self._parse_search_query(self._search_query)
        self._search_status_filter = q.status
        self._search_priority_filter = q.priority
        self._search_sort_filter = q.sort

        if not q.text and q.status is None and q.priority is None and q.sort is None:
            self._tasks = list(self._all_tasks)
        else:
            self._tasks = [
                task
                for task in self._all_tasks
                if self._matches_search(
                    task,
                    text_query=q.text,
                    status_filter=q.status,
                    priority_filter=q.priority,
                )
            ]

        self._tasks = self._apply_sort(self._tasks, q.sort)

        tasks = self._tasks
        if tasks and (self._selected_task_id is None or self._selected_task() is None):
            self._selected_task_id = self._preferred_task_id(tasks)
        elif not tasks:
            self._selected_task_id = None

        board = self.query_one(BoardView)
        board.set_tasks(self._board_tasks(tasks), selected_task_id=self._selected_task_id)
        if self._inspector_visible():
            if self._selected_task() is None:
                self._hide_inspector()
            else:
                self._show_inspector_for_selected()
        status_counts, high_priority_count = self._compute_task_stats()
        self.query_one(SearchBar).update_state(
            filtered_count=len(tasks),
            total_count=len(self._all_tasks),
            status_counts=status_counts,
            high_priority_count=high_priority_count,
            status_filter=q.status.value.lower() if q.status is not None else "",
            priority_filter=q.priority or "",
            sort_filter=q.sort or "",
            search_active=self.search_visible,
        )
        self._refresh_header()
        self._update_review_queue_hint()
        self._update_hint_bar()
        self._sync_search_header_swap_state()

    def _compute_task_stats(self) -> tuple[dict[str, int], int]:
        """Count tasks per status and high-priority tasks."""
        status_counts = {status.value: 0 for status in TaskStatus}
        high_priority_count = 0
        for task in self._all_tasks:
            status_counts[task.status.value] += 1
            if task.priority >= Priority.HIGH:
                high_priority_count += 1
        return status_counts, high_priority_count

    def _update_search_bar_state(self) -> None:
        status_counts, high_priority_count = self._compute_task_stats()
        status_filter = self._search_status_filter
        priority_filter = self._search_priority_filter
        sort_filter = self._search_sort_filter
        self.query_one(SearchBar).update_state(
            filtered_count=len(self._tasks),
            total_count=len(self._all_tasks),
            status_counts=status_counts,
            high_priority_count=high_priority_count,
            status_filter=status_filter.value.lower() if status_filter is not None else "",
            priority_filter=priority_filter or "",
            sort_filter=sort_filter or "",
            search_active=self.search_visible,
        )

    def _selected_task(self) -> Task | None:
        if self._selected_task_id is None:
            return None
        for task in self._tasks:
            if task.id == self._selected_task_id:
                return task
        return None

    def _inspector(self) -> TaskInspector:
        return self.query_one(TaskInspector)

    def _inspector_visible(self) -> bool:
        try:
            return self._inspector().is_open
        except NoMatches:
            return False

    def _show_inspector_for_selected(self) -> None:
        task = self._selected_task()
        inspector = self._inspector()
        if task is None:
            inspector.hide_inspector()
            inspector.set_message("Select a task card to inspect.", level="info")
            self._update_hint_bar()
            return
        inspector.show_task(task)
        self._set_inline_action_message(None)
        self._update_hint_bar()

    def _hide_inspector(self) -> None:
        self._inspector().hide_inspector()
        self._update_hint_bar()

    def _require_inspector(self, *, action_label: str) -> bool:
        if self._inspector_visible():
            return True
        self.app.notify(
            f"{action_label} requires the inspector. Press Enter first.",
            severity="warning",
        )
        self._set_inline_action_message(f"{action_label}: press Enter to inspect first")
        self._inspector().set_message(
            f"{action_label} blocked until inspector is open. Press Enter.",
            level="warning",
        )
        return False

    def _navigation_hints(self) -> list[tuple[str, str]]:
        left = get_key_for_action(KANBAN_BINDINGS, "move_left", default="Shift+Left")
        right = get_key_for_action(KANBAN_BINDINGS, "move_right", default="Shift+Right")
        return [
            (left, "move left"),
            (right, "move right"),
        ]

    @staticmethod
    def _preferred_task_id(tasks: list[Task]) -> str:
        if not tasks:
            return ""
        for status in (
            TaskStatus.IN_PROGRESS,
            TaskStatus.REVIEW,
            TaskStatus.BACKLOG,
            TaskStatus.DONE,
        ):
            for task in tasks:
                if task.status == status:
                    return task.id
        return tasks[0].id

    @staticmethod
    def _global_hints() -> list[tuple[str, str]]:
        rows = [
            row
            for row in get_global_shortcut_help_rows()
            if row[1].lower() not in {"help", "quick actions"}
        ]
        return rows[:3]

    def _mode_label(self) -> str:
        if self.search_visible:
            return "Search"
        if self._inspector_visible():
            return "Inspector"
        if self._inline_action_message:
            return "Launching"
        return "Board"

    def _set_inline_action_message(self, message: str | None) -> None:
        self._inline_action_message = message.strip() if message else None
        self._update_hint_bar()

    def _refresh_header(self) -> None:
        with contextlib.suppress(NoMatches):
            header = self.query_one(KaganHeader)
            project = self.kagan_app.project
            header.update_project(project.name if project is not None else "No project")
            header.update_repo(self.kagan_app.selected_repo_name or "")
            header.update_count(len(self._all_tasks))
            active = sum(1 for task in self._all_tasks if task.status is TaskStatus.IN_PROGRESS)
            review = sum(1 for task in self._all_tasks if task.status is TaskStatus.REVIEW)
            done = sum(1 for task in self._all_tasks if task.status is TaskStatus.DONE)
            header.update_health_strip(active=active, review=review, done=done)
            return

    def _sync_search_header_swap_state(self) -> None:
        self.set_class(
            self.search_visible and bool(self._search_query.strip()),
            "search-replace-header",
        )

    async def _sync_branch(self) -> None:
        app = self.kagan_app
        repo_id = app.selected_repo_id
        project = app.project
        if not repo_id or not project:
            return
        repos = await app.core.projects.repos(project.id)
        repo = next((r for r in repos if r.id == repo_id), None)
        if repo is None:
            return
        from kagan.core import git

        branch = await git.current_branch(repo.path)
        if not branch:
            return
        try:
            header = self.query_one(KaganHeader)
        except NoMatches:
            return
        if branch == header.git_branch:
            return
        header.update_branch(branch)
        with contextlib.suppress(KaganError):
            await app.core.projects.set_repo_default_branch(project.id, repo_id, branch)

    async def _run_branch_sync_loop(self) -> None:
        while True:
            await asyncio.sleep(BRANCH_SYNC_INTERVAL)
            with contextlib.suppress(KaganError, OSError, RuntimeError):
                await self._sync_branch()

    def _task_actions(self, task: Task | None) -> list[tuple[str, str]]:
        keys = {
            "open_task": get_key_for_action(KANBAN_BINDINGS, "open_task", default="Enter"),
            "search": get_key_for_action(KANBAN_BINDINGS, "search", default="/"),
            "new_task": get_key_for_action(KANBAN_BINDINGS, "new_task", default="n"),
            "toggle_chat": get_key_for_action(KANBAN_BINDINGS, "toggle_chat", default="Ctrl+."),
            "move_right": get_key_for_action(KANBAN_BINDINGS, "move_right", default="Shift+Right"),
            "move_left": get_key_for_action(KANBAN_BINDINGS, "move_left", default="Shift+Left"),
            "stop_agent": get_key_for_action(KANBAN_BINDINGS, "stop_agent", default="Shift+S"),
            "attach_agent": get_key_for_action(KANBAN_BINDINGS, "attach_agent", default="a"),
            "start_agent": get_key_for_action(KANBAN_BINDINGS, "start_agent", default="s"),
        }
        open_key = keys["open_task"]
        search_key = keys["search"]
        new_key = keys["new_task"]
        overlay_key = keys["toggle_chat"]
        right_key = keys["move_right"]
        left_key = keys["move_left"]
        session_key = keys["open_task"]
        stop_key = keys["stop_agent"]
        attach_key = keys["attach_agent"]
        start_agent_key = keys["start_agent"]

        if task is None:
            return [
                (new_key, "new"),
                (search_key, "search"),
                (overlay_key, "assistant"),
            ]

        if task.status is TaskStatus.BACKLOG:
            return [
                (open_key, "inspect"),
                (session_key, "open"),
                (new_key, "new"),
                (right_key, "start"),
                (start_agent_key, "agent"),
                (attach_key, "attach"),
            ]

        if task.status is TaskStatus.IN_PROGRESS:
            summary = self._session_summary_by_task.get(task.id, _TaskSessionSummary())
            actions = [
                (open_key, "inspect"),
                (session_key, "open"),
                (right_key, "review"),
            ]
            if summary.has_active:
                actions.append((stop_key, "stop"))
            else:
                actions.append((start_agent_key, "agent"))
            actions.append((attach_key, "attach"))
            return actions

        if task.status is TaskStatus.REVIEW:
            return [
                (open_key, "inspect"),
                (right_key, "merge"),
                (left_key, "reopen"),
                (session_key, "open"),
            ]

        return [
            (open_key, "inspect"),
            (session_key, "history"),
        ]

    def on_board_view_task_selected(self, message: BoardView.TaskSelected) -> None:
        self._selected_task_id = message.task_id
        if self._inspector_visible():
            self._show_inspector_for_selected()
        self._update_hint_bar()

    def action_next_card(self) -> None:
        self.query_one(BoardView).action_next_card()

    def action_prev_card(self) -> None:
        self.query_one(BoardView).action_prev_card()

    def action_focus_next_card(self) -> None:
        self.action_next_card()

    def action_focus_prev_card(self) -> None:
        self.action_prev_card()

    def action_prev_column(self) -> None:
        self.query_one(BoardView).action_prev_column()

    def action_focus_left(self) -> None:
        self.action_prev_column()

    def action_next_column(self) -> None:
        self.query_one(BoardView).action_next_column()

    def action_focus_right(self) -> None:
        self.action_next_column()

    def action_focus_up(self) -> None:
        self.action_prev_card()

    def action_focus_down(self) -> None:
        self.action_next_card()

    def action_toggle_chat(self) -> None:
        task = self._selected_task()
        self.app.push_screen(OrchestratorOverlay(task_id=task.id if task else None))

    async def action_switch_session(self) -> None:
        task = self._selected_task()
        self.app.push_screen(OrchestratorOverlay(task_id=task.id if task else None))

    async def action_fullscreen_chat(self) -> None:
        task = self._selected_task()
        self.app.push_screen(OrchestratorOverlay(task_id=task.id if task else None))

    async def action_expand_chat_overlay(self) -> None:
        task = self._selected_task()
        self.app.push_screen(OrchestratorOverlay(task_id=task.id if task else None))

    def action_peek_task(self) -> None:
        overlay = self.query_one(PeekOverlay)
        if overlay.has_class("visible"):
            overlay.hide_overlay()
            return

        task = self._selected_task()
        if task is None:
            return
        overlay.show_task(task)
        card = self._selected_card()
        if card is None:
            return

        x_pos = min(
            card.region.x + card.region.width + PEEK_OFFSET_X,
            self.size.width - PEEK_RIGHT_MARGIN,
        )
        y_pos = max(PEEK_MIN_Y, card.region.y)
        overlay.show_at(x_pos, y_pos)

    def action_open_task(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        if self._inspector_visible():
            self._open_task(task)
        else:
            self._show_inspector_for_selected()

    def _open_task(self, task: Task) -> None:
        from kagan.tui.screens.task_screen import TaskScreen

        self.app.push_screen(TaskScreen(task_id=task.id))

    def _resolve_interactive_backend(self, task: Task, settings: dict[str, Any]) -> str | None:
        """Resolve the interactive launcher backend with fallback logic.

        Returns the resolved backend name, or ``None`` if no usable backend
        is available (caller should abort the flow).
        """
        import platform

        from kagan.tui.terminals.installer import (
            check_terminal_installed,
            first_available_attached_backend,
            get_manual_install_fallback,
        )

        settings_launcher_raw = settings.get("attached_launcher", "tmux")
        settings_launcher = (
            settings_launcher_raw.strip().lower()
            if isinstance(settings_launcher_raw, str)
            else "tmux"
        )
        task_launcher = task.launcher.strip().lower() if isinstance(task.launcher, str) else ""
        backend = task_launcher or settings_launcher
        is_windows = platform.system() == "Windows"
        self._set_inline_action_message(f"Checking {backend} launcher...")

        if check_terminal_installed(backend):
            return backend

        fallback = first_available_attached_backend(windows=is_windows)
        if fallback is not None:
            self.app.notify(
                f"{backend} not found. Using fallback: {fallback}.",
                severity="information",
            )
            self._set_inline_action_message(f"Using fallback launcher: {fallback}.")
            return fallback

        hint = get_manual_install_fallback(backend)
        self.app.notify(
            f"Attach cancelled: {backend} not installed. {hint}",
            severity="warning",
        )
        return None

    async def _ensure_interactive_workspace(self, task: Task) -> Worktree | None:
        """Provision a worktree for the task, creating one if needed.

        Returns the ``Worktree`` instance, or ``None`` on failure.
        """
        workspace = await self.kagan_app.core.worktrees.get(task.id)
        if workspace is not None:
            return workspace

        self._set_inline_action_message("Provisioning workspace...")
        self.app.notify("Creating workspace...", severity="information")
        try:
            await self.kagan_app.core.worktrees.create(task.id)
            workspace = await self.kagan_app.core.worktrees.get(task.id)
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            self.app.notify(f"Failed to create workspace: {exc}", severity="error")
            return None

        if workspace is None:
            self.app.notify("Failed to provision workspace.", severity="error")
        return workspace

    async def _attach_interactive_terminal(
        self,
        task: Task,
        interactive_session: Any,
        *,
        backend: str,
        agent_backend: str,
        launcher: str,
        ide_name: str | None,
        wt_path: Path,
        prompt_path: Path,
    ) -> bool:
        """Attach the user's terminal to the interactive session.

        Returns ``True`` if the terminal session was attached successfully.
        """
        if backend == "tmux":
            self._set_inline_action_message("Attaching tmux session...")
            session_name = self._tmux_session_name(interactive_session.id)
            with self._suspend_app():
                attached = await self._attach_tmux_session(session_name)
            if not attached:
                self.app.notify(
                    "Interactive session missing; recreating session...",
                    severity="information",
                )
                with contextlib.suppress(KaganError):
                    retry_session = await self.kagan_app.core.tasks.run(
                        task.id,
                        agent_backend=agent_backend,
                        launcher=launcher,
                        ide=ide_name,
                    )
                    session_name = self._tmux_session_name(retry_session.id)
                with self._suspend_app():
                    attached = await self._attach_tmux_session(session_name)
            return attached

        if backend == "nvim":
            self._set_inline_action_message("Opening Neovim session...")
            with self._suspend_app():
                return await self._attach_nvim_session(wt_path, prompt_path)

        # IDE backends (vscode/cursor/windsurf/kiro/antigravity) launch externally
        self.app.notify(
            f"Workspace opened in {backend}. Use startup prompt: {prompt_path}",
            severity="information",
        )
        return False

    async def _open_interactive_session_flow(self, task: Task) -> None:
        from kagan.tui.screens.gateway import AttachedInstructionsModal

        settings = await self.kagan_app.core.settings.get()

        # 1. Resolve backend
        backend = self._resolve_interactive_backend(task, settings)
        if backend is None:
            self._set_inline_action_message(None)
            return

        # Check whether a managed (background) agent is running on this task.
        summary = self._session_summary_by_task.get(task.id, _TaskSessionSummary())
        taking_over = summary.has_active and summary.active_launcher is None

        # 2. Show instructions modal (unless skipped)
        skip_instructions_raw = settings.get("skip_attached_instructions_popup", "")
        skip_instructions = str(skip_instructions_raw).strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

        workspace = await self.kagan_app.core.worktrees.get(task.id)
        wt_path = Path(workspace.worktree_path) if workspace is not None else Path(".")
        prompt_path = wt_path / ".kagan" / "start_prompt.md"

        if not skip_instructions:
            result = await self.app.push_screen_wait(
                AttachedInstructionsModal(
                    task.id,
                    task.title,
                    backend,
                    prompt_path,
                    taking_over=taking_over,
                )
            )
            if result is None:
                self._set_inline_action_message(None)
                return
            if result == "skip_future":
                await self.kagan_app.core.settings.set({"skip_attached_instructions_popup": "true"})

        # Cancel the managed run after user confirms (or if instructions skipped).
        if taking_over:
            self._set_inline_action_message("Stopping managed agent...")
            with contextlib.suppress(KaganError):
                await self.kagan_app.core.tasks.cancel(task.id)
            await self._reload_tasks()

        # 3. Ensure workspace exists
        workspace = await self._ensure_interactive_workspace(task)
        if workspace is None:
            self._set_inline_action_message(None)
            return

        wt_path = Path(workspace.worktree_path)
        prompt_path = wt_path / ".kagan" / "start_prompt.md"

        # 4. Start interactive session
        agent_backend = task.agent_backend or resolve_default_agent_backend(settings)
        launcher, ide_name = resolve_launcher(backend)

        try:
            self._set_inline_action_message("Starting interactive session...")
            interactive_session = await self.kagan_app.core.tasks.run(
                task.id,
                agent_backend=agent_backend,
                launcher=launcher,
                ide=ide_name,
            )
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            self.app.notify(f"Failed to start interactive session: {exc}", severity="error")
            self._set_inline_action_message(None)
            return

        # 5. Attach terminal
        attached = await self._attach_interactive_terminal(
            task,
            interactive_session,
            backend=backend,
            agent_backend=agent_backend,
            launcher=launcher,
            ide_name=ide_name,
            wt_path=wt_path,
            prompt_path=prompt_path,
        )

        if attached:
            with contextlib.suppress(KaganError):
                await self.kagan_app.core.tasks.detach(task.id)
        # Always reload board state after returning from a suspended terminal
        # so the UI reflects any changes made during the interactive session.
        await self._reload_tasks()
        self._set_inline_action_message(None)

    @staticmethod
    def _tmux_session_name(session_id: str) -> str:
        return f"kagan-{session_id.replace(':', '-')}"

    @contextlib.contextmanager
    def _suspend_app(self):
        try:
            with self.app.suspend():
                yield
            # Force full repaint after resuming — some terminals don't
            # properly restore the alternate screen buffer on their own.
            self.app.refresh(layout=True)
            self.screen.refresh(layout=True)
        except SuspendNotSupported:
            self.app.notify(
                "Terminal suspend not supported in this environment. "
                "Use attach from a standard terminal (not textual dev).",
                severity="warning",
            )

    @staticmethod
    async def _attach_tmux_session(session_name: str) -> bool:
        import asyncio as _aio

        try:
            resolved = resolve_spawn_command("tmux", "attach-session", "-t", session_name)
            proc = await _aio.create_subprocess_exec(
                *resolved,
                env=build_sanitized_subprocess_environment(),
            )
        except OSError:
            return False
        returncode = await proc.wait()
        return returncode == 0

    @staticmethod
    async def _attach_nvim_session(workspace_path: Path, prompt_path: Path) -> bool:
        import asyncio as _aio

        target = str(prompt_path) if prompt_path.exists() else str(workspace_path)
        try:
            resolved = resolve_spawn_command("nvim", target)
            proc = await _aio.create_subprocess_exec(
                *resolved,
                cwd=str(workspace_path),
                env=build_sanitized_subprocess_environment(),
            )
        except OSError:
            return False
        returncode = await proc.wait()
        return returncode == 0

    def action_open_session(self) -> None:
        if not self._require_inspector(action_label="Open session"):
            return
        task = self._selected_task()
        if task is None:
            return
        self._open_task(task)

    def action_review_task(self) -> None:
        task = self._selected_task()
        if task is None:
            self.app.notify(
                "Select a task first. Press Enter to inspect.",
                severity="warning",
            )
            return
        if task.status is not TaskStatus.REVIEW:
            self.app.notify("Review shortcut is available for REVIEW tasks", severity="information")
            return

        from kagan.tui.screens.task_screen import TaskScreen

        self.app.push_screen(TaskScreen(task_id=task.id))

    async def action_delete_task(self) -> None:
        if not self._require_inspector(action_label="Delete"):
            return
        task = self._selected_task()
        if task is None:
            return
        await self._confirm_delete_task(task)

    async def action_delete_task_direct(self) -> None:
        await self.action_delete_task()

    async def action_duplicate_task(self) -> None:
        if not self._require_inspector(action_label="Duplicate"):
            return
        task = self._selected_task()
        if task is None:
            return

        await self.kagan_app.core.tasks.create(
            f"{task.title} (copy)",
            description=task.description,
            priority=task.priority,
            base_branch=task.base_branch,
            agent_backend=task.agent_backend,
            acceptance_criteria=list(task.acceptance_criteria),
        )
        await self._reload_tasks()

    async def action_start_agent(self) -> None:
        if not self._require_inspector(action_label="Start agent"):
            return
        task = self._selected_task()
        if task is None:
            return

        settings = await self.kagan_app.core.settings.get()
        backend = task.agent_backend or resolve_default_agent_backend(settings)
        workspace = await self.kagan_app.core.worktrees.get(task.id)
        if workspace is None:
            await self.kagan_app.core.worktrees.create(task.id)
        await self.kagan_app.core.tasks.run(task.id, agent_backend=backend)
        await self._reload_tasks()

    async def action_attach_agent(self) -> None:
        if not self._require_inspector(action_label="Attach"):
            return
        task = self._selected_task()
        if task is None:
            return
        self.run_worker(self._open_interactive_session_flow(task), exclusive=False)

    async def action_stop_agent(self) -> None:
        if not self._require_inspector(action_label="Stop agent"):
            return
        task = self._selected_task()
        if task is None:
            return
        await self.kagan_app.core.tasks.cancel(task.id)
        await self._reload_tasks()

    def action_edit_task(self) -> None:
        if not self._require_inspector(action_label="Edit"):
            return
        task = self._selected_task()
        if task is None:
            return
        self.app.push_screen(TaskEditorModal(task=task))

    def action_expand_description(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        self.query_one(PeekOverlay).show_task(task)

    async def _move_selected_task(self, direction: int) -> None:
        if not self._require_inspector(action_label="Move task"):
            return
        task = self._selected_task()
        if task is None:
            return

        order = [TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW]
        if task.status not in order:
            return

        current_index = order.index(task.status)
        target_index = current_index + direction
        if target_index < 0 or target_index >= len(order):
            return

        target = order[target_index]

        # Optimistic: move card to new column immediately
        prev_status = task.status
        for t in self._all_tasks:
            if t.id == task.id:
                t.status = target
                break
        self._apply_filter()

        try:
            await self.kagan_app.core.tasks.set_status(task.id, target)
        except KaganError as exc:
            # Revert optimistic update on failure
            for t in self._all_tasks:
                if t.id == task.id:
                    t.status = prev_status
                    break
            self._apply_filter()
            self.app.notify(f"Unable to move task: {exc}", severity="warning")
            return
        # Full reload to reconcile with DB
        await self._reload_tasks()

    async def action_move_left(self) -> None:
        await self._move_selected_task(-1)

    async def action_move_right(self) -> None:
        await self._move_selected_task(1)

    def action_set_branch(self) -> None:
        if not self._require_inspector(action_label="Set branch"):
            return
        task = self._selected_task()
        if task is None:
            return
        self.app.push_screen(TaskEditorModal(task=task, focus_field="task-base-branch"))

    def action_switch_agent(self) -> None:
        self.app.push_screen("agent-picker-modal")

    def action_sync_repo(self) -> None:
        self.run_worker(
            self._reload_tasks(),
            group="kanban-reload",
            exclusive=True,
            exit_on_error=False,
        )

    def action_import_github(self) -> None:
        from kagan.tui.screens.github_import_modal import GitHubImportModal

        def _on_result(summary: GitHubImportSummary | None) -> None:
            if summary is None:
                return
            self.run_worker(
                self._after_github_import(summary),
                group="kanban-github-import",
                exclusive=True,
                exit_on_error=False,
            )

        self.app.push_screen(GitHubImportModal(), callback=_on_result)

    async def _after_github_import(self, summary: GitHubImportSummary) -> None:
        await self._reload_tasks()
        message = f"GitHub import complete: {summary.created} created, {summary.skipped} skipped"
        if summary.error_count:
            self.app.notify(f"{message}, {summary.error_count} errors", severity="warning")
            return
        self.app.notify(message, severity="information")

    async def action_clear_focus(self) -> None:
        if self.search_visible:
            self._cancel_search()
        overlay = self.query_one(PeekOverlay)
        if overlay.has_class("visible"):
            overlay.hide_overlay()
            return
        if self._inspector_visible():
            self._hide_inspector()

    def action_interrupt(self) -> None:
        return

    def action_search(self) -> None:
        if self.search_visible:
            self._cancel_search()
            return
        self.search_visible = True
        self._sync_search_header_swap_state()
        self._update_review_queue_hint()

    def _cancel_search(self) -> None:
        self.query_one(SearchBar).remember_current_query()
        self.search_visible = False
        self._search_query = ""
        self._apply_filter()

    @on(SearchBar.QueryChanged)
    def on_search_query_changed(self, message: SearchBar.QueryChanged) -> None:
        if not self.search_visible:
            return
        self._search_query = message.query
        self._apply_filter()

    def _update_review_queue_hint(self) -> None:
        if not self.is_mounted:
            return
        try:
            hint = self.query_one("#review-queue-hint", Static)
        except NoMatches:
            return
        if self.search_visible:
            hint.update(self._search_hint_message())
            hint.add_class("visible")
            return
        if not self._all_tasks:
            new_key = get_key_for_action(KANBAN_BINDINGS, "new_task", default="n")
            help_keys = " / ".join(get_keys_for_action(self.app.BINDINGS, "show_help")) or "? / F1"
            actions_key = "."
            hint.update(
                "No tasks yet. "
                f"Press {new_key} to create one, {help_keys} for help, "
                f"or {actions_key} for actions."
            )
            hint.add_class("visible")
            return
        review_count = sum(1 for task in self._all_tasks if task.status is TaskStatus.REVIEW)
        if review_count > 1:
            hint.update("Review queue has multiple tasks. Process oldest first.")
            hint.add_class("visible")
            return
        hint.update("")
        hint.remove_class("visible")

    def _search_hint_message(self) -> str:
        clear_key = get_key_for_action(KANBAN_BINDINGS, "clear_focus", default="Esc")
        hide_key = get_key_for_action(KANBAN_BINDINGS, "search", default="/")
        query = self._search_query.strip()
        if not query:
            return f"Search active. Type to filter tasks. {clear_key} clear, {hide_key} hide."

        filtered_count = len(self._tasks)
        if filtered_count == 0:
            return (
                f'No tasks match "{query}". Try fewer words or a broader term. '
                f"{clear_key} clear, {hide_key} hide."
            )

        task_word = "task" if filtered_count == 1 else "tasks"
        return (
            f'Search "{query}": {filtered_count} {task_word}. {clear_key} clear, {hide_key} hide.'
        )

    def _update_hint_bar(self) -> None:
        hint_bar = self.query_one(KanbanHintBar)
        task = self._selected_task()
        actions = self._task_actions(task)
        if self._inline_action_message:
            actions = [("", self._inline_action_message), *actions]
        hint_bar.show_kanban_hints(
            navigation=self._navigation_hints() if task is not None else [],
            actions=actions,
            global_hints=self._global_hints(),
            mode_label=self._mode_label(),
        )

    def on_board_view_task_opened(self, _: BoardView.TaskOpened) -> None:
        self.action_open_task()

    def action_open_repo_picker(self) -> None:
        self.app.push_screen("repo-picker-modal")

    def action_open_settings(self) -> None:
        self.app.push_screen("settings-modal", callback=self._on_settings_dismissed)

    def action_toggle_workspace(self) -> None:
        self.app.switch_screen("workspace-screen")

    def action_open_analytics(self) -> None:
        self.app.push_screen("analytics-modal")

    def _on_settings_dismissed(self, _result: None) -> None:
        from kagan.tui.app import KaganApp

        app = self.app
        if isinstance(app, KaganApp):
            app.run_worker(app._apply_saved_theme(), exclusive=False)

    def action_new_task(self) -> None:
        self.app.push_screen(TaskEditorModal())

    async def on_screen_resume(self) -> None:
        self.call_after_refresh(self._on_screen_resume_deferred)

    async def _on_screen_resume_deferred(self) -> None:
        await self._reload_tasks()
        self._auto_focus_board()

    def _handle_search_key(self, event: events.Key) -> bool:
        search_bar = self.query_one(SearchBar)
        if event.key == "slash":
            event.prevent_default()
            event.stop()
            self._cancel_search()
            return True
        if event.key in {"up", "down"} and search_bar.handle_history_key(event.key):
            event.prevent_default()
            event.stop()
            return True
        if event.key in {"left", "right", "enter", "tab"} and search_bar.handle_preset_key(
            event.key
        ):
            event.prevent_default()
            event.stop()
            return True
        if event.key == "enter":
            search_bar.remember_current_query()
            event.prevent_default()
            event.stop()
            return True
        if event.key == "escape":
            event.prevent_default()
            event.stop()
            self._cancel_search()
            return True
        return False

    async def on_key(self, event: events.Key) -> None:
        if self._tutorial_visible() and event.key in {"escape", "q"}:
            event.prevent_default()
            event.stop()
            self._set_tutorial_visible(False)
            return

        if self.search_visible and self._handle_search_key(event):
            return

        if event.key == "escape":
            overlay = self.query_one(PeekOverlay)
            if overlay.has_class("visible"):
                event.prevent_default()
                event.stop()
                overlay.hide_overlay()
                return
            if self._inspector_visible():
                event.prevent_default()
                event.stop()
                self._hide_inspector()
                return

        navigation_actions = {
            "h": self.action_focus_left,
            "left": self.action_focus_left,
            "j": self.action_focus_down,
            "down": self.action_focus_down,
            "k": self.action_focus_up,
            "up": self.action_focus_up,
            "l": self.action_focus_right,
            "right": self.action_focus_right,
        }
        action = navigation_actions.get(event.key)
        if action is not None:
            event.prevent_default()
            event.stop()
            action()
            return

    def action_copy_task_id(self) -> None:
        task = self._selected_task()
        if task is None:
            return
        self.app.copy_to_clipboard(f"#{task.id[:8]}")
        self.app.notify("Copied task ID", severity="information")

    async def _confirm_delete_task(self, task: Task) -> None:
        worktree = await self.kagan_app.core.worktrees.get(task.id)
        has_worktree = worktree is not None
        has_active_session = await self.kagan_app.core.tasks.sessions.has_active(task.id)

        def _on_result(confirmed: bool | None) -> None:
            if not confirmed:
                return
            self.run_worker(
                self._delete_task(task.id),
                group="kanban-delete-task",
                exclusive=True,
                exit_on_error=False,
            )

        warning_lines = ["This removes the task from the board and its persisted state."]
        if has_active_session:
            warning_lines.append("⚠ An active agent session will be stopped.")
        if has_worktree:
            warning_lines.append("⚠ The git worktree and branch will be removed.")
        self.app.push_screen(
            ConfirmModal(
                title="Delete Task",
                message=f"Delete #{task.id[:8]} · {task.title}?",
                detail="\n".join(warning_lines),
                confirm_label="Delete",
                cancel_label="Cancel",
            ),
            callback=_on_result,
        )

    async def _delete_task(self, task_id: str) -> None:
        # Optimistic: remove card from board immediately before async delete
        self._all_tasks = [t for t in self._all_tasks if t.id != task_id]
        self._session_summary_by_task.pop(task_id, None)
        self._apply_filter()

        await self.kagan_app.core.tasks.delete(task_id)
        # Full reload to reconcile with DB (picks up concurrent changes)
        await self._reload_tasks()

    @staticmethod
    def _apply_sort(tasks: list[Task], sort_filter: str | None) -> list[Task]:
        if not tasks:
            return []
        if sort_filter == "priority":
            return sorted(
                tasks,
                key=lambda task: (
                    -int(task.priority),
                    str(getattr(task, "created_at", "") or ""),
                    task.id,
                ),
            )
        if sort_filter == "recent":
            return sorted(
                tasks,
                key=lambda task: (
                    str(getattr(task, "updated_at", "") or ""),
                    str(getattr(task, "created_at", "") or ""),
                    task.id,
                ),
                reverse=True,
            )
        if sort_filter == "created":
            return sorted(
                tasks,
                key=lambda task: (str(getattr(task, "created_at", "") or ""), task.id),
            )
        return list(tasks)

    @staticmethod
    def _parse_search_query(query: str) -> SearchQuery:
        tokens = [token for token in query.split() if token.strip()]
        text_parts: list[str] = []
        status_filter: TaskStatus | None = None
        priority_filter: str | None = None
        sort_filter: str | None = None

        for token in tokens:
            normalized = token.strip().lower()
            if normalized.startswith("@status:"):
                status_filter = _SEARCH_STATUS_ALIASES.get(normalized.removeprefix("@status:"))
                if status_filter is not None:
                    continue
            if normalized.startswith("@priority:"):
                priority_filter = _SEARCH_PRIORITY_ALIASES.get(
                    normalized.removeprefix("@priority:")
                )
                if priority_filter is not None:
                    continue
            if normalized.startswith("@sort:"):
                sort_filter = _SEARCH_SORT_ALIASES.get(normalized.removeprefix("@sort:"))
                if sort_filter is not None:
                    continue
            text_parts.append(token)

        return SearchQuery(
            text=" ".join(text_parts).strip().lower(),
            status=status_filter,
            priority=priority_filter,
            sort=sort_filter,
        )

    @staticmethod
    def _matches_search(
        task: Task,
        *,
        text_query: str,
        status_filter: TaskStatus | None,
        priority_filter: str | None,
    ) -> bool:
        if status_filter is not None and task.status != status_filter:
            return False
        if priority_filter == "high" and task.priority < Priority.HIGH:
            return False
        if priority_filter == "medium" and task.priority != Priority.MEDIUM:
            return False
        if priority_filter == "low" and task.priority != Priority.LOW:
            return False
        if not text_query:
            return True

        haystacks = [
            task.title.lower(),
            task.description.lower(),
            task.id.lower(),
            (task.agent_backend or "").lower(),
            (task.base_branch or "").lower(),
            " ".join(item.lower() for item in task.acceptance_criteria),
        ]
        return any(text_query in haystack for haystack in haystacks)

    def on_resize(self, event: events.Resize) -> None:
        del event
        self._check_screen_size()
