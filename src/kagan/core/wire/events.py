"""Wire event type hierarchy for the Wire protocol.

All events are Pydantic BaseModel for serialization and persistence.
Domain events from core/events.py are bridged to WireEvents, not replaced.
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 - required at runtime for Pydantic model schema
from typing import Any, TypeGuard, cast

from pydantic import BaseModel, Field

from kagan.core.time import utc_now
from kagan.sdk._types import PlanItem  # noqa: TC001 - required for Pydantic model schema


def _now() -> datetime:
    return utc_now()


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------


class WireEvent(BaseModel):
    """Base for all Wire events. Serializable via Pydantic."""

    timestamp: datetime = Field(default_factory=_now)
    task_id: str | None = None  # None for system-level events


# ---------------------------------------------------------------------------
# Domain state changes (from aggregates)
# ---------------------------------------------------------------------------


class TaskCreated(WireEvent):
    """Emitted when a task is created."""

    status: str
    title: str


class TaskTransitioned(WireEvent):
    """Emitted when a task status changes."""

    from_status: str
    to_status: str
    reason: str | None = None


class TaskDeleted(WireEvent):
    """Emitted when a task is deleted."""

    pass


class ProjectOpened(WireEvent):
    """Emitted when a project is opened."""

    project_id: str


class ActiveRepoSwitched(WireEvent):
    """Emitted when the active repo changes. Broadcast to all clients."""

    repo_path: str


class SessionOpened(WireEvent):
    """Emitted when a PAIR session opens."""

    backend: str
    worktree_path: str


class SessionClosed(WireEvent):
    """Emitted when a PAIR session closes."""

    pass


class ReviewRequested(WireEvent):
    """Emitted when a review is requested."""

    pass


class ReviewApproved(WireEvent):
    """Emitted when a review is approved."""

    pass


class TaskMerged(WireEvent):
    """Emitted when a task is merged."""

    merge_strategy: str


class PlanGenerated(WireEvent):
    """Emitted when a plan is generated."""

    items: list[PlanItem] = Field(default_factory=list)


class PlanApproved(WireEvent):
    """Emitted when a plan is approved."""

    created_task_ids: list[str] = Field(default_factory=list)


class PlanDismissed(WireEvent):
    """Emitted when a plan is dismissed (saved as draft)."""

    proposal_id: str | None = None


# ---------------------------------------------------------------------------
# Agent I/O (from running jobs)
# ---------------------------------------------------------------------------


class StreamChunk(WireEvent):
    """Streaming text chunk from agent. Consecutive chunks can be coalesced."""

    text: str = ""

    def merge_in_place(self, other: StreamChunk) -> bool:
        """Merge another chunk into this one. Returns True if merged."""
        if other.task_id != self.task_id:
            return False
        self.text = self.text + other.text
        return True


class ToolExecution(WireEvent):
    """Tool call execution result."""

    tool_name: str
    args: str | dict[str, Any] | None = None
    result: str | dict[str, Any] | None = None


class AgentStep(WireEvent):
    """Agent step boundary."""

    step_number: int


class AgentStatus(WireEvent):
    """Agent runtime status update."""

    status: str | None = None
    message: str | None = None
    tokens_used: int | None = None
    context_pct: float | None = None


class AgentCompleted(WireEvent):
    """Agent run completed successfully."""

    outcome: str | None = None


class AgentFailed(WireEvent):
    """Agent run failed."""

    error: str


# ---------------------------------------------------------------------------
# Interaction
# ---------------------------------------------------------------------------


class PermissionPrompt(WireEvent):
    """Request for user permission before proceeding."""

    tool_name: str
    description: str


class PermissionResponse(WireEvent):
    """Response to a permission prompt."""

    approved: bool


class FollowUpQueued(WireEvent):
    """Follow-up message queued for agent."""

    message: str


class FollowUpDelivered(WireEvent):
    """Follow-up message delivered to agent."""

    message: str


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------


class JobStarted(WireEvent):
    """Job started."""

    job_id: str


class JobCancelled(WireEvent):
    """Job cancelled."""

    job_id: str


# ---------------------------------------------------------------------------
# GitHub plugin
# ---------------------------------------------------------------------------


class PRCreated(WireEvent):
    """PR created for a repo."""

    pr_number: int | str
    url: str


class PRMerged(WireEvent):
    """PR merged."""

    pr_number: int | str


class CIStatusChecked(WireEvent):
    """CI status checked."""

    overall: str
    checks: list[dict[str, Any]] = Field(default_factory=list)


class IssuesSynced(WireEvent):
    """GitHub issues synced."""

    created_count: int = 0
    updated_count: int = 0


# ---------------------------------------------------------------------------
# Type union and envelope
# ---------------------------------------------------------------------------

WireEventType = (
    TaskCreated
    | TaskTransitioned
    | TaskDeleted
    | ProjectOpened
    | ActiveRepoSwitched
    | SessionOpened
    | SessionClosed
    | ReviewRequested
    | ReviewApproved
    | TaskMerged
    | PlanGenerated
    | PlanApproved
    | PlanDismissed
    | StreamChunk
    | ToolExecution
    | AgentStep
    | AgentStatus
    | AgentCompleted
    | AgentFailed
    | PermissionPrompt
    | PermissionResponse
    | FollowUpQueued
    | FollowUpDelivered
    | JobStarted
    | JobCancelled
    | PRCreated
    | PRMerged
    | CIStatusChecked
    | IssuesSynced
)

_WIRE_EVENT_TYPES: tuple[type[WireEvent], ...] = (
    TaskCreated,
    TaskTransitioned,
    TaskDeleted,
    ProjectOpened,
    ActiveRepoSwitched,
    SessionOpened,
    SessionClosed,
    ReviewRequested,
    ReviewApproved,
    TaskMerged,
    PlanGenerated,
    PlanApproved,
    PlanDismissed,
    StreamChunk,
    ToolExecution,
    AgentStep,
    AgentStatus,
    AgentCompleted,
    AgentFailed,
    PermissionPrompt,
    PermissionResponse,
    FollowUpQueued,
    FollowUpDelivered,
    JobStarted,
    JobCancelled,
    PRCreated,
    PRMerged,
    CIStatusChecked,
    IssuesSynced,
)

_NAME_TO_TYPE: dict[str, type[WireEvent]] = {cls.__name__: cls for cls in _WIRE_EVENT_TYPES}


def is_wire_event(msg: Any) -> TypeGuard[WireEventType]:
    """Check if the message is a WireEvent."""
    return isinstance(msg, _WIRE_EVENT_TYPES)


class WireEventEnvelope(BaseModel):
    """Type-discriminated envelope for JSON round-trip of WireEvents."""

    type: str
    payload: dict[str, Any]

    @classmethod
    def from_wire_event(cls, event: WireEvent) -> WireEventEnvelope:
        """Wrap a WireEvent for serialization."""
        typename = type(event).__name__
        if typename not in _NAME_TO_TYPE:
            raise ValueError(f"Unknown wire event type: {typename}")
        return cls(
            type=typename,
            payload=event.model_dump(mode="json"),
        )

    def to_wire_event(self) -> WireEventType:
        """Unwrap envelope back to WireEvent."""
        event_type = _NAME_TO_TYPE.get(self.type)
        if event_type is None:
            raise ValueError(f"Unknown wire event type: {self.type}")
        return cast("WireEventType", event_type.model_validate(self.payload))


__all__ = [
    "ActiveRepoSwitched",
    "AgentCompleted",
    "AgentFailed",
    "AgentStatus",
    "AgentStep",
    "CIStatusChecked",
    "FollowUpDelivered",
    "FollowUpQueued",
    "IssuesSynced",
    "JobCancelled",
    "JobStarted",
    "PRCreated",
    "PRMerged",
    "PermissionPrompt",
    "PermissionResponse",
    "PlanApproved",
    "PlanDismissed",
    "PlanGenerated",
    "ProjectOpened",
    "ReviewApproved",
    "ReviewRequested",
    "SessionClosed",
    "SessionOpened",
    "StreamChunk",
    "TaskCreated",
    "TaskDeleted",
    "TaskMerged",
    "TaskTransitioned",
    "ToolExecution",
    "WireEvent",
    "WireEventEnvelope",
    "WireEventType",
    "is_wire_event",
]
