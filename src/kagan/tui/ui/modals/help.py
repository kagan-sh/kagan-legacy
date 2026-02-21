"""Help modal with keybindings reference and usage guide."""

from __future__ import annotations

import contextlib
import re
from typing import TYPE_CHECKING

from rich.text import Text
from textual import on
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.screen import ModalScreen
from textual.widgets import Footer, Input, Label, Rule, Static, TabbedContent, TabPane

from kagan.core.limits import DEBUG_BUILD
from kagan.tui.keybindings import HELP_BINDINGS

if TYPE_CHECKING:
    from textual.app import ComposeResult
    from textual.widget import Widget
type KeybindingRow = tuple[str, str]
type KeybindingGroup = tuple[str | None, list[KeybindingRow]]
type KeybindingSection = tuple[str, list[KeybindingGroup]]


class HelpModal(ModalScreen[None]):
    """Full help system modal with keybindings, concepts, and workflows."""

    BINDINGS = HELP_BINDINGS
    _MODIFIER_TOKEN_PATTERN = re.compile(r"\b(?:Ctrl|Shift|Alt|Esc|F\d+)\b", re.IGNORECASE)

    def __init__(self) -> None:
        super().__init__()
        self._search_query = ""

    def compose(self) -> ComposeResult:
        with Vertical(id="help-container"):
            yield Label("Kagan Help", classes="modal-title")
            yield Input(placeholder="Search commands or bindings...", id="help-search-input")
            with TabbedContent(id="help-tabs"):
                with TabPane("Keybindings", id="tab-keys"):
                    with VerticalScroll(id="help-keybindings-scroll"):
                        yield self._compose_keybindings()
                with TabPane("Navigation", id="tab-nav"):
                    yield VerticalScroll(self._compose_navigation())
                with TabPane("Concepts", id="tab-concepts"):
                    yield VerticalScroll(self._compose_concepts())
                with TabPane("Workflows", id="tab-workflows"):
                    yield VerticalScroll(self._compose_workflows())
        yield Footer(show_command_palette=False)

    @on(Input.Changed, "#help-search-input")
    async def on_help_search_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        if query == self._search_query:
            return
        self._search_query = query
        if query:
            self._focus_keybindings_tab()
        await self._refresh_keybindings_content()

    async def _refresh_keybindings_content(self) -> None:
        with contextlib.suppress(Exception):
            scroll = self.query_one("#help-keybindings-scroll", VerticalScroll)
            await scroll.remove_children()
            await scroll.mount(self._compose_keybindings(self._search_query))

    def _focus_keybindings_tab(self) -> None:
        with contextlib.suppress(Exception):
            tabs = self.query_one("#help-tabs", TabbedContent)
            tabs.active = "tab-keys"

    def action_focus_search(self) -> None:
        with contextlib.suppress(Exception):
            self.query_one("#help-search-input", Input).focus()

    def _keybinding_sections(self) -> list[KeybindingSection]:
        global_keys: list[KeybindingRow] = [
            ("? / F1", "Help"),
            (". / Ctrl+Shift+P", "Actions palette"),
            ("Ctrl+Shift+O", "Project selector"),
            ("Ctrl+R", "Repo selector"),
        ]
        if DEBUG_BUILD:
            global_keys.append(("F12", "Debug log"))
        global_keys.append(("Ctrl+Q", "Quit"))

        modal_groups: list[KeybindingGroup] = [
            ("Help", [("Esc / q", "Close"), ("Ctrl+F", "Focus search")]),
            ("Confirm", [("Enter", "Confirm"), ("y", "Yes"), ("n", "No"), ("Esc", "Cancel")]),
            (
                "Task Details",
                [
                    ("e", "Toggle edit"),
                    ("d", "Delete"),
                    ("f", "Expand description"),
                    ("F5", "Full editor"),
                    ("Ctrl+S / Alt+S", "Save (edit mode)"),
                    ("y", "Copy"),
                    ("Esc", "Close/Cancel"),
                ],
            ),
            ("Task Editor", [("Ctrl+S / Alt+S", "Finish editing"), ("Esc", "Cancel")]),
            ("Description Editor", [("Ctrl+S / Alt+S", "Save"), ("Esc", "Cancel")]),
            ("Settings", [("Ctrl+S / Alt+S", "Save"), ("Esc", "Cancel")]),
            ("Duplicate Task", [("Enter", "Create"), ("Esc", "Cancel")]),
            ("Diff", [("Enter", "Approve"), ("r", "Reject"), ("y", "Copy"), ("Esc", "Close")]),
            (
                "Task Output",
                [
                    ("Enter", "Approve"),
                    ("r", "Reject"),
                    ("g", "Run review"),
                    ("y", "Copy"),
                    ("Esc", "Close/Cancel"),
                ],
            ),
            ("Rejection Input", [("Enter", "Back to In Progress"), ("Esc", "Backlog")]),
            (
                "Agent/Review Chat Input",
                [("Enter", "Send message"), ("Shift+Enter / Ctrl+J", "New line")],
            ),
            ("Tmux Gateway", [("Enter", "Continue"), ("Esc", "Cancel"), ("s", "Don't show again")]),
            ("Base Branch", [("Enter", "Submit"), ("Esc", "Cancel")]),
            (
                "Permission Prompt",
                [("y / Enter", "Allow once"), ("a", "Allow always"), ("n / d / Esc", "Deny")],
            ),
            (
                "No Dedicated Hotkeys",
                [
                    ("Merge Dialog", "Use buttons and checkboxes"),
                    ("New Project", "Use inputs and buttons"),
                    ("Folder Picker", "Use input/tree and buttons"),
                ],
            ),
        ]
        if DEBUG_BUILD:
            modal_groups.insert(
                11,
                ("Debug Log", [("c", "Clear logs"), ("s", "Save logs"), ("Esc", "Close")]),
            )

        return [
            ("◈ Global", [(None, global_keys)]),
            (
                "▤ Board (Kanban)",
                [
                    (
                        "Navigation",
                        [
                            ("h / Left", "Focus left column"),
                            ("l / Right", "Focus right column"),
                            ("j / Down", "Focus next card"),
                            ("k / Up", "Focus previous card"),
                            ("Tab", "Next card (wraps across columns)"),
                            ("Shift+Tab", "Previous card (wraps across columns)"),
                            ("Esc", "Clear focus → close overlay/search → back to projects"),
                        ],
                    ),
                    (
                        "Tasks",
                        [
                            ("n", "New task"),
                            ("Shift+N", "New AUTO task"),
                            ("Enter", "View task details"),
                            ("o", "Open task workspace/output"),
                            ("/", "Search/filter tasks"),
                            ("v", "View details (alternate)"),
                            ("e", "Edit task"),
                            ("x", "Delete task"),
                            ("y", "Duplicate task"),
                            ("c", "Copy task ID"),
                            ("space", "Peek overlay"),
                            ("f", "Expand description"),
                            ("F5", "Full editor"),
                        ],
                    ),
                    (
                        "Workflow",
                        [
                            ("Shift+Left / Shift+H", "Move task left"),
                            ("Shift+Right / Shift+L", "Move task right"),
                            ("Ctrl+P", "Toggle fullscreen AI Assistant"),
                            ("Ctrl+O", "Toggle docked AI Assistant"),
                            ("a", "Start agent (AUTO)"),
                            ("s", "Stop agent (AUTO)"),
                            ("Shift+D", "View diff (REVIEW)"),
                            ("r", "Task Output (REVIEW)"),
                            ("m", "Merge (REVIEW)"),
                            ("b", "Set task branch"),
                            (",", "Settings"),
                        ],
                    ),
                ],
            ),
            (
                "✦ AI Assistant Overlay",
                [
                    (
                        "Screen",
                        [
                            ("Esc", "Interrupt stream; close overlay when idle"),
                            ("Ctrl+P", "Toggle fullscreen (switches from docked)"),
                            ("Ctrl+O", "Toggle docked (switches from fullscreen)"),
                            (
                                "Tab",
                                "Cycle active scoped sessions (opens picker when single target)",
                            ),
                            ("Ctrl+K", "Open session quick-pick"),
                        ],
                    ),
                    (
                        "Input",
                        [
                            ("/", "Open slash command popup"),
                            ("Enter", "Send message / run highlighted slash command"),
                            ("Shift+Enter / Ctrl+J", "New line"),
                            ("Ctrl+C", "Clear chat input"),
                            ("/clear", "Clear conversation"),
                            ("/help", "Show commands"),
                            ("/export", "Copy active session transcript to clipboard"),
                            ("/compact", "Compact context (native preferred, snapshot fallback)"),
                            ("/mode", "List agent modes"),
                            ("/mode <id>", "Switch AI Assistant mode"),
                            ("/sessions", "Open session quick-pick"),
                            ("/agent <command>", "Run grouped agent command"),
                        ],
                    ),
                    (
                        "Slash Complete",
                        [
                            ("Up / Down", "Navigate commands"),
                            ("Enter", "Run highlighted command"),
                            ("Esc", "Dismiss popup (overlay stays open)"),
                        ],
                    ),
                    (
                        "Plan Approval",
                        [
                            ("Up / Down or j / k", "Move selection"),
                            ("Enter", "Preview task"),
                            ("a", "Approve"),
                            ("e", "Edit"),
                            ("d / Esc", "Dismiss"),
                        ],
                    ),
                ],
            ),
            (
                "⌂ Welcome & Onboarding",
                [
                    (
                        "Welcome Screen",
                        [
                            ("Up / Down or j / k", "Move project selection"),
                            ("Tab / Shift+Tab", "Move focus to next/previous control"),
                            ("Enter", "Open selected project"),
                            ("n", "New project"),
                            ("o", "Open folder"),
                            ("s", "Settings"),
                            (
                                "Ctrl+P / Ctrl+O",
                                "After opening a board: fullscreen/docked AI Assistant",
                            ),
                            ("1-9", "Open project by number"),
                            ("Esc", "Back to board (if open) / Quit (with confirm)"),
                        ],
                    ),
                    (
                        "Onboarding",
                        [
                            ("Tab / Shift+Tab", "Move focus between setup controls"),
                            ("Enter / Ctrl+S", "Save setup and continue"),
                            ("Esc", "Quit"),
                        ],
                    ),
                ],
            ),
            (
                "⌁ Repo Picker",
                [
                    (
                        None,
                        [
                            ("Up / Down or j / k", "Navigate repos"),
                            ("Enter", "Select repo"),
                            ("n", "Add repo"),
                            ("Esc", "Cancel"),
                        ],
                    )
                ],
            ),
            ("☰ Modals", modal_groups),
        ]

    @staticmethod
    def _matches_keybinding(query: str, *, key: str, description: str) -> bool:
        if not query:
            return True
        normalized = query.casefold()
        return normalized in key.casefold() or normalized in description.casefold()

    def _compose_keybindings(self, query: str = "") -> Vertical:
        """Compose the keybindings reference section."""
        children: list[Widget] = []
        for section_title, groups in self._keybinding_sections():
            section_children: list[Widget] = []
            for subgroup_title, rows in groups:
                visible_rows = [
                    (key, description)
                    for key, description in rows
                    if self._matches_keybinding(query, key=key, description=description)
                ]
                if not visible_rows:
                    continue
                if subgroup_title is not None:
                    section_children.append(Static(subgroup_title, classes="help-subsection"))
                for key, description in visible_rows:
                    section_children.append(self._key_row(key, description))
            if not section_children:
                continue
            if children:
                children.append(Rule())
            children.append(Static(section_title, classes="help-section-title"))
            children.extend(section_children)

        if not children:
            children.append(
                Static(
                    "No keybindings match your search.",
                    classes="help-paragraph",
                )
            )

        return Vertical(*children, id="keybindings-content")

    def _compose_navigation(self) -> Vertical:
        """Compose the navigation guide section."""
        return Vertical(
            Static("Vim-Style Navigation", classes="help-section-title"),
            Static(
                "Kagan uses vim-inspired navigation for efficiency. "
                "Arrow keys always work as alternatives.",
                classes="help-paragraph",
            ),
            Static(""),
            Static("Movement Keys:", classes="help-subsection"),
            Static("  h / Left   - Move left between columns", classes="help-code"),
            Static("  j / Down   - Move down within a column", classes="help-code"),
            Static("  k / Up     - Move up within a column", classes="help-code"),
            Static("  l / Right  - Move right between columns", classes="help-code"),
            Static(""),
            Rule(),
            Static("Actions Palette", classes="help-section-title"),
            Static(
                "Press '.' (or Ctrl+Shift+P) to open the Actions palette. "
                "It lists commands for the current screen and task context, "
                "including popup actions.",
                classes="help-paragraph",
            ),
            Static(""),
            Static("Palette Tips:", classes="help-subsection"),
            Static("  Type to filter commands", classes="help-code"),
            Static("  Enter to run selected action", classes="help-code"),
            Static("  Esc closes the palette", classes="help-code"),
            Static(""),
            Rule(),
            Static("Modes At A Glance", classes="help-section-title"),
            Static(
                "Look at the board footer/header mode label to confirm where input goes:",
                classes="help-paragraph",
            ),
            Static(
                "  Board                 - Kanban navigation and task actions",
                classes="help-code",
            ),
            Static("  Search                - Task filtering input is active", classes="help-code"),
            Static(
                "  Assistant (Docked/Fullscreen) - Chat input captures keys/messages",
                classes="help-code",
            ),
            Static(""),
            Rule(),
            Static("Focus & Selection", classes="help-section-title"),
            Static(
                "Only task cards can receive focus. The focused card is highlighted "
                "with a colored border. Click a card to focus it, then press Enter "
                "to open details.",
                classes="help-paragraph",
            ),
            id="navigation-content",
        )

    def _compose_concepts(self) -> Vertical:
        """Compose the concepts guide section."""
        return Vertical(
            Static("Task Types", classes="help-section-title"),
            Static(""),
            Static("PAIR (Human-in-the-loop):", classes="help-subsection"),
            Static(
                "  Opens an interactive session (tmux/Neovim/IDE) where you work alongside "
                "an AI agent. "
                "You control the pace and can intervene at any time. "
                "Best for complex tasks where you want to stay in control.",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Static("AUTO (Autonomous Agent):", classes="help-subsection"),
            Static(
                "  Agent works independently with minimal supervision. "
                "You can watch progress or let it run in the background. "
                "Best for well-defined, routine tasks.",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Rule(),
            Static("Workflow Columns", classes="help-section-title"),
            Static(""),
            Static("BACKLOG", classes="help-subsection"),
            Static("  Tasks waiting to be started.", classes="help-paragraph-indented"),
            Static(""),
            Static("IN PROGRESS", classes="help-subsection"),
            Static(
                "  Active work. PAIR tasks run in your selected terminal backend; "
                "AUTO tasks have agents running.",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Static("REVIEW", classes="help-subsection"),
            Static(
                "  Work complete, pending review. View diff, run AI review, "
                "then approve or reject.",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Static("DONE", classes="help-subsection"),
            Static(
                "  Merged and completed. Worktrees are cleaned up.",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Rule(),
            Static("Visual Indicators", classes="help-section-title"),
            Static(""),
            Static("Card Borders:", classes="help-subsection"),
            Static("  Green border  - PAIR session active", classes="help-code"),
            Static("  Pulsing border - Agent actively working", classes="help-code"),
            Static(""),
            Static("Type Badges:", classes="help-subsection"),
            Static("  Human icon   - PAIR task", classes="help-code"),
            Static("  Lightning    - AUTO task", classes="help-code"),
            id="concepts-content",
        )

    def _compose_workflows(self) -> Vertical:
        """Compose the workflows guide section."""
        return Vertical(
            Static("Creating Tasks", classes="help-section-title"),
            Static(""),
            Static("Quick Create (n):", classes="help-subsection"),
            Static(
                "  Press 'n' to open the task form. Fill in title, description, "
                "priority, and type. Press Ctrl+S to save.",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Static("AI Assistant Overlay (Ctrl+P / Ctrl+O):", classes="help-subsection"),
            Static(
                "  Press 'Ctrl+P' for fullscreen or 'Ctrl+O' for docked overlay. "
                "Press the same key again to close back to board. "
                "Use '/' to open popup commands, Enter to run, and Esc to dismiss. "
                "Describe what you want to build in natural language and AI Assistant will "
                "break it down into tasks.",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Rule(),
            Static("Working on Tasks", classes="help-section-title"),
            Static(""),
            Static("PAIR Workflow:", classes="help-subsection"),
            Static(
                "  1. Select task in BACKLOG, press o\n"
                "  2. Kagan creates a git worktree and opens your PAIR backend\n"
                "  3. Work with your AI agent in tmux/Neovim/IDE\n"
                "  4. When done, move to REVIEW with Shift+Right or Shift+L",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Static("AUTO Workflow:", classes="help-subsection"),
            Static(
                "  1. Select task in BACKLOG, press o\n"
                "  2. Confirm start to run the agent and open output\n"
                "  3. Press o on IN_PROGRESS to open output\n"
                "  4. Agent moves task to REVIEW when done",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Rule(),
            Static("Reviewing & Completing", classes="help-section-title"),
            Static(""),
            Static("Review Process:", classes="help-subsection"),
            Static(
                "  1. Select task in REVIEW\n"
                "  2. Press o to open Task Output\n"
                "  3. Use Summary/Diff/Review Output/Agent Output tabs\n"
                "  4. Press Enter to approve or 'r' to reject",
                classes="help-paragraph-indented",
            ),
            Static(""),
            Static("Completing:", classes="help-subsection"),
            Static(
                "  Press 'm' on the board to merge approved tasks. Worktrees are cleaned up.",
                classes="help-paragraph-indented",
            ),
            id="workflows-content",
        )

    def _render_key(self, key: str) -> Text:
        rendered = Text(key, style="dim")
        for match in self._MODIFIER_TOKEN_PATTERN.finditer(key):
            rendered.stylize("bold", match.start(), match.end())
        return rendered

    def _key_row(self, key: str, description: str) -> Horizontal:
        """Create a key-description row."""
        return Horizontal(
            Static(self._render_key(key), classes="help-key"),
            Static("│", classes="help-key-separator"),
            Static(description, classes="help-desc"),
            classes="help-key-row",
        )

    def action_close(self) -> None:
        if self._search_query:
            self._search_query = ""
            with contextlib.suppress(Exception):
                search_input = self.query_one("#help-search-input", Input)
                search_input.value = ""
                search_input.focus()
            return
        self.dismiss(None)
