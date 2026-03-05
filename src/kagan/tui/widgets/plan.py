from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol, cast

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.message import Message
from textual.widgets import Static

PlanStatus = Literal["pending", "in_progress", "completed", "failed"]


@dataclass
class _PlanEntry:
    content: str
    status: PlanStatus = "pending"


class PlanTaskLike(Protocol):
    title: str
    description: str
    acceptance_criteria: list[str]
    priority: object


class PlanEntryRow(Static):
    def __init__(self, index: int, entry: _PlanEntry) -> None:
        self._entry = entry
        self._index = index
        classes = f"plan-entry plan-row {self._status_css(entry.status)}"
        super().__init__(self._render_text(), classes=classes, id=f"plan-row-{index}")

    @staticmethod
    def _status_css(status: PlanStatus) -> str:
        return {
            "pending": "priority-medium",
            "in_progress": "priority-high",
            "completed": "priority-low",
            "failed": "priority-critical",
        }[status]

    def _render_text(self) -> str:
        icon = {
            "pending": "[ ]",
            "in_progress": "[~]",
            "completed": "[x]",
            "failed": "[!]",
        }[self._entry.status]
        return f"{icon} {self._index}. {self._entry.content}"


class PlanApprovalWidget(Vertical):
    DEFAULT_CLASSES = "plan-approval chat-plan-approval"
    BINDINGS = [
        Binding("a", "approve", "Approve"),
        Binding("e", "edit", "Edit"),
        Binding("d", "dismiss", "Dismiss"),
    ]

    class Approved(Message):
        def __init__(self, tasks: list[PlanTaskLike]) -> None:
            super().__init__()
            self.tasks = tasks

    class EditRequested(Message):
        def __init__(self, tasks: list[PlanTaskLike]) -> None:
            super().__init__()
            self.tasks = tasks

    class Dismissed(Message):
        pass

    def __init__(
        self,
        tasks: list[PlanTaskLike],
        *,
        id: str | None = None,
        classes: str | None = None,
    ) -> None:
        merged_classes = (
            self.DEFAULT_CLASSES if not classes else f"{classes} {self.DEFAULT_CLASSES}"
        )
        super().__init__(id=id, classes=merged_classes)
        self._tasks = tasks

    def compose(self) -> ComposeResult:
        count = len(self._tasks)
        plural = "s" if count != 1 else ""
        yield Static(f"Generated Plan ({count} task{plural})", classes="plan-header")
        yield Static("Use Up/Down to review tasks", classes="plan-hint")
        with Vertical(id="task-list"):
            for idx, task in enumerate(self._tasks):
                priority = self._priority_css(getattr(task, "priority", "medium"))
                title = self._task_title(task.title)
                row = f"• {title} [{self._priority_label(getattr(task, 'priority', 'medium'))}]"
                yield Static(row, classes=f"task-row plan-row {priority}", id=f"task-row-{idx}")
        yield Static("[a] approve · [e] edit · [d] dismiss", classes="approval-hint")

    @staticmethod
    def _task_title(title: str) -> str:
        text = title.strip()
        return f"{text[:57]}..." if len(text) > 60 else text

    @staticmethod
    def _priority_label(priority: object) -> str:
        value = str(getattr(priority, "label", getattr(priority, "value", priority))).strip()
        return value.upper() if value else "MEDIUM"

    @staticmethod
    def _priority_css(priority: object) -> str:
        value = (
            str(getattr(priority, "css_class", getattr(priority, "value", priority)))
            .strip()
            .lower()
        )
        if "critical" in value:
            return "priority-critical"
        if "high" in value:
            return "priority-high"
        if "low" in value:
            return "priority-low"
        return "priority-medium"

    def action_approve(self) -> None:
        self.post_message(self.Approved(self._tasks))
        self.remove()

    def action_edit(self) -> None:
        self.post_message(self.EditRequested(self._tasks))
        self.remove()

    def action_dismiss(self) -> None:
        self.post_message(self.Dismissed())
        self.remove()


class PlanDisplay(Vertical):
    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        merged_classes = "plan-display chat-plan-display"
        if classes:
            merged_classes = f"{classes} {merged_classes}"
        super().__init__(id=id, classes=merged_classes)
        self._entries: list[_PlanEntry] = []

    def compose(self) -> ComposeResult:
        yield Static("Plan", classes="plan-title", id="plan-title")
        with Vertical(id="plan-body"):
            yield Static("No plan yet", classes="plan-empty", id="plan-empty")

    def set_plan(self, text: str) -> None:
        cleaned = text.strip()
        if not cleaned:
            self._entries.clear()
            self._render_entries()
            return

        lines = [line.strip("- ").strip() for line in cleaned.splitlines() if line.strip()]
        self.set_entries(lines)

    def set_entries(self, entries: Sequence[str | dict[str, str]]) -> None:
        normalized: list[_PlanEntry] = []
        for entry in entries:
            if isinstance(entry, str):
                text = entry.strip()
                if text:
                    normalized.append(_PlanEntry(content=text))
                continue

            text = str(entry.get("content", "")).strip()
            if not text:
                continue
            raw_status = str(entry.get("status", "pending")).strip().lower()
            status: PlanStatus
            if raw_status in {"pending", "in_progress", "completed", "failed"}:
                status = cast("PlanStatus", raw_status)
            else:
                status = "pending"
            normalized.append(_PlanEntry(content=text, status=status))

        self._entries = normalized
        self._render_entries()

    def update_entry_status(self, index: int, status: PlanStatus) -> None:
        if 0 <= index < len(self._entries):
            self._entries[index].status = status
            self._render_entries()

    def append_entry(self, content: str, status: PlanStatus = "pending") -> None:
        text = content.strip()
        if not text:
            return
        self._entries.append(_PlanEntry(content=text, status=status))
        self._render_entries()

    def clear(self) -> None:
        self._entries.clear()
        self._render_entries()

    def _render_entries(self) -> None:
        body = self.query_one("#plan-body", Vertical)
        empty = self.query_one("#plan-empty", Static)
        for child in list(body.children):
            if child is empty:
                continue
            child.remove()
        if not self._entries:
            empty.display = True
            empty.update("No plan yet")
            return

        empty.display = False
        for idx, entry in enumerate(self._entries, start=1):
            body.mount(PlanEntryRow(index=idx, entry=entry))
