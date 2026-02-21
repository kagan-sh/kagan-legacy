"""Typed builders for task command handler tests."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

if TYPE_CHECKING:
    from kagan.core.domain.enums import TaskStatus


@dataclass(slots=True)
class TaskCommandApiStub:
    """API stub exposing task/review command entrypoints as AsyncMocks."""

    update_task: AsyncMock
    approve_task: AsyncMock
    request_review: AsyncMock
    reject_task: AsyncMock


@dataclass(slots=True)
class TaskCommandContextStub:
    """Context stub with only the API surface needed by command tests."""

    api: TaskCommandApiStub


@dataclass(slots=True)
class TaskResultStub:
    """Minimal task-like object returned by command API mocks."""

    id: str
    status: TaskStatus | None = None


def build_task_command_context(
    *,
    update_task: AsyncMock | None = None,
    approve_task: AsyncMock | None = None,
    request_review: AsyncMock | None = None,
    reject_task: AsyncMock | None = None,
) -> TaskCommandContextStub:
    return TaskCommandContextStub(
        api=TaskCommandApiStub(
            update_task=update_task if update_task is not None else AsyncMock(),
            approve_task=approve_task if approve_task is not None else AsyncMock(),
            request_review=request_review if request_review is not None else AsyncMock(),
            reject_task=reject_task if reject_task is not None else AsyncMock(),
        )
    )


def build_task_result(
    *,
    task_id: str = "task-1",
    status: TaskStatus | None = None,
) -> TaskResultStub:
    return TaskResultStub(id=task_id, status=status)
