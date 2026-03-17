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
