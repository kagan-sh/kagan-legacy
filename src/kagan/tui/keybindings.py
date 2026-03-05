from textual.binding import Binding, BindingType

__all__ = [
    "APPROVAL_BINDINGS",
    "APP_BINDINGS",
    "CHAT_BINDINGS",
    "CONFIRM_BINDINGS",
    "DEBUG_LOG_BINDINGS",
    "DESCRIPTION_EDITOR_BINDINGS",
    "DIFF_BINDINGS",
    "HELP_BINDINGS",
    "KANBAN_BINDINGS",
    "ONBOARDING_BINDINGS",
    "PERMISSION_PROMPT_BINDINGS",
    "PLANNER_BINDINGS",
    "REJECTION_INPUT_BINDINGS",
    "SESSION_DASHBOARD_BINDINGS",
    "SETTINGS_BINDINGS",
    "TASK_EDITOR_BINDINGS",
    "TASK_SCREEN_BINDINGS",
    "TMUX_GATEWAY_BINDINGS",
    "WELCOME_BINDINGS",
    "get_global_shortcut_help_rows",
    "get_help_rows_for_actions",
    "get_key_for_action",
    "get_keys_for_action",
]

APP_BINDINGS: list[BindingType] = [
    Binding("ctrl+shift+p,.", "command_palette", "Actions", key_display="Ctrl+Shift+P / ."),
    Binding("question_mark", "show_help", "Help", key_display="?"),
    Binding("f1", "show_help", "", show=False, key_display="F1", priority=True),
    Binding("ctrl+q", "quit", "Quit", key_display="Ctrl+Q"),
    Binding(
        "ctrl+shift+o",
        "open_project_selector",
        "Projects",
        key_display="Ctrl+Shift+O",
        show=False,
        priority=True,
    ),
    Binding(
        "ctrl+r",
        "open_repo_selector",
        "Repos",
        key_display="Ctrl+R",
        show=False,
        priority=True,
    ),
    Binding("f12", "toggle_debug_log", "Debug", show=False),
]

KANBAN_BINDINGS: list[BindingType] = [
    Binding("n", "new_task", "New"),
    Binding("N", "new_auto_task", "New AUTO", key_display="Shift+N", show=False),
    Binding("enter", "open_task", "Inspect", key_display="Enter"),
    Binding("o,p", "open_session", "Open Session", key_display="O / P"),
    Binding("slash", "toggle_search", "Search", key_display="/"),
    Binding("v", "view_details", "View", show=False),
    Binding("e", "edit_task", "Edit", show=False),
    Binding("x", "delete_task_direct", "Delete", show=False),
    Binding("a", "start_agent", "Agent", show=False),
    Binding("s", "stop_agent", "Stop", show=False),
    Binding("g", "import_from_github", "Import GitHub", show=False),
    Binding("comma", "open_settings", "Settings", key_display=",", show=False),
    Binding("y", "duplicate_task", "Duplicate", show=False),
    Binding("c", "copy_task_id", "Copy ID", show=False),
    Binding("r", "review_task", "Review", show=False),
    Binding("space", "toggle_peek", "Peek", show=False),
    Binding(
        "ctrl+p",
        "open_chat_fullscreen",
        "AI Assistant Fullscreen",
        key_display="Ctrl+P",
        show=False,
    ),
    Binding(
        "ctrl+o",
        "toggle_chat_overlay",
        "AI Assistant View",
        key_display="Ctrl+O",
        show=False,
    ),
    Binding("f", "expand_description", "Expand", show=False),
    Binding("f5", "expand_description", "Full Editor", key_display="F5", show=False),
    Binding("shift+left", "move_backward", "Move Left", key_display="Shift+Left", show=False),
    Binding(
        "shift+right",
        "move_forward",
        "Move Right",
        key_display="Shift+Right",
        show=False,
    ),
    Binding("H", "move_backward", "Move Left", key_display="Shift+H", show=False),
    Binding("L", "move_forward", "Move Right", key_display="Shift+L", show=False),
    Binding("b", "set_task_branch", "Set Task Branch", show=False),
    Binding(
        "ctrl+a,A",
        "switch_global_agent",
        "Switch AI Assistant",
        key_display="Ctrl+A / Shift+A",
        show=False,
    ),
    Binding("G", "repo_sync", "Repo Sync", key_display="Shift+G", show=False),
    Binding("h", "focus_left", "Left", show=False),
    Binding("j", "focus_down", "Down", show=False),
    Binding("k", "focus_up", "Up", show=False),
    Binding("l", "focus_right", "Right", show=False),
    Binding("left", "focus_left", "Left", show=False),
    Binding("right", "focus_right", "Right", show=False),
    Binding("down", "focus_down", "Down", show=False),
    Binding("up", "focus_up", "Up", show=False),
    Binding("tab", "focus_next_card", "Next", key_display="Tab", show=False),
    Binding("shift+tab", "focus_prev_card", "Prev", key_display="Shift+Tab", show=False),
    Binding("escape", "deselect", "", key_display="Esc", show=False),
    Binding("ctrl+c", "interrupt", "", show=False),
]

