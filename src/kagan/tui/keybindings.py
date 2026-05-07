"""Keyboard bindings for Kagan TUI."""

from collections.abc import Iterable, Sequence

from textual.binding import Binding, BindingType

__all__ = [
    "AGENT_PICKER_BINDINGS",
    "ANALYTICS_BINDINGS",
    "APP_BINDINGS",
    "CHAT_BINDINGS",
    "CHAT_PERMISSION_BINDINGS",
    "CHECK_ROW_BINDINGS",
    "CONFIRM_BINDINGS",
    "DIFF_BINDINGS",
    "DIFF_CONTENT_PANE_BINDINGS",
    "DIFF_FILE_TREE_BINDINGS",
    "DIFF_VIEW_BINDINGS",
    "DOCTOR_MODAL_BINDINGS",
    "EDITOR_BINDINGS",
    "GITHUB_IMPORT_BINDINGS",
    "HELP_BINDINGS",
    "KANBAN_BINDINGS",
    "MESSAGE_ACTIONS_BINDINGS",
    "ORCHESTRATOR_OVERLAY_BINDINGS",
    "PERMISSION_BINDINGS",
    "REJECTION_BINDINGS",
    "REJECTION_INPUT_BINDINGS",
    "REPO_PICKER_BINDINGS",
    "REVIEW_NO_CRITERIA_BINDINGS",
    "RUNNING_AGENTS_BAR_BINDINGS",
    "SESSION_DASHBOARD_BINDINGS",
    "SESSION_PICKER_BINDINGS",
    "SETTINGS_BINDINGS",
    "SETTINGS_COMMAND_BINDINGS",
    "SETUP_FLOW_BINDINGS",
    "STREAMING_TIMELINE_BINDINGS",
    "TASK_EDITOR_BINDINGS",
    "TASK_SCREEN_BINDINGS",
    "TMUX_GATEWAY_BINDINGS",
    "TOOL_CALL_VIEW_BINDINGS",
    "USER_INPUT_BINDINGS",
    "WORKSPACE_BINDINGS",
    "FooterBuilder",
    "get_global_shortcut_help_rows",
    "get_help_rows_for_actions",
    "get_key_for_action",
    "get_keys_for_action",
]

APP_BINDINGS: list[BindingType] = [
    Binding("question_mark,f1", "show_help", "Help", key_display="?"),
    Binding(
        "ctrl+shift+p,f2",
        "command_palette",
        "Quick Actions",
        key_display="Ctrl+Shift+P",
    ),
    Binding("ctrl+o", "open_project_selector", "Projects", key_display="Ctrl+O"),
    Binding("ctrl+r", "open_repo_selector", "Repos", key_display="Ctrl+R"),
    Binding("ctrl+comma", "open_settings", "Settings", key_display="Ctrl+,"),
    Binding("ctrl+q", "quit", "Quit", key_display="Ctrl+Q"),
    Binding("o", "open_orchestrator", "AI Overlay", key_display="o"),
    Binding("ctrl+space", "open_orchestrator", "", show=False),
]

ORCHESTRATOR_OVERLAY_BINDINGS: list[BindingType] = [
    Binding("escape", "handle_esc", "Back / Close", priority=True),
    Binding("ctrl+space", "handle_esc", "", show=False, priority=True),
]

RUNNING_AGENTS_BAR_BINDINGS: list[BindingType] = [
    Binding("escape", "return_focus", "Back to input", show=False, priority=True),
]

CHECK_ROW_BINDINGS: list[BindingType] = [
    Binding("enter", "run_fix", "Run fix", show=False),
]

DOCTOR_MODAL_BINDINGS: list[BindingType] = [
    Binding("tab", "focus_next", "Next", show=False),
    Binding("shift+tab", "focus_previous", "Prev", show=False),
]

