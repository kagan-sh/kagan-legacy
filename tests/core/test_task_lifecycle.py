"""Feature tests: Task Lifecycle — docs/internal/features/core.md §4.

Behavioral specs using KaganDriver DSL. No private imports.
Each test is isolated with its own tmp_path and fresh DB.
"""

import pytest

from kagan.core import InvalidTransitionError, TaskStatus
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.core, pytest.mark.smoke]

# ---------------------------------------------------------------------------
# §4.1 — Valid transitions: BACKLOG → IN_PROGRESS → REVIEW
# ---------------------------------------------------------------------------


async def test_valid_transitions_backlog_to_in_progress_to_review(board: KaganDriver) -> None:
    """Tasks can move BACKLOG → IN_PROGRESS → REVIEW via valid transitions."""
    task = await board.create_task("Lifecycle Task")
    assert task.status == TaskStatus.BACKLOG

    in_progress = await board.move_task(task.id, TaskStatus.IN_PROGRESS)
    assert in_progress.status == TaskStatus.IN_PROGRESS

    in_review = await board.move_task(task.id, TaskStatus.REVIEW)
    assert in_review.status == TaskStatus.REVIEW


# ---------------------------------------------------------------------------
# §4.2 — REVIEW can go back to IN_PROGRESS or BACKLOG
# ---------------------------------------------------------------------------


async def test_review_can_go_back_to_in_progress(board: KaganDriver) -> None:
    """A task in REVIEW can be moved back to IN_PROGRESS."""
    task = await board.create_task("Review Bounce Task")
    await board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await board.move_task(task.id, TaskStatus.REVIEW)

    back = await board.move_task(task.id, TaskStatus.IN_PROGRESS)
    assert back.status == TaskStatus.IN_PROGRESS


async def test_review_can_go_back_to_backlog(board: KaganDriver) -> None:
    """A task in REVIEW can be moved back to BACKLOG."""
    task = await board.create_task("Review to Backlog Task")
    await board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await board.move_task(task.id, TaskStatus.REVIEW)

    back = await board.move_task(task.id, TaskStatus.BACKLOG)
    assert back.status == TaskStatus.BACKLOG


# ---------------------------------------------------------------------------
# §4.3 — DONE is only reachable via review.merge(), never via direct move
# ---------------------------------------------------------------------------


async def test_direct_move_to_done_raises_invalid_transition(board: KaganDriver) -> None:
    """Attempting to move a task directly to DONE raises InvalidTransitionError."""
    task = await board.create_task("Cannot Be Done Directly")
    await board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await board.move_task(task.id, TaskStatus.REVIEW)

    with pytest.raises(InvalidTransitionError):
        await board.move_task(task.id, TaskStatus.DONE)


async def test_backlog_to_done_raises_invalid_transition(board: KaganDriver) -> None:
    """Moving directly from BACKLOG to DONE raises InvalidTransitionError."""
    task = await board.create_task("Backlog Cannot Jump to Done")

    with pytest.raises(InvalidTransitionError):
        await board.move_task(task.id, TaskStatus.DONE)


# ---------------------------------------------------------------------------
# §4.4 — Invalid transitions raise InvalidTransitionError
# ---------------------------------------------------------------------------


async def test_invalid_transition_in_progress_to_done_raises(board: KaganDriver) -> None:
    """Moving IN_PROGRESS → DONE directly raises InvalidTransitionError."""
    task = await board.create_task("Invalid Transition Task")
    await board.move_task(task.id, TaskStatus.IN_PROGRESS)

    with pytest.raises(InvalidTransitionError):
        await board.move_task(task.id, TaskStatus.DONE)


# ---------------------------------------------------------------------------
# §4.5 — Moving away from IN_PROGRESS cancels any active session
# ---------------------------------------------------------------------------


async def test_cancel_in_progress_task_moves_to_backlog(board: KaganDriver) -> None:
    """Cancelling an IN_PROGRESS task moves it back to BACKLOG."""
    task = await board.create_task("Cancellable Task")
    await board.move_task(task.id, TaskStatus.IN_PROGRESS)

    await board.stop_auto(task.id)

    fetched = await board.get_task(task.id)
    assert fetched.status == TaskStatus.BACKLOG
