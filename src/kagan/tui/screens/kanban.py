import asyncio
import contextlib
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from textual import events, on
from textual.app import ComposeResult, SuspendNotSupported
from textual.containers import Container
from textual.css.query import NoMatches
from textual.reactive import var
from textual.screen import Screen
from textual.widgets import Input, Select, Static, TextArea

from kagan.chat import (
    resolve_default_agent_backend,
    warm_orchestrator_backend,
)
from kagan.core import resolve_launcher
from kagan.core.enums import ChatMode, Priority, SessionKind, TaskStatus, WorkMode
from kagan.core.errors import KaganError
from kagan.core.models import Task
from kagan.runtime_env import build_sanitized_subprocess_environment
from kagan.tui._chat_helpers import (
    TitleGenerationSession,
    build_session_options,
    kick_title_generation,
    send_task_message,
)
from kagan.tui.keybindings import (
    KANBAN_BINDINGS,
    get_global_shortcut_help_rows,
    get_key_for_action,
    get_keys_for_action,
)
from kagan.tui.orchestrator_sessions import is_orchestrator_session_key
from kagan.tui.screens.github_import_modal import GitHubImportSummary
from kagan.tui.screens.kanban_chat import (
    apply_task_chat_event,
)
from kagan.tui.screens.kanban_chat import (
    send_orchestrator_message as send_chat_message,
)
from kagan.tui.screens.kanban_commands import KanbanCommandProvider
from kagan.tui.screens.task_editor_modal import (
    TaskDeleteConfirmModal,
    TaskEditorModal,
)
from kagan.tui.screens.tutorial import TutorialOverlay
from kagan.tui.widgets.board import BoardView
from kagan.tui.widgets.card import TaskCard
from kagan.tui.widgets.chat import ChatPanel
from kagan.tui.widgets.header import KaganHeader
from kagan.tui.widgets.hint_bar import KanbanHintBar
from kagan.tui.widgets.peek import PeekOverlay
from kagan.tui.widgets.search_bar import SearchBar
from kagan.tui.widgets.streaming import StreamingOutput
from kagan.tui.widgets.task_inspector import TaskInspector

if TYPE_CHECKING:
    from kagan.core.client import DBWatcher
    from kagan.tui.app import KaganApp


TASK_WORKER_SESSION_KEY = "task-worker"
TASK_REVIEWER_SESSION_KEY = "task-reviewer"
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
_SEARCH_MODE_ALIASES: dict[str, WorkMode] = {
    "auto": WorkMode.AUTO,
    "pair": WorkMode.PAIR,
}
_SEARCH_SORT_ALIASES: dict[str, str] = {
    "default": "default",
    "created": "created",
    "priority": "priority",
    "recent": "recent",
}


def _is_enabled(value: str | None, *, default: bool) -> bool:
    if value is None:
        return default
    return value.strip().lower() not in {"0", "false", "no", "off"}


@dataclass(frozen=True, slots=True)
class _TaskSessionSummary:
    has_history: bool = False
    has_active: bool = False
    active_mode: WorkMode | None = None
    latest_mode: WorkMode | None = None


@dataclass(frozen=True, slots=True)
class _BoardTaskView:
    id: str
    title: str
    description: str
    priority: Priority
    execution_mode: WorkMode
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
    latest_session_mode: WorkMode | None = None