KANBAN_BINDINGS: list[BindingType] = [
    Binding("n", "new_task", "New Task"),
    Binding("enter", "open_task", "Open"),
    Binding("w", "toggle_workspace", "Workspace"),
    Binding("i", "open_analytics", "Analytics"),
    Binding("e", "edit_task", "Edit"),
    Binding("x", "delete_task", "Delete"),
    Binding("y", "copy_task_id", "Copy ID"),
    Binding("s", "start_agent", "Start"),
    Binding("a", "attach_agent", "Attach"),
    Binding("shift+s", "stop_agent", "Stop", key_display="Shift+S"),
    Binding("shift+left", "move_left", "Move Left", key_display="Shift+←"),
    Binding("shift+right", "move_right", "Move Right", key_display="Shift+→"),
    Binding("slash", "search", "Search", key_display="/"),
    Binding("f", "expand_description", "Expand Description"),
    Binding("p", "peek_task", "Peek"),
    Binding("ctrl+f", "expand_chat_overlay", "AI Fullscreen", key_display="Ctrl+F"),
    Binding("ctrl+period,ctrl+i,f4", "toggle_chat", "AI Panel", key_display="Ctrl+."),
    Binding("ctrl+shift+t", "fullscreen_chat", "", key_display="Ctrl+Shift+T", show=False),
    Binding("ctrl+k", "switch_session", "Session Switcher", key_display="Ctrl+K"),
    Binding("b", "set_branch", "Branch"),
    Binding("h,left", "focus_left", "Left", show=False),
    Binding("j,down", "focus_down", "Down", show=False),
    Binding("k,up", "focus_up", "Up", show=False),
    Binding("l,right", "focus_right", "Right", show=False),
    Binding("tab", "focus_next_card", "Next Card", show=False),
    Binding("shift+tab", "focus_prev_card", "Prev Card", show=False),
    Binding("escape", "clear_focus", "Clear", show=False),
]

TASK_SCREEN_BINDINGS: list[BindingType] = [
    Binding("1", "tab_overview", "Overview"),
    Binding("2", "tab_changes", "Changes"),
    Binding("3", "tab_review", "Review"),
    Binding("enter", "primary_action", "Primary Action"),
    Binding("e", "edit_task", "Edit"),
    Binding("d", "delete_task", "Delete"),
    Binding("a", "approve", "Approve"),
    Binding("x", "reject", "Reject"),
    Binding("m", "merge", "Merge"),
    Binding("b", "rebase", "Rebase"),
    Binding("ctrl+f", "expand_chat_overlay", "AI Fullscreen", key_display="Ctrl+F"),
    Binding("ctrl+period,ctrl+i,f4", "toggle_chat", "AI Panel", key_display="Ctrl+."),
    Binding("ctrl+shift+t", "fullscreen_chat", "", key_display="Ctrl+Shift+T", show=False),
    Binding("ctrl+k", "switch_session", "Session Switcher", key_display="Ctrl+K"),
    Binding("escape", "back", "Back"),
]

SESSION_DASHBOARD_BINDINGS: list[BindingType] = [
    Binding("enter", "primary_action", "Start/Focus"),
    Binding("s", "start_agent", "Start"),
    Binding("x", "stop_agent", "Stop"),
    Binding("r", "restart_agent", "Restart"),
    Binding("ctrl+period,ctrl+i,f4", "toggle_chat", "AI Panel", key_display="Ctrl+."),
    Binding("ctrl+shift+t", "fullscreen_chat", "", key_display="Ctrl+Shift+T", show=False),
    Binding("ctrl+k", "switch_session", "Session Switcher", key_display="Ctrl+K"),
    Binding("escape", "back", "Back"),
]

WORKSPACE_BINDINGS: list[BindingType] = [
    Binding("enter", "open_session", "Open"),
    Binding("n", "new_session", "New"),
    Binding("x", "delete_session", "Delete"),
    Binding("slash", "focus_search", "Search", key_display="/"),
    Binding("ctrl+period,ctrl+i,f4", "focus_chat", "Chat", key_display="Ctrl+."),
    Binding("ctrl+k", "switch_session", "Session Switcher", key_display="Ctrl+K"),
    Binding("w", "toggle_board", "Board"),
    Binding("escape", "back", "Back"),
]

CHAT_BINDINGS: list[BindingType] = [
    Binding("enter", "send_message", "Send"),
    Binding("shift+enter", "insert_newline", "Newline", key_display="Shift+Enter"),
    Binding("tab", "accept_completion", "Complete"),
    Binding("ctrl+p", "open_file_picker", "Files", key_display="Ctrl+P"),
    Binding("ctrl+c", "clear_input", "Clear", key_display="Ctrl+C"),
    Binding("escape", "dismiss", "Stop / Edit", key_display="Esc"),
    Binding("ctrl+k", "open_session_picker", "Session Switcher", key_display="Ctrl+K"),
]

SETTINGS_BINDINGS: list[BindingType] = [
    Binding("escape", "cancel", "Close"),
    Binding("slash", "search", "Search", key_display="/"),
]

SETTINGS_COMMAND_BINDINGS: list[BindingType] = [
    Binding("slash", "focus_search", "Search", key_display="/", show=False),
]

SETUP_FLOW_BINDINGS: list[BindingType] = [
    Binding("enter", "submit", "Continue"),
    Binding("escape", "dismiss", "Close"),
]

CONFIRM_BINDINGS: list[BindingType] = [
    Binding("enter", "confirm", "Confirm"),
    Binding("escape", "cancel", "Cancel"),
]

