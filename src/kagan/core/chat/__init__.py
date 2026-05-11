"""Chat domain — sessions, messages, conversation engine.

Public API exported here is the only seam transports (CLI/TUI/server) should
use. The legacy `kagan.cli.chat.sessions` raw-SQL helpers are gone — call
`client.chat_sessions.X(...)` instead. New surfaces should consume
`client.chat` (the :class:`ChatEngine`) rather than driving ACP directly.
"""

from kagan.core.chat._attach import (
    AgentNotificationKind,
    notify_project_chat_sessions,
    record_agent_lifecycle_event,
)
from kagan.core.chat._factories import LongLivedACPFactory, make_raw_backend_acp_factory
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
from kagan.core.chat.sessions import (
    CHAT_LAST_SESSION_PREFIX,
    CHAT_SCOPE_PREFIX,
    ChatSessions,
    ChatSessionView,
    chat_session_to_view,
    clean_generated_title,
    format_relative_time,
)
from kagan.core.events import (
    AgentLifecycle,
    AssistantChunk,
    AssistantMessagePersisted,
    Error,
    Event,
    ThinkingChunk,
    ToolCall,
    ToolCallResult,
    ToolCallUpdate,
    TurnEnd,
    TurnStart,
    UsageUpdate,
    UserMessagePersisted,
)
from kagan.core.permission import PermissionRequest, PermissionResolved

# ``ChatEvent`` is kept as an alias for ``Event`` — it is the public name
# used by transport layers (CLI/TUI/server) to type-annotate the stream.
ChatEvent = Event

__all__ = [
    "CHAT_LAST_SESSION_PREFIX",
    "CHAT_SCOPE_PREFIX",
    "ACPSessionFactory",
    "ACPTurnResult",
    "AgentLifecycle",
    "AgentNotificationKind",
    "AssistantChunk",
    "AssistantMessagePersisted",
    "CancelResult",
    "ChatEngine",
    "ChatEvent",
    "ChatSessionView",
    "ChatSessions",
    "Error",
    "Event",
    "LongLivedACPFactory",
    "PermissionRequest",
    "PermissionResolved",
    "ThinkingChunk",
    "ToolCall",
    "ToolCallResult",
    "ToolCallUpdate",
    "TurnEnd",
    "TurnInProgressError",
    "TurnStart",
    "TurnStatus",
    "UsageSnapshot",
    "UsageUpdate",
    "UserMessagePersisted",
    "acp_update_to_chat_event",
    "chat_session_to_view",
    "clean_generated_title",
    "format_relative_time",
    "make_raw_backend_acp_factory",
    "make_spawn_per_turn_acp_factory",
    "notify_project_chat_sessions",
    "record_agent_lifecycle_event",
    "run_spawn_per_turn_acp_prompt",
]
