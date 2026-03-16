"""Chat module — orchestrator chat, slash commands, sessions, and REPL.

Public API re-exported from private sub-modules.
"""

from kagan.chat._completion import fuzzy_match
from kagan.chat._title import ensure_session_title, generate_session_title, is_default_title
from kagan.chat.acp import run_orchestrator_turn, warm_orchestrator_backend
from kagan.chat.agents import (
    format_agent_backend_list,
    format_agent_switching,
    format_agent_usage,
    list_registered_agent_backends,
    resolve_agent_backend_selection,
    resolve_agent_command_argument,
    resolve_default_agent_backend,
)
from kagan.chat.commands import (
    SLASH_COMMAND_REGISTRY,
    SlashCommandInvocation,
    SlashCommandOutcome,
    SlashCommandRegistry,
    SlashCommandSpec,
    SlashPresentationLine,
    build_slash_presentation_lines,
    format_unknown_slash_command,
    parse_slash_invocation,
    resolve_slash_command,
    resolve_slash_input,
)
from kagan.chat.controller import (
    ChatController,
)
from kagan.chat.prompt import (
    build_chat_status_line,
    build_orchestrator_prompt,
    format_session_payload,
    merge_task_follow_up_description,
    normalize_chat_input,
)
from kagan.chat.repl import (
    run_chat,
    run_chat_async,
)
from kagan.chat.sessions import (
    CHAT_LAST_SESSION_PREFIX,
    CHAT_SCOPE_PREFIX,
    CHAT_SESSIONS_SETTING_KEY,
    MAX_STORED_HISTORY,
    MAX_STORED_MESSAGES,
    MAX_STORED_SESSIONS,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    get_last_session_id,
    get_scope_state,
    list_chat_sessions,
    save_chat_session,
    save_scope_state,
    set_last_session_id,
)

__all__ = [
    "CHAT_LAST_SESSION_PREFIX",
    "CHAT_SCOPE_PREFIX",
    "CHAT_SESSIONS_SETTING_KEY",
    "MAX_STORED_HISTORY",
    "MAX_STORED_MESSAGES",
    "MAX_STORED_SESSIONS",
    "SLASH_COMMAND_REGISTRY",
    "ChatController",
    "SlashCommandInvocation",
    "SlashCommandOutcome",
    "SlashCommandRegistry",
    "SlashCommandSpec",
    "SlashPresentationLine",
    "build_chat_status_line",
    "build_orchestrator_prompt",
    "build_slash_presentation_lines",
    "create_chat_session",
    "delete_chat_session",
    "ensure_session_title",
    "format_agent_backend_list",
    "format_agent_switching",
    "format_agent_usage",
    "format_session_payload",
    "format_unknown_slash_command",
    "fuzzy_match",
    "generate_session_title",
    "get_chat_session",
    "get_last_session_id",
    "get_scope_state",
    "is_default_title",
    "list_chat_sessions",
    "list_registered_agent_backends",
    "merge_task_follow_up_description",
    "normalize_chat_input",
    "parse_slash_invocation",
    "resolve_agent_backend_selection",
    "resolve_agent_command_argument",
    "resolve_default_agent_backend",
    "resolve_slash_command",
    "resolve_slash_input",
    "run_chat",
    "run_chat_async",
    "run_orchestrator_turn",
    "save_chat_session",
    "save_scope_state",
    "set_last_session_id",
    "warm_orchestrator_backend",
]
