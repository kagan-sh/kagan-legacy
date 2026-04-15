from dataclasses import dataclass
from typing import Protocol

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer, Vertical
from textual.message import Message
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from kagan.core.enums import Priority, TaskStatus
from kagan.tui.widgets.card import TaskCard


class _TaskData(Protocol):
    id: str
    title: str
    description: str
    priority: Priority
    status: TaskStatus
    review_approved: bool
    acceptance_criteria: list[str]
    has_active_session: bool
    has_session_history: bool
    active_launcher: str | None
    latest_launcher: str | None


_COLUMN_ORDER: tuple[TaskStatus, ...] = (
    TaskStatus.BACKLOG,
    TaskStatus.IN_PROGRESS,
    TaskStatus.REVIEW,
    TaskStatus.DONE,
)


class BoardColumn(Vertical):
    DEFAULT_CSS = """
    BoardColumn {
        layout: vertical;
    }

    BoardColumn .column-header {
        width: 100%;
        height: auto;
    }

    BoardColumn .column-header-text,
    BoardColumn .column-count {
        width: auto;
    }

    BoardColumn .column-content {
        width: 100%;
        height: 1fr;
    }

    BoardColumn .column-empty {
        width: 100%;
        height: 1fr;
        layout: vertical;
        align: center middle;
        padding: 1;
    }

    BoardColumn .empty-message {
        width: 100%;
        text-align: center;
    }
    """

    def __init__(self, status: TaskStatus) -> None:
        super().__init__(id=f"column-{status.value.lower()}", classes="kanban-column")
        self.status = status

    def compose(self) -> ComposeResult:
        with Horizontal(classes="column-header kanban-column-header"):
            header_widget = Static(
                self._header_title(),
                id=f"header-{self.status.value.lower()}",
                classes="column-header-text kanban-column-header-text",
            )
            header_widget.tooltip = f"Column: {self._header_label()}"
            yield header_widget
            count_widget = Static(
                "",
                id=f"count-{self.status.value.lower()}",
                classes="column-count kanban-column-count",
            )
            count_widget.tooltip = "Task count in this column"
            yield count_widget
        content = ScrollableContainer(
            id=f"content-{self.status.value.lower()}",
            classes="column-content kanban-column-content",
        )
        content.tooltip = f"{self._header_label()} tasks (use arrow keys to navigate)"
        yield content

    def set_tasks(self, tasks: list[_TaskData], selected_task_id: str | None) -> None:
        content = self.query_one(f"#content-{self.status.value.lower()}", ScrollableContainer)
        existing_cards: dict[str, TaskCard] = {}
        for card in content.query(TaskCard):
            task_data = card.task_data
            if task_data is None:
                continue
            existing_cards[task_data.id] = card

        if not tasks:
            for child in list(content.children):
                child.remove()
            empty_title, empty_detail = self._empty_message()
            content.mount(
                Vertical(
                    Static(
                        empty_title,
                        classes="empty-message empty-message-title column-empty-title",
                    ),
                    Static(
                        empty_detail,
                        classes="empty-message empty-message-detail column-empty-detail",
                    ),
                    classes="column-empty kanban-column-empty",
                ),
            )
            self._update_header_count(0)
            return

        for child in list(content.children):
            if not isinstance(child, TaskCard):
                child.remove()

        incoming_ids = {task.id for task in tasks}
        for task_id, card in existing_cards.items():
            if task_id not in incoming_ids:
                card.remove()

        for task in tasks:
            existing = existing_cards.get(task.id)
            if existing is not None:
                existing.task_data = task
                existing.selected = task.id == selected_task_id
                continue
            content.mount(TaskCard(task, selected=task.id == selected_task_id))
        self._update_header_count(len(tasks))

    def _header_title(self) -> str:
        if self.status == TaskStatus.BACKLOG:
            return "▫ BACKLOG"
        if self.status == TaskStatus.IN_PROGRESS:
            return "▶ IN PROGRESS"
        if self.status == TaskStatus.REVIEW:
            return "◉ REVIEW"
        return "✓ DONE"

    def _header_label(self) -> str:
        """Return plain text label for accessibility."""
        if self.status == TaskStatus.BACKLOG:
            return "Backlog"
        if self.status == TaskStatus.IN_PROGRESS:
            return "In Progress"
        if self.status == TaskStatus.REVIEW:
            return "Review"
        return "Done"

    def _update_header_count(self, count: int) -> None:
        self.query_one(f"#count-{self.status.value.lower()}", Static).update(f"({count})")

    def _empty_message(self) -> tuple[str, str]:
        if self.status == TaskStatus.BACKLOG:
            return ("No backlog tasks", "Capture upcoming work here.")
        if self.status == TaskStatus.IN_PROGRESS:
            return ("No active runs", "Launch a task to see progress.")
        if self.status == TaskStatus.REVIEW:
            return ("Nothing in review", "Completed work collects here.")
        return ("No completed work", "Merged tasks move here.")


