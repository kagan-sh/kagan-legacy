from dataclasses import dataclass
from datetime import UTC, datetime

from textual import events
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.reactive import reactive, var
from textual.widget import Widget
from textual.widgets import Static

from kagan.core.enums import Priority, TaskStatus
from kagan.tui.types import TaskData

_TITLE_MAX = 56
_DESC_MAX = 64
_BACKEND_MAX = 18

_INDICATOR_CLASSES = frozenset(
    {
        "indicator-passed",
        "indicator-reviewing",
        "indicator-running-managed",
        "indicator-running-interactive",
        "indicator-not-started",
        "indicator-idle",
    }
)

_PRIORITY_CLASSES = frozenset({"priority-low", "priority-medium", "priority-high"})

_STATUS_CLASSES = frozenset(
    {
        "card-run-state",
        "run-state-managed-running",
        "run-state-interactive-running",
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
        height: 3;
    }

    TaskCard.-selected {
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

    task_data: reactive[TaskData | None] = reactive(None, always_update=True)
    selected: var[bool] = var(False, always_update=True)

    @dataclass
    class Selected(Message):
        task_id: str

    @dataclass
    class Opened(Message):
        task_id: str

    def __init__(self, task: TaskData, *, selected: bool = False) -> None:
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
        # Row container refs — toggled for compact/expanded layout.
        self._desc_row: Horizontal | None = None
        self._badge_row: Horizontal | None = None
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
    def _indicator_state(task: TaskData) -> tuple[str, str]:
        status = task.status
        if bool(getattr(task, "review_approved", False)) or status == TaskStatus.DONE:
            return ("●", "indicator-passed")
        if status == TaskStatus.REVIEW:
            return ("◉", "indicator-reviewing")
        if bool(getattr(task, "has_active_session", False)):
            active_launcher = getattr(task, "active_launcher", None)
            if active_launcher:
                return ("◉", "indicator-running-interactive")
            return ("◉", "indicator-running-managed")
        if not bool(getattr(task, "has_session_history", False)):
            return ("○", "indicator-not-started")
        if status == TaskStatus.IN_PROGRESS:
            return ("●", "indicator-idle")
        return ("●", "indicator-idle")

    @staticmethod
    def _status_line(task: TaskData) -> tuple[str, str]:
        status = task.status

        if status == TaskStatus.DONE:
            return ("Done", "card-run-state run-state-done")
        if status == TaskStatus.REVIEW:
            return ("In review", "card-run-state run-state-review")
        if bool(getattr(task, "has_active_session", False)):
            active_launcher = getattr(task, "active_launcher", None)
            if active_launcher:
                return (
                    f"Interactive session active ({active_launcher})",
                    "card-run-state run-state-interactive-running",
                )
            return ("Agent running", "card-run-state run-state-managed-running")
        if not bool(getattr(task, "has_session_history", False)):
            return ("Not started", "card-run-state run-state-not-started")
        return ("Ready", "card-run-state run-state-idle")

    # ------------------------------------------------------------------
    # Compose — skeleton only, no data computation
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        self._rail_label = Static("▌", classes="card-rail task-card-rail rail-normal")
        self._rail_label.tooltip = "Task status indicator"
        self._indicator_label = Static("", classes="card-indicator task-card-indicator")
        self._indicator_label.tooltip = "Task execution state"
        self._title_label = Static("", classes="card-title task-card-title")
        self._title_label.tooltip = "Task title (press Enter to open)"
        self._id_label = Static("", classes="card-id task-card-id")
        self._id_label.display = False
        self._id_label.tooltip = "Task identifier"
        self._desc_label = Static("", classes="card-desc task-card-desc")
        self._desc_label.tooltip = "Task description"
        self._elapsed_label = Static("", classes="card-elapsed task-card-elapsed")
        self._elapsed_label.display = False
        self._elapsed_label.tooltip = "Time since last update"
        self._status_label = Static("", classes="")
        self._status_label.tooltip = "Current task status and session info"
        self._backend_label = Static(
            "", classes="card-badge card-badge-backend task-card-badge-backend"
        )
        self._backend_label.display = False
        self._backend_label.tooltip = "Agent backend"
        self._branch_label = Static("", classes="card-badge card-branch task-card-branch")
        self._branch_label.display = False
        self._branch_label.tooltip = "Git branch"
        self._issue_label = Static(
            "", classes="card-badge card-badge-gh card-badge-gh-issue task-card-badge-gh-issue"
        )
        self._issue_label.display = False
        self._issue_label.tooltip = "GitHub issue reference"
        self._pr_label = Static(
            "", classes="card-badge card-badge-gh card-badge-gh-pr task-card-badge-gh-pr"
        )
        self._pr_label.display = False
        self._pr_label.tooltip = "GitHub pull request reference"
        self._type_label = Static("", classes="card-badge card-badge-type task-card-badge-type")
        self._type_label.tooltip = "Task type classification"
        self._priority_label = Static(
            "", classes="card-badge card-badge-priority task-card-badge-priority"
        )
        self._priority_label.tooltip = "Priority level"

        self._desc_row = Horizontal(classes="card-row task-card-row")
        self._badge_row = Horizontal(
            classes="card-row task-card-row card-badge-row task-card-badge-row"
        )

        with Vertical(classes="card-content task-card-content"):
            with Horizontal(classes="card-row task-card-row"):
                yield self._rail_label
                yield self._indicator_label
                yield self._title_label
                yield self._id_label

            with self._desc_row:
                yield self._desc_label
                yield self._elapsed_label

            with Horizontal(classes="card-row task-card-row"):
                yield self._status_label

            with self._badge_row:
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
        self._update_aria_label()
        self._render_task()

    def watch_task_data(self, _task: TaskData | None) -> None:
        self._update_aria_label()
        self._render_task()

    def watch_selected(self, selected: bool) -> None:
        self.set_class(selected, "-selected")
        self._update_aria_label()
        self._render_task()

    # ------------------------------------------------------------------
    # Incremental render — update labels in-place, never recompose
    # ------------------------------------------------------------------

    def _labels_ready(self) -> bool:
        return (
            self._title_label is not None
            and self._desc_label is not None
            and self._desc_row is not None
            and self._badge_row is not None
        )

    def _update_aria_label(self) -> None:
        """Update ARIA label to reflect task state for screen readers."""
        task = self.task_data
        if task is None:
            self.tooltip = None
            return

        status_text, _status_css = self._status_line(task)
        priority_text = _priority_label(task.priority)
        label = f"Task: {task.title}, Status: {status_text}, Priority: {priority_text}"
        self.tooltip = label

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
        assert self._desc_row is not None
        assert self._badge_row is not None

        # Compact vs expanded row visibility
        self._desc_row.display = self.selected
        self._badge_row.display = self.selected

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

        elapsed = self._format_elapsed(getattr(task, "updated_at", None))

        # Description row — only shown when selected
        desc = (task.description or "").strip()
        if self.selected and desc:
            self._desc_label.update(_truncate_text(desc, _DESC_MAX))
            self._desc_label.remove_class("card-desc-empty")
            self._desc_label.display = True
        else:
            self._desc_label.update("")
            self._desc_label.display = False

        # Elapsed — on desc row when selected, appended to status row when unselected
        if self.selected:
            if elapsed:
                self._elapsed_label.update(elapsed)
                self._elapsed_label.display = True
            else:
                self._elapsed_label.update("")
                self._elapsed_label.display = False
        else:
            self._elapsed_label.update("")
            self._elapsed_label.display = False

        # Status line — when unselected, append elapsed inline
        status_text, status_css = self._status_line(task)
        if not self.selected and elapsed:
            status_text = f"{status_text}  {elapsed}"
        self._status_label.update(status_text)
        for cls in _STATUS_CLASSES:
            self._status_label.remove_class(cls)
        for cls in status_css.split():
            self._status_label.add_class(cls)

        # Backend
        self._backend_label.update("")
        self._backend_label.display = False

        # Branch
        self._branch_label.update("")
        self._branch_label.display = False

        # GitHub badges
        self._issue_label.update("")
        self._issue_label.display = False

        self._pr_label.update("")
        self._pr_label.display = False

        # Type badge — only shown when selected
        task_type = str(getattr(getattr(task, "task_type", None), "value", "")).strip()
        if self.selected and task_type:
            self._type_label.update(task_type)
            self._type_label.display = True
        else:
            self._type_label.update("")
            self._type_label.display = False

        # Priority badge — only shown when selected
        priority = _priority_label(task.priority)
        priority_css = self._priority_css(task.priority)
        if self.selected:
            self._priority_label.update(priority)
            for cls in _PRIORITY_CLASSES:
                self._priority_label.remove_class(cls)
            self._priority_label.add_class(priority_css)
            self._priority_label.display = True
        else:
            self._priority_label.update("")
            for cls in _PRIORITY_CLASSES:
                self._priority_label.remove_class(cls)
            self._priority_label.display = False

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