DIFF_BINDINGS: list[BindingType] = [
    Binding("j,down", "next", "Next"),
    Binding("k,up", "prev", "Prev"),
    Binding("enter", "approve", "Approve"),
    Binding("x", "reject", "Reject"),
    Binding("y", "copy", "Copy"),
    Binding("escape", "close", "Close"),
]

DIFF_FILE_TREE_BINDINGS: list[BindingType] = [
    Binding("j,down", "cursor_down", "Next file", show=True),
    Binding("k,up", "cursor_up", "Prev file", show=True),
    Binding("enter", "select", "Select", show=True),
]

DIFF_CONTENT_PANE_BINDINGS: list[BindingType] = [
    Binding("j,down", "scroll_down", "Scroll down", show=True),
    Binding("k,up", "scroll_up", "Scroll up", show=True),
    Binding("f,pagedown", "page_down", "Page down", show=True),
    Binding("b,pageup", "page_up", "Page up", show=True),
    Binding("g,home", "scroll_home", "Top", show=True),
    Binding("G,end", "scroll_end", "Bottom", show=True),
]

DIFF_VIEW_BINDINGS: list[BindingType] = [
    Binding("h,left", "focus_file_tree", "Files", show=True),
    Binding("l,right", "focus_diff_content", "Diff", show=True),
]

EDITOR_BINDINGS: list[BindingType] = [
    Binding("ctrl+s", "finish", "Create", key_display="Ctrl+S"),
    Binding("escape", "cancel", "Cancel"),
    Binding("pagedown", "page_down", "Page Down", show=False),
    Binding("pageup", "page_up", "Page Up", show=False),
]

HELP_BINDINGS: list[BindingType] = [
    Binding("slash", "focus_search", "Search", key_display="/"),
    Binding("escape", "close", "Close"),
]

PERMISSION_BINDINGS: list[BindingType] = [
    Binding("enter", "allow_once", "Allow Once"),
    Binding("a", "allow_always", "Allow Always"),
    Binding("escape", "deny", "Deny"),
]

REJECTION_BINDINGS: list[BindingType] = [
    Binding("enter", "send_back", "Confirm", priority=True),
    Binding("ctrl+s", "send_back", "Submit", key_display="Ctrl+S"),
    Binding("escape", "cancel", "Cancel"),
]

REVIEW_NO_CRITERIA_BINDINGS: list[BindingType] = [
    Binding("a", "add_criteria", "Add Criteria"),
    Binding("enter", "approve_manually", "Approve Manually", priority=True),
    Binding("x", "reject", "Reject"),
    Binding("escape", "cancel", "Cancel"),
]

TMUX_GATEWAY_BINDINGS: list[BindingType] = [
    Binding("enter", "proceed", "Continue"),
    Binding("escape", "cancel", "Cancel"),
    Binding("s", "skip_future", "Don't show again"),
]


SESSION_PICKER_BINDINGS: list[BindingType] = [
    Binding("escape", "cancel", "Cancel", show=False),
    Binding("enter", "select", "Select", show=False, priority=True),
    Binding("k,up", "cursor_up", "Up", show=False, priority=True),
    Binding("j,down", "cursor_down", "Down", show=False, priority=True),
    Binding("h,left", "focus_groups", "Groups", show=False, priority=True),
    Binding("l,right", "focus_sessions", "Sessions", show=False, priority=True),
    Binding("slash", "focus_filter", "Filter", show=False, priority=True, key_display="/"),
    Binding("x", "delete_session", "Delete", show=False, priority=True),
]

REPO_PICKER_BINDINGS: list[BindingType] = [
    Binding("enter", "select_repo", "Select"),
    Binding("escape", "dismiss", "Close"),
]

GITHUB_IMPORT_BINDINGS: list[BindingType] = [
    Binding("enter", "run_import", "Import", key_display="Enter", priority=True),
    Binding("escape", "dismiss", "Close", key_display="Esc"),
    Binding("a", "select_all", "Select All", show=False),
    Binding("n", "select_none", "Select None", show=False),
]

AGENT_PICKER_BINDINGS: list[BindingType] = [
    Binding("enter", "select_agent", "Select", show=False, priority=True),
    Binding("escape", "dismiss", "Close"),
    Binding("a", "toggle_all_backends", "Show all"),
]

ANALYTICS_BINDINGS: list[BindingType] = [
    Binding("escape", "close", "Close"),
    Binding("r", "refresh", "Refresh"),
    Binding("e", "export", "Export JSON"),
]

CHAT_PERMISSION_BINDINGS: list[BindingType] = [
    Binding("a", "allow", "Allow once"),
    Binding("s", "allow_session", "Allow session"),
    Binding("A", "allow_all", "Allow all"),
    Binding("d", "deny", "Deny"),
    Binding("escape", "deny", "Deny"),
]

