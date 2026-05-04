"""Typed AgentEvent discriminated union for agent task sessions.

This module defines the typed event surface that flows through
``kagan.core._events.Events.emit`` for agent task sessions (i.e. the events
persisted to the ``task_events`` DB table and streamed over SSE to clients).

The ``AgentEvent`` union is the authoritative shape.  Constructors in
``kagan.core._sessions`` and ``kagan.core._acp`` build instances from ACP
updates; the DB stores them as ``event_type = variant.kind``,
``payload = variant.model_dump(mode="json")``.

Shared base variants (MessageStart/Update/End, ToolExecutionStart/Update/End)
live in ``kagan.core.events_common`` — import from there, not here.
"""

from __future__ import annotations

from typing import Annotated, Any, Literal, Union

from pydantic import BaseModel, ConfigDict, Field

from kagan.core.events_common import (
    MessageEnd,
    MessageStart,
    MessageUpdate,
    ToolExecutionEnd,
    ToolExecutionStart,
    ToolExecutionUpdate,
)


class _AgentEventBase(BaseModel):
    """Shared config for agent-session-specific variants."""

    model_config = ConfigDict(frozen=True, extra="forbid")


# ── Agent session lifecycle ───────────────────────────────────────────────────


class AgentStart(_AgentEventBase):
    """The agent session has started and is ready to receive prompts."""

    kind: Literal["agent_start"] = "agent_start"
    session_id: str
    agent_backend: str


class AgentEnd(_AgentEventBase):
    """The agent session has ended.

    ``stop_reason`` values:
    - ``"completed"`` — normal completion
    - ``"error"`` — session failed with an unrecoverable error
    - ``"aborted"`` — user or system-initiated cancellation
    - ``"compacted"`` — context compaction triggered a session restart
    """

    kind: Literal["agent_end"] = "agent_end"
    session_id: str
    stop_reason: Literal["completed", "error", "aborted", "compacted"]


# ── Turn lifecycle ────────────────────────────────────────────────────────────


class TurnStart(_AgentEventBase):
    """A new agent turn (prompt-response cycle) has begun."""

    kind: Literal["turn_start"] = "turn_start"
    turn_index: int


class TurnEnd(_AgentEventBase):
    """An agent turn has completed."""

    kind: Literal["turn_end"] = "turn_end"
    turn_index: int


# ── Context management ────────────────────────────────────────────────────────


class CompactionOccurred(_AgentEventBase):
    """Context compaction was triggered for this session.

    ``threshold`` is the usage ratio (0.0-1.0) that triggered compaction when
    reported by the backend; ``None`` when the backend does not expose it.
    """

    kind: Literal["compaction_occurred"] = "compaction_occurred"
    backend: str
    threshold: float | None = None


# ── ACP-forwarded variants ────────────────────────────────────────────────────
# These carry dict-payload structures forwarded verbatim from ACP updates.
# They are included in the union so that the Events aggregate can accept any
# AgentEvent in its emit_typed() signature.


class OutputChunk(_AgentEventBase):
    """A streamed text chunk from the agent (assistant message or thought)."""

    kind: Literal["output_chunk"] = "output_chunk"
    text: str
    thought: bool = False
    # Raw ACP payload forwarded for downstream rendering compatibility.
    acp: dict[str, Any] | None = None


class AgentStatus(_AgentEventBase):
    """Agent status update (usage snapshot, mode change, etc.).

    The ``acp`` field carries the raw ACP update payload.
    The ``usage`` sub-dict (when present) mirrors ACP's UsageUpdate fields:
    ``used``, ``size``, ``cost``, ``cost_currency``.
    """

    kind: Literal["agent_status"] = "agent_status"
    usage: dict[str, Any] | None = None
    acp: dict[str, Any] | None = None


class ToolCallStart(_AgentEventBase):
    """A tool call dispatched by the agent (ACP ToolCallStart)."""

    kind: Literal["tool_call_start"] = "tool_call_start"
    acp: dict[str, Any]


class ToolCallUpdate(_AgentEventBase):
    """Tool call progress (ACP ToolCallProgress)."""

    kind: Literal["tool_call_update"] = "tool_call_update"
    acp: dict[str, Any]


class PlanUpdate(_AgentEventBase):
    """Agent plan update (ACP AgentPlanUpdate)."""

    kind: Literal["plan_update"] = "plan_update"
    acp: dict[str, Any]


# ── System / lifecycle events ─────────────────────────────────────────────────


class TaskStatusChanged(_AgentEventBase):
    """Task status transition recorded by the session manager."""

    kind: Literal["task_status_changed"] = "task_status_changed"
    from_status: str
    to_status: str


class AgentCompleted(_AgentEventBase):
    """Agent completed successfully."""

    kind: Literal["agent_completed"] = "agent_completed"
    message: str | None = None


class AgentFailed(_AgentEventBase):
    """Agent failed with an error message."""

    kind: Literal["agent_failed"] = "agent_failed"
    message: str | None = None


