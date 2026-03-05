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
                            ("open_selected", "Open project", ("Enter",)),
                            ("new_project", "Create project", ("n",)),
                            ("open_folder", "Open folder", ("o",)),
                            ("settings", "Settings", ("s",)),
                            ("move_selection_up", "Move up", ("Up / k",)),
                            ("move_selection_down", "Move down", ("Down / j",)),
                            ("focus_next", "Next field", ("Tab",)),
                            ("focus_previous", "Previous field", ("Shift+Tab",)),
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
                            ("new_task", "Create PAIR task", ("n",)),
                            ("new_auto_task", "Create AUTO task", ("N",)),
                            ("view_details", "Open task details", ("Enter",)),
                            ("open_session", "Open workspace/session", ("o",)),
                            ("start_agent", "Start agent on task", ("a",)),
                            ("stop_agent", "Stop agent", ("s",)),
                            ("toggle_search", "Filter tasks", ("/",)),
                            ("toggle_peek", "Peek task details", ("space",)),
                            ("review_task", "Open review", ("r",)),
                            ("edit_task", "Edit task", ("e",)),
                            ("delete_task_direct", "Delete task", ("x",)),
                            ("duplicate_task", "Duplicate task", ("y",)),
                            ("move_backward", "Move to previous column", ("Shift+H",)),
                            ("move_forward", "Move to next column", ("Shift+L",)),
                            ("focus_up", "Navigate up", ("k",)),
                            ("focus_down", "Navigate down", ("j",)),
                            ("focus_left", "Navigate left", ("h",)),
                            ("focus_right", "Navigate right", ("l",)),
                            ("open_settings", "Settings", (",",)),
                            ("open_chat_fullscreen", "AI assistant fullscreen", ("Ctrl+P",)),
                            ("toggle_chat_overlay", "Toggle AI assistant", ("Ctrl+O",)),
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
                            ("stop_run", "Stop agent", ("s",)),
                            ("restart_run", "Restart agent", ("r",)),
                            ("cycle_chat_session", "Cycle chat session", ("Tab",)),
                            ("open_chat_fullscreen", "AI assistant fullscreen", ("Ctrl+P",)),
                            ("toggle_chat_overlay", "Toggle AI assistant", ("Ctrl+O",)),
                            ("open_session_picker", "Session picker", ("Ctrl+K",)),
                            ("cancel_run", "Stop agent", ("Ctrl+C",)),
                            ("back", "Back to board", ("Esc",)),
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
                            ("switch_tab('overview')", "Overview tab", ("1",)),
                            ("switch_tab('changes')", "Changes tab", ("2",)),
                            ("switch_tab('review')", "Review tab", ("3",)),
                            ("primary_action", "Start run / approve / merge", ("Enter",)),
                            ("edit_task", "Edit task", ("e",)),
                            ("delete_task", "Delete task", ("d",)),
                            ("approve", "Approve review", ("a",)),
                            ("merge", "Merge task", ("m",)),
                            ("reject", "Reject review", ("x",)),
                            ("rebase", "Rebase branch", ("b",)),
                            ("generate_review", "Run AI review", ("g",)),
                            ("cycle_chat_session", "Cycle chat session", ("Tab",)),
                            ("open_session_picker", "Session picker", ("Ctrl+K",)),
                            ("cancel_run", "Stop agent", ("Ctrl+C",)),
                            ("back", "Back to board", ("Esc",)),
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
            Static("Quick Start", classes="help-section-title"),
            Static(
                "Create a project (n) or open a folder (o) from Welcome. "
                "Enable 'Open last project on launch' in Settings to skip Welcome.",
                classes="help-paragraph",
            ),
            Static("Kanban Workflow", classes="help-section-title"),
            Static(
                "BACKLOG → IN_PROGRESS: Select task, press Enter or 'a' to start agent. "
                "Use Shift+H/L to move tasks between columns.",
                classes="help-paragraph",
            ),
            Static(
                "IN_PROGRESS → REVIEW: Agent submits for review. Press 'r' to open review UI.",
                classes="help-paragraph",
            ),
            Static(
                "REVIEW → DONE: Press 'a' to approve, 'm' to merge. "
                "Press 'x' to reject or 'b' to rebase.",
                classes="help-paragraph",
            ),
            Static("AI Assistant Chat", classes="help-section-title"),
            Static(
                "Ctrl+O toggles overlay (horizontal/vertical/hidden). "
                "Ctrl+P opens fullscreen. Ctrl+K switches session. "
                "Tab cycles between Task and Orchestrator sessions.",
                classes="help-paragraph",
            ),
            Static("Repository Management", classes="help-section-title"),
            Static(
                "Ctrl+R opens repo selector. Each project can have multiple repos. "
                "The preferred repo is used for new worktrees.",
                classes="help-paragraph",
            ),
            Static("Task Creation", classes="help-section-title"),
            Static(
                "'n' creates PAIR task (interactive). 'N' (Shift+N) creates AUTO task (autonomous)."
                " Set default mode in Settings.",
                classes="help-paragraph",
            ),
        )

    def _compose_concepts(self) -> Widget:
        return Vertical(
            Static("Projects", classes="help-section-title"),
            Static(
                "A project groups repositories and tasks. Each project has its own kanban board "
                "and settings. Switch projects with Ctrl+Shift+O.",
                classes="help-paragraph",
            ),
            Static("Repositories", classes="help-section-title"),
            Static(
                "Repos are git directories. Add multiple repos to a project. "
                "The preferred repo (Ctrl+R) is used for new worktrees and patches.",
                classes="help-paragraph",
            ),
            Static("AUTO vs PAIR Mode", classes="help-section-title"),
            Static(
                "AUTO: Agent works autonomously to completion. Best for well-defined tasks. "
                "Runs in background without user interaction.",
                classes="help-paragraph",
            ),
            Static(
                "PAIR: Agent works interactively with you in a terminal (tmux, Cursor, etc.). "
                "Best for exploration and complex debugging.",
                classes="help-paragraph",
            ),
            Static("Chat Sessions", classes="help-section-title"),
            Static(
                "Task session: Context-aware chat tied to the current task. "
                "Orchestrator session: General assistant for planning and questions. "
                "Switch with Tab or Ctrl+K.",
                classes="help-paragraph",
            ),
            Static("Agent Backends", classes="help-section-title"),
            Static(
                "Configure default backend in Settings (claude-code, codex, gemini-cli, etc.). "
                "Switch backends mid-session with /agent command or Ctrl+A.",
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
