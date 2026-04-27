"""Unit tests for the trigger-keyed task lifecycle state machine."""

from __future__ import annotations

import pytest

from kagan.core._transitions import (
    Trigger,
    all_allowed_targets,
    allowed_targets,
    can_move,
    transition,
    validate_merge_move,
    validate_move,
)
from kagan.core.enums import TaskStatus
from kagan.core.errors import InvalidTransitionError

pytestmark = [pytest.mark.core]


# ── transition(): happy paths ─────────────────────────────────────────


@pytest.mark.parametrize(
    ("from_status", "trigger", "expected"),
    [
        (TaskStatus.BACKLOG, Trigger.START, TaskStatus.IN_PROGRESS),
        (TaskStatus.IN_PROGRESS, Trigger.AGENT_DONE, TaskStatus.REVIEW),
        (TaskStatus.IN_PROGRESS, Trigger.AGENT_CANCELLED, TaskStatus.BACKLOG),
        (TaskStatus.IN_PROGRESS, Trigger.REQUEUE, TaskStatus.BACKLOG),
        (TaskStatus.REVIEW, Trigger.REVIEW_REJECT, TaskStatus.IN_PROGRESS),
        (TaskStatus.REVIEW, Trigger.MERGE, TaskStatus.DONE),
        (TaskStatus.REVIEW, Trigger.REQUEUE, TaskStatus.BACKLOG),
        (TaskStatus.DONE, Trigger.REQUEUE, TaskStatus.BACKLOG),
    ],
)
def test_transition_returns_destination(
    from_status: TaskStatus, trigger: Trigger, expected: TaskStatus
) -> None:
    assert transition(from_status, trigger) is expected


# ── transition(): rejection paths ─────────────────────────────────────


@pytest.mark.parametrize(
    ("from_status", "trigger"),
    [
        (TaskStatus.BACKLOG, Trigger.AGENT_DONE),
        (TaskStatus.BACKLOG, Trigger.MERGE),
        (TaskStatus.BACKLOG, Trigger.REVIEW_REJECT),
        (TaskStatus.IN_PROGRESS, Trigger.MERGE),
        (TaskStatus.IN_PROGRESS, Trigger.START),
        (TaskStatus.REVIEW, Trigger.START),
        (TaskStatus.DONE, Trigger.START),
        (TaskStatus.DONE, Trigger.MERGE),
    ],
)
def test_transition_rejects_invalid_trigger(from_status: TaskStatus, trigger: Trigger) -> None:
    with pytest.raises(InvalidTransitionError) as exc:
        transition(from_status, trigger)
    assert exc.value.from_status == str(from_status)
    assert exc.value.to_status == str(trigger)


# ── validate_merge_move ───────────────────────────────────────────────


def test_validate_merge_move_accepts_review_to_done() -> None:
    validate_merge_move(TaskStatus.REVIEW, TaskStatus.DONE)


@pytest.mark.parametrize(
    ("from_status", "to_status"),
    [
        # All ordinary moves must be rejected by the *merge* gate, even if
        # they are valid via validate_move(). This guards against silent
        # widening of the merge-action contract.
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
        validate_merge_move(from_status, to_status)


# ── validate_move / can_move ──────────────────────────────────────────


def test_validate_move_rejects_merge_path() -> None:
    """REVIEW → DONE must not be reachable via the ordinary move guard."""
    with pytest.raises(InvalidTransitionError):
        validate_move(TaskStatus.REVIEW, TaskStatus.DONE)
    assert can_move(TaskStatus.REVIEW, TaskStatus.DONE) is False


def test_validate_move_accepts_known_paths() -> None:
    validate_move(TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS)
    validate_move(TaskStatus.IN_PROGRESS, TaskStatus.REVIEW)
    validate_move(TaskStatus.REVIEW, TaskStatus.IN_PROGRESS)
    validate_move(TaskStatus.DONE, TaskStatus.BACKLOG)


# ── allowed_targets ───────────────────────────────────────────────────


def test_allowed_targets_excludes_merge() -> None:
    targets = set(allowed_targets(TaskStatus.REVIEW))
    assert TaskStatus.DONE not in targets
    assert TaskStatus.IN_PROGRESS in targets
    assert TaskStatus.BACKLOG in targets


def test_all_allowed_targets_includes_merge() -> None:
    targets = set(all_allowed_targets(TaskStatus.REVIEW))
    assert TaskStatus.DONE in targets
    assert TaskStatus.IN_PROGRESS in targets
    assert TaskStatus.BACKLOG in targets
