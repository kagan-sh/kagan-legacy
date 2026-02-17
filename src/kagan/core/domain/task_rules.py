"""Task lifecycle transition rules — single source of truth.

All task status transition logic is consolidated here.  Every function is pure
(no I/O, no side-effects) so the module can be unit-tested in isolation.
"""

from __future__ import annotations

from kagan.core.domain.enums import TaskStatus

# ---------------------------------------------------------------------------
# Transition table
# ---------------------------------------------------------------------------

_TASK_LIFECYCLE_TRANSITIONS: dict[str, dict[TaskStatus, TaskStatus]] = {
    "agent_complete_success": {
        TaskStatus.BACKLOG: TaskStatus.BACKLOG,
        TaskStatus.IN_PROGRESS: TaskStatus.REVIEW,
        TaskStatus.REVIEW: TaskStatus.REVIEW,
        TaskStatus.DONE: TaskStatus.DONE,
    },
    "agent_complete_failure": {
        TaskStatus.BACKLOG: TaskStatus.BACKLOG,
        TaskStatus.IN_PROGRESS: TaskStatus.IN_PROGRESS,
        TaskStatus.REVIEW: TaskStatus.REVIEW,
        TaskStatus.DONE: TaskStatus.DONE,
    },
    "review_pass": {
        TaskStatus.BACKLOG: TaskStatus.BACKLOG,
        TaskStatus.IN_PROGRESS: TaskStatus.IN_PROGRESS,
        TaskStatus.REVIEW: TaskStatus.DONE,
        TaskStatus.DONE: TaskStatus.DONE,
    },
    "review_reject": {
        TaskStatus.BACKLOG: TaskStatus.BACKLOG,
        TaskStatus.IN_PROGRESS: TaskStatus.IN_PROGRESS,
        TaskStatus.REVIEW: TaskStatus.IN_PROGRESS,
        TaskStatus.DONE: TaskStatus.DONE,
    },
}

# Statuses that may be reached via direct move/update (DONE is excluded).
_DIRECTLY_MOVABLE: frozenset[TaskStatus] = frozenset(TaskStatus) - {TaskStatus.DONE}

DONE_TRANSITION_ERROR = (
    "Direct move/update to DONE is not allowed. "
    "Use review merge (or close no-change flow) from REVIEW."
)

# ---------------------------------------------------------------------------
# Public helpers
# ---------------------------------------------------------------------------


def can_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """Return whether a direct user-initiated move from *from_status* to *to_status* is allowed."""
    return to_status in _DIRECTLY_MOVABLE


def validate_transition(from_status: TaskStatus, to_status: TaskStatus) -> None:
    """Raise ``ValueError`` when a direct move to *to_status* is forbidden."""
    if not can_transition(from_status, to_status):
        raise ValueError(DONE_TRANSITION_ERROR)


# ---------------------------------------------------------------------------
# Agent-complete / review resolution
# ---------------------------------------------------------------------------


def resolve_status_after_review(action: str, current_status: TaskStatus) -> TaskStatus:
    """Return the next status after a review *action* (``"pass"`` or ``"reject"``)."""
    key = {"pass": "review_pass", "reject": "review_reject"}.get(action)
    if key is None:
        raise ValueError(f"Unknown review action: {action!r}")
    return _TASK_LIFECYCLE_TRANSITIONS[key][current_status]


def resolve_status_after_agent_complete(current_status: TaskStatus, *, success: bool) -> TaskStatus:
    """Return the next status after an agent run completes."""
    key = "agent_complete_success" if success else "agent_complete_failure"
    return _TASK_LIFECYCLE_TRANSITIONS[key][current_status]


# ---------------------------------------------------------------------------
# Compat shims — keep old names importable during migration
# ---------------------------------------------------------------------------


def transition_status_from_agent_complete(current_status: TaskStatus, success: bool) -> TaskStatus:
    """Return next status after an implementation agent run completes."""
    return resolve_status_after_agent_complete(current_status, success=success)


def transition_status_from_review_pass(current_status: TaskStatus) -> TaskStatus:
    """Return next status after review approval."""
    return _TASK_LIFECYCLE_TRANSITIONS["review_pass"][current_status]


def transition_status_from_review_reject(current_status: TaskStatus) -> TaskStatus:
    """Return next status after review rejection."""
    return _TASK_LIFECYCLE_TRANSITIONS["review_reject"][current_status]
