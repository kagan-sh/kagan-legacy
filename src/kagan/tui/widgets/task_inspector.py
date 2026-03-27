from typing import Protocol

from textual.app import ComposeResult
from textual.containers import VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from kagan.core.enums import Priority, TaskStatus


class _TaskData(Protocol):
    id: str
    title: str
    description: str
    status: TaskStatus
    priority: Priority
    agent_backend: str | None
    base_branch: str | None
    launcher: str | None
    acceptance_criteria: list[str]
    review_approved: bool


def _priority_label(priority: Priority) -> str:
    if priority >= Priority.HIGH:
        return "High"
    if priority == Priority.MEDIUM:
        return "Medium"
    return "Low"


def _status_label(status: TaskStatus) -> str:
    mapping = {
        TaskStatus.BACKLOG: "Backlog",
        TaskStatus.IN_PROGRESS: "In Progress",
        TaskStatus.REVIEW: "Review",
        TaskStatus.DONE: "Done",
    }
    return mapping[status]


class TaskInspector(Widget):
    task_data: reactive[_TaskData | None] = reactive(None)
    is_open: reactive[bool] = reactive(False)
    message: reactive[str] = reactive("")
    message_level: reactive[str] = reactive("info")

    DEFAULT_CSS = """
    TaskInspector {
        display: none;
    }

    TaskInspector.is-open {
        display: block;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="inspector-scroll", classes="inspector-scroll"):
            title = Static("Task Inspector", classes="inspector-title")
            title.tooltip = "Detailed task information and metadata"
            yield title
            head = Static("", id="inspector-head", classes="inspector-head")
            head.tooltip = "Task title and ID"
            yield head
            meta = Static("", id="inspector-meta", classes="inspector-meta")
            meta.tooltip = "Task metadata (status, priority, backend, branch)"
            yield meta
            desc_label = Static("Description", classes="inspector-section-label")
            desc_label.tooltip = "Task description section"
            yield desc_label
            desc = Static(
                "", id="inspector-description", classes="inspector-description", markup=False
            )
            desc.tooltip = "Full task description text"
            yield desc
            criteria_label = Static("Acceptance Criteria", classes="inspector-section-label")
            criteria_label.tooltip = "Task acceptance criteria section"
            yield criteria_label
            criteria = Static("", id="inspector-criteria", classes="inspector-criteria", markup=False)
            criteria.tooltip = "List of acceptance criteria for task completion"
            yield criteria
            message = Static("", id="inspector-message", classes="inspector-message")
            message.tooltip = "Status messages and notifications"
            yield message
            actions = Static("", id="inspector-actions", classes="inspector-actions")
            actions.tooltip = "Available task actions"
            yield actions

    def watch_is_open(self, is_open: bool) -> None:
        self.set_class(is_open, "is-open")

    def watch_task_data(self, _: _TaskData | None) -> None:
        self._render_task_data()

    def watch_message(self, _: str) -> None:
        self._render_message()

    def watch_message_level(self, _: str) -> None:
        self._render_message()

    def on_mount(self) -> None:
        self.query_one("#inspector-scroll", VerticalScroll).can_focus = False

    def show_task(self, task: _TaskData) -> None:
        self.task_data = task
        self.is_open = True
        self.call_after_refresh(self._scroll_to_top)

    def hide_inspector(self) -> None:
        self.is_open = False
        self._scroll_to_top()

    def set_message(self, message: str, *, level: str = "info") -> None:
        self.message = message.strip()
        self.message_level = level

    def clear_message(self) -> None:
        self.message = ""
        self.message_level = "info"

    def _render_task_data(self) -> None:
        head = self.query_one("#inspector-head", Static)
        meta = self.query_one("#inspector-meta", Static)
        description = self.query_one("#inspector-description", Static)
        criteria = self.query_one("#inspector-criteria", Static)
        actions = self.query_one("#inspector-actions", Static)

        task = self.task_data
        if task is None:
            head.update("No task selected")
            meta.update("Select a card and press Enter to inspect.")
            description.update("No description.")
            criteria.update("No acceptance criteria.")
            actions.update("[bold]Enter[/] to inspect task")
            self._render_message()
            return

        head.update(f"#{task.id[:8]} · {task.title}")
        status = _status_label(task.status)
        priority = _priority_label(task.priority)
        branch = (task.base_branch or "-").strip() or "-"
        backend = (task.agent_backend or "project default").strip() or "project default"
        launcher = (task.launcher or "project default").strip() or "project default"
        meta.update(
            f"Status: {status}   Priority: {priority}\n"
            f"Branch: {branch}   Launcher: {launcher}\n"
            f"Backend: {backend}"
        )

        text = (task.description or "").strip() or "No description."
        description.update(text)

        lines = [item.strip() for item in task.acceptance_criteria if item and item.strip()]
        if not lines:
            criteria.update("No acceptance criteria.")
        else:
            displayed = lines[:6]
            extra = len(lines) - len(displayed)
            rendered = "\n".join(f"- {line}" for line in displayed)
            if extra > 0:
                rendered = f"{rendered}\n- (+{extra} more)"
            criteria.update(rendered)

        if task.status is TaskStatus.REVIEW and not task.acceptance_criteria:
            self.set_message(
                "Review blocked: add acceptance criteria before merge.", level="warning"
            )
        elif task.status is TaskStatus.REVIEW and not task.review_approved:
            self.set_message("Ready to approve.", level="info")
        else:
            self.clear_message()

        actions.update(
            "[bold]Enter[/] open  [bold]e[/] edit  [bold]x[/] delete\n"
            "[bold]s[/] start  [bold]a[/] attach  [bold]Shift+S[/] stop  "
            "[bold]Shift+←/→[/] move  [bold]Esc[/] close"
        )
        self._render_message()

    def _render_message(self) -> None:
        message = self.query_one("#inspector-message", Static)
        message.update(self.message)
        message.display = bool(self.message)
        message.remove_class("is-warning", "is-error", "is-info")
        if self.message_level == "warning":
            message.add_class("is-warning")
        elif self.message_level == "error":
            message.add_class("is-error")
        elif self.message:
            message.add_class("is-info")

    def _scroll_to_top(self) -> None:
        self.query_one("#inspector-scroll", VerticalScroll).scroll_home(animate=False)
