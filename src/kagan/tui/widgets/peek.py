from dataclasses import dataclass
from typing import Protocol

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.reactive import reactive
from textual.widgets import Static

from kagan.core.enums import Priority, TaskStatus


class _TaskData(Protocol):
    id: str
    title: str
    description: str
    status: TaskStatus
    priority: Priority


def _priority_name(value: Priority) -> str:
    mapping = {
        Priority.LOW: "LOW",
        Priority.MEDIUM: "MEDIUM",
        Priority.HIGH: "HIGH",
        Priority.CRITICAL: "CRITICAL",
    }
    return mapping[value]


@dataclass
class _PeekModel:
    title: str
    status: str
    content: str


class PeekOverlay(Vertical):
    DEFAULT_CSS = """
    PeekOverlay {
        layout: vertical;
    }
    """

    peek_task: reactive[_TaskData | None] = reactive(None)
    peek_visible: reactive[bool] = reactive(False)

    def __init__(self, **kwargs) -> None:
        classes = str(kwargs.pop("classes", "")).strip()
        merged_classes = (
            "peek-overlay task-peek-overlay"
            if not classes
            else f"{classes} peek-overlay task-peek-overlay"
        )
        kwargs.setdefault("id", "peek-overlay")
        super().__init__(classes=merged_classes, **kwargs)
        self.display = False

    def compose(self) -> ComposeResult:
        yield Static("", id="peek-title", classes="peek-title")
        yield Static("", id="peek-status", classes="peek-status")
        yield Static("", id="peek-content", classes="peek-content")

    def watch_peek_task(self, task: _TaskData | None) -> None:
        model = self._build_model(task)
        self.query_one("#peek-title", Static).update(model.title)
        self.query_one("#peek-status", Static).update(model.status)
        self.query_one("#peek-content", Static).update(model.content)

    def watch_peek_visible(self, visible: bool) -> None:
        self.display = visible
        self.set_class(visible, "visible")

    def show_task(self, task: _TaskData) -> None:
        self.peek_task = task
        self.peek_visible = True

    def show_at(self, x: int, y: int) -> None:
        self.styles.offset = (x, y)
        self.peek_visible = True

    def hide_overlay(self) -> None:
        self.peek_visible = False

    def toggle(self) -> bool:
        if self.has_class("visible"):
            self.hide_overlay()
            return False
        self.peek_visible = True
        return True

    def _build_model(self, task: _TaskData | None) -> _PeekModel:
        if task is None:
            return _PeekModel("", "", "")
        title = f"#{task.id}: {task.title[:30]}"
        status = f"{task.status.value} · {_priority_name(task.priority)}"
        content = (task.description.strip() or "(No content)")[:300]
        return _PeekModel(title, status, content)
