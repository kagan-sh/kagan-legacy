"""Task lifecycle state machine."""

from __future__ import annotations

from enum import StrEnum

from loguru import logger

from kagan.core.enums import TaskStatus
from kagan.core.errors import InvalidTransitionError


class Trigger(StrEnum):
    """Named lifecycle events that drive task status transitions."""

    START = "START"  # BACKLOG → IN_PROGRESS
    AGENT_DONE = "AGENT_DONE"  # IN_PROGRESS → REVIEW
    AGENT_CANCELLED = "AGENT_CANCELLED"  # IN_PROGRESS → BACKLOG
    REVIEW_REJECT = "REVIEW_REJECT"  # REVIEW → IN_PROGRESS
    MERGE = "MERGE"  # REVIEW → DONE
    REQUEUE = "REQUEUE"  # IN_PROGRESS|REVIEW|DONE → BACKLOG


# Single source of truth: status → trigger → next status.
_TRANSITIONS: dict[TaskStatus, dict[Trigger, TaskStatus]] = {
    TaskStatus.BACKLOG: {
        Trigger.START: TaskStatus.IN_PROGRESS,
    },
    TaskStatus.IN_PROGRESS: {
        Trigger.AGENT_DONE: TaskStatus.REVIEW,
        Trigger.AGENT_CANCELLED: TaskStatus.BACKLOG,
        Trigger.REQUEUE: TaskStatus.BACKLOG,
    },
    TaskStatus.REVIEW: {
        Trigger.REVIEW_REJECT: TaskStatus.IN_PROGRESS,
        Trigger.MERGE: TaskStatus.DONE,
        Trigger.REQUEUE: TaskStatus.BACKLOG,
    },
    TaskStatus.DONE: {
        Trigger.REQUEUE: TaskStatus.BACKLOG,
    },
}

# MERGE is reserved for the merge action; direct move_task() must not satisfy it.
_MOVE_ALLOWED: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset(
    (from_status, to_status)
    for from_status, triggers in _TRANSITIONS.items()
    for trigger, to_status in triggers.items()
    if trigger is not Trigger.MERGE
)

_MERGE_ALLOWED: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset(
    (from_status, to_status)
    for from_status, triggers in _TRANSITIONS.items()
    for trigger, to_status in triggers.items()
    if trigger is Trigger.MERGE
)


def transition(from_status: TaskStatus, trigger: Trigger) -> TaskStatus:
    """Return the destination status for *trigger* from *from_status*.

    Raises InvalidTransitionError when the trigger is not valid from the
    current status.
    """
    targets = _TRANSITIONS.get(from_status, {})
    if trigger not in targets:
        raise InvalidTransitionError(from_status, trigger)  # type: ignore[arg-type]
    return targets[trigger]


def can_move(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    return (from_status, to_status) in _MOVE_ALLOWED


def validate_move(from_status: TaskStatus, to_status: TaskStatus) -> None:
    if not can_move(from_status, to_status):
        logger.warning("Invalid transition: {} -> {}", from_status.value, to_status.value)
        raise InvalidTransitionError(from_status, to_status)
    logger.debug("Transition validated: {} -> {}", from_status.value, to_status.value)


def validate_merge_move(from_status: TaskStatus, to_status: TaskStatus) -> None:
    if (from_status, to_status) not in _MOVE_ALLOWED | _MERGE_ALLOWED:
        logger.warning("Invalid merge transition: {} -> {}", from_status.value, to_status.value)
        raise InvalidTransitionError(from_status, to_status)


def allowed_targets(status: TaskStatus) -> list[TaskStatus]:
    """Return valid direct-move targets (excludes merge-only)."""
    return [to for (frm, to) in _MOVE_ALLOWED if frm == status]


def all_allowed_targets(status: TaskStatus) -> list[TaskStatus]:
    """Return all valid targets including merge."""
    return [to for (frm, to) in _MOVE_ALLOWED | _MERGE_ALLOWED if frm == status]
