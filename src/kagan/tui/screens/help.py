from collections.abc import Iterable

from textual import on
from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Input, Label, Static, TabbedContent, TabPane

from kagan.tui.keybindings import (
    HELP_BINDINGS,
    KANBAN_BINDINGS,
    SESSION_DASHBOARD_BINDINGS,
    SETTINGS_BINDINGS,
    TASK_SCREEN_BINDINGS,
    WELCOME_BINDINGS,
    get_global_shortcut_help_rows,
    get_help_rows_for_actions,
)

HelpRow = tuple[str, str]
HelpSection = tuple[str, tuple[HelpRow, ...]]


class HelpModal(ModalScreen[None]):
    BINDINGS = HELP_BINDINGS

    def __init__(self) -> None:
        super().__init__(id="help-modal")
        self._search_query = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Label("Kagan Help", classes="modal-title")
            yield Input(placeholder="Search commands or workflows...", id="help-search-input")
            with TabbedContent(id="help-tabs"):
                with TabPane("Shortcuts", id="help-shortcuts-pane"):
                    with VerticalScroll(id="help-shortcuts-scroll"):
                        yield self._compose_shortcuts()
                with TabPane("Flows", id="help-flows-pane"):
                    with VerticalScroll():
                        yield self._compose_flows()
                with TabPane("Concepts", id="help-concepts-pane"):
                    with VerticalScroll():
                        yield self._compose_concepts()
        yield Footer(show_command_palette=False)

    @on(Input.Changed, "#help-search-input")
    async def _on_search_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        if query == self._search_query:
            return
        self._search_query = query
        tabs = self.query_one("#help-tabs", TabbedContent)
        tabs.active = "help-shortcuts-pane"
        scroll = self.query_one("#help-shortcuts-scroll", VerticalScroll)
        await scroll.remove_children()
        await scroll.mount(self._compose_shortcuts())

    def action_focus_search(self) -> None:
        self.query_one("#help-search-input", Input).focus()

    async def action_close(self) -> None:
        self.dismiss(None)

    async def action_dismiss(self, result: None = None) -> None:
        self.dismiss(result)

    def _compose_shortcuts(self) -> Widget:
        sections: tuple[HelpSection, ...] = (
            ("Global", tuple(get_global_shortcut_help_rows())),
            (
                "Welcome",
                tuple(
                    get_help_rows_for_actions(
                        WELCOME_BINDINGS,
                        [
                            ("open_selected", "Open the highlighted project", ("Enter",)),
                            ("new_project", "Create a new project", ("n",)),
                            ("open_folder", "Open or create from a repo path", ("o",)),
                            ("settings", "Open settings", ("s",)),
                            ("move_selection_up", "Move up", ("Up / k",)),
                            ("move_selection_down", "Move down", ("Down / j",)),
                        ],
                    )
                ),
            ),
            (
                "Board",
                tuple(
                    get_help_rows_for_actions(
                        KANBAN_BINDINGS,
                        [
                            ("new_task", "Create a task", ("n",)),
                            ("view_details", "Open the selected task", ("Enter",)),
                            ("open_session", "Open task output or workspace", ("o",)),
                            ("toggle_search", "Filter tasks", ("/",)),
                            ("toggle_peek", "Peek selected task", ("space",)),
                            ("review_task", "Open review flow", ("r",)),
                            ("open_settings", "Open settings", (",",)),
                            ("open_chat_fullscreen", "Fullscreen assistant", ("Ctrl+P",)),
                            ("toggle_chat_overlay", "Cycle assistant view", ("Ctrl+O",)),
                        ],
                    )
                ),
            ),
            (
                "Session Dashboard",
                tuple(
                    get_help_rows_for_actions(
                        SESSION_DASHBOARD_BINDINGS,
                        [
                            ("primary_action", "Start or focus agent", ("Enter",)),
                            ("stop_run", "Stop the running agent", ("s",)),
                            ("restart_run", "Restart the agent", ("r",)),
                            ("open_chat_fullscreen", "Fullscreen assistant", ("Ctrl+P",)),
                            ("toggle_chat_overlay", "Docked assistant", ("Ctrl+O",)),
                            ("open_session_picker", "Session picker", ("Ctrl+K",)),
                            ("cancel_run", "Cancel active run", ("Ctrl+C",)),
                            ("back", "Return to board", ("Esc",)),
                        ],
                    )
                ),
            ),
            (
                "Task Screen",
                tuple(
                    get_help_rows_for_actions(
                        TASK_SCREEN_BINDINGS,
                        [
                            ("primary_action", "Start run or approve merge", ("Enter",)),
                            ("generate_review", "Run AI review", ("g",)),
                            ("reject", "Reject review", ("x",)),
                            ("rebase", "Rebase worktree branch", ("b",)),
                            ("cancel_run", "Stop the active run", ("Ctrl+C",)),
                            ("back", "Return to the board", ("Esc",)),
                        ],
                    )
                ),
            ),
            (
                "Settings",
                tuple(
                    get_help_rows_for_actions(
                        SETTINGS_BINDINGS,
                        [
                            ("save", "Save settings", ("Ctrl+S",)),
                            ("focus_search", "Search settings", ("/",)),
                            ("dismiss", "Close settings", ("Esc",)),
                        ],
                    )
                ),
            ),
        )

        return self._render_sections(sections)

    def _compose_flows(self) -> Widget:
        return Vertical(
            Static("Project Startup", classes="help-section-title"),
            Static(
                "Create a project from Welcome with `n`, or open a repo path with `o`.",
                classes="help-paragraph",
            ),
            Static(
                'Enable "Open last project on launch" in Settings to skip the welcome screen.',
                classes="help-paragraph",
            ),
            Static("Repository Selection", classes="help-section-title"),
            Static(
                "Use `Ctrl+R` on the board to choose the preferred repository for the current "
                "project or add another repo path.",
                classes="help-paragraph",
            ),
            Static("Task Workflow", classes="help-section-title"),
            Static(
                "The board is the control surface: select a task, open its output/workspace with "
                "`o`, or open review with `r` when it reaches REVIEW.",
                classes="help-paragraph",
            ),
            Static("Settings", classes="help-section-title"),
            Static(
                "Settings control default agent backend, PAIR launcher, startup behavior, git "
                "identity, and automation defaults.",
                classes="help-paragraph",
            ),
        )

    def _compose_concepts(self) -> Widget:
        return Vertical(
            Static("Projects", classes="help-section-title"),
            Static(
                "A project groups one or more repositories and provides the scope for the kanban "
                "board.",
                classes="help-paragraph",
            ),
            Static("Repositories", classes="help-section-title"),
            Static(
                "Repository selection is a UI preference used by the TUI surfaces that need a "
                "primary repo context.",
                classes="help-paragraph",
            ),
            Static("AUTO vs PAIR", classes="help-section-title"),
            Static(
                "AUTO runs autonomous agent sessions. PAIR opens a collaborative environment using "
                "your configured launcher.",
                classes="help-paragraph",
            ),
        )

    def _render_sections(self, sections: Iterable[HelpSection]) -> Widget:
        query = self._search_query.casefold()
        widgets: list[Widget] = []
        for title, rows in sections:
            filtered_rows = [
                row
                for row in rows
                if not query
                or query in title.casefold()
                or query in row[0].casefold()
                or query in row[1].casefold()
            ]
            if not filtered_rows:
                continue

            widgets.append(Static(title, classes="help-section-title"))
            for key, description in filtered_rows:
                widgets.append(
                    Horizontal(
                        Static(key, classes="help-key"),
                        Static("│", classes="help-key-separator"),
                        Static(description, classes="help-desc"),
                        classes="help-key-row",
                    )
                )

        if not widgets:
            widgets.append(Static("No shortcuts match your search.", classes="help-paragraph"))
        return Vertical(*widgets)
