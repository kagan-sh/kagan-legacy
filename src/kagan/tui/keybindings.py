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
    "SESSION_DASHBOARD_BINDINGS",
    "SESSION_LIST_BINDINGS",
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
    Binding("question_mark,f1", "show_help", "help", key_display="?"),
    Binding(
        "ctrl+shift+p,f2",
        "command_palette",
        "quick actions",
        key_display="Ctrl+Shift+P",
    ),
    Binding("ctrl+o", "open_project_selector", "projects", key_display="Ctrl+O"),
    Binding("ctrl+r", "open_repo_selector", "repos", key_display="Ctrl+R"),
    Binding("ctrl+comma", "open_settings", "settings", key_display="Ctrl+,"),
    Binding("ctrl+q", "quit", "quit", key_display="Ctrl+Q"),
    Binding(
        "ctrl+space",
        "open_orchestrator",
        "orchestrator",
        key_display="Ctrl+Space",
    ),
    Binding("ctrl+w", "toggle_mode", "toggle chat/board", key_display="Ctrl+W"),
]

ORCHESTRATOR_OVERLAY_BINDINGS: list[BindingType] = [
    Binding("escape", "handle_esc", "back / close", priority=True),
    Binding("ctrl+space", "handle_esc", "", show=False, priority=True),
    # Ctrl+↑/↓ are Mission Control / Spaces on macOS — prefer Ctrl+Shift+[/] there;
    # keep Ctrl+↑/↓ as secondary for Linux/Windows terminals.
    Binding(
        "ctrl+shift+close_square_bracket,ctrl+down",
        "cycle_agent_next",
        "next agent",
        key_display="Ctrl+Shift+] / Ctrl+↓",
        priority=True,
    ),
    Binding(
        "ctrl+shift+open_square_bracket,ctrl+up",
        "cycle_agent_prev",
        "previous agent",
        key_display="Ctrl+Shift+[ / Ctrl+↑",
        priority=True,
    ),
    Binding(
        "ctrl+shift+f",
        "toggle_fullscreen",
        "AI fullscreen",
        key_display="Ctrl+Shift+F",
        priority=True,
    ),
]

CHECK_ROW_BINDINGS: list[BindingType] = [
    Binding("enter", "run_fix", "Run fix", show=False),
]

DOCTOR_MODAL_BINDINGS: list[BindingType] = [
    Binding("tab", "focus_next", "Next", show=False),
    Binding("shift+tab", "focus_previous", "Prev", show=False),
]

KANBAN_BINDINGS: list[BindingType] = [
    Binding("n", "new_task", "new task"),
    Binding("enter", "open_task", "open"),
    Binding("w", "toggle_workspace", "workspace"),
    Binding("ctrl+w", "toggle_mode", "chat/board", key_display="Ctrl+W"),
    Binding("i", "open_analytics", "analytics"),
    Binding("e", "edit_task", "edit"),
    Binding("x", "delete_task", "delete"),
    Binding("y", "copy_task_id", "copy id"),
    Binding("s", "start_agent", "start"),
    Binding("a", "attach_agent", "attach"),
    Binding("shift+s", "stop_agent", "stop", key_display="Shift+S"),
    Binding("shift+left", "move_left", "move left", key_display="Shift+Left"),
    Binding("shift+right", "move_right", "move right", key_display="Shift+Right"),
    Binding("slash", "search", "search", key_display="/"),
    Binding("f", "expand_description", "expand description"),
    Binding("p", "peek_task", "peek"),
    Binding("ctrl+f", "expand_chat_overlay", "AI expand", key_display="Ctrl+F"),
    Binding("ctrl+period", "toggle_chat", "sessions", key_display="Ctrl+."),
    Binding("ctrl+shift+t", "fullscreen_chat", "", key_display="Ctrl+Shift+T", show=False),
    Binding("ctrl+k", "switch_session", "session switcher", key_display="Ctrl+K"),
    Binding("b", "set_branch", "branch"),
    Binding("h,left", "focus_left", "left", show=False),
    Binding("j,down", "focus_down", "down", show=False),
    Binding("k,up", "focus_up", "up", show=False),
    Binding("l,right", "focus_right", "right", show=False),
    Binding("tab", "focus_next_card", "next card", show=False),
    Binding("shift+tab", "focus_prev_card", "prev card", show=False),
    Binding("escape", "clear_focus", "clear", show=False),
]

