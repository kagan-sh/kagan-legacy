from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive, var
from textual.widget import Widget
from textual.widgets import Static

from kagan.core.enums import Priority, TaskStatus, WorkMode


class _TaskData(Protocol):
    id: str
    title: str
    description: str
    priority: Priority
    execution_mode: WorkMode
    status: TaskStatus
    review_approved: bool
    acceptance_criteria: list[str]
    has_active_session: bool
    has_session_history: bool
    latest_session_mode: WorkMode | None


_TITLE_MAX = 56
_DESC_MAX = 64
_BACKEND_MAX = 18

_INDICATOR_CLASSES = frozenset(
    {
        "indicator-passed",
        "indicator-reviewing",
        "indicator-running-auto",
        "indicator-running-pair",
        "indicator-not-started",
        "indicator-idle",
    }
)

_PRIORITY_CLASSES = frozenset({"priority-low", "priority-medium", "priority-high"})

_STATUS_CLASSES = frozenset(
    {
        "card-run-state",
        "run-state-auto-running",
        "run-state-pair-running",
        "run-state-not-started",
        "run-state-idle",
        "run-state-review",
        "run-state-done",
    }
)


def _truncate_text(value: str, max_len: int) -> str:
    text = value.strip()
    if len(text) <= max_len:
        return text
    return f"{text[: max_len - 1]}…"


def _priority_label(priority: Priority) -> str:
    mapping = {
        Priority.LOW: "LOW",
        Priority.MEDIUM: "MEDIUM",
        Priority.HIGH: "HIGH",
        Priority.CRITICAL: "CRITICAL",
    }
    return mapping[priority]