class KanbanScreen(Screen[None]):
    COMMANDS = {KanbanCommandProvider}
    BINDINGS = KANBAN_BINDINGS
    search_visible: var[bool] = var(False, init=False)

    def __init__(self) -> None:
        super().__init__(id="kanban-screen")
        self._all_tasks: list[Task] = []
        self._tasks: list[Task] = []
        self._selected_task_id: str | None = None
        self._search_query = ""
        self._search_status_filter: TaskStatus | None = None
        self._search_priority_filter: str | None = None
        self._search_mode_filter: WorkMode | None = None
        self._search_sort_filter: str | None = None
        self._chat_mode = ChatMode.ORCHESTRATOR
        self._chat_active_task_id: str | None = None
        self._chat_overlay_layout_mode = "vertical"
        self._chat_auto_opened = False
        self._chat_orchestrator_history: list[tuple[str, str]] = []
        self._chat_session_switch_token = 0
        self._chat_message_task: asyncio.Task[None] | None = None
        self._chat_stream_task: asyncio.Task[None] | None = None
        self._watcher: DBWatcher | None = None
        self._watcher_reload_task: asyncio.Task[None] | None = None
        self._branch_sync_task: asyncio.Task[None] | None = None
        self._inline_action_message: str | None = None
        self._session_summary_by_task: dict[str, _TaskSessionSummary] = {}

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
            yield ChatPanel(classes="chat-overlay")
        with Container(classes="size-warning"):
            yield Static(self._size_warning_message(), classes="size-warning-text")
        yield PeekOverlay(id="peek-overlay", classes="task-peek-overlay")
        yield KanbanHintBar(id="kanban-hint-bar", classes="board-hint-bar")

    async def on_mount(self) -> None:
        self._refresh_header()
        panel = self.query_one(ChatPanel)
        panel.set_overlay_shortcuts(split="Space", fullscreen="Ctrl+F", close="Esc")
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        await self._load_orchestrator_panel_state(panel)
        panel.set_mode_title("Orchestrator")
        panel.set_session_kind(SessionKind.ORCHESTRATOR)
        self._set_tutorial_visible(False)
        self._chat_auto_opened = False
        self._update_search_bar_state()
        self._check_screen_size()
        self._sync_layout_state()
        self._update_hint_bar()
        self._update_review_queue_hint()
        self.call_after_refresh(self._focus_default_widget)
        self.run_worker(
            self._bootstrap_initial_state(),
            group="kanban-bootstrap",
            exclusive=True,
            exit_on_error=False,
        )
        self.run_worker(
            self._warm_orchestrator_backend(),
            group="kanban-chat-warmup",
            exclusive=False,
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
        panel = self.query_one(ChatPanel)
        panel.set_first_boot(not tutorial_seen)
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

            # Auto-open chat overlay when no tasks exist
            if not self._all_tasks:
                panel = self.query_one(ChatPanel)
                if not panel.has_class("visible"):
                    self._chat_overlay_layout_mode = "vertical"
                    self._chat_auto_opened = True
                    await self.action_open_orchestrator_chat()

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
        with contextlib.suppress(KaganError, NoMatches, OSError, RuntimeError, ValueError):
            await self.kagan_app.orchestrator_sessions.persist_active(
                history=self._chat_orchestrator_history,
                rendered_messages=[],
                agent_backend=self.query_one(ChatPanel).preferred_agent_backend(),
            )
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
        panel = self.query_one(ChatPanel)
        if panel.has_class("visible"):
            panel.query_one("#chat-overlay-input", Input).focus()
            return
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

    def _sync_layout_state(self) -> None:
        panel = self.query_one(ChatPanel)
        visible = panel.has_class("visible")
        fullscreen = visible and panel.has_class("fullscreen")
        if not self._all_tasks and visible and not fullscreen:
            self._chat_overlay_layout_mode = "vertical"
        expanded = visible and (panel.has_class("expanded") or fullscreen)

        self.set_class(visible, "chat-overlay-visible")
        self.set_class(expanded, "chat-overlay-expanded")
        self.set_class(
            visible and not fullscreen and self._chat_overlay_layout_mode == "vertical",
            "chat-overlay-vertical",
        )
        self.set_class(
            visible and not fullscreen and self._chat_overlay_layout_mode == "horizontal",
            "chat-overlay-horizontal",
        )
        self._update_hint_bar()
        self._update_review_queue_hint()

    async def _reload_tasks(self) -> None:
        tasks = await self.kagan_app.core.tasks.list()
        if not self.is_mounted:
            return
        self._all_tasks = sorted(
            tasks,
            key=lambda task: (str(getattr(task, "created_at", "") or ""), task.id),
        )
        self._session_summary_by_task = await self._collect_session_summaries(self._all_tasks)
        self._apply_filter()

    async def _collect_session_summaries(self, tasks: list[Task]) -> dict[str, _TaskSessionSummary]:
        if not tasks:
            return {}

        task_ids = [task.id for task in tasks]
        summaries_data = await self.kagan_app.core.tasks.sessions.active_session_summaries(task_ids)

        summaries: dict[str, _TaskSessionSummary] = {}
        for task_id, summary_data in summaries_data.items():
            summaries[task_id] = _TaskSessionSummary(
                has_history=bool(summary_data.get("has_history")),
                has_active=bool(summary_data.get("has_active")),
                active_mode=summary_data.get("active_mode"),
                latest_mode=summary_data.get("latest_mode"),
            )

        return summaries

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
                    execution_mode=task.execution_mode,
                    status=task.status,
                    review_approved=task.review_approved,
                    acceptance_criteria=list(task.acceptance_criteria),
                    updated_at=task.updated_at,
                    agent_backend=task.agent_backend,
                    base_branch=task.base_branch,
                    github_issue_number=getattr(task, "github_issue_number", None),
                    github_pr_number=getattr(task, "github_pr_number", None),
                    task_type=getattr(task, "task_type", None),
                    has_active_session=summary.has_active,
                    has_session_history=summary.has_history,
                    latest_session_mode=summary.latest_mode,
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
        text_query, status_filter, priority_filter, mode_filter, sort_filter = (
            self._parse_search_query(self._search_query)
        )
        self._search_status_filter = status_filter
        self._search_priority_filter = priority_filter
        self._search_mode_filter = mode_filter
        self._search_sort_filter = sort_filter

        if (
            not text_query
            and status_filter is None
            and priority_filter is None
            and mode_filter is None
            and sort_filter is None
        ):
            self._tasks = list(self._all_tasks)
        else:
            self._tasks = [
                task
                for task in self._all_tasks
                if self._matches_search(
                    task,
                    text_query=text_query,
                    status_filter=status_filter,
                    priority_filter=priority_filter,
                    mode_filter=mode_filter,
                )
            ]

        self._tasks = self._apply_sort(self._tasks, sort_filter)

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
        status_counts = {status.value: 0 for status in TaskStatus}
        high_priority_count = 0
        for task in self._all_tasks:
            status_counts[task.status.value] += 1
            if task.priority >= Priority.HIGH:
                high_priority_count += 1
        self.query_one(SearchBar).update_state(
            filtered_count=len(tasks),
            total_count=len(self._all_tasks),
            status_counts=status_counts,
            high_priority_count=high_priority_count,
            status_filter=status_filter.value.lower() if status_filter is not None else "",
            priority_filter=priority_filter or "",
            mode_filter=mode_filter.value.lower() if mode_filter is not None else "",
            sort_filter=sort_filter or "",
            search_active=self.search_visible,
        )
        self._refresh_header()
        self._update_review_queue_hint()
        self._update_hint_bar()
        self._sync_search_header_swap_state()
        self._sync_layout_state()

    def _update_search_bar_state(self) -> None:
        status_counts = {status.value: 0 for status in TaskStatus}
        high_priority_count = 0
        for task in self._all_tasks:
            status_counts[task.status.value] += 1
            if task.priority >= Priority.HIGH:
                high_priority_count += 1
        sf = self._search_status_filter
        pf = self._search_priority_filter
        mf = self._search_mode_filter
        sf2 = self._search_sort_filter
        self.query_one(SearchBar).update_state(
            filtered_count=len(self._tasks),
            total_count=len(self._all_tasks),
            status_counts=status_counts,
            high_priority_count=high_priority_count,
            status_filter=sf.value.lower() if sf is not None else "",
            priority_filter=pf or "",
            mode_filter=mf.value.lower() if mf is not None else "",
            sort_filter=sf2 or "",
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
        return self._inspector().is_open

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
        left = get_key_for_action(KANBAN_BINDINGS, "move_backward", default="Shift+Left")
        right = get_key_for_action(KANBAN_BINDINGS, "move_forward", default="Shift+Right")
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
        rows = get_global_shortcut_help_rows()
        return rows[:3]

    def _mode_label(self) -> str:
        panel = self.query_one(ChatPanel)
        if panel.has_class("visible") and panel.has_class("fullscreen"):
            return "Assistant"
        if panel.has_class("visible") and self._chat_overlay_layout_mode == "vertical":
            return "Split"
        if panel.has_class("visible") and self._chat_overlay_layout_mode == "horizontal":
            return "Docked"
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
        header = self.query_one(KaganHeader)
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
        open_key = get_key_for_action(KANBAN_BINDINGS, "open_task", default="Enter")
        search_key = get_key_for_action(KANBAN_BINDINGS, "search", default="/")
        new_key = get_key_for_action(KANBAN_BINDINGS, "new_task", default="n")
        overlay_key = get_key_for_action(KANBAN_BINDINGS, "toggle_chat", default="Ctrl+I")
        right_key = get_key_for_action(KANBAN_BINDINGS, "move_right", default="Shift+Right")
        left_key = get_key_for_action(KANBAN_BINDINGS, "move_left", default="Shift+Left")
        session_key = get_key_for_action(KANBAN_BINDINGS, "open_task", default="Enter")
        stop_key = get_key_for_action(KANBAN_BINDINGS, "stop_agent", default="Shift+S")
        start_agent_key = get_key_for_action(KANBAN_BINDINGS, "start_agent", default="s")
        panel = self.query_one(ChatPanel)
        overlay_open = panel.has_class("visible")
        fullscreen_key = get_key_for_action(
            KANBAN_BINDINGS, "expand_chat_overlay", default="Ctrl+F"
        )

        overlay_hints: list[tuple[str, str]] = []
        if overlay_open:
            overlay_hints.extend(
                [
                    (overlay_key, "split"),
                    (fullscreen_key, "fullscreen"),
                    ("Esc", "close"),
                ]
            )

        if task is None:
            return [
                (new_key, "new"),
                (search_key, "search"),
                (overlay_key, "assistant split"),
                *overlay_hints,
            ]

        if task.status is TaskStatus.BACKLOG:
            return [
                (open_key, "inspect"),
                (session_key, "open"),
                (new_key, "new"),
                (right_key, "start"),
                (start_agent_key, "agent"),
                *overlay_hints,
            ]

        if task.status is TaskStatus.IN_PROGRESS:
            actions = [
                (open_key, "inspect"),
                (session_key, "open"),
                (right_key, "review"),
            ]
            if task.execution_mode is WorkMode.AUTO:
                actions.append((stop_key, "stop"))
            actions.extend(overlay_hints)
            return actions

        if task.status is TaskStatus.REVIEW:
            return [
                (open_key, "inspect"),
                (right_key, "merge"),
                (left_key, "reopen"),
                (session_key, "open"),
                *overlay_hints,
            ]

        return [
            (open_key, "inspect"),
            (session_key, "history"),
            *overlay_hints,
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

    async def action_open_orchestrator_chat(self) -> None:
        panel = self.query_one(ChatPanel)
        was_visible = panel.has_class("visible")
        panel.set_visible(True)
        panel.set_fullscreen(False)
        if not was_visible:
            self._chat_overlay_layout_mode = "vertical"
        panel.set_mode_title("Orchestrator")
        panel.set_session_kind(SessionKind.ORCHESTRATOR)
        await self._load_orchestrator_panel_state(panel)
        panel.query_one("#chat-overlay-input", Input).focus()
        self._chat_mode = ChatMode.ORCHESTRATOR
        self._chat_active_task_id = None
        self._sync_layout_state()
        self.run_worker(
            self._warm_orchestrator_backend(panel.preferred_agent_backend()),
            group="kanban-chat-warmup",
            exclusive=False,
            exit_on_error=False,
        )

    async def action_open_task_overlay(self) -> None:
        panel = self.query_one(ChatPanel)
        was_visible = panel.has_class("visible")
        panel.set_visible(True)
        panel.set_fullscreen(False)
        if not was_visible:
            self._chat_overlay_layout_mode = "vertical"
        panel.query_one("#chat-overlay-input", Input).focus()
        self._chat_mode = ChatMode.TASK

        task = self._selected_task()
        if task is None:
            panel.set_mode_title("Task Chat")
            panel.add_system_message("Select a task first")
            self._sync_layout_state()
            return

        self._chat_active_task_id = task.id
        panel.set_mode_title(f"Task #{task.id[:8]}")
        panel.set_session_kind(SessionKind.AUTO)
        panel.set_sessions(build_session_options(self.kagan_app, task), TASK_WORKER_SESSION_KEY)
        self._ensure_chat_stream_worker(task.id)
        self._sync_layout_state()

    async def action_open_task_chat(self) -> None:
        panel = self.query_one(ChatPanel)
        panel.set_visible(True)
        panel.set_fullscreen(True)
        panel.query_one("#chat-overlay-input", Input).focus()
        self._chat_mode = ChatMode.TASK

        task = self._selected_task()
        if task is None:
            panel.set_mode_title("Task Chat")
            panel.add_system_message("Select a task first")
            return

        self._chat_active_task_id = task.id
        panel.set_mode_title(f"Task #{task.id[:8]}")
        panel.set_session_kind(SessionKind.AUTO)
        panel.set_sessions(build_session_options(self.kagan_app, task), TASK_WORKER_SESSION_KEY)
        self._ensure_chat_stream_worker(task.id)
        self._sync_layout_state()

    def _transition_from_fullscreen(self, panel: ChatPanel) -> None:
        """Exit fullscreen mode and return to vertical overlay."""
        panel.set_fullscreen(False)
        self._chat_auto_opened = False
        self._chat_overlay_layout_mode = "vertical"
        panel.query_one("#chat-overlay-input", Input).focus()
        self._sync_layout_state()

    def _transition_from_hidden(self) -> None:
        """Open the orchestrator chat when panel is not visible."""
        self._chat_overlay_layout_mode = "vertical"
        self._chat_auto_opened = False
        self.run_worker(
            self.action_open_orchestrator_chat(),
            group="kanban-chat-mode",
            exclusive=True,
        )

    def _transition_to_horizontal(self, panel: ChatPanel) -> None:
        """Switch from vertical to horizontal layout mode."""
        if not self._all_tasks:
            self._transition_to_hidden(panel)
            return
        self._chat_overlay_layout_mode = "horizontal"
        self._chat_auto_opened = False
        panel.query_one("#chat-overlay-input", Input).focus()
        self._sync_layout_state()

    def _transition_to_hidden(self, panel: ChatPanel) -> None:
        """Hide the chat panel completely."""
        panel.set_visible(False)
        panel.set_fullscreen(False)
        self._chat_auto_opened = False
        self._chat_overlay_layout_mode = "vertical"
        self._sync_layout_state()

    def action_toggle_chat(self) -> None:
        panel = self.query_one(ChatPanel)

        visible = panel.has_class("visible")
        fullscreen = visible and panel.has_class("fullscreen")
        vertical = self._chat_overlay_layout_mode == "vertical"

        if fullscreen:
            self._transition_from_fullscreen(panel)
        elif not visible:
            self._transition_from_hidden()
        elif vertical:
            self._transition_to_horizontal(panel)
        else:
            self._transition_to_hidden(panel)

    async def action_switch_session(self) -> None:
        panel = self.query_one(ChatPanel)
        if not panel.has_class("visible"):
            await self.action_open_task_overlay()
        panel.action_open_session_picker()

    async def action_fullscreen_chat(self) -> None:
        panel = self.query_one(ChatPanel)
        if panel.has_class("visible") and panel.has_class("fullscreen"):
            panel.set_visible(False)
            panel.set_fullscreen(False)
            self._chat_auto_opened = False
            self._chat_overlay_layout_mode = "vertical"
            self._sync_layout_state()
            return
        if panel.has_class("visible"):
            panel.set_fullscreen(True)
            self._chat_auto_opened = False
            panel.query_one("#chat-overlay-input", Input).focus()
            self._sync_layout_state()
            return
        panel.set_visible(True)
        panel.set_fullscreen(True)
        self._chat_auto_opened = False
        panel.set_mode_title("Orchestrator")
        panel.set_session_kind(SessionKind.ORCHESTRATOR)
        await self._load_orchestrator_panel_state(panel)
        panel.query_one("#chat-overlay-input", Input).focus()
        self._chat_mode = ChatMode.ORCHESTRATOR
        self._chat_active_task_id = None
        self._sync_layout_state()
        self.run_worker(
            self._warm_orchestrator_backend(panel.preferred_agent_backend()),
            group="kanban-chat-warmup",
            exclusive=False,
            exit_on_error=False,
        )

    async def action_expand_chat_overlay(self) -> None:
        panel = self.query_one(ChatPanel)
        if not panel.has_class("visible"):
            return
        panel.set_fullscreen(True)
        self._chat_auto_opened = False
        panel.query_one("#chat-overlay-input", Input).focus()
        self._sync_layout_state()

    async def _warm_orchestrator_backend(self, preferred_backend: str | None = None) -> None:
        panel = self.query_one(ChatPanel)
        settings = await self.kagan_app.core.settings.get()
        backend = (
            preferred_backend
            or panel.preferred_agent_backend()
            or resolve_default_agent_backend(settings)
        )
        if not backend.strip():
            return
        with contextlib.suppress(KaganError, NoMatches, OSError, RuntimeError, ValueError):
            await warm_orchestrator_backend(self.kagan_app.core, agent_backend=backend)

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
        self.kagan_app._active_task_id = task.id
        if task.execution_mode == WorkMode.PAIR:
            self.run_worker(self._open_pair_session_flow(task), exclusive=False)
            return

        from kagan.tui.screens.task_screen import TaskScreen

        self.app.push_screen(TaskScreen(task_id=task.id))

    async def _open_pair_session_flow(self, task: Task) -> None:
        import platform
        from pathlib import Path

        from kagan.tui.screens.gateway import PairInstructionsModal
        from kagan.tui.terminals.installer import (
            check_terminal_installed,
            first_available_pair_backend,
            get_manual_install_fallback,
        )

        settings = await self.kagan_app.core.settings.get()
        settings_launcher_raw = settings.get("pair_launcher", "tmux")
        settings_launcher = (
            settings_launcher_raw.strip().lower()
            if isinstance(settings_launcher_raw, str)
            else "tmux"
        )
        task_launcher = task.launcher.strip().lower() if isinstance(task.launcher, str) else ""
        backend = task_launcher or settings_launcher
        is_windows = platform.system() == "Windows"
        self._set_inline_action_message(f"Checking {backend} backend...")

        if not check_terminal_installed(backend):
            # Try to find a fallback
            fallback = first_available_pair_backend(windows=is_windows)
            if fallback is not None:
                self.app.notify(
                    f"{backend} not found. Using fallback: {fallback}.",
                    severity="information",
                )
                backend = fallback
                self._set_inline_action_message(f"Using fallback backend: {fallback}.")
            else:
                hint = get_manual_install_fallback(backend)
                self.app.notify(
                    f"PAIR cancelled: {backend} not installed. {hint}",
                    severity="warning",
                )
                self._set_inline_action_message(None)
                return

        skip_instructions_raw = settings.get("skip_pair_instructions_popup", "")
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
                PairInstructionsModal(task.id, task.title, backend, prompt_path)
            )
            if result is None:
                self._set_inline_action_message(None)
                return  # User cancelled
            if result == "skip_future":
                await self.kagan_app.core.settings.set({"skip_pair_instructions_popup": "true"})

        if workspace is None:
            self._set_inline_action_message("Provisioning workspace...")
            self.app.notify("Creating workspace...", severity="information")
            try:
                await self.kagan_app.core.worktrees.create(task.id)
                workspace = await self.kagan_app.core.worktrees.get(task.id)
            except (KaganError, OSError, RuntimeError, ValueError) as exc:
                self.app.notify(f"Failed to create workspace: {exc}", severity="error")
                self._set_inline_action_message(None)
                return
        if workspace is None:
            self.app.notify("Failed to provision workspace.", severity="error")
            self._set_inline_action_message(None)
            return

        wt_path = Path(workspace.worktree_path)
        prompt_path = wt_path / ".kagan" / "start_prompt.md"

        agent_backend = task.agent_backend or resolve_default_agent_backend(settings)
        launcher, ide_name = resolve_launcher(backend)

        try:
            self._set_inline_action_message("Starting PAIR session...")
            pair_session = await self.kagan_app.core.tasks.pair(
                task.id,
                agent_backend=agent_backend,
                launcher=launcher,
                ide=ide_name,
            )
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            self.app.notify(f"Failed to start PAIR session: {exc}", severity="error")
            self._set_inline_action_message(None)
            return

        attached = False
        if backend == "tmux":
            self._set_inline_action_message("Attaching tmux session...")
            session_name = self._tmux_session_name(pair_session.id)
            with self._suspend_app():
                attached = await self._attach_tmux_session(session_name)
            if not attached:
                # Retry: session may have been killed — recreate and re-attach
                self.app.notify(
                    "PAIR session missing; recreating session...",
                    severity="information",
                )
                with contextlib.suppress(KaganError):
                    retry_session = await self.kagan_app.core.tasks.pair(
                        task.id,
                        agent_backend=agent_backend,
                        launcher=launcher,
                        ide=ide_name,
                    )
                    session_name = self._tmux_session_name(retry_session.id)
                with self._suspend_app():
                    attached = await self._attach_tmux_session(session_name)
        elif backend == "nvim":
            self._set_inline_action_message("Opening Neovim session...")
            with self._suspend_app():
                attached = await self._attach_nvim_session(wt_path, prompt_path)
        else:
            # IDE backends (vscode/cursor/windsurf/kiro/antigravity) launch externally
            self.app.notify(
                f"Workspace opened in {backend}. Use startup prompt: {prompt_path}",
                severity="information",
            )
            self._set_inline_action_message(None)
            return

        if attached:
            with contextlib.suppress(KaganError):
                await self.kagan_app.core.tasks.end_pairing(task.id)
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
        except SuspendNotSupported:
            self.app.notify(
                "Terminal suspend not supported in this environment. "
                "Run PAIR from a standard terminal (not textual dev).",
                severity="warning",
            )

    @staticmethod
    async def _attach_tmux_session(session_name: str) -> bool:
        import asyncio as _aio

        try:
            proc = await _aio.create_subprocess_exec(
                "tmux",
                "attach-session",
                "-t",
                session_name,
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
            proc = await _aio.create_subprocess_exec(
                "nvim",
                target,
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

        self.kagan_app._active_task_id = task.id
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
            execution_mode=task.execution_mode,
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

    async def action_stop_agent(self) -> None:
        if not self._require_inspector(action_label="Stop agent"):
            return
        task = self._selected_task()
        if task is None:
            return
        await self.kagan_app.core.tasks.cancel(task.id)
        await self._reload_tasks()

    def action_new_auto_task(self) -> None:
        self.app.push_screen(TaskEditorModal(execution_mode=WorkMode.AUTO))

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
            chat_visible = self.query_one(ChatPanel).has_class("visible")
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
            if chat_visible:
                hint.update(
                    "No tasks yet. "
                    f"Press {new_key} to create one, {actions_key} for actions, "
                    "or type in chat to get started."
                )
            else:
                hint.update(
                    "No tasks yet. "
                    f"Press {new_key} to create one, {help_keys} for help, "
                    f"or {actions_key} for actions."
                )
            hint.add_class("visible")
            return
        review_count = sum(1 for task in self._all_tasks if task.status is TaskStatus.REVIEW)
        if review_count > 1:
            if chat_visible:
                hint.update(
                    "Review queue has multiple tasks. Process oldest first (oldest at top)."
                )
            else:
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

    async def on_chat_panel_submit_requested(self, message: ChatPanel.SubmitRequested) -> None:
        if self._chat_message_task is not None and not self._chat_message_task.done():
            self._chat_message_task.cancel()

        if self._chat_mode == ChatMode.ORCHESTRATOR:
            self._chat_message_task = asyncio.create_task(
                self._send_orchestrator_message(message.text),
                name="kanban-chat-orchestrator-send",
            )
            return

        self._chat_message_task = asyncio.create_task(
            self._send_task_message(message.text),
            name="kanban-chat-task-send",
        )

    def on_chat_panel_session_changed(self, message: ChatPanel.SessionChanged) -> None:
        if is_orchestrator_session_key(message.key):
            self._chat_mode = ChatMode.ORCHESTRATOR
            self._chat_active_task_id = None
            panel = self.query_one(ChatPanel)
            panel.set_mode_title("Orchestrator")
            panel.set_session_kind(SessionKind.ORCHESTRATOR)
            self._chat_orchestrator_history = self.kagan_app.orchestrator_sessions.history_for_key(
                message.key
            )
            panel.hydrate_current_session_history(self._chat_orchestrator_history)
            self._chat_session_switch_token += 1
            token = self._chat_session_switch_token
            self.run_worker(
                self._switch_orchestrator_session(panel, message.key, token=token),
                exit_on_error=False,
            )
            return
        self._chat_mode = ChatMode.TASK
        task = self._selected_task()
        panel = self.query_one(ChatPanel)
        if task is None:
            panel.set_mode_title("Task Chat")
            panel.set_session_kind(SessionKind.AUTO)
            panel.add_system_message("Select a task first")
            return
        self._chat_active_task_id = task.id
        panel.set_mode_title(f"Task #{task.id[:8]}")
        kind = SessionKind.REVIEW if "review" in message.key.casefold() else SessionKind.AUTO
        panel.set_session_kind(kind)
        panel.set_sessions(build_session_options(self.kagan_app, task), message.key)
        self._ensure_chat_stream_worker(task.id)

    def on_chat_panel_session_picker_requested(
        self, message: ChatPanel.SessionPickerRequested
    ) -> None:
        panel = cast("Any", getattr(message, "control", getattr(message, "sender", None)))
        if not isinstance(panel, ChatPanel):
            panel = self.query_one(ChatPanel)

        modal = panel.create_session_picker_modal(initial_query=message.initial_query)

        def _on_select(selected_key: str | None) -> None:
            if selected_key is None:
                return
            selector = panel.query_one("#chat-overlay-session-select", Select)
            selector.value = selected_key

        self.app.push_screen(modal, callback=_on_select)

    def on_chat_panel_agent_picker_requested(
        self, _message: ChatPanel.AgentPickerRequested
    ) -> None:
        panel = self.query_one(ChatPanel)

        def _on_agent_selected(selected: str | None) -> None:
            if selected is None:
                return
            panel._agent_hint = selected
            panel.add_system_message(f"Default agent set to {selected}")
            self.run_worker(
                self._warm_orchestrator_backend(selected),
                group="kanban-chat-warmup",
                exclusive=False,
                exit_on_error=False,
            )

        self.app.push_screen("agent-picker-modal", callback=_on_agent_selected)

    def on_chat_panel_close_requested(self, message: ChatPanel.CloseRequested) -> None:
        panel = cast("Any", getattr(message, "control", getattr(message, "sender", None)))
        if not isinstance(panel, ChatPanel):
            panel = self.query_one(ChatPanel)
        panel.set_visible(False)
        panel.set_fullscreen(False)
        self._chat_overlay_layout_mode = "vertical"
        self._sync_layout_state()

    def on_chat_panel_interrupt_requested(self, _: ChatPanel.InterruptRequested) -> None:
        if self._chat_message_task is not None and not self._chat_message_task.done():
            self._chat_message_task.cancel()
            return
        self.run_worker(self.action_stop_agent(), exit_on_error=False)

    def on_chat_panel_new_session_requested(self, _: ChatPanel.NewSessionRequested) -> None:
        panel = self.query_one(ChatPanel)
        self.run_worker(self._create_new_orchestrator_session(panel), exit_on_error=False)

    async def _send_orchestrator_message(self, text: str) -> None:
        panel = self.query_one(ChatPanel)
        # Prepend accumulated DB-change context (invisible to user)
        ctx = self._watcher.drain_context() if self._watcher else None
        enriched = f"{ctx}\n\n{text}" if ctx else text
        should_title = self.kagan_app.orchestrator_sessions.should_generate_title()
        try:
            self._chat_orchestrator_history = await send_chat_message(
                core=self.kagan_app.core,
                panel=panel,
                text=enriched,
                history=self._chat_orchestrator_history,
            )
            await self.kagan_app.orchestrator_sessions.persist_active(
                history=self._chat_orchestrator_history,
                rendered_messages=panel.export_rendered_messages(),
                agent_backend=panel.preferred_agent_backend(),
            )
            if should_title and self._chat_orchestrator_history:
                task = self._selected_task()
                asyncio.create_task(
                    kick_title_generation(
                        TitleGenerationSession(
                            orchestrator_sessions=self.kagan_app.orchestrator_sessions,
                            panel=panel,
                            user_message=text,
                            history=self._chat_orchestrator_history,
                            session_options=build_session_options(self.kagan_app, task),
                            is_mounted=lambda: self.is_mounted,
                        ),
                        self.kagan_app.core,
                    ),
                    name="tui-chat-title-gen",
                )
        except asyncio.CancelledError:
            panel.set_runtime_status("ready")
            panel.set_stream_action("Waiting for prompt", confidence="certain")
            raise
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            panel.set_runtime_status("error")
            panel.set_stream_action("Orchestrator error", confidence="needs-validation")
            panel.add_system_message(f"Orchestrator error: {exc}")

    async def _switch_orchestrator_session(
        self,
        panel: ChatPanel,
        key: str,
        *,
        token: int | None = None,
    ) -> None:
        if token is not None and token != self._chat_session_switch_token:
            return
        await self.kagan_app.orchestrator_sessions.persist_active(
            history=self._chat_orchestrator_history,
            rendered_messages=panel.export_rendered_messages(),
            agent_backend=panel.preferred_agent_backend(),
        )
        if token is not None and token != self._chat_session_switch_token:
            return
        await self._load_orchestrator_panel_state(panel, requested_key=key)
        if token is not None and token != self._chat_session_switch_token:
            return
        self.run_worker(
            self._warm_orchestrator_backend(panel.preferred_agent_backend()),
            group="kanban-chat-warmup",
            exclusive=False,
            exit_on_error=False,
        )

    async def _create_new_orchestrator_session(self, panel: ChatPanel) -> None:
        await self.kagan_app.orchestrator_sessions.persist_active(
            history=self._chat_orchestrator_history,
            rendered_messages=panel.export_rendered_messages(),
            agent_backend=panel.preferred_agent_backend(),
        )
        next_key = await self.kagan_app.orchestrator_sessions.create_new(
            agent_backend=panel.preferred_agent_backend()
        )
        await self._load_orchestrator_panel_state(panel, requested_key=next_key)
        panel.add_system_message("New session started.")

    async def _load_orchestrator_panel_state(
        self,
        panel: ChatPanel,
        *,
        requested_key: str | None = None,
    ) -> None:
        await self.kagan_app.orchestrator_sessions.ensure_loaded()
        if requested_key is not None and is_orchestrator_session_key(requested_key):
            self._chat_orchestrator_history = await self.kagan_app.orchestrator_sessions.switch(
                requested_key
            )
        else:
            self._chat_orchestrator_history = self.kagan_app.orchestrator_sessions.active_history()

        active_key = self.kagan_app.orchestrator_sessions.active_key()
        task = self._selected_task()
        panel.set_sessions(build_session_options(self.kagan_app, task), active_key)
        panel.hydrate_current_session_history(self._chat_orchestrator_history)
        session_backend = self.kagan_app.orchestrator_sessions.agent_backend_for_key(active_key)
        if session_backend is not None:
            panel.set_preferred_agent_backend(session_backend)

    def _task_session_options(self, task: Task) -> list[tuple[str, str]]:
        ticket = task.title.strip() or f"Ticket #{task.id[:8]}"
        return [
            (f"{ticket} · Worker", TASK_WORKER_SESSION_KEY),
            (f"{ticket} · Reviewer", TASK_REVIEWER_SESSION_KEY),
        ]

    async def _send_task_message(self, text: str) -> None:
        panel = self.query_one(ChatPanel)
        task = self._selected_task()
        if task is None:
            panel.add_system_message("No selected task")
            return

        self._chat_active_task_id = task.id
        try:
            updated_task = await send_task_message(self.kagan_app.core, task, text)

            settings = await self.kagan_app.core.settings.get()
            backend = (
                panel.preferred_agent_backend()
                or updated_task.agent_backend
                or resolve_default_agent_backend(settings)
            )
            panel.set_runtime_status("initializing")
            panel.set_stream_action("Restarting task agent...", confidence="assumption")
            await self.kagan_app.core.tasks.run(task.id, agent_backend=backend)
            self._ensure_chat_stream_worker(task.id)
        except (KaganError, OSError, RuntimeError, ValueError) as exc:
            panel.set_runtime_status("error")
            panel.set_stream_action("Unable to restart task agent", confidence="needs-validation")
            panel.add_system_message(f"Unable to restart agent: {exc}")

    def _ensure_chat_stream_worker(self, task_id: str) -> None:
        if self._chat_stream_task is not None and not self._chat_stream_task.done():
            self._chat_stream_task.cancel()
        self._chat_stream_task = asyncio.create_task(
            self._stream_task_chat(task_id),
            name=f"kanban-chat-stream:{task_id}",
        )

    async def _stream_task_chat(self, task_id: str) -> None:
        panel = self.query_one(ChatPanel)
        try:
            async for event in self.kagan_app.core.tasks.events.stream(task_id):
                if self._chat_mode != ChatMode.TASK or self._chat_active_task_id != task_id:
                    continue

                payload = event.payload or {}
                apply_task_chat_event(panel, event.event_type, payload)
        except asyncio.CancelledError:
            raise
        except (KaganError, NoMatches, AttributeError, OSError, RuntimeError) as exc:
            panel.set_runtime_status("error")
            panel.set_stream_action("Stream error", confidence="needs-validation")
            panel.add_system_message(f"Stream error: {exc}")

    def _focused_widget_accepts_text(self) -> bool:
        focused = self.focused
        return isinstance(focused, Input | TextArea)

    def _chat_timeline_stream(self) -> StreamingOutput | None:
        panel = self.query_one(ChatPanel)
        if not panel.has_class("visible"):
            return None
        try:
            return panel.query_one("#chat-overlay-output", StreamingOutput)
        except NoMatches:
            return None

    def _focused_widget_in_chat_timeline(self) -> bool:
        stream = self._chat_timeline_stream()
        if stream is None:
            return False
        focused = self.focused
        if focused is None:
            return False
        return any(widget is focused for widget in stream.query("#streaming-body-content > *"))

    def action_open_repo_picker(self) -> None:
        self.app.push_screen("repo-picker-modal")

    def action_open_settings(self) -> None:
        self.app.push_screen("settings-modal", callback=self._on_settings_dismissed)

    def _on_settings_dismissed(self, _result: None) -> None:
        from kagan.tui.app import KaganApp

        app = self.app
        if isinstance(app, KaganApp):
            app.run_worker(app._apply_saved_theme(), exclusive=False)

    def action_new_task(self) -> None:
        self.app.push_screen(TaskEditorModal())

    async def on_screen_resume(self) -> None:
        await self._reload_tasks()
        self._sync_layout_state()
        self.call_after_refresh(self._auto_focus_board)

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
            self.query_one(ChatPanel).set_first_boot(False)
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
            panel = self.query_one(ChatPanel)
            if panel.has_class("visible"):
                if self._focused_widget_in_chat_timeline():
                    event.prevent_default()
                    event.stop()
                    panel.query_one("#chat-overlay-input", Input).focus()
                    return
                event.prevent_default()
                event.stop()
                panel.set_visible(False)
                panel.set_fullscreen(False)
                self._chat_overlay_layout_mode = "vertical"
                self._sync_layout_state()
                return

        if event.key == "ctrl+k":
            event.prevent_default()
            event.stop()
            panel = self.query_one(ChatPanel)
            if not panel.has_class("visible"):
                await self.action_open_task_overlay()
            panel.action_open_session_picker()
            return

        if event.key == "ctrl+f":
            panel = self.query_one(ChatPanel)
            if panel.has_class("visible"):
                event.prevent_default()
                event.stop()
                await self.action_expand_chat_overlay()
                return

        if self._focused_widget_accepts_text():
            if event.key == "enter":
                panel = self.query_one(ChatPanel)
                if panel.has_class("visible"):
                    event.prevent_default()
                    event.stop()
                    panel.action_send_message()
                    return
            return

        stream = self._chat_timeline_stream()
        if stream is not None and self._focused_widget_in_chat_timeline():
            timeline_actions = {
                "j": stream.action_focus_next_entry,
                "down": stream.action_focus_next_entry,
                "k": stream.action_focus_prev_entry,
                "up": stream.action_focus_prev_entry,
                "h": stream.action_collapse_entry,
                "left": stream.action_collapse_entry,
                "l": stream.action_expand_entry,
                "right": stream.action_expand_entry,
                "g": stream.action_focus_first_entry,
                "home": stream.action_focus_first_entry,
                "G": stream.action_jump_to_latest,
                "end": stream.action_jump_to_latest,
            }
            action = timeline_actions.get(event.key)
            if action is not None:
                event.prevent_default()
                event.stop()
                action()
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

        self.app.push_screen(
            TaskDeleteConfirmModal(
                task,
                has_worktree=has_worktree,
                has_active_session=has_active_session,
            ),
            callback=_on_result,
        )

    async def _delete_task(self, task_id: str) -> None:
        # Optimistic: remove card from board immediately before async delete
        self._all_tasks = [t for t in self._all_tasks if t.id != task_id]
        self._session_summary_by_task.pop(task_id, None)
        self._apply_filter()

        await self.kagan_app.core.tasks.delete(task_id)
        if self._chat_active_task_id == task_id:
            self._chat_active_task_id = None
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
    def _parse_search_query(
        query: str,
    ) -> tuple[str, TaskStatus | None, str | None, WorkMode | None, str | None]:
        tokens = [token for token in query.split() if token.strip()]
        text_parts: list[str] = []
        status_filter: TaskStatus | None = None
        priority_filter: str | None = None
        mode_filter: WorkMode | None = None
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
            if normalized.startswith("@mode:"):
                mode_filter = _SEARCH_MODE_ALIASES.get(normalized.removeprefix("@mode:"))
                if mode_filter is not None:
                    continue
            if normalized.startswith("@sort:"):
                sort_filter = _SEARCH_SORT_ALIASES.get(normalized.removeprefix("@sort:"))
                if sort_filter is not None:
                    continue
            text_parts.append(token)

        return (
            " ".join(text_parts).strip().lower(),
            status_filter,
            priority_filter,
            mode_filter,
            sort_filter,
        )

    @staticmethod
    def _matches_search(
        task: Task,
        *,
        text_query: str,
        status_filter: TaskStatus | None,
        priority_filter: str | None,
        mode_filter: WorkMode | None,
    ) -> bool:
        if status_filter is not None and task.status != status_filter:
            return False
        if priority_filter == "high" and task.priority < Priority.HIGH:
            return False
        if priority_filter == "medium" and task.priority != Priority.MEDIUM:
            return False
        if priority_filter == "low" and task.priority != Priority.LOW:
            return False
        if mode_filter is not None and task.execution_mode != mode_filter:
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
