from collections.abc import Iterable

from textual import on
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widget import Widget
from textual.widgets import Footer, Input, Label, Static, TabbedContent, TabPane

from kagan.tui.keybindings import (
    AGENT_PICKER_BINDINGS,
    APP_BINDINGS,
    CHAT_BINDINGS,
    CHAT_PERMISSION_BINDINGS,
    CONFIRM_BINDINGS,
    DIFF_BINDINGS,
    EDITOR_BINDINGS,
    GITHUB_IMPORT_BINDINGS,
    HELP_BINDINGS,
    KANBAN_BINDINGS,
    MESSAGE_ACTIONS_BINDINGS,
    PERMISSION_BINDINGS,
    REJECTION_BINDINGS,
    REPO_PICKER_BINDINGS,
    REVIEW_NO_CRITERIA_BINDINGS,
    SESSION_DASHBOARD_BINDINGS,
    SESSION_PICKER_BINDINGS,
    SETTINGS_BINDINGS,
    TASK_SCREEN_BINDINGS,
    TMUX_GATEWAY_BINDINGS,
)
from kagan.tui.widgets.diff import (
    DIFF_CONTENT_PANE_BINDINGS,
    DIFF_FILE_TREE_BINDINGS,
    DIFF_VIEW_BINDINGS,
)
from kagan.tui.widgets.streaming import STREAMING_TIMELINE_BINDINGS

HelpRow = tuple[str, str]
HelpSection = tuple[str, tuple[HelpRow, ...]]