CHAT_BINDINGS: list[BindingType] = [
    Binding("enter", "send_message", "Send", key_display="Enter"),
    Binding("shift+enter", "insert_newline", "Newline", key_display="Shift+Enter", show=False),
    Binding("tab", "accept_completion", "Complete", key_display="Tab", show=False),
    Binding("ctrl+k", "open_session_picker", "Sessions", key_display="Ctrl+K", show=False),
    Binding("ctrl+u", "clear_input", "Clear", key_display="Ctrl+U", show=False),
    Binding("c", "dismiss", "Close", show=False),
    Binding("escape", "dismiss", "Close", key_display="Esc"),
]

TASK_SCREEN_BINDINGS: list[BindingType] = [
    Binding("1", "switch_tab('overview')", "Overview", priority=True),
    Binding("2", "switch_tab('changes')", "Changes", priority=True),
    Binding("3", "switch_tab('review')", "Review", priority=True),
    Binding("1", "switch_tab('overview')", "Overview", show=False),
    Binding("2", "switch_tab('changes')", "Changes", show=False),
    Binding("3", "switch_tab('review')", "Review", show=False),
    Binding("enter", "primary_action", "Action", key_display="Enter"),
    Binding("e", "edit_task", "Edit"),
    Binding("d", "delete_task", "Delete"),
    Binding("a", "approve", "Approve"),
    Binding("m", "merge", "Merge"),
    Binding("x", "reject", "Reject"),
    Binding("b", "rebase", "Rebase"),
    Binding("g", "generate_review", "Run Review"),
    Binding("tab", "cycle_chat_session", "Next Session", show=False),
    Binding("ctrl+k", "open_session_picker", "Session Picker", key_display="Ctrl+K", show=False),
    Binding("ctrl+p", "open_chat_fullscreen", "Chat Fullscreen", show=False),
    Binding("ctrl+o", "toggle_chat_overlay", "Chat View", show=False),
    Binding("ctrl+r", "open_repo_picker", "Repos", key_display="Ctrl+R", show=False),
    Binding("ctrl+c", "cancel_run", "Stop", key_display="Ctrl+C"),
    Binding("escape", "back", "Back", key_display="Esc"),
]

SESSION_DASHBOARD_BINDINGS: list[BindingType] = [
    Binding("tab", "cycle_chat_session", "Next Session", show=False),
    Binding("ctrl+p", "open_chat_fullscreen", "AI Chat Fullscreen", show=False),
    Binding("ctrl+o", "toggle_chat_overlay", "AI Chat Overlay", show=False),
    Binding("ctrl+k", "open_session_picker", "Session Picker", key_display="Ctrl+K", show=False),
    Binding("enter", "primary_action", "Start/Focus", key_display="Enter"),
    Binding("s", "stop_run", "Stop Agent"),
    Binding("r", "restart_run", "Restart Agent"),
    Binding("ctrl+r", "open_repo_picker", "Repos", key_display="Ctrl+R", show=False),
    Binding("ctrl+c", "cancel_run", "Stop", key_display="Ctrl+C"),
    Binding("escape", "back", "Back", key_display="Esc"),
]

