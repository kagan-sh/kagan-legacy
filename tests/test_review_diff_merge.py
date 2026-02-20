"""Review, diff, and merge: approval/rejection flows and merge safety.

Covers:
- Approve / reject / rebase actions via review resolution
- Rejection feedback moves task back to BACKLOG or IN_PROGRESS
- No-change close flow (exploratory tasks)
- Full review cycle at repository layer
"""

from __future__ import annotations

from kagan.core.domain.enums import TaskStatus
from kagan.core.domain.task_rules import (
    resolve_status_after_review,
)


class TestReviewApproval:
    """Review pass moves REVIEW -> DONE."""

    def test_approve_from_review(self) -> None:
        assert resolve_status_after_review("pass", TaskStatus.REVIEW) == TaskStatus.DONE

    def test_approve_from_non_review_is_noop(self) -> None:
        assert resolve_status_after_review("pass", TaskStatus.IN_PROGRESS) == TaskStatus.IN_PROGRESS
        assert resolve_status_after_review("pass", TaskStatus.BACKLOG) == TaskStatus.BACKLOG


class TestReviewRejection:
    """Review reject moves REVIEW -> IN_PROGRESS with notes."""

    def test_reject_from_review(self) -> None:
        assert resolve_status_after_review("reject", TaskStatus.REVIEW) == TaskStatus.IN_PROGRESS

    async def test_rejection_records_feedback_in_scratchpad(
        self, state_manager, task_factory
    ) -> None:
        from kagan.core.adapters.db.repositories.auxiliary import ScratchRepository

        task = task_factory(title="Rejected task", status=TaskStatus.REVIEW)
        created = await state_manager.create(task)
        # Simulate rejection: move back + record notes
        await state_manager.update(created.id, status=TaskStatus.IN_PROGRESS)

        scratch = ScratchRepository(state_manager.session_factory)
        await scratch.update_scratchpad(created.id, "Rejection: missing tests")
        content = await scratch.get_scratchpad(created.id)

        fetched = await state_manager.get(created.id)
        assert fetched is not None
        assert fetched.status == TaskStatus.IN_PROGRESS
        assert "Rejection: missing tests" in content


class TestFullReviewCycle:
    """End-to-end review cycle at repository layer."""

    async def test_task_through_full_review_approve_cycle(
        self, state_manager, task_factory
    ) -> None:
        task = task_factory(title="Review cycle", status=TaskStatus.IN_PROGRESS)
        created = await state_manager.create(task)

        # Move to REVIEW
        await state_manager.update(created.id, status=TaskStatus.REVIEW)
        fetched = await state_manager.get(created.id)
        assert fetched is not None
        assert fetched.status == TaskStatus.REVIEW

        # Resolve review pass -> DONE
        next_status = resolve_status_after_review("pass", fetched.status)
        await state_manager.update(created.id, status=next_status)
        fetched = await state_manager.get(created.id)
        assert fetched is not None
        assert fetched.status == TaskStatus.DONE
