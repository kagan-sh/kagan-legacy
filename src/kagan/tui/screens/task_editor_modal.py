from typing import TYPE_CHECKING, cast

from loguru import logger
from textual.app import ComposeResult
from textual.containers import Container
from textual.screen import ModalScreen
from textual.widgets import Static

from kagan.cli.chat import list_registered_agent_backends
from kagan.core.models import Task

if TYPE_CHECKING:
    from textual.timer import Timer

    from kagan.tui.app import KaganApp
from kagan.tui.keybindings import TASK_EDITOR_BINDINGS
from kagan.tui.messages import TaskSubmitted
from kagan.tui.widgets.task_editor import TaskEditor


class TaskEditorModal(ModalScreen[None]):
    BINDINGS = TASK_EDITOR_BINDINGS

    DEFAULT_CSS = """
    TaskEditorModal {
        align: center middle;
    }
    """

    def __init__(
        self,
        *,
        task: Task | None = None,
        focus_field: str | None = None,
    ) -> None:
        super().__init__(id="task-editor-modal")
        self._editing_task = task
        self._focus_field = focus_field
        self._auto_save_timer: Timer | None = None

    @property
    def kagan_app(self) -> "KaganApp":
        return cast("KaganApp", self.app)

    def compose(self) -> ComposeResult:
        editing_task = self._editing_task
        is_editing = editing_task is not None
        agent_backends = list_registered_agent_backends()
        project_id = self.kagan_app.project.id if self.kagan_app.project is not None else None
        client = self.kagan_app.core
        with Container(id="task-editor-container"):
            if editing_task is None:
                yield TaskEditor(
                    available_agent_backends=agent_backends,
                    focus_field=self._focus_field,
                    client=client,
                    project_id=project_id,
                )
            else:
                yield TaskEditor(
                    title=editing_task.title,
                    description=editing_task.description,
                    priority=editing_task.priority,
                    agent_backend=editing_task.agent_backend,
                    launcher=editing_task.launcher,
                    available_agent_backends=agent_backends,
                    base_branch=editing_task.base_branch,
                    acceptance_criteria=list(editing_task.acceptance_criteria),
                    github_issue=editing_task.github_issue,
                    focus_field=self._focus_field,
                    editing=True,
                    client=client,
                    project_id=project_id,
                )
            if is_editing:
                yield Static(
                    "Auto-saved  ·  [bold]Esc[/] close  [bold]Ctrl+.[/] advanced",
                    classes="modal-action-hint",
                )
            else:
                yield Static(
                    "[bold]Ctrl+S[/] create  [bold]Esc[/] cancel  [bold]Ctrl+.[/] advanced",
                    classes="modal-action-hint",
                )

    async def on_task_submitted(self, message: TaskSubmitted) -> None:
        editor = self.query_one(TaskEditor)
        acceptance_criteria = editor.acceptance_criteria()
        try:
            if self._editing_task is None:
                await self.kagan_app.core.tasks.create(
                    message.title,
                    description=message.description,
                    priority=message.priority,
                    base_branch=message.base_branch,
                    agent_backend=message.agent_backend,
                    launcher=message.launcher,
                    acceptance_criteria=acceptance_criteria,
                    github_issue=message.github_issue,
                )
            else:
                await self.kagan_app.core.tasks.update(
                    self._editing_task.id,
                    title=message.title,
                    description=message.description,
                    priority=message.priority,
                    base_branch=message.base_branch,
                    agent_backend=message.agent_backend,
                    launcher=message.launcher,
                    acceptance_criteria=acceptance_criteria,
                )
        except Exception as exc:  # quality-allow-broad-except
            self.kagan_app.notify(f"Unable to save task: {exc}", severity="error")
            return

        self.dismiss(None)

    def on_task_editor_cancelled(self, _: TaskEditor.Cancelled) -> None:
        self.dismiss(None)

    def on_task_editor_field_changed(self, _: TaskEditor.FieldChanged) -> None:
        if self._editing_task is None:
            return
        self._schedule_auto_save()

    def _schedule_auto_save(self) -> None:
        if self._auto_save_timer is not None:
            self._auto_save_timer.stop()
        self._auto_save_timer = self.set_timer(0.4, self._fire_auto_save)

    def _fire_auto_save(self) -> None:
        self._auto_save_timer = None
        self.run_worker(self._auto_save_task(), exit_on_error=False)

    async def _auto_save_task(self) -> None:
        if self._editing_task is None:
            return
        editor = self.query_one(TaskEditor)
        values = editor.collect_values()
        if values is None:
            return
        acceptance_criteria = editor.acceptance_criteria()
        try:  # quality-allow-broad-except
            await self.kagan_app.core.tasks.update(
                self._editing_task.id,
                title=values.title,
                description=values.description,
                priority=values.priority,
                base_branch=values.base_branch,
                agent_backend=values.agent_backend,
                launcher=values.launcher,
                acceptance_criteria=acceptance_criteria,
            )
        except Exception as exc:
            logger.debug("Auto-save failed for task {}: {}", self._editing_task.id, exc)

    def action_finish(self) -> None:
        self.query_one(TaskEditor).submit()

    def action_toggle_advanced(self) -> None:
        self.query_one(TaskEditor).action_toggle_advanced()

    def action_scroll_down(self) -> None:
        self.query_one(TaskEditor).scroll_form(3)

    def action_scroll_up(self) -> None:
        self.query_one(TaskEditor).scroll_form(-3)

    def action_cancel(self) -> None:
        self.dismiss(None)

    async def action_dismiss(self, result: None = None) -> None:
        self.dismiss(result)