class HelpModal(ModalScreen[None]):
    BINDINGS = HELP_BINDINGS

    def __init__(self, context_sections: tuple[HelpSection, ...] | None = None) -> None:
        super().__init__(id="help-modal")
        self._search_query = ""
        self._context_sections = context_sections or ()

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Label("Kagan Help", classes="modal-title")
            yield Input(
                placeholder="Search commands or workflows...",
                id="help-search-input",
            )
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
            *self._context_sections,
            ("Global", tuple(self._rows_from_bindings(APP_BINDINGS))),
            ("Kanban Board", tuple(self._rows_from_bindings(KANBAN_BINDINGS))),
            ("Task Screen", tuple(self._rows_from_bindings(TASK_SCREEN_BINDINGS))),
            ("Session Dashboard", tuple(self._rows_from_bindings(SESSION_DASHBOARD_BINDINGS))),
            ("Chat Panel", tuple(self._rows_from_bindings(CHAT_BINDINGS))),
            ("Diff Viewer", tuple(self._rows_from_bindings(DIFF_BINDINGS))),
            ("Diff File Tree", tuple(self._rows_from_bindings(DIFF_FILE_TREE_BINDINGS))),
            ("Diff Content", tuple(self._rows_from_bindings(DIFF_CONTENT_PANE_BINDINGS))),
            ("Diff Navigation", tuple(self._rows_from_bindings(DIFF_VIEW_BINDINGS))),
            ("Streaming Timeline", tuple(self._rows_from_bindings(STREAMING_TIMELINE_BINDINGS))),
            ("Editors", tuple(self._rows_from_bindings(EDITOR_BINDINGS))),
            ("Settings", tuple(self._rows_from_bindings(SETTINGS_BINDINGS))),
            ("Repo Picker", tuple(self._rows_from_bindings(REPO_PICKER_BINDINGS))),
            ("Session Switcher", tuple(self._rows_from_bindings(SESSION_PICKER_BINDINGS))),
            ("GitHub Import", tuple(self._rows_from_bindings(GITHUB_IMPORT_BINDINGS))),
            ("Agent Picker", tuple(self._rows_from_bindings(AGENT_PICKER_BINDINGS))),
            ("Permission Prompt", tuple(self._rows_from_bindings(PERMISSION_BINDINGS))),
            ("Chat Permission", tuple(self._rows_from_bindings(CHAT_PERMISSION_BINDINGS))),
            ("Message Actions", tuple(self._rows_from_bindings(MESSAGE_ACTIONS_BINDINGS))),
            ("Review (No Criteria)", tuple(self._rows_from_bindings(REVIEW_NO_CRITERIA_BINDINGS))),
            ("Rejection Input", tuple(self._rows_from_bindings(REJECTION_BINDINGS))),
            ("Tmux Gateway", tuple(self._rows_from_bindings(TMUX_GATEWAY_BINDINGS))),
            ("Confirm Modal", tuple(self._rows_from_bindings(CONFIRM_BINDINGS))),
            ("Help Modal", tuple(self._rows_from_bindings(HELP_BINDINGS))),
        )
        return self._render_sections(sections)

    def _rows_from_bindings(self, bindings: list) -> list[HelpRow]:
        rows: list[HelpRow] = []
        seen: set[tuple[str, str]] = set()
        for binding in bindings:
            if not isinstance(binding, Binding) or not binding.description:
                continue
            key = binding.key_display or binding.key
            row = (key, binding.description)
            if row in seen:
                continue
            rows.append(row)
            seen.add(row)
        return rows

    def _compose_flows(self) -> Widget:
        return Vertical(
            Static("Quick Start", classes="help-section-title"),
            Static(
                "From Welcome, create or open a project, then go to the Board to "
                "create tasks and follow the canonical Create -> Start -> Review -> Merge flow.",
                classes="help-paragraph",
            ),
            Static("Creating Tasks", classes="help-section-title"),
            Static(
                "Press 'n' to create a task. Press 's' to start the default managed run. "
                "Use 'a' to attach an interactive run when you need live collaboration.",
                classes="help-paragraph",
            ),
            Static("Kanban Workflow", classes="help-section-title"),
            Static(
                "BACKLOG → IN_PROGRESS: Select a task and press 's' to start the agent. "
                "Use 'a' for an interactive takeover when background execution is not enough.",
                classes="help-paragraph",
            ),
            Static(
                "IN_PROGRESS → REVIEW: The agent submits for review when done. "
                "Open the task (Enter) and use tabs 1/2 (Detail/Diff) to inspect "
                "evidence before deciding.",
                classes="help-paragraph",
            ),
            Static(
                "REVIEW → DONE: In the Review tab, press 'a' to approve, 'm' to merge, "
                "'x' to reject, or 'b' to rebase. If the task has no acceptance criteria, "
                "the guided modal lets you add criteria before merge.",
                classes="help-paragraph",
            ),
            Static("AI Review (Advisory)", classes="help-section-title"),
            Static(
                "Open Quick Actions (Ctrl+Shift+P) and run AI review in the Review stage. "
                "It adds evidence only — it does not approve or merge. "
                "You make the final decision with 'a' (approve) and 'm' (merge).",
                classes="help-paragraph",
            ),
            Static("Using the AI Assistant", classes="help-section-title"),
            Static(
                "Use the key hints shown in your current screen for AI controls: each context "
                "lists overlay/fullscreen/session shortcuts in the footer and in this modal.",
                classes="help-paragraph",
            ),
            Static("Repository Management", classes="help-section-title"),
            Static(
                "Use Ctrl+R to select a repository. "
                "Open Quick Actions (Ctrl+Shift+P) for repo sync and GitHub import.",
                classes="help-paragraph",
            ),
        )

    def _compose_concepts(self) -> Widget:
        return Vertical(
            Static("Projects", classes="help-section-title"),
            Static(
                "A project groups repositories and tasks. Each project has its own kanban board "
                "and settings. Switch projects with Ctrl+O.",
                classes="help-paragraph",
            ),
            Static("Repositories", classes="help-section-title"),
            Static(
                "Repos are git directories. Add multiple repos to a project. "
                "The preferred repo (set via Ctrl+R) is used for new worktrees and patches.",
                classes="help-paragraph",
            ),
            Static("Runs: Managed vs Interactive", classes="help-section-title"),
            Static(
                "Managed run: The default path. Use it for most tasks and reviews.",
                classes="help-paragraph",
            ),
            Static(
                "Interactive run (attach): Secondary path. Launches via a launcher "
                "(tmux, nvim, VS Code, Cursor, etc.) when you want to work alongside the agent.",
                classes="help-paragraph",
            ),
            Static("Chat Sessions", classes="help-section-title"),
            Static(
                "Task session: Context-aware chat tied to the current task. "
                "Orchestrator session: General assistant for planning and questions. "
                "Switch sessions with Ctrl+K. Toggle the AI chat overlay with Ctrl+.",
                classes="help-paragraph",
            ),
            Static("Agent Backends", classes="help-section-title"),
            Static(
                "Configure the default backend in Settings for new tasks. "
                "Change backends from Settings or Quick Actions when needed.",
                classes="help-paragraph",
            ),
            Static("Settings Layers", classes="help-section-title"),
            Static(
                "Settings has typed controls for workflow, review strictness, and planning depth. "
                "Additional Instructions lets you add free-text rules to every agent prompt. "
                "For full prompt replacement, place .kagan/prompts/ files in your repo.",
                classes="help-paragraph",
            ),
            Static("Keyboard Philosophy", classes="help-section-title"),
            Static(
                "Kagan uses vim-style navigation (h/j/k/l) throughout. "
                "Single keys are for common actions, Ctrl+ for advanced, Shift+ for variants. "
                "The footer always shows the most relevant shortcuts for your current context.",
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
