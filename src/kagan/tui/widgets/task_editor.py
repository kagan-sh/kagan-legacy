from dataclasses import dataclass
from typing import cast

from textual import events
from textual.app import ComposeResult
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.widgets import Checkbox, Input, Label, Select, Static, TextArea

from kagan.core.enums import Priority
from kagan.tui.messages import TaskSubmitted

_PRIORITY_OPTIONS: list[tuple[str, int]] = [
    ("Low", int(Priority.LOW)),
    ("Medium", int(Priority.MEDIUM)),
    ("High", int(Priority.HIGH)),
    ("Critical", int(Priority.CRITICAL)),
]

_LAUNCHER_OPTIONS: list[tuple[str, str]] = [
    ("tmux", "tmux"),
    ("nvim", "nvim"),
    ("vscode", "vscode"),
    ("cursor", "cursor"),
    ("windsurf", "windsurf"),
    ("kiro", "kiro"),
    ("antigravity", "antigravity"),
]


class TaskEditor(Vertical):
    DEFAULT_CSS = """
    TaskEditor {
        layout: vertical;
        height: 1fr;
        min-height: 0;
        width: 100%;
    }

    TaskEditor .task-form {
        width: 100%;
        height: 1fr;
        min-height: 0;
    }

    TaskEditor .task-editor-actions {
        width: 100%;
        height: auto;
        layout: horizontal;
    }
    """

    @dataclass
    class Cancelled(Message):
        pass

    @dataclass
    class FieldChanged(Message):
        pass

    def __init__(
        self,
        *,
        title: str = "",
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        agent_backend: str | None = None,
        launcher: str | None = None,
        available_agent_backends: list[str] | None = None,
        base_branch: str | None = None,
        acceptance_criteria: list[str] | None = None,
        focus_field: str | None = None,
        editing: bool = False,
    ) -> None:
        super().__init__()
        self._initial_title = title
        self._initial_description = description
        self._initial_priority = priority
        self._initial_agent_backend = agent_backend or ""
        self._initial_launcher = launcher or ""
        self._editing = editing
        backend_set = set(available_agent_backends or [])
        if self._initial_agent_backend:
            backend_set.add(self._initial_agent_backend)
        self._available_agent_backends = sorted(backend_set)
        self._launcher_options = [("Use project default", ""), *_LAUNCHER_OPTIONS]
        available_launchers = {value for _, value in self._launcher_options}
        if self._initial_launcher and self._initial_launcher not in available_launchers:
            self._launcher_options.append((self._initial_launcher, self._initial_launcher))
        self._initial_base_branch = base_branch or ""
        self._initial_acceptance_criteria = "\n".join(acceptance_criteria or [])
        self._focus_field = focus_field
        self._show_advanced = bool(
            self._initial_agent_backend
            or self._initial_launcher
            or self._initial_base_branch
            or self._initial_acceptance_criteria
        )

    def compose(self) -> ComposeResult:
        with VerticalScroll(classes="task-form"):
            yield Label("Quick Setup", classes="task-section-label")
            yield Label("Title", classes="task-label")
            title_input = Input(value=self._initial_title, id="task-title", classes="task-input")
            title_input.tooltip = "Task title (required, max 200 characters)"
            yield title_input
            yield Static("", id="task-title-error", classes="task-field-error")
            show_advanced_checkbox = Checkbox(
                "Show advanced options",
                value=self._show_advanced,
                id="task-show-advanced",
                classes="task-checkbox",
            )
            show_advanced_checkbox.tooltip = "Toggle advanced options (Ctrl+.)"
            yield show_advanced_checkbox
            yield Label("Description", classes="task-label")
            description_area = TextArea(
                self._initial_description,
                id="task-description",
                classes="task-textarea",
            )
            description_area.tooltip = "Task description and context"
            yield description_area
            yield Label("Priority", classes="task-label")
            priority_select = Select[int](
                options=_PRIORITY_OPTIONS,
                value=int(self._initial_priority),
                id="task-priority",
                allow_blank=False,
                classes="task-select",
            )
            priority_select.tooltip = "Priority level: Low, Medium, High, or Critical"
            yield priority_select
            with Vertical(id="task-advanced-fields", classes="task-advanced-fields"):
                yield Label("Acceptance Criteria", classes="task-label")
                criteria_area = TextArea(
                    self._initial_acceptance_criteria,
                    id="task-acceptance-criteria",
                    classes="task-textarea",
                )
                criteria_area.tooltip = "List of acceptance criteria (one per line)"
                yield criteria_area
                yield Label("Agent backend", classes="task-label")
                backend_select = Select[str](
                    options=[
                        ("Use project default", ""),
                        *((name, name) for name in self._available_agent_backends),
                    ],
                    value=self._initial_agent_backend,
                    id="task-agent-backend",
                    allow_blank=False,
                    classes="task-select",
                )
                backend_select.tooltip = "AI agent backend for task execution"
                yield backend_select
                yield Label("Interactive launcher", classes="task-label")
                launcher_select = Select[str](
                    options=self._launcher_options,
                    value=self._initial_launcher,
                    id="task-launcher",
                    allow_blank=False,
                    classes="task-select",
                )
                launcher_select.tooltip = "Interactive editor for manual task execution"
                yield launcher_select
                yield Label("Base branch", classes="task-label")
                branch_input = Input(
                    value=self._initial_base_branch,
                    placeholder="main",
                    id="task-base-branch",
                    classes="task-input",
                )
                branch_input.tooltip = "Git branch to base task on (default: project default)"
                yield branch_input
        if self._editing:
            yield Static(
                "Auto-saved  ·  [bold]Ctrl+.[/] advanced  "
                "[bold]PgUp/PgDn[/] scroll  [bold]Esc[/] close",
                classes="modal-action-hint",
            )
        else:
            yield Static(
                "[bold]Ctrl+S[/] create  [bold]Ctrl+.[/] advanced  "
                "[bold]PgUp/PgDn[/] scroll  [bold]Esc[/] cancel",
                classes="modal-action-hint",
            )

    def on_mount(self) -> None:
        self._sync_advanced_visibility()
        self.focus_preferred_field()
        self.call_after_refresh(self._restore_initial_title)
        self._set_title_error(None)

    def _restore_initial_title(self) -> None:
        self.query_one("#task-title", Input).value = self._initial_title

    def _sync_advanced_visibility(self) -> None:
        advanced = self.query_one("#task-advanced-fields", Vertical)
        advanced.set_class(not self._show_advanced, "hidden")
        advanced.refresh(layout=True)
        self.query_one(".task-form", VerticalScroll).refresh(layout=True)
        self.refresh(layout=True)

    def _reveal_advanced_fields(self) -> None:
        form = self.query_one(".task-form", VerticalScroll)
        form.scroll_end(animate=False)
        criteria = self.query_one("#task-acceptance-criteria", TextArea)
        criteria.focus()
        criteria.scroll_visible(top=True, animate=False)

    def _set_title_error(self, message: str | None) -> None:
        error = self.query_one("#task-title-error", Static)
        error.update(message or "")
        error.display = bool(message)

    def _validate_title(self) -> str | None:
        title = self.query_one("#task-title", Input).value.strip()
        if title:
            return None
        return "Title is required."

    _ADVANCED_FIELD_IDS = {
        "task-acceptance-criteria",
        "task-agent-backend",
        "task-launcher",
        "task-base-branch",
    }

    def focus_preferred_field(self) -> None:
        field_id = self._focus_field or "task-title"
        if not self._show_advanced and field_id in self._ADVANCED_FIELD_IDS:
            self._show_advanced = True
            checkbox = self.query_one("#task-show-advanced", Checkbox)
            if checkbox.value != self._show_advanced:
                checkbox.value = self._show_advanced
            self._sync_advanced_visibility()
        field = self.query_one(f"#{field_id}")
        if isinstance(field, Input | TextArea | Select):
            field.focus()

    def acceptance_criteria(self) -> list[str]:
        criteria_field = self.query_one("#task-acceptance-criteria", TextArea)
        return [line.strip() for line in criteria_field.text.splitlines() if line.strip()]

    def action_toggle_advanced(self) -> None:
        self._show_advanced = not self._show_advanced
        checkbox = self.query_one("#task-show-advanced", Checkbox)
        if checkbox.value != self._show_advanced:
            checkbox.value = self._show_advanced
        self._sync_advanced_visibility()
        if self._show_advanced:
            self.call_after_refresh(self._reveal_advanced_fields)

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        if event.checkbox.id != "task-show-advanced":
            return
        self._show_advanced = event.value
        self._sync_advanced_visibility()
        if self._show_advanced:
            self.call_after_refresh(self._reveal_advanced_fields)

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "task-title":
            self._set_title_error(self._validate_title())
        if self._editing:
            self.post_message(self.FieldChanged())

    def on_select_changed(self, _: Select.Changed) -> None:
        if self._editing:
            self.post_message(self.FieldChanged())

    def on_text_area_changed(self, _: TextArea.Changed) -> None:
        if self._editing:
            self.post_message(self.FieldChanged())

    def scroll_form(self, delta_y: int) -> None:
        form = self.query_one(".task-form", VerticalScroll)
        form.scroll_relative(y=delta_y, animate=False)

    def on_mouse_scroll_down(self, event: events.MouseScrollDown) -> None:
        self.scroll_form(3)
        event.stop()

    def on_mouse_scroll_up(self, event: events.MouseScrollUp) -> None:
        self.scroll_form(-3)
        event.stop()

    def collect_values(self) -> TaskSubmitted | None:
        title = self.query_one("#task-title", Input).value.strip()
        if not title:
            return None

        description = self.query_one("#task-description", TextArea).text
        priority_select = cast("Select[int]", self.query_one("#task-priority", Select))
        backend_select = cast("Select[str]", self.query_one("#task-agent-backend", Select))
        launcher_select = cast("Select[str]", self.query_one("#task-launcher", Select))
        base_branch = self.query_one("#task-base-branch", Input).value.strip() or None

        priority_value = priority_select.value
        if priority_value is Select.BLANK or not isinstance(priority_value, int):
            priority = self._initial_priority
        else:
            priority = Priority(priority_value)

        backend_value = backend_select.value
        if backend_value is Select.BLANK or not isinstance(backend_value, str):
            agent_backend = None
        else:
            agent_backend = backend_value.strip() or None

        launcher_value = launcher_select.value
        if launcher_value is Select.BLANK or not isinstance(launcher_value, str):
            launcher = None
        else:
            launcher = launcher_value.strip() or None

        return TaskSubmitted(
            title=title,
            description=description,
            priority=priority,
            agent_backend=agent_backend,
            launcher=launcher,
            base_branch=base_branch,
        )

    def submit(self) -> None:
        values = self.collect_values()
        if values is None:
            self._set_title_error("Title is required.")
            self.app.notify("Task title is required.", severity="warning")
            self.query_one("#task-title", Input).focus()
            return
        self._set_title_error(None)
        self.post_message(values)

    def cancel(self) -> None:
        self.post_message(self.Cancelled())
