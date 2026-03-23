"""Task lifecycle state machine."""

from loguru import logger

from kagan.core.enums import TaskStatus
from kagan.core.errors import InvalidTransitionError

_ALLOWED: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset(
    {
        (TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS),
        (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW),
        (TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG),
        (TaskStatus.REVIEW, TaskStatus.IN_PROGRESS),
        (TaskStatus.REVIEW, TaskStatus.BACKLOG),
        (TaskStatus.DONE, TaskStatus.BACKLOG),
    }
)

_MERGE_ALLOWED: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset(
    {
        (TaskStatus.REVIEW, TaskStatus.DONE),
    }
)


def can_move(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    return (from_status, to_status) in _ALLOWED


def validate_move(from_status: TaskStatus, to_status: TaskStatus) -> None:
    if not can_move(from_status, to_status):
        logger.warning("Invalid transition: {} -> {}", from_status.value, to_status.value)
        raise InvalidTransitionError(from_status, to_status)
    logger.debug("Transition validated: {} -> {}", from_status.value, to_status.value)


def can_merge_move(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    return (from_status, to_status) in _MERGE_ALLOWED


def validate_merge_move(from_status: TaskStatus, to_status: TaskStatus) -> None:
    if not can_merge_move(from_status, to_status):
        raise InvalidTransitionError(from_status, to_status)


def allowed_targets(status: TaskStatus) -> list[TaskStatus]:
    """Return valid transition targets for a given status (excluding merge-only)."""
    return [to for (frm, to) in _ALLOWED if frm == status]


def all_allowed_targets(status: TaskStatus) -> list[TaskStatus]:
    """Return all valid targets including merge transitions."""
    merge = [to for (frm, to) in _MERGE_ALLOWED if frm == status]
    return allowed_targets(status) + merge