TASK_SCREEN_BINDINGS: list[BindingType] = [
    Binding("1", "tab_overview", "overview"),
    Binding("2", "tab_changes", "changes"),
    Binding("3", "tab_review", "review"),
    Binding("enter", "primary_action", "primary action"),
    Binding("e", "edit_task", "edit"),
    Binding("d", "delete_task", "delete"),
    Binding("a", "approve", "approve"),
    Binding("x", "reject", "reject"),
    Binding("m", "merge", "merge"),
    Binding("b", "rebase", "rebase"),
    Binding("ctrl+f", "expand_chat_overlay", "AI expand", key_display="Ctrl+F"),
    Binding("ctrl+period", "toggle_chat", "sessions", key_display="Ctrl+."),
    Binding("ctrl+shift+t", "fullscreen_chat", "", key_display="Ctrl+Shift+T", show=False),
    Binding("ctrl+k", "switch_session", "session switcher", key_display="Ctrl+K"),
    Binding("escape", "back", "back"),
]

SESSION_DASHBOARD_BINDINGS: list[BindingType] = [
    Binding("enter", "primary_action", "start/focus"),
    Binding("s", "start_agent", "start"),
    Binding("x", "stop_agent", "stop"),
    Binding("r", "restart_agent", "restart"),
    Binding("ctrl+period", "toggle_chat", "sessions", key_display="Ctrl+."),
    Binding("ctrl+shift+t", "fullscreen_chat", "", key_display="Ctrl+Shift+T", show=False),
    Binding("ctrl+k", "switch_session", "session switcher", key_display="Ctrl+K"),
    Binding("escape", "back", "back"),
]

WORKSPACE_BINDINGS: list[BindingType] = [
    Binding("enter", "open_session", "open"),
    Binding("n", "new_session", "new"),
    Binding("x", "delete_session", "delete"),
    Binding("slash", "focus_search", "search", key_display="/"),
    Binding("ctrl+period", "focus_chat", "chat", key_display="Ctrl+."),
    Binding("ctrl+k", "switch_session", "session switcher", key_display="Ctrl+K"),
    Binding("w", "toggle_board", "board"),
    Binding("ctrl+w", "toggle_mode", "chat/board", key_display="Ctrl+W"),
    Binding("escape", "back", "back"),
]

CHAT_BINDINGS: list[BindingType] = [
    Binding("enter", "send_message", "send"),
    Binding("shift+enter", "insert_newline", "newline", key_display="Shift+Enter"),
    Binding("tab", "accept_completion", "complete"),
    Binding("ctrl+p", "open_file_picker", "files", key_display="Ctrl+P"),
    Binding("ctrl+c", "clear_input", "clear", key_display="Ctrl+C"),
    Binding("escape", "dismiss", "stop / edit", key_display="Esc"),
    Binding("ctrl+k", "open_session_picker", "session switcher", key_display="Ctrl+K"),
]

SETTINGS_BINDINGS: list[BindingType] = [
    Binding("escape", "cancel", "close"),
    Binding("slash", "search", "search", key_display="/"),
]

SETTINGS_COMMAND_BINDINGS: list[BindingType] = [
    Binding("slash", "focus_search", "Search", key_display="/", show=False),
]

SETUP_FLOW_BINDINGS: list[BindingType] = [
    Binding("enter", "submit", "continue"),
    Binding("escape", "dismiss", "close"),
]

CONFIRM_BINDINGS: list[BindingType] = [
    Binding("enter", "confirm", "confirm"),
    Binding("escape", "cancel", "cancel"),
]

DIFF_BINDINGS: list[BindingType] = [
    Binding("j,down", "next", "next"),
    Binding("k,up", "prev", "prev"),
    Binding("enter", "approve", "approve"),
    Binding("x", "reject", "reject"),
    Binding("y", "copy", "copy"),
    Binding("escape", "close", "close"),
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
    Binding("ctrl+s", "finish", "create", key_display="Ctrl+S"),
    Binding("escape", "cancel", "cancel"),
    Binding("pagedown", "page_down", "page down", show=False),
    Binding("pageup", "page_up", "page up", show=False),
]

