"""Core enums for kagan.core — task lifecycle, execution modes, and event types."""

from enum import IntEnum, StrEnum


class TaskStatus(StrEnum):
    BACKLOG = "BACKLOG"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    DONE = "DONE"


class WorkMode(StrEnum):
    AUTO = "AUTO"
    PAIR = "PAIR"


class SessionStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class Priority(IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3


class SessionEventType(StrEnum):
    OUTPUT_CHUNK = "OUTPUT_CHUNK"
    AGENT_STATUS = "AGENT_STATUS"
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_UPDATE = "TOOL_CALL_UPDATE"
    AGENT_COMPLETED = "AGENT_COMPLETED"
    AGENT_FAILED = "AGENT_FAILED"
    PLAN_UPDATE = "PLAN_UPDATE"
    TASK_STATUS_CHANGED = "TASK_STATUS_CHANGED"
    MERGE_COMPLETED = "MERGE_COMPLETED"
    MERGE_FAILED = "MERGE_FAILED"
    CRITERION_VERDICT = "CRITERION_VERDICT"
    AUTO_REVIEW_STARTED = "AUTO_REVIEW_STARTED"


class AgentRole(StrEnum):
    WORKER = "WORKER"
    REVIEWER = "REVIEWER"
    ORCHESTRATOR = "ORCHESTRATOR"


class BranchRefStrategy(StrEnum):
    LOCAL = "local"
    REMOTE = "remote"
    LOCAL_IF_AHEAD = "local_if_ahead"


class SessionKind(StrEnum):
    """Kind of chat session in the TUI."""

    ORCHESTRATOR = "orchestrator"
    AUTO = "auto"
    REVIEW = "review"
    PAIR = "pair"


class ChatMode(StrEnum):
    """Chat panel mode."""

    ORCHESTRATOR = "orchestrator"
    TASK = "task"


class StreamSource(StrEnum):
    """Source of agent output stream."""

    WORKER = "worker"
    REVIEWER = "reviewer"


class ReviewStrictness(StrEnum):
    """Review strictness level."""

    STRICT = "strict"
    BALANCED = "balanced"
    RELAXED = "relaxed"


class PlanningDepth(StrEnum):
    """Planning depth setting."""

    ALWAYS = "always"
    MULTI_TASK = "multi_task"
    NEVER = "never"


class ExecutionModeChoice(StrEnum):
    """Default execution mode choice (includes 'ask' UI option)."""

    ASK = "ask"
    AUTO = "auto"
    PAIR = "pair"


class WsMessageType(StrEnum):
    """WebSocket protocol message types."""

    # Client → Server
    PING = "PING"
    BOARD_SUBSCRIBE = "BOARD_SUBSCRIBE"
    RUN_START = "RUN_START"
    RUN_CANCEL = "RUN_CANCEL"
    CHAT_SUBSCRIBE = "CHAT_SUBSCRIBE"
    CHAT_SEND = "CHAT_SEND"
    CHAT_INTERRUPT = "CHAT_INTERRUPT"
    TASK_FOLLOW_UP = "TASK_FOLLOW_UP"
    # Server → Client
    PONG = "PONG"
    BOARD_SYNC = "BOARD_SYNC"
    TASK_UPDATED = "TASK_UPDATED"
    SESSION_EVENT = "SESSION_EVENT"
    RUN_STARTED = "RUN_STARTED"
    RUN_CANCELLED = "RUN_CANCELLED"
    RUN_ERROR = "RUN_ERROR"
    CHAT_CHUNK = "CHAT_CHUNK"
    CHAT_TOOL_START = "CHAT_TOOL_START"
    CHAT_TOOL_PROGRESS = "CHAT_TOOL_PROGRESS"
    CHAT_DONE = "CHAT_DONE"
    CHAT_ERROR = "CHAT_ERROR"
    CHAT_INTERRUPTED = "CHAT_INTERRUPTED"
    CHAT_SESSION_UPDATED = "CHAT_SESSION_UPDATED"
    CHAT_SUBSCRIBED = "CHAT_SUBSCRIBED"
    CHAT_BUSY = "CHAT_BUSY"
    TOOL_PERMISSION_REQUEST = "TOOL_PERMISSION_REQUEST"
    FOLLOW_UP_QUEUED = "FOLLOW_UP_QUEUED"
    FOLLOW_UP_SENT = "FOLLOW_UP_SENT"
    TASK_FOLLOW_UP_ACK = "TASK_FOLLOW_UP_ACK"
    TASK_FOLLOW_UP_ERROR = "TASK_FOLLOW_UP_ERROR"


def parse_priority(value: str | int | None) -> Priority:
    """Parse a string, int, or None into a Priority enum value."""
    if value is None:
        return Priority.MEDIUM
    if isinstance(value, int):
        return Priority(value)
    if value.isdigit():
        return Priority(int(value))
    return Priority[value]


def parse_work_mode(value: str | None) -> WorkMode:
    """Parse a string or None into a WorkMode enum value."""
    return WorkMode(value) if value else WorkMode.AUTO
