"""Core enums for kagan.core — task lifecycle and event types."""

from enum import IntEnum, StrEnum


class TaskStatus(StrEnum):
    BACKLOG = "BACKLOG"
    IN_PROGRESS = "IN_PROGRESS"
    REVIEW = "REVIEW"
    DONE = "DONE"


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
    INSIGHT_EXTRACTED = "INSIGHT_EXTRACTED"
    STEP_VERIFIED = "STEP_VERIFIED"
    CHECKPOINT_CREATED = "CHECKPOINT_CREATED"
    SESSION_REWOUND = "SESSION_REWOUND"
    HOOK_BLOCKED = "HOOK_BLOCKED"
    COMPACTION_TRIGGERED = "COMPACTION_TRIGGERED"


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
    DETACHED = "detached"
    REVIEW = "review"
    ATTACHED = "attached"


class ChatMode(StrEnum):
    """Chat panel mode."""

    ORCHESTRATOR = "orchestrator"
    TASK = "task"


class StreamSource(StrEnum):
    """Source of agent output stream."""

    WORKER = "worker"
    REVIEWER = "reviewer"


class TaskType(StrEnum):
    """Task classification types for analytics and intelligent routing."""

    CODE_IMPLEMENTATION = "code_implementation"
    BUG_FIX = "bug_fix"
    REFACTORING = "refactoring"
    DOCUMENTATION = "documentation"
    ARCHITECTURE = "architecture"
    DESIGN = "design"
    ANALYSIS = "analysis"
    TESTING = "testing"
    DEPLOYMENT = "deployment"
    INVESTIGATION = "investigation"
    OPTIMIZATION = "optimization"
    UNKNOWN = "unknown"  # Fallback for unclassified tasks


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


def parse_priority(value: str | int | None) -> Priority:
    """Parse a string, int, or None into a Priority enum value."""
    if value is None:
        return Priority.MEDIUM
    if isinstance(value, int):
        return Priority(value)
    if value.isdigit():
        return Priority(int(value))
    return Priority[value]
