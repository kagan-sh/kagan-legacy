"""Chat domain — sessions, messages, conversation engine.

Public API exported here is the only seam transports (CLI/TUI/server) should
use. The legacy `kagan.cli.chat.sessions` raw-SQL helpers are gone — call
`client.chat_sessions.X(...)` instead.
"""

from kagan.core.chat.sessions import (
    CHAT_LAST_SESSION_PREFIX,
    CHAT_SCOPE_PREFIX,
    ChatSessions,
    clean_generated_title,
    format_relative_time,
)

__all__ = [
    "CHAT_LAST_SESSION_PREFIX",
    "CHAT_SCOPE_PREFIX",
    "ChatSessions",
    "clean_generated_title",
    "format_relative_time",
]
