"""Chat domain — sessions, messages, conversation engine.

Public API exported here is the only seam transports (CLI/TUI/server) should
use. The legacy `kagan.cli.chat.sessions` raw-SQL helpers are gone — call
`client.chat_sessions.X(...)` instead. New surfaces should consume
`client.chat` (the :class:`ChatEngine`) rather than driving ACP directly.
"""

from kagan.core.chat._attach import (
    AgentNotificationKind,
    attach_chat_to_session,
    notify_project_chat_sessions,
    record_agent_lifecycle_event,
)
from kagan.core.chat._factories import LongLivedACPFactory
from kagan.core.chat.acp import (
    ACPSessionFactory,
    ACPTurnResult,
    UsageSnapshot,
    acp_update_to_chat_event,
    make_spawn_per_turn_acp_factory,
    run_spawn_per_turn_acp_prompt,
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
    ChatSessionView,
    chat_session_to_view,
    clean_generated_title,
    format_relative_time,
)

__all__ = [
    "CHAT_LAST_SESSION_PREFIX",
    "CHAT_SCOPE_PREFIX",
    "ACPSessionFactory",
    "ACPTurnResult",
    "AgentNotificationKind",
    "AssistantChunk",
    "AssistantMessagePersisted",
    "CancelResult",
    "ChatEngine",
    "ChatEvent",
    "ChatSessionView",
    "ChatSessions",
    "LongLivedACPFactory",
    "PermissionRequest",
    "PermissionResolved",
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
    "attach_chat_to_session",
    "chat_session_to_view",
    "clean_generated_title",
    "format_relative_time",
    "make_spawn_per_turn_acp_factory",
    "notify_project_chat_sessions",
    "record_agent_lifecycle_event",
    "run_spawn_per_turn_acp_prompt",
]
