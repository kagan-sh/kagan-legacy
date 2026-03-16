from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from kagan.core.enums import TaskStatus
from kagan.core.models import Task


class TaskDetailPane(Widget):
    task_data: reactive[Task | None] = reactive(None)

    DEFAULT_CSS = """
    TaskDetailPane {
        height: 1fr;
        width: 1fr;
    }
    """

    def compose(self) -> ComposeResult:
        with VerticalScroll(id="ts-overview-scroll"):
            yield Static("", id="ts-overview-meta", classes="ts-detail-meta-line")

            with Vertical(id="ts-resume-context-section"):
                yield Static("Resume Context", classes="ts-section-label")
                yield Static(
                    "",
                    id="ts-resume-context",
                    classes="ts-section-body ts-resume-context-body",
                    markup=False,
                )

            yield Static("Description", classes="ts-section-label")
            yield Static("", id="ts-overview-description", classes="ts-section-body", markup=False)

            yield Static("Acceptance Criteria", classes="ts-section-label")
            yield Static("", id="ts-overview-criteria", classes="ts-section-body", markup=False)

            with Horizontal(id="ts-overview-fields"):
                yield Static("", id="ts-overview-base-branch", classes="ts-detail-meta")
                yield Static("", id="ts-overview-agent-backend", classes="ts-detail-meta")

            with Vertical(id="ts-detail-review-section"):
                yield Static("Review", classes="ts-section-label")
                yield Static("", id="ts-merge-readiness", classes="ts-detail-review")

                yield Static("Verify Criteria", classes="ts-section-label")
                yield Vertical(id="ts-detail-criteria-list", classes="ts-detail-criteria-list")
                yield Static(
                    "", id="ts-detail-criteria-status", classes="ts-detail-criteria-status"
                )

                yield Static("", id="ts-detail-stream-source", classes="ts-detail-stream-source")
                yield Static("", id="ts-detail-status", classes="ts-detail-status")
                yield Static(
                    "", id="ts-detail-changes-summary", classes="ts-detail-changes-summary"
                )

    def watch_task_data(self, task: Task | None) -> None:
        self._render_overview(task)

    def _render_overview(self, task: Task | None) -> None:
        if task is None:
            self._render_empty()
            return
        self._render_task(task)

    def _render_empty(self) -> None:
        self.query_one("#ts-overview-meta", Static).update("No task selected")

        desc = self.query_one("#ts-overview-description", Static)
        desc.update("No description provided.")
        desc.add_class("ts-empty")

        criteria_w = self.query_one("#ts-overview-criteria", Static)
        criteria_w.update("No acceptance criteria defined.")
        criteria_w.add_class("ts-empty")

        self.query_one("#ts-overview-base-branch", Static).update("Base branch: repo default")
        self.query_one("#ts-overview-agent-backend", Static).update("Agent: project default")
        self._set_review_section_visible(False)
        self._hide_resume_context()

    def _render_task(self, task: Task) -> None:
        self._hide_resume_context()
        has_description = bool(task.description and task.description.strip())
        description = (task.description or "").strip() or "No description provided."
        desc_w = self.query_one("#ts-overview-description", Static)
        desc_w.update(description)
        desc_w.set_class(not has_description, "ts-empty")

        criteria_items = [item.strip() for item in task.acceptance_criteria if item.strip()]
        criteria_w = self.query_one("#ts-overview-criteria", Static)
        if criteria_items:
            criteria_w.update("\n".join(f"- {item}" for item in criteria_items))
            criteria_w.remove_class("ts-empty")
        else:
            criteria_w.update("No acceptance criteria defined.")
            criteria_w.add_class("ts-empty")

        status_label = task.status.value.replace("_", " ").title()
        if task.review_approved:
            status_label += " | APPROVED"
        meta = " | ".join(
            [
                f"#{task.id[:8]}",
                status_label,
                task.execution_mode.value,
                task.priority.name.title(),
            ]
        )
        self.query_one("#ts-overview-meta", Static).update(meta)

        self.query_one("#ts-overview-base-branch", Static).update(
            f"Base branch: {task.base_branch or 'repo default'}"
        )
        self.query_one("#ts-overview-agent-backend", Static).update(
            f"Agent: {task.agent_backend or 'project default'}"
        )
        has_verdicts = bool(task.review_verdicts)
        self._set_review_section_visible(
            task.status is TaskStatus.REVIEW or (task.status is TaskStatus.DONE and has_verdicts)
        )

    def _set_review_section_visible(self, is_visible: bool) -> None:
        self.query_one("#ts-detail-review-section", Vertical).display = is_visible

    def _hide_resume_context(self) -> None:
        container = self.query_one("#ts-resume-context-section", Vertical)
        container.display = False
        body = self.query_one("#ts-resume-context", Static)
        body.update("")
        body.remove_class("ts-empty")

    def set_resume_context(self, notes: list[str] | None, status: TaskStatus | None) -> None:
        container = self.query_one("#ts-resume-context-section", Vertical)
        body = self.query_one("#ts-resume-context", Static)
        if status not in {TaskStatus.IN_PROGRESS, TaskStatus.REVIEW}:
            container.display = False
            body.update("")
            body.remove_class("ts-empty")
            return
        container.display = True
        cleaned = [note.strip() for note in (notes or []) if note.strip()]
        if not cleaned:
            body.update("(No notes yet)")
            body.add_class("ts-empty")
            return
        combined = "\n\n".join(cleaned)
        trimmed = combined[-500:]
        if len(combined) > 500:
            trimmed = f"…{trimmed}"
        body.update(trimmed)
        body.remove_class("ts-empty")