class TaskCard(Widget):
    can_focus = True
    _NAVIGATION_ACTIONS: dict[str, str] = {
        "h": "action_focus_left",
        "left": "action_focus_left",
        "j": "action_focus_down",
        "down": "action_focus_down",
        "k": "action_focus_up",
        "up": "action_focus_up",
        "l": "action_focus_right",
        "right": "action_focus_right",
    }

    DEFAULT_CSS = """
    TaskCard {
        layout: vertical;
        height: 4;
    }

    TaskCard .card-content {
        width: 100%;
        height: 100%;
    }

    TaskCard .card-row {
        width: 100%;
        height: 1;
    }

    TaskCard .card-rail {
        width: 1;
    }

    TaskCard .card-indicator {
        width: 2;
    }

    TaskCard .card-title {
        width: 1fr;
    }

    TaskCard .card-id {
        width: auto;
    }

    TaskCard .card-desc {
        width: 1fr;
    }

    TaskCard .card-elapsed {
        width: auto;
    }

    TaskCard .card-badge-row {
        width: 100%;
    }

    TaskCard .card-badge {
        width: auto;
        margin-right: 1;
    }

    TaskCard .card-spacer {
        width: 1fr;
    }
    """

    task_data: reactive[_TaskData | None] = reactive(None, always_update=True)
    selected: var[bool] = var(False, always_update=True)

    @dataclass
    class Selected(Message):
        task_id: str

    @dataclass
    class Opened(Message):
        task_id: str

    def __init__(self, task: _TaskData, *, selected: bool = False) -> None:
        super().__init__(id=f"card-{task.id}", classes="kanban-card")
        # Label refs — populated in compose(), updated incrementally.
        self._rail_label: Static | None = None
        self._indicator_label: Static | None = None
        self._title_label: Static | None = None
        self._id_label: Static | None = None
        self._desc_label: Static | None = None
        self._elapsed_label: Static | None = None
        self._status_label: Static | None = None
        self._backend_label: Static | None = None
        self._branch_label: Static | None = None
        self._issue_label: Static | None = None
        self._pr_label: Static | None = None
        self._type_label: Static | None = None
        self._priority_label: Static | None = None
        # Set reactive after super().__init__ so id is assigned.
        self.task_data = task
        self.selected = selected

    # ------------------------------------------------------------------
    # Static helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_elapsed(updated_at: object) -> str | None:
        if not updated_at:
            return None
        try:
            if isinstance(updated_at, datetime):
                ts = updated_at
            else:
                ts = datetime.fromisoformat(str(updated_at).rstrip("Z"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=UTC)
            delta = datetime.now(tz=UTC) - ts
            seconds = int(delta.total_seconds())
            if seconds < 60:
                return None
            if seconds < 3600:
                return f"{seconds // 60}m"
            return f"{seconds // 3600}h"
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _rail_class(status: TaskStatus | str | None) -> str:
        normalized = str(getattr(status, "value", status) or "").upper()
        if normalized == TaskStatus.IN_PROGRESS.value:
            return "rail-running"
        if normalized == TaskStatus.REVIEW.value:
            return "rail-warning"
        if normalized == TaskStatus.DONE.value:
            return "rail-success"
        return "rail-normal"

    @staticmethod
    def _priority_css(priority: Priority) -> str:
        if priority >= Priority.HIGH:
            return "priority-high"
        if priority == Priority.MEDIUM:
            return "priority-medium"
        return "priority-low"

    @staticmethod
    def _indicator_state(task: _TaskData) -> tuple[str, str]:
        status = task.status
        if bool(task.review_approved) or status == TaskStatus.DONE:
            return ("●", "indicator-passed")
        if status == TaskStatus.REVIEW:
            return ("◉", "indicator-reviewing")
        if task.has_active_session:
            if task.execution_mode == WorkMode.PAIR:
                return ("◉", "indicator-running-pair")
            return ("◉", "indicator-running-auto")
        if not task.has_session_history:
            return ("○", "indicator-not-started")
        if status == TaskStatus.IN_PROGRESS:
            return ("●", "indicator-idle")
        return ("●", "indicator-idle")

    @staticmethod
    def _status_line(task: _TaskData) -> tuple[str, str]:
        mode_label = "PAIR" if task.execution_mode == WorkMode.PAIR else "AUTO"
        status = task.status

        if status == TaskStatus.DONE:
            return (f"{mode_label} done", "card-run-state run-state-done")
        if status == TaskStatus.REVIEW:
            return (f"{mode_label} in review", "card-run-state run-state-review")
        if task.has_active_session:
            if task.execution_mode == WorkMode.PAIR:
                return ("PAIR session active", "card-run-state run-state-pair-running")
            return ("AUTO agent running", "card-run-state run-state-auto-running")
        if not task.has_session_history:
            return (f"{mode_label} not started", "card-run-state run-state-not-started")
        return (f"{mode_label} ready", "card-run-state run-state-idle")

    # ------------------------------------------------------------------
    # Compose — skeleton only, no data computation
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        self._rail_label = Static("▌", classes="card-rail task-card-rail rail-normal")
        self._indicator_label = Static("", classes="card-indicator task-card-indicator")
        self._title_label = Static("", classes="card-title task-card-title")
        self._id_label = Static("", classes="card-id task-card-id")
        self._id_label.display = False
        self._desc_label = Static("", classes="card-desc task-card-desc")
        self._elapsed_label = Static("", classes="card-elapsed task-card-elapsed")
        self._elapsed_label.display = False
        self._status_label = Static("", classes="")
        self._backend_label = Static(
            "", classes="card-badge card-badge-backend task-card-badge-backend"
        )
        self._backend_label.display = False
        self._branch_label = Static("", classes="card-badge card-branch task-card-branch")
        self._branch_label.display = False
        self._issue_label = Static(
            "", classes="card-badge card-badge-gh card-badge-gh-issue task-card-badge-gh-issue"
        )
        self._issue_label.display = False
        self._pr_label = Static(
            "", classes="card-badge card-badge-gh card-badge-gh-pr task-card-badge-gh-pr"
        )
        self._pr_label.display = False
        self._type_label = Static("", classes="card-badge card-badge-type task-card-badge-type")
        self._priority_label = Static(
            "", classes="card-badge card-badge-priority task-card-badge-priority"
        )

        with Vertical(classes="card-content task-card-content"):
            with Horizontal(classes="card-row task-card-row"):
                yield self._rail_label
                yield self._indicator_label
                yield self._title_label
                yield self._id_label

            with Horizontal(classes="card-row task-card-row"):
                yield self._desc_label
                yield self._elapsed_label

            with Horizontal(classes="card-row task-card-row"):
                yield self._status_label

            with Horizontal(classes="card-row task-card-row card-badge-row task-card-badge-row"):
                yield self._backend_label
                yield self._branch_label
                yield self._issue_label
                yield self._pr_label
                yield self._type_label
                yield Static("", classes="card-spacer task-card-spacer")
                yield self._priority_label

    # ------------------------------------------------------------------
    # Lifecycle & watchers
    # ------------------------------------------------------------------

    def on_mount(self) -> None:
        self.set_class(self.selected, "-selected")
        self._render_task()

    def watch_task_data(self, _task: _TaskData | None) -> None:
        self._render_task()

    def watch_selected(self, selected: bool) -> None:
        self.set_class(selected, "-selected")
        self._render_task()

    # ------------------------------------------------------------------
    # Incremental render — update labels in-place, never recompose
    # ------------------------------------------------------------------

    def _labels_ready(self) -> bool:
        return self._title_label is not None and self._desc_label is not None

    def _render_task(self) -> None:
        task = self.task_data
        if task is None or not self._labels_ready():
            return

        assert self._rail_label is not None
        assert self._indicator_label is not None
        assert self._title_label is not None
        assert self._id_label is not None
        assert self._desc_label is not None
        assert self._elapsed_label is not None
        assert self._status_label is not None
        assert self._backend_label is not None
        assert self._branch_label is not None
        assert self._issue_label is not None
        assert self._pr_label is not None
        assert self._type_label is not None
        assert self._priority_label is not None

        # Title
        self._title_label.update(_truncate_text(task.title, _TITLE_MAX))
        self._id_label.update(f"#{task.id[:8]}")
        self._id_label.display = True

        # Rail
        status = getattr(task, "status", None)
        rail_cls = self._rail_class(status)
        self._rail_label.remove_class("rail-running", "rail-warning", "rail-success", "rail-normal")
        self._rail_label.add_class(rail_cls)

        # Indicator
        indicator_text, indicator_css = self._indicator_state(task)
        self._indicator_label.update(indicator_text)
        for cls in _INDICATOR_CLASSES:
            self._indicator_label.remove_class(cls)
        self._indicator_label.add_class(indicator_css)

        # Description
        desc = (task.description or "").strip()
        if self.selected and desc:
            self._desc_label.update(_truncate_text(desc, _DESC_MAX))
            self._desc_label.remove_class("card-desc-empty")
            self._desc_label.display = True
        else:
            self._desc_label.update("")
            self._desc_label.display = False

        # Elapsed
        elapsed = self._format_elapsed(getattr(task, "updated_at", None))
        if elapsed:
            self._elapsed_label.update(elapsed)
            self._elapsed_label.display = True
        else:
            self._elapsed_label.update("")
            self._elapsed_label.display = False

        # Status line
        status_text, status_css = self._status_line(task)
        self._status_label.update(status_text)
        for cls in _STATUS_CLASSES:
            self._status_label.remove_class(cls)
        for cls in status_css.split():
            self._status_label.add_class(cls)

        # Backend
        backend = (getattr(task, "agent_backend", None) or "").strip()
        show_extended = False

        if backend and show_extended:
            self._backend_label.update(_truncate_text(backend, _BACKEND_MAX))
            self._backend_label.display = True
        else:
            self._backend_label.update("")
            self._backend_label.display = False

        # Branch
        branch = (getattr(task, "base_branch", None) or "").strip()
        if branch and show_extended:
            self._branch_label.update(f"⎇ {branch}")
            self._branch_label.display = True
        else:
            self._branch_label.update("")
            self._branch_label.display = False

        # GitHub badges
        issue_number = getattr(task, "github_issue_number", None)
        if isinstance(issue_number, int) and show_extended:
            self._issue_label.update(f"GH#{issue_number}")
            self._issue_label.display = True
        else:
            self._issue_label.update("")
            self._issue_label.display = False

        pr_number = getattr(task, "github_pr_number", None)
        if isinstance(pr_number, int) and show_extended:
            self._pr_label.update(f"PR #{pr_number}")
            self._pr_label.display = True
        else:
            self._pr_label.update("")
            self._pr_label.display = False

        # Type
        task_type = str(getattr(getattr(task, "task_type", None), "value", "")).strip()
        task_type = task_type or ("AUTO" if task.execution_mode == WorkMode.AUTO else "PAIR")
        self._type_label.update(task_type)

        # Priority
        priority = _priority_label(task.priority)
        priority_css = self._priority_css(task.priority)
        self._priority_label.update(priority)
        for cls in _PRIORITY_CLASSES:
            self._priority_label.remove_class(cls)
        self._priority_label.add_class(priority_css)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    async def on_click(self, _: events.Click) -> None:
        task = self.task_data
        if task is None:
            return
        self.post_message(self.Selected(task.id))

    async def _on_key(self, event: events.Key) -> None:
        if event.key == "enter":
            task = self.task_data
            if task is None:
                return
            event.prevent_default()
            event.stop()
            self.post_message(self.Opened(task.id))
            return

        action_name = self._NAVIGATION_ACTIONS.get(event.key)
        if action_name is not None:
            action = getattr(self.screen, action_name, None)
            if callable(action):
                event.prevent_default()
                event.stop()
                action()
                return

        await super()._on_key(event)
