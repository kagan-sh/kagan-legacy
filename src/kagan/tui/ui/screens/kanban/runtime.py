"""Kanban runtime surface for screen controller/state wiring."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from kagan.tui.ui.screens.kanban.board_controller import KanbanBoardController
from kagan.tui.ui.screens.kanban.review_controller import KanbanReviewController
from kagan.tui.ui.screens.kanban.session_controller import KanbanSessionController
from kagan.tui.ui.screens.kanban.task_controller import KanbanTaskController

if TYPE_CHECKING:
    from collections.abc import Sequence

    from kagan.core.domain.enums import TaskStatus
    from kagan.tui.ui.types import TaskView


@dataclass(slots=True)
class KanbanUiState:
    """Mutable UI state for transient Kanban interactions."""

    filtered_tasks: Sequence[TaskView] | None = None
    editing_task_id: str | None = None
    pending_delete_task: TaskView | None = None
    pending_merge_task: TaskView | None = None
    pending_close_task: TaskView | None = None
    pending_advance_task: TaskView | None = None
    pending_auto_move_task: TaskView | None = None
    pending_auto_move_status: TaskStatus | None = None

    def clear_pending(self) -> None:
        self.pending_delete_task = None
        self.pending_merge_task = None
        self.pending_close_task = None
        self.pending_advance_task = None
        self.pending_auto_move_task = None
        self.pending_auto_move_status = None

    def clear_all(self) -> None:
        self.clear_pending()
        self.editing_task_id = None
        self.filtered_tasks = None


__all__ = [
    "KanbanBoardController",
    "KanbanReviewController",
    "KanbanSessionController",
    "KanbanTaskController",
    "KanbanUiState",
]