HELP_BINDINGS: list[BindingType] = [
    Binding("slash", "focus_search", "search", key_display="/"),
    Binding("escape", "close", "close"),
]

PERMISSION_BINDINGS: list[BindingType] = [
    Binding("enter", "allow_once", "allow once"),
    Binding("a", "allow_always", "allow always"),
    Binding("escape", "deny", "deny"),
]

REJECTION_BINDINGS: list[BindingType] = [
    Binding("enter", "send_back", "confirm", priority=True),
    Binding("ctrl+s", "send_back", "submit", key_display="Ctrl+S"),
    Binding("escape", "cancel", "cancel"),
]

REVIEW_NO_CRITERIA_BINDINGS: list[BindingType] = [
    Binding("a", "add_criteria", "add criteria"),
    Binding("enter", "approve_manually", "approve manually", priority=True),
    Binding("x", "reject", "reject"),
    Binding("escape", "cancel", "cancel"),
]

TMUX_GATEWAY_BINDINGS: list[BindingType] = [
    Binding("enter", "proceed", "continue"),
    Binding("escape", "cancel", "cancel"),
    Binding("s", "skip_future", "don't show again"),
]


SESSION_LIST_BINDINGS: list[BindingType] = [
    Binding("escape", "return_focus", "Back to input", show=False, priority=True),
    Binding("s", "stop_session", "Stop session", show=False),
    Binding("x", "close_session", "Close session", show=False),
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
    Binding("enter", "select_repo", "select"),
    Binding("escape", "dismiss", "close"),
]

GITHUB_IMPORT_BINDINGS: list[BindingType] = [
    Binding("enter", "run_import", "import", key_display="Enter", priority=True),
    Binding("escape", "dismiss", "close", key_display="Esc"),
    Binding("a", "select_all", "select all", show=False),
    Binding("n", "select_none", "select none", show=False),
]

AGENT_PICKER_BINDINGS: list[BindingType] = [
    Binding("enter", "select_agent", "select", show=False, priority=True),
    Binding("escape", "dismiss", "close"),
    Binding("a", "toggle_all_backends", "show all"),
]

ANALYTICS_BINDINGS: list[BindingType] = [
    Binding("escape", "close", "close"),
    Binding("r", "refresh", "refresh"),
    Binding("e", "export", "export JSON"),
]

CHAT_PERMISSION_BINDINGS: list[BindingType] = [
    Binding("a", "allow", "allow once"),
    Binding("s", "allow_session", "allow session"),
    Binding("A", "allow_all", "allow all"),
    Binding("d", "deny", "deny"),
    Binding("escape", "deny", "deny"),
]

MESSAGE_ACTIONS_BINDINGS: list[BindingType] = [
    Binding("enter", "select", "select"),
    Binding("escape", "cancel", "cancel"),
    Binding("j,down", "cursor_down", "next", show=False),
    Binding("k,up", "cursor_up", "prev", show=False),
]

TOOL_CALL_VIEW_BINDINGS: list[BindingType] = [
    Binding("enter", "toggle_expand", "toggle details", show=False),
]

STREAMING_TIMELINE_BINDINGS: list[BindingType] = [
    Binding("j,down", "focus_next_entry", "next", show=False),
    Binding("k,up", "focus_prev_entry", "prev", show=False),
    Binding("h,left", "collapse_entry", "collapse", show=False),
    Binding("l,right", "expand_entry", "expand", show=False),
    Binding("g,home", "focus_first_entry", "first", show=False),
    Binding("G,end", "jump_to_latest", "latest", key_display="Shift+G", show=False),
    Binding("ctrl+t", "toggle_reasoning", "reasoning", key_display="Ctrl+T", show=False),
]

USER_INPUT_BINDINGS: list[BindingType] = [
    Binding("enter", "open_actions", "actions", priority=True),
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
            ("Ctrl+.", "sessions"),
            ("p", "peek"),
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
            ("Ctrl+.", "sessions"),
            ("Ctrl+F", "AI expand"),
            ("Ctrl+K", "switch session"),
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
            ("Ctrl+.", "sessions"),
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
