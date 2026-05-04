"""Chat domain — sessions, messages, conversation engine.

Public API exported here is the only seam transports (CLI/TUI/server) should
use. The legacy `kagan.cli.chat.sessions` raw-SQL helpers are gone — call
`client.chat_sessions.X(...)` instead. New surfaces should consume
`client.chat` (the :class:`ChatEngine`) rather than driving ACP directly.
"""

from kagan.core.chat._factories import LongLivedACPFactory
from kagan.core.chat.acp import (
    ACPSessionFactory,
    ACPTurnResult,
    SpawnPerTurnACPFactory,
    UsageSnapshot,
    acp_update_to_chat_event,
)
from kagan.core.chat.engine import (
    CancelResult,
    ChatEngine,
    TurnInProgressError,
    TurnStatus,
)
from kagan.core.chat.events import (
    AssistantChunk,
    AssistantMessagePersisted,
    ChatEvent,
    PermissionRequest,
    PermissionResolved,
    ToolCallProgress,
    ToolCallStart,
    TurnCancelled,
    TurnDone,
    TurnError,
    TurnStarted,
    UsageUpdate,
    UserMessagePersisted,
)
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
    "ACPSessionFactory",
    "ACPTurnResult",
    "AssistantChunk",
    "AssistantMessagePersisted",
    "CancelResult",
    "ChatEngine",
    "ChatEvent",
    "ChatSessions",
    "LongLivedACPFactory",
    "PermissionRequest",
    "PermissionResolved",
    "SpawnPerTurnACPFactory",
    "ToolCallProgress",
    "ToolCallStart",
    "TurnCancelled",
    "TurnDone",
    "TurnError",
    "TurnInProgressError",
    "TurnStarted",
    "TurnStatus",
    "UsageSnapshot",
    "UsageUpdate",
    "UserMessagePersisted",
    "acp_update_to_chat_event",
    "clean_generated_title",
    "format_relative_time",
]
