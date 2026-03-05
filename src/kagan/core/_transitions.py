"""Task lifecycle state machine for kagan.core.

Valid transitions (for task.move — direct user moves):

    BACKLOG     → IN_PROGRESS
    IN_PROGRESS → REVIEW
    IN_PROGRESS → BACKLOG
    REVIEW      → IN_PROGRESS
    REVIEW      → BACKLOG
    DONE        → BACKLOG

REVIEW → DONE is intentionally excluded from task.move().
Only review.merge() may transition a task to DONE; use validate_merge_move / can_merge_move.
"""

from loguru import logger

from kagan.core.enums import TaskStatus
from kagan.core.errors import InvalidTransitionError

# Transitions allowed via task.move() — direct user-initiated moves.
# REVIEW → DONE is absent: only review.merge() may set DONE.
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

# Transitions allowed only via review.merge().
_MERGE_ALLOWED: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset(
    {
        (TaskStatus.REVIEW, TaskStatus.DONE),
    }
)


def can_move(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """Return True if the transition is valid for task.move()."""
    return (from_status, to_status) in _ALLOWED


def validate_move(from_status: TaskStatus, to_status: TaskStatus) -> None:
    """Raise InvalidTransitionError if the transition is not valid for task.move().

    Does not permit REVIEW → DONE; that path is reserved for review.merge().
    """
    if not can_move(from_status, to_status):
        logger.warning("Invalid transition: {} -> {}", from_status.value, to_status.value)
        raise InvalidTransitionError(from_status, to_status)
    logger.debug("Transition validated: {} -> {}", from_status.value, to_status.value)


def can_merge_move(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """Return True if the transition is valid for review.merge()."""
    return (from_status, to_status) in _MERGE_ALLOWED


def validate_merge_move(from_status: TaskStatus, to_status: TaskStatus) -> None:
    """Raise InvalidTransitionError if the transition is not valid for review.merge()."""
    if not can_merge_move(from_status, to_status):
        raise InvalidTransitionError(from_status, to_status)
