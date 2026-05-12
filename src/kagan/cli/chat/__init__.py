"""Chat module — orchestrator chat, slash commands, sessions, and REPL.

Public API re-exported from private sub-modules.
"""

from kagan.cli.chat._session_picker import (
    ChatSessionListItem,
    ChatSessionView,
    build_chat_session_list_items,
    chat_session_to_view,
    resolve_chat_session_selector,
)
from kagan.cli.chat._title import ensure_session_title, generate_session_title, is_default_title
from kagan.cli.chat._utils import fuzzy_match
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
from kagan.core.chat.sessions import CHAT_LAST_SESSION_PREFIX, CHAT_SCOPE_PREFIX

__all__ = [
    "CHAT_LAST_SESSION_PREFIX",
    "CHAT_SCOPE_PREFIX",
    "SLASH_COMMAND_REGISTRY",
    "ChatController",
    "ChatSessionListItem",
    "ChatSessionView",
    "SlashAction",
    "SlashCommandInvocation",
    "SlashCommandOutcome",
    "SlashCommandRegistry",
    "SlashCommandSpec",
    "SlashPresentationLine",
    "build_chat_session_list_items",
    "build_chat_status_line",
    "build_orchestrator_prompt",
    "build_slash_presentation_lines",
    "chat_session_to_view",
    "ensure_session_title",
    "format_agent_backend_list",
    "format_agent_usage",
    "format_session_payload",
    "format_unknown_slash_command",
    "fuzzy_match",
    "generate_session_title",
    "is_default_title",
    "list_registered_agent_backends",
    "merge_task_follow_up_description",
    "normalize_chat_input",
    "parse_slash_invocation",
    "resolve_agent_backend_selection",
    "resolve_agent_command_argument",
    "resolve_chat_session_selector",
    "resolve_default_agent_backend",
    "resolve_slash_command",
    "resolve_slash_input",
    "run_chat",
    "run_chat_async",
    "run_orchestrator_turn",
    "warm_orchestrator_backend",
]
