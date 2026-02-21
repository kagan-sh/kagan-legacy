"""Task/review command handlers should delegate canonical logic to API methods."""

from __future__ import annotations

from unittest.mock import AsyncMock

from kagan.core.commands import tasks as task_commands
from kagan.core.domain.enums import TaskStatus
from kagan.core.domain.errors import (
    ReviewApprovalContextMissingError,
    ReviewGuardrailBlockedError,
)
from tests.helpers.mocks import build_task_command_context, build_task_result


class TestTaskReviewCommandDelegation:
    async def test_update_task_delegates_to_api_without_task_service(self) -> None:
        ctx = build_task_command_context(
            update_task=AsyncMock(return_value=build_task_result()),
        )

        result = await task_commands.update_task(
            ctx,
            {"task_id": "task-1", "status": "IN_PROGRESS"},
        )

        assert result == {"success": True, "task_id": "task-1", "code": "UPDATED"}
        ctx.api.update_task.assert_awaited_once_with("task-1", status=TaskStatus.IN_PROGRESS)

    async def test_update_task_done_error_payload_from_api_value_error(self) -> None:
        ctx = build_task_command_context(
            update_task=AsyncMock(side_effect=ValueError("Invalid transition")),
        )

        result = await task_commands.update_task(
            ctx,
            {"task_id": "task-1", "status": "DONE"},
        )

        assert result == {
            "success": False,
            "task_id": "task-1",
            "message": "Invalid transition",
            "code": "INVALID_STATUS_TRANSITION",
            "hint": "Use review merge (or close no-change flow) from REVIEW to reach DONE.",
        }

    async def test_approve_review_delegates_to_api_without_task_service(self) -> None:
        ctx = build_task_command_context(
            approve_task=AsyncMock(
                return_value=build_task_result(status=TaskStatus.REVIEW),
            ),
        )

        result = await task_commands.approve_review(ctx, {"task_id": "task-1"})

        assert result == {
            "success": True,
            "task_id": "task-1",
            "status": "approved",
            "task_status": "REVIEW",
            "code": "APPROVED",
        }
        ctx.api.approve_task.assert_awaited_once_with("task-1")

    async def test_approve_review_not_ready_payload_uses_task_status_from_api(self) -> None:
        ctx = build_task_command_context(
            approve_task=AsyncMock(
                return_value=build_task_result(status=TaskStatus.IN_PROGRESS),
            ),
        )

        result = await task_commands.approve_review(ctx, {"task_id": "task-1"})

        assert result == {
            "success": False,
            "task_id": "task-1",
            "code": "REVIEW_NOT_READY",
            "message": (
                "Task is not in REVIEW (current: IN_PROGRESS). "
                "Move task to REVIEW before approving."
            ),
            "hint": "Use task_patch with transition='request_review' to move task to REVIEW.",
        }

    async def test_approve_review_context_missing_payload(self) -> None:
        ctx = build_task_command_context(
            approve_task=AsyncMock(
                side_effect=ReviewApprovalContextMissingError(
                    code="REVIEW_APPROVAL_CONTEXT_MISSING",
                    message="Cannot approve review: no execution context exists for this task.",
                    hint="Create a review execution for this task, then retry approve.",
                )
            ),
        )

        result = await task_commands.approve_review(ctx, {"task_id": "task-1"})

        assert result == {
            "success": False,
            "task_id": "task-1",
            "code": "REVIEW_APPROVAL_CONTEXT_MISSING",
            "message": "Cannot approve review: no execution context exists for this task.",
            "hint": "Create a review execution for this task, then retry approve.",
        }

    async def test_request_review_maps_guardrail_error_payload(self) -> None:
        ctx = build_task_command_context(
            request_review=AsyncMock(
                side_effect=ReviewGuardrailBlockedError(
                    code="REVIEW_GUARDRAIL_TIMEOUT",
                    message="REVIEW transition blocked: review guardrail check timed out.",
                    hint="Retry after fixing plugin health.",
                )
            ),
        )

        result = await task_commands.request_review(
            ctx,
            {"task_id": "task-1", "summary": "ready"},
        )

        assert result == {
            "success": False,
            "task_id": "task-1",
            "code": "REVIEW_GUARDRAIL_TIMEOUT",
            "message": "REVIEW transition blocked: review guardrail check timed out.",
            "hint": "Retry after fixing plugin health.",
        }

    async def test_reject_review_delegates_to_api_without_task_service(self) -> None:
        ctx = build_task_command_context(
            reject_task=AsyncMock(
                return_value=build_task_result(status=TaskStatus.BACKLOG),
            ),
        )

        result = await task_commands.reject_review(
            ctx,
            {"task_id": "task-1", "feedback": "needs tests", "action": "backlog"},
        )

        assert result == {
            "success": True,
            "task_id": "task-1",
            "status": "BACKLOG",
            "code": "REJECTED",
        }
        ctx.api.reject_task.assert_awaited_once_with("task-1", "needs tests", "backlog")