CONFIRM_BINDINGS: list[BindingType] = [
    Binding("enter", "confirm", "Confirm", key_display="Enter"),
    Binding("escape", "cancel", "Cancel"),
]

DESCRIPTION_EDITOR_BINDINGS: list[BindingType] = [
    Binding("escape", "cancel", "Cancel"),
    Binding("ctrl+s", "save", "Save", key_display="Ctrl+S"),
]

DIFF_BINDINGS: list[BindingType] = [
    Binding("enter", "approve", "Approve", key_display="Enter"),
    Binding("r", "reject", "Reject"),
    Binding("y", "copy", "Copy", show=False),
    Binding("escape", "close", "Close"),
]

HELP_BINDINGS: list[BindingType] = [
    Binding("ctrl+f", "focus_search", "Search", key_display="Ctrl+F"),
    Binding("escape", "close", "Close"),
    Binding("q", "close", "Close", show=False),
]

REJECTION_INPUT_BINDINGS: list[BindingType] = [
    Binding("enter", "send_back", "Back to In Progress", key_display="Enter", priority=True),
    Binding("B", "backlog", "To Backlog", key_display="Shift+B"),
    Binding("escape", "cancel", "Cancel", key_display="Esc"),
]

SETTINGS_BINDINGS: list[BindingType] = [
    Binding("escape", "cancel", "Cancel"),
    Binding("ctrl+s", "save", "Save", key_display="Ctrl+S"),
]

DEBUG_LOG_BINDINGS: list[BindingType] = [
    Binding("escape", "close", "Close"),
    Binding("c", "clear_logs", "Clear"),
    Binding("s", "save_logs", "Save"),
]

TMUX_GATEWAY_BINDINGS: list[BindingType] = [
    Binding("enter", "proceed", "Continue", priority=True),
    Binding("escape", "cancel", "Cancel", priority=True),
    Binding("s", "skip_future", "Don't show again", priority=True),
]

APPROVAL_BINDINGS: list[BindingType] = [
    Binding("escape", "cancel", "Cancel"),
    Binding("enter", "approve", "Approve"),
    Binding("t", "toggle_type", "Toggle Type"),
]

PLANNER_BINDINGS: list[BindingType] = [
    Binding("escape", "to_board", "Board"),
    Binding("ctrl+c", "cancel", "Stop", priority=True),
    Binding("ctrl+e", "refine", "Enhance", key_display="Ctrl+E", priority=True),
    Binding("f2", "refine", "Enhance", show=False),
    Binding("b", "set_task_branch", "Set Task Branch", show=False),
]

TASK_EDITOR_BINDINGS: list[BindingType] = [
    Binding("escape", "cancel", "Cancel"),
    Binding("ctrl+s", "finish", "Finish Editing", key_display="Ctrl+S"),
    Binding("ctrl+.", "toggle_advanced", "Advanced", key_display="Ctrl+."),
    Binding("pagedown", "scroll_down", "Scroll Down", key_display="PgDn", show=False),
    Binding("pageup", "scroll_up", "Scroll Up", key_display="PgUp", show=False),
]

