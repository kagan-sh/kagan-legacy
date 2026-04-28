"""Chat module — orchestrator chat, slash commands, sessions, and REPL.

Public API re-exported from private sub-modules.
"""

from kagan.cli.chat._completion import fuzzy_match
from kagan.cli.chat._title import ensure_session_title, generate_session_title, is_default_title
from kagan.cli.chat.acp import run_orchestrator_turn, warm_orchestrator_backend
from kagan.cli.chat.agents import (
    format_agent_backend_list,
    format_agent_usage,
    list_registered_agent_backends,
    resolve_agent_backend_selection,
    resolve_agent_command_argument,
    resolve_default_agent_backend,
)
from kagan.cli.chat.commands import (
    SLASH_COMMAND_REGISTRY,
    SlashAction,
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
from kagan.cli.chat.controller import (
    ChatController,
)
from kagan.cli.chat.prompt import (
    build_chat_status_line,
    build_orchestrator_prompt,
    format_session_payload,
    merge_task_follow_up_description,
    normalize_chat_input,
)
from kagan.cli.chat.repl import (
    run_chat,
    run_chat_async,
)
from kagan.cli.chat.sessions import (
    CHAT_LAST_SESSION_PREFIX,
    CHAT_SCOPE_PREFIX,
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
    "SLASH_COMMAND_REGISTRY",
    "ChatController",
    "SlashAction",
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