MESSAGE_ACTIONS_BINDINGS: list[BindingType] = [
    Binding("enter", "select", "Select"),
    Binding("escape", "cancel", "Cancel"),
    Binding("j,down", "cursor_down", "Next", show=False),
    Binding("k,up", "cursor_up", "Prev", show=False),
]

TOOL_CALL_VIEW_BINDINGS: list[BindingType] = [
    Binding("enter", "toggle_expand", "Toggle Details", show=False),
]

STREAMING_TIMELINE_BINDINGS: list[BindingType] = [
    Binding("j,down", "focus_next_entry", "Next", show=False),
    Binding("k,up", "focus_prev_entry", "Prev", show=False),
    Binding("h,left", "collapse_entry", "Collapse", show=False),
    Binding("l,right", "expand_entry", "Expand", show=False),
    Binding("g,home", "focus_first_entry", "First", show=False),
    Binding("G,end", "jump_to_latest", "Latest", key_display="Shift+G", show=False),
]

USER_INPUT_BINDINGS: list[BindingType] = [
    Binding("enter", "open_actions", "Actions", priority=True),
]

TASK_EDITOR_BINDINGS = EDITOR_BINDINGS
REJECTION_INPUT_BINDINGS = REJECTION_BINDINGS


class FooterBuilder:
    @staticmethod
    def global_hints() -> list[tuple[str, str]]:
        return [("?", "help"), ("Ctrl+Shift+P", "quick actions")]

    @staticmethod
    def kanban_core() -> list[tuple[str, str]]:
        return [("n", "new"), ("/", "search")]

    @staticmethod
    def kanban_with_card() -> list[tuple[str, str]]:
        return [
            ("Enter", "open"),
            ("Ctrl+.", "AI panel"),
            ("P", "peek"),
            ("e", "edit"),
            ("x", "delete"),
            ("s", "start"),
            ("Shift+S", "stop"),
        ]

    @staticmethod
    def kanban_navigation() -> list[tuple[str, str]]:
        return [("h/j/k/l", "navigate"), ("Shift+←/→", "move")]

    @staticmethod
    def task_screen() -> list[tuple[str, str]]:
        return [
            ("1/2", "tabs"),
            ("Enter", "action"),
            ("Ctrl+.", "AI panel"),
            ("Ctrl+F", "assistant full"),
            ("e", "edit"),
            ("d", "delete"),
            ("a", "approve"),
            ("x", "reject"),
            ("Esc", "back"),
        ]

    @staticmethod
    def task_screen_review() -> list[tuple[str, str]]:
        return [
            ("1/2", "tabs"),
            ("a", "approve"),
            ("x", "reject"),
            ("m", "merge"),
            ("Esc", "back"),
        ]

    @staticmethod
    def session_dashboard() -> list[tuple[str, str]]:
        return [
            ("Enter", "start"),
            ("s", "start"),
            ("x", "stop"),
            ("r", "restart"),
            ("Ctrl+.", "AI panel"),
            ("Esc", "back"),
        ]

    @staticmethod
    def settings() -> list[tuple[str, str]]:
        return [("/", "search"), ("Esc", "close")]

    @staticmethod
    def confirm() -> list[tuple[str, str]]:
        return [("Enter/y", "yes"), ("Esc/n", "no")]

    @staticmethod
    def chat() -> list[tuple[str, str]]:
        return [
            ("Enter", "send"),
            ("Shift+Enter", "newline"),
            ("Ctrl+P", "files"),
            ("Ctrl+K", "sessions"),
            ("Esc", "stop / edit"),
        ]


def get_key_for_action(bindings: list[BindingType], action: str, default: str = "?") -> str:
    for binding in bindings:
        if isinstance(binding, Binding) and binding.action == action:
            return binding.key_display or binding.key
    return default


def get_keys_for_action(bindings: list[BindingType], action: str) -> list[str]:
    keys: list[str] = []
    for binding in bindings:
        if not isinstance(binding, Binding) or binding.action != action:
            continue
        label = binding.key_display or binding.key
        if label not in keys:
            keys.append(label)
    return keys


def get_global_shortcut_help_rows() -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for binding in APP_BINDINGS:
        if not isinstance(binding, Binding) or not binding.description:
            continue
        rows.append((binding.key_display or binding.key, binding.description))
    return rows


def get_help_rows_for_actions(
    bindings: list[BindingType],
    action_specs: Iterable[tuple[str, str, Sequence[str]]],
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for action, description, fallback_keys in action_specs:
        labels = get_keys_for_action(bindings, action)
        if not labels:
            labels = [key for key in fallback_keys if key]
        if not labels:
            continue
        rows.append((" / ".join(labels), description))
    return rows
