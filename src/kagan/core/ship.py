"""Ship transition guards and the push/PR command strings the user runs.

No push, merge, or PR-API call happens here — these are printed strings only
(TUI-SHIP-01/02/03), and this module invokes no git. The user runs the commands
under their own git identity (TUI-CONFIG-05).
"""

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from kagan.core.enums import TaskState
from kagan.core.errors import InvalidTransitionError, NotFoundError

if TYPE_CHECKING:
    from kagan.core.ledger import Ledger
    from kagan.core.models import Task


class ShipService:
    def __init__(self, ledger: Ledger) -> None:
        self._ledger = ledger

    def _load(self, task_id: str) -> Task:
        task = self._ledger.load_task(task_id)
        if task is None:
            raise NotFoundError("task", task_id)
        return task

    def _save(self, task: Task, event: dict) -> None:
        task.updated_at = datetime.now(UTC)
        self._ledger.save_task(task)
        self._ledger.append_event(task.id, event)

    def approve(self, task_id: str) -> Task:
        task = self._load(task_id)
        if task.state not in {TaskState.REVIEW, TaskState.DONE}:
            raise InvalidTransitionError(task.state, TaskState.READY)
        task.state = TaskState.READY
        self._save(task, {"type": "approved", "to": TaskState.READY.value})
        return task

    def mark_pushed(self, task_id: str) -> Task:
        task = self._load(task_id)
        if task.state != TaskState.READY:
            raise InvalidTransitionError(task.state, TaskState.PR_OPEN)
        task.state = TaskState.PR_OPEN
        self._save(task, {"type": "pushed", "to": TaskState.PR_OPEN.value})
        return task

    def push_command(self, task: Task) -> str:
        if not task.branch:
            raise ValueError("task has no branch")
        return f"git push -u origin {task.branch}"

    def pr_command(self, task: Task) -> str:
        if not task.branch:
            raise ValueError("task has no branch")
        return f'gh pr create --base {task.base_branch} --head {task.branch} --title "{task.title}"'
