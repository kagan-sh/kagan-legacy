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
    """Task priority — higher value means higher urgency."""

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


class BranchRefStrategy(StrEnum):
    """How to resolve the base ref when diffing or creating worktrees.

    LOCAL          — always use the local branch.
    REMOTE         — always prefer origin/<branch>.
    LOCAL_IF_AHEAD — use local when it has commits ahead of origin,
                     otherwise fall back to origin/<branch>.
    """

    LOCAL = "local"
    REMOTE = "remote"
    LOCAL_IF_AHEAD = "local_if_ahead"
