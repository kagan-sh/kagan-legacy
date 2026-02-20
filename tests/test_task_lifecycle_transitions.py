"""Task lifecycle: BACKLOG -> IN_PROGRESS -> REVIEW -> DONE enforcement.

Covers:
- Status transitions follow BACKLOG -> IN_PROGRESS -> REVIEW -> DONE
- Direct move to DONE is blocked from generic move/patch flows
- Task type (AUTO/PAIR) is separate from status; invalid status values rejected
- Agent completion and review resolution drive correct transitions
"""

from __future__ import annotations

import pytest

from kagan.core.domain.enums import TaskStatus, TaskType
from kagan.core.domain.task_rules import (
    can_transition,
    resolve_status_after_agent_complete,
    resolve_status_after_review,
    validate_transition,
)


class TestDirectMoveGuardrails:
    """Direct user-initiated moves must never reach DONE."""

    @pytest.mark.parametrize("from_status", list(TaskStatus))
    def test_direct_move_to_done_is_blocked(self, from_status: TaskStatus) -> None:
        assert can_transition(from_status, TaskStatus.DONE) is False

    @pytest.mark.parametrize("from_status", list(TaskStatus))
    def test_validate_transition_raises_on_done(self, from_status: TaskStatus) -> None:
        with pytest.raises(ValueError, match="Direct move/update to DONE"):
            validate_transition(from_status, TaskStatus.DONE)

    @pytest.mark.parametrize(
        "to_status",
        [TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS, TaskStatus.REVIEW],
    )
    def test_non_done_moves_are_allowed(self, to_status: TaskStatus) -> None:
        for from_status in TaskStatus:
            assert can_transition(from_status, to_status) is True


class TestAgentCompletionTransitions:
    """Agent completion drives IN_PROGRESS -> REVIEW on success."""

    def test_success_moves_in_progress_to_review(self) -> None:
        result = resolve_status_after_agent_complete(TaskStatus.IN_PROGRESS, success=True)
        assert result == TaskStatus.REVIEW

    def test_failure_keeps_in_progress(self) -> None:
        result = resolve_status_after_agent_complete(TaskStatus.IN_PROGRESS, success=False)
        assert result == TaskStatus.IN_PROGRESS

    def test_success_from_backlog_stays_backlog(self) -> None:
        result = resolve_status_after_agent_complete(TaskStatus.BACKLOG, success=True)
        assert result == TaskStatus.BACKLOG

    def test_done_is_idempotent(self) -> None:
        result = resolve_status_after_agent_complete(TaskStatus.DONE, success=True)
        assert result == TaskStatus.DONE


class TestReviewResolutionTransitions:
    """Review pass/reject drives REVIEW -> DONE or REVIEW -> IN_PROGRESS."""

    def test_review_pass_moves_review_to_done(self) -> None:
        result = resolve_status_after_review("pass", TaskStatus.REVIEW)
        assert result == TaskStatus.DONE

    def test_review_reject_moves_review_to_in_progress(self) -> None:
        result = resolve_status_after_review("reject", TaskStatus.REVIEW)
        assert result == TaskStatus.IN_PROGRESS

    def test_review_pass_from_non_review_is_noop(self) -> None:
        for status in (TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS, TaskStatus.DONE):
            result = resolve_status_after_review("pass", status)
            assert result == status

    def test_unknown_review_action_raises(self) -> None:
        with pytest.raises(ValueError, match="Unknown review action"):
            resolve_status_after_review("maybe", TaskStatus.REVIEW)


class TestTaskTypeIsSeparateFromStatus:
    """Task type (AUTO/PAIR) is orthogonal to lifecycle status."""

    @pytest.mark.parametrize("task_type", list(TaskType))
    async def test_task_created_with_type_and_status(
        self, state_manager, task_factory, task_type: TaskType
    ) -> None:
        task = task_factory(
            title=f"{task_type.value} task",
            task_type=task_type,
            status=TaskStatus.BACKLOG,
        )
        created = await state_manager.create(task)
        assert created.task_type == task_type
        assert created.status == TaskStatus.BACKLOG

    async def test_status_update_preserves_task_type(self, state_manager, task_factory) -> None:
        task = task_factory(title="Typed task", task_type=TaskType.AUTO)
        created = await state_manager.create(task)
        updated = await state_manager.update(created.id, status=TaskStatus.IN_PROGRESS)
        assert updated is not None
        assert updated.task_type == TaskType.AUTO
        assert updated.status == TaskStatus.IN_PROGRESS
