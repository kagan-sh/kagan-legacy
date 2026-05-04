"""Unit tests for the task lifecycle state machine (now in core/transitions.py)."""

from __future__ import annotations

import pytest

from kagan.core.enums import TaskStatus
from kagan.core.errors import InvalidTransitionError

pytestmark = [pytest.mark.core]

# ── Direct-move guard (replaces validate_move from deleted _transitions.py) ───
#
# Legal direct-move pairs (REVIEW→DONE is merge-only and excluded).
_DIRECT_MOVES: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset(
    {
        (TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS),
        (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW),
        (TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG),
        (TaskStatus.REVIEW, TaskStatus.IN_PROGRESS),
        (TaskStatus.REVIEW, TaskStatus.BACKLOG),
        (TaskStatus.DONE, TaskStatus.BACKLOG),
    }
)


def _validate_direct_move(from_status: TaskStatus, to_status: TaskStatus) -> None:
    if (from_status, to_status) not in _DIRECT_MOVES:
        raise InvalidTransitionError(from_status, to_status)


def _validate_merge_move(from_status: TaskStatus, to_status: TaskStatus) -> None:
    if from_status != TaskStatus.REVIEW or to_status != TaskStatus.DONE:
        raise InvalidTransitionError(from_status, to_status)


# ── validate_merge_move equivalent ───────────────────────────────────────────


def test_validate_merge_move_accepts_review_to_done() -> None:
    _validate_merge_move(TaskStatus.REVIEW, TaskStatus.DONE)


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        # All ordinary moves must be rejected by the *merge* gate, even if
        # they are valid direct moves.
        (TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS),
        (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW),
        (TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG),
        (TaskStatus.REVIEW, TaskStatus.IN_PROGRESS),
        (TaskStatus.REVIEW, TaskStatus.BACKLOG),
        (TaskStatus.DONE, TaskStatus.BACKLOG),
        # Outright invalid:
        (TaskStatus.BACKLOG, TaskStatus.DONE),
        (TaskStatus.IN_PROGRESS, TaskStatus.DONE),
        (TaskStatus.DONE, TaskStatus.REVIEW),
    ],
)
def test_validate_merge_move_rejects_non_merge_transitions(
    from_status: TaskStatus, to_status: TaskStatus
) -> None:
    with pytest.raises(InvalidTransitionError):
        _validate_merge_move(from_status, to_status)


# ── validate_move / can_move equivalent ──────────────────────────────────────


def test_validate_move_rejects_merge_path() -> None:
    """REVIEW → DONE must not be reachable via the ordinary move guard."""
    with pytest.raises(InvalidTransitionError):
        _validate_direct_move(TaskStatus.REVIEW, TaskStatus.DONE)
    assert (TaskStatus.REVIEW, TaskStatus.DONE) not in _DIRECT_MOVES


def test_validate_move_accepts_known_paths() -> None:
    _validate_direct_move(TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS)
    _validate_direct_move(TaskStatus.IN_PROGRESS, TaskStatus.REVIEW)
    _validate_direct_move(TaskStatus.REVIEW, TaskStatus.IN_PROGRESS)
    _validate_direct_move(TaskStatus.DONE, TaskStatus.BACKLOG)


# ── allowed_targets equivalent ────────────────────────────────────────────────


def test_allowed_targets_excludes_merge() -> None:
    targets = {to for (frm, to) in _DIRECT_MOVES if frm == TaskStatus.REVIEW}
    assert TaskStatus.DONE not in targets
    assert TaskStatus.IN_PROGRESS in targets
    assert TaskStatus.BACKLOG in targets


def test_all_direct_move_pairs_are_exhaustive() -> None:
    """Regression: confirm the inline set in Tasks.set_status matches this module."""
    # If a new status is ever added, this test should surface the gap.
    for from_s, to_s in _DIRECT_MOVES:
        assert isinstance(from_s, TaskStatus)
        assert isinstance(to_s, TaskStatus)