WELCOME_BINDINGS: list[BindingType] = [
    Binding("enter", "open_selected", "Open", key_display="Enter"),
    Binding("n", "new_project", "New Project"),
    Binding("o", "open_folder", "Open Folder"),
    Binding("s", "settings", "Settings"),
    Binding("up,k", "move_selection_up", "Up", key_display="Up / k", show=False),
    Binding("down,j", "move_selection_down", "Down", key_display="Down / j", show=False),
    Binding("tab", "focus_next", "Next", key_display="Tab", show=False),
    Binding("shift+tab", "focus_previous", "Previous", key_display="Shift+Tab", show=False),
    Binding("escape", "quit", "Quit"),
    Binding("1", "open_project('0')", "Open #1", show=False),
    Binding("2", "open_project('1')", "Open #2", show=False),
    Binding("3", "open_project('2')", "Open #3", show=False),
    Binding("4", "open_project('3')", "Open #4", show=False),
    Binding("5", "open_project('4')", "Open #5", show=False),
    Binding("6", "open_project('5')", "Open #6", show=False),
    Binding("7", "open_project('6')", "Open #7", show=False),
    Binding("8", "open_project('7')", "Open #8", show=False),
    Binding("9", "open_project('8')", "Open #9", show=False),
]

ONBOARDING_BINDINGS: list[BindingType] = [
    Binding("enter", "continue_setup", "Continue", key_display="Enter"),
    Binding("ctrl+s", "continue_setup", "Continue", key_display="Ctrl+S", show=False),
    Binding("tab", "focus_next", "Next", key_display="Tab", show=False),
    Binding("shift+tab", "focus_previous", "Previous", key_display="Shift+Tab", show=False),
    Binding("escape", "quit", "Quit", key_display="Esc"),
]

PERMISSION_PROMPT_BINDINGS: list[BindingType] = [
    Binding("enter", "allow_once", "Allow once", key_display="Enter"),
    Binding("y", "allow_once", "Allow once", show=False),
    Binding("a", "allow_always", "Allow always", show=False),
    Binding("escape", "deny", "Deny"),
    Binding("n", "deny", "Deny", show=False),
    Binding("d", "deny", "Deny", show=False),
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


def _normalize_help_key_label(label: str) -> str:
    special_tokens = {
        "ctrl": "Ctrl",
        "shift": "Shift",
        "alt": "Alt",
        "escape": "Esc",
        "enter": "Enter",
        "tab": "Tab",
        "space": "space",
    }
    parts = [part.strip() for part in label.split("+")]
    normalized_parts: list[str] = []
    for part in parts:
        token = special_tokens.get(part.casefold())
        if token is not None:
            normalized_parts.append(token)
            continue
        if len(parts) > 1 and len(part) == 1 and part.isalpha():
            normalized_parts.append(part.upper())
            continue
        if part.lower().startswith("f") and part[1:].isdigit():
            normalized_parts.append(part.upper())
            continue
        normalized_parts.append(part)
    return "+".join(normalized_parts)


def get_help_rows_for_actions(
    bindings: list[BindingType],
    specs: list[tuple[str, str, tuple[str, ...] | None]],
) -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for action, description, include_keys in specs:
        keys = [_normalize_help_key_label(key) for key in get_keys_for_action(bindings, action)]
        if include_keys is not None:
            include_order = list(include_keys)
            allowed = set(include_order)
            filtered = [key for key in keys if key in allowed]
            keys = [key for key in include_order if key in filtered]
        if not keys:
            continue
        rows.append((" / ".join(keys), description))
    return rows


def get_global_shortcut_help_rows() -> list[tuple[str, str]]:
    return [
        (" / ".join(get_keys_for_action(APP_BINDINGS, "show_help")), "Help"),
        (
            get_key_for_action(APP_BINDINGS, "command_palette", "Ctrl+Shift+P / ."),
            "Actions palette",
        ),
        (
            get_key_for_action(APP_BINDINGS, "open_project_selector", "Ctrl+Shift+O"),
            "Project selector",
        ),
        (get_key_for_action(APP_BINDINGS, "open_repo_selector", "Ctrl+R"), "Repo selector"),
        (get_key_for_action(APP_BINDINGS, "quit", "Ctrl+Q"), "Quit"),
    ]