class BoardView(Widget):
    DEFAULT_CSS = """
    BoardView {
        layout: horizontal;
        height: 1fr;
    }
    """

    @dataclass
    class TaskSelected(Message):
        task_id: str

    @dataclass
    class TaskOpened(Message):
        task_id: str

    tasks: reactive[list[_TaskData]] = reactive(list)
    selected_task_id: reactive[str | None] = reactive(None)

    def compose(self) -> ComposeResult:
        for status in _COLUMN_ORDER:
            yield BoardColumn(status)

    def watch_tasks(self, _: list[_TaskData]) -> None:
        self._refresh_columns()

    def watch_selected_task_id(self, _: str | None) -> None:
        self._update_selection_only()

    def set_tasks(self, tasks: list[_TaskData], *, selected_task_id: str | None = None) -> None:
        self.tasks = tasks
        if selected_task_id is not None:
            self.selected_task_id = selected_task_id
        else:
            self._normalize_selection()

    def action_next_column(self) -> None:
        self._move_column(1)

    def action_prev_column(self) -> None:
        self._move_column(-1)

    def action_next_card(self) -> None:
        self._move_within_column(1)

    def action_prev_card(self) -> None:
        self._move_within_column(-1)

    def _move_within_column(self, delta: int) -> None:
        columns = self._column_task_ids()
        if not columns:
            return

        for task_ids in columns:
            if self.selected_task_id in task_ids:
                index = task_ids.index(self.selected_task_id)
                new_index = index + delta
                if 0 <= new_index < len(task_ids):
                    self._select_task(task_ids[new_index])
                return

        for task_ids in columns:
            if task_ids:
                self._select_task(task_ids[0])
                return

    def _move_selection(self, delta: int) -> None:
        ordered_ids = self._ordered_task_ids()
        if not ordered_ids:
            return

        current = self.selected_task_id if self.selected_task_id in ordered_ids else ordered_ids[0]
        index = ordered_ids.index(current)
        target_id = ordered_ids[(index + delta) % len(ordered_ids)]
        self._select_task(target_id)

    def _move_column(self, delta: int) -> None:
        columns = self._column_task_ids()
        if not columns:
            return

        current_column_index = 0
        current_row_index = 0
        found = False
        if self.selected_task_id is not None:
            for idx, task_ids in enumerate(columns):
                if self.selected_task_id in task_ids:
                    current_column_index = idx
                    current_row_index = task_ids.index(self.selected_task_id)
                    found = True
                    break

        if not found:
            for task_ids in columns:
                if task_ids:
                    self._select_task(task_ids[0])
                    return
            return

        for step in range(1, len(columns) + 1):
            idx = (current_column_index + (delta * step)) % len(columns)
            task_ids = columns[idx]
            if task_ids:
                target_row_index = min(current_row_index, len(task_ids) - 1)
                self._select_task(task_ids[target_row_index])
                return

    def _refresh_columns(self) -> None:
        grouped = self._tasks_by_status()
        self._normalize_selection()
        for status in _COLUMN_ORDER:
            column = self.query_one(f"#column-{status.value.lower()}", BoardColumn)
            column.set_tasks(grouped[status], self.selected_task_id)

    def _update_selection_only(self) -> None:
        selected = self.selected_task_id
        for card in self.query(TaskCard):
            task_data = card.task_data
            card.selected = bool(task_data is not None and task_data.id == selected)

    def _tasks_by_status(self) -> dict[TaskStatus, list[_TaskData]]:
        grouped: dict[TaskStatus, list[_TaskData]] = {status: [] for status in _COLUMN_ORDER}
        for task in self.tasks:
            grouped[task.status].append(task)
        return grouped

    def _ordered_task_ids(self) -> list[str]:
        grouped = self._tasks_by_status()
        ordered_ids: list[str] = []
        for status in _COLUMN_ORDER:
            ordered_ids.extend(task.id for task in grouped[status])
        return ordered_ids

    def _column_task_ids(self) -> list[list[str]]:
        grouped = self._tasks_by_status()
        return [[task.id for task in grouped[status]] for status in _COLUMN_ORDER]

    def _normalize_selection(self) -> None:
        ordered_ids = self._ordered_task_ids()
        if not ordered_ids:
            self.selected_task_id = None
            return
        if self.selected_task_id not in ordered_ids:
            grouped = self._tasks_by_status()
            for status in (
                TaskStatus.IN_PROGRESS,
                TaskStatus.REVIEW,
                TaskStatus.BACKLOG,
                TaskStatus.DONE,
            ):
                if grouped[status]:
                    self.selected_task_id = grouped[status][0].id
                    return
            self.selected_task_id = ordered_ids[0]

    def _select_task(self, task_id: str) -> None:
        if self.selected_task_id == task_id:
            self._focus_card_by_id(task_id)
            return
        self.selected_task_id = task_id
        self._focus_card_by_id(task_id)
        self.post_message(self.TaskSelected(task_id))

    def _focus_card_by_id(self, task_id: str) -> None:
        for card in self.query(TaskCard):
            task_data = card.task_data
            if task_data is not None and task_data.id == task_id:
                card.focus()
                return

    def on_task_card_selected(self, message: TaskCard.Selected) -> None:
        self._select_task(message.task_id)

    def on_task_card_opened(self, message: TaskCard.Opened) -> None:
        self.post_message(self.TaskOpened(message.task_id))
