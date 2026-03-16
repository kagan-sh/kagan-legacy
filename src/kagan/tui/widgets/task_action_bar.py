from textual.app import ComposeResult
from textual.containers import Horizontal
from textual.reactive import reactive
from textual.widget import Widget
from textual.widgets import Static

from kagan.core.enums import TaskStatus
from kagan.core.models import Task
from kagan.tui.keybindings import TASK_SCREEN_BINDINGS
from kagan.tui.widgets.hint_bar import action_hints_from_bindings, format_hint


class TaskActionBar(Widget):
    active_tab: reactive[str] = reactive("detail")
    task_data: reactive[Task | None] = reactive(None)
    task_running: reactive[bool] = reactive(False)
    has_criteria: reactive[bool] = reactive(False)
    chat_visible: reactive[bool] = reactive(False)
    chat_fullscreen: reactive[bool] = reactive(False)

    DEFAULT_CSS = """
    TaskActionBar {
        height: auto;
        width: 1fr;
        dock: bottom;
    }
    """

    def compose(self) -> ComposeResult:
        with Horizontal():
            yield Static(
                "1-2 tabs  Enter action  Esc back", id="ts-action-hint", classes="ts-action-hint"
            )

    def watch_active_tab(self, _value: str) -> None:
        self._sync_hints()

    def watch_task_data(self, _value: Task | None) -> None:
        self._sync_hints()

    def watch_task_running(self, _value: bool) -> None:
        self._sync_hints()

    def watch_has_criteria(self, _value: bool) -> None:
        self._sync_hints()

    def watch_chat_visible(self, _value: bool) -> None:
        self._sync_hints()

    def watch_chat_fullscreen(self, _value: bool) -> None:
        self._sync_hints()

    def _sync_hints(self) -> None:
        hint = self.query_one("#ts-action-hint", Static)
        active = self.active_tab
        task = self.task_data
        b = TASK_SCREEN_BINDINGS
        tabs_hint: tuple[str, str] = ("1-2", "tabs")
        shared_specs: list[tuple[str | tuple[str, ...], str]] = [
            ("switch_session", "sessions"),
        ]
        if self.chat_visible:
            shared_specs = [
                ("toggle_chat", "split"),
                ("expand_chat_overlay", "fullscreen"),
                ("back", "close"),
                *shared_specs,
            ]
            esc = []
        else:
            shared_specs = [("toggle_chat", "split"), *shared_specs]
            esc = action_hints_from_bindings(b, [("back", "back")])

        if active == "detail":
            self._sync_detail_hints(hint, task, b, tabs_hint, shared_specs, esc)
            return

        if active == "diff":
            nav_hints: list[tuple[str, str]] = [
                tabs_hint,
                ("j/k", "navigate"),
                ("h/l", "tree/diff"),
            ]
            self._update_hint_text(
                hint,
                format_hint(
                    [
                        *nav_hints,
                        *action_hints_from_bindings(b, shared_specs),
                        *esc,
                    ]
                ),
            )
            return

        self._update_hint_text(
            hint,
            format_hint(
                [
                    tabs_hint,
                    *action_hints_from_bindings(b, shared_specs),
                    *esc,
                ]
            ),
        )

    def _sync_detail_hints(
        self,
        hint: Static,
        task: Task | None,
        b: list,
        tabs_hint: tuple[str, str],
        shared_specs: list[tuple[str | tuple[str, ...], str]],
        esc: list[tuple[str, str]],
    ) -> None:
        specs: list[tuple[str | tuple[str, ...], str]]
        hints: list[tuple[str, str]]
        if task is not None and task.status is TaskStatus.REVIEW:
            criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
            if not criteria:
                no_ac: list[tuple[str | tuple[str, ...], str]] = [
                    (("primary_action", "approve"), "approve manually"),
                    ("edit_task", "add criteria"),
                    ("reject", "reject"),
                    ("rebase", "rebase"),
                    ("run_review", "ai review"),
                ]
                hints = [
                    ("!", "no acceptance criteria"),
                    *action_hints_from_bindings(b, no_ac),
                ]
                hints = [
                    tabs_hint,
                    *hints,
                    *action_hints_from_bindings(b, shared_specs),
                    *esc,
                ]
                self._update_hint_text(hint, format_hint(hints))
                return

            if task.review_approved:
                specs = [
                    (("primary_action", "merge"), "merge"),
                    ("reject", "reject+feedback"),
                    ("rebase", "rebase"),
                    ("run_review", "ai review"),
                ]
                hints = [("OK", "approved"), *action_hints_from_bindings(b, specs)]
            else:
                specs = [
                    (("primary_action", "approve"), "approve"),
                    ("reject", "reject+feedback"),
                    ("rebase", "rebase"),
                    ("run_review", "ai review"),
                ]
                hints = [("!", "needs review"), *action_hints_from_bindings(b, specs)]
        else:
            specs = [
                ("edit_task", "edit"),
                ("delete_task", "delete"),
                ("primary_action", "run"),
            ]
            hints = action_hints_from_bindings(b, specs)

        hints = [
            tabs_hint,
            *hints,
            *action_hints_from_bindings(b, shared_specs),
            *esc,
        ]
        self._update_hint_text(hint, format_hint(hints))

    @staticmethod
    def _update_hint_text(hint: Static, value: str) -> None:
        if str(hint.content) == value:
            return
        hint.update(value)