class MergeCompleted(_AgentEventBase):
    """Worktree merge completed successfully."""

    kind: Literal["merge_completed"] = "merge_completed"
    message: str | None = None


class MergeFailed(_AgentEventBase):
    """Worktree merge failed."""

    kind: Literal["merge_failed"] = "merge_failed"
    message: str | None = None


class CriterionVerdict(_AgentEventBase):
    """AI review verdict for a single acceptance criterion."""

    kind: Literal["criterion_verdict"] = "criterion_verdict"
    verdict: Literal["pass", "fail", "skip"]
    reason: str
    criterion_index: int | None = None


class AutoReviewStarted(_AgentEventBase):
    """Automated review session has started."""

    kind: Literal["auto_review_started"] = "auto_review_started"


class InsightExtracted(_AgentEventBase):
    """An insight note was extracted and persisted."""

    kind: Literal["insight_extracted"] = "insight_extracted"
    content: str
    category: str | None = None


class StepVerified(_AgentEventBase):
    """A plan step was verified."""

    kind: Literal["step_verified"] = "step_verified"
    step_index: int
    step_description: str
    verdict: str
    reason: str


class CheckpointCreated(_AgentEventBase):
    """A git-tag checkpoint was created for the worktree."""

    kind: Literal["checkpoint_created"] = "checkpoint_created"
    step_index: int
    commit_sha: str
    tag_name: str
    description: str | None = None


class SessionRewound(_AgentEventBase):
    """The worktree was hard-reset to a checkpoint commit."""

    kind: Literal["session_rewound"] = "session_rewound"
    step_index: int
    commit_sha: str


class HookBlocked(_AgentEventBase):
    """A pre-commit / CI hook blocked the agent action."""

    kind: Literal["hook_blocked"] = "hook_blocked"
    hook: str
    details: str | None = None


class CompactionTriggered(_AgentEventBase):
    """Context compaction was triggered during an agent session."""

    kind: Literal["compaction_triggered"] = "compaction_triggered"
    backend: str
    threshold: float | None = None


class DoctorWarned(_AgentEventBase):
    """Doctor / environment check emitted a warning."""

    kind: Literal["doctor_warned"] = "doctor_warned"
    message: str
    check: str | None = None


class FirstSessionSuccess(_AgentEventBase):
    """The first successful agent session for this task completed."""

    kind: Literal["first_session_success"] = "first_session_success"


class BackendAutoPromoted(_AgentEventBase):
    """The agent backend was automatically promoted to a better option."""

    kind: Literal["backend_auto_promoted"] = "backend_auto_promoted"
    from_backend: str
    to_backend: str
    reason: str | None = None


# ── Discriminated union ───────────────────────────────────────────────────────

AgentEvent = Annotated[
    Union[  # noqa: UP007 — pydantic discriminator requires typing.Union
        # Session lifecycle
        AgentStart,
        AgentEnd,
        # Turn lifecycle
        TurnStart,
        TurnEnd,
        # Shared base variants (from events_common)
        MessageStart,
        MessageUpdate,
        MessageEnd,
        ToolExecutionStart,
        ToolExecutionUpdate,
        ToolExecutionEnd,
        # Compaction
        CompactionOccurred,
        # Legacy ACP-forwarded variants
        OutputChunk,
        AgentStatus,
        ToolCallStart,
        ToolCallUpdate,
        PlanUpdate,
        # System / lifecycle
        TaskStatusChanged,
        AgentCompleted,
        AgentFailed,
        MergeCompleted,
        MergeFailed,
        CriterionVerdict,
        AutoReviewStarted,
        InsightExtracted,
        StepVerified,
        CheckpointCreated,
        SessionRewound,
        HookBlocked,
        CompactionTriggered,
        DoctorWarned,
        FirstSessionSuccess,
        BackendAutoPromoted,
    ],
    Field(discriminator="kind"),
]


__all__ = [
    "AgentCompleted",
    "AgentEnd",
    "AgentEvent",
    "AgentFailed",
    "AgentStart",
    "AgentStatus",
    "AutoReviewStarted",
    "BackendAutoPromoted",
    "CheckpointCreated",
    "CompactionOccurred",
    "CompactionTriggered",
    "CriterionVerdict",
    "DoctorWarned",
    "FirstSessionSuccess",
    "HookBlocked",
    "InsightExtracted",
    "MergeCompleted",
    "MergeFailed",
    "MessageEnd",
    "MessageStart",
    "MessageUpdate",
    "OutputChunk",
    "PlanUpdate",
    "SessionRewound",
    "StepVerified",
    "TaskStatusChanged",
    "ToolCallStart",
    "ToolCallUpdate",
    "ToolExecutionEnd",
    "ToolExecutionStart",
    "ToolExecutionUpdate",
    "TurnEnd",
    "TurnStart",
]
