"""Tests for task delete api adapter function (formerly CQRS handler)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock

import pytest

from kagan.core.commands.tasks import (
    delete_task as handle_task_delete,
)
from kagan.core.commands.tasks import (
    get_scratchpad as handle_task_scratchpad,
)
from kagan.core.commands.tasks import (
    get_task_context as handle_task_context,
)
from kagan.core.commands.tasks import (
    get_task_logs as handle_task_logs,
)
from kagan.core.commands.tasks import (
    move_task as handle_task_move,
)
from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType
from kagan.core.events import TaskDeleted


def _ctx(**services: object) -> Any:
    return SimpleNamespace(**services)


def _task(task_id: str, *, status: TaskStatus) -> SimpleNamespace:
    now = datetime.now(tz=UTC)
    return SimpleNamespace(
        id=task_id,
        project_id="proj-1",
        parent_id=None,
        title=f"Task {task_id}",
        description=f"Description {task_id}",
        status=status,
        priority=TaskPriority.MEDIUM,
        task_type=TaskType.PAIR,
        terminal_backend=None,
        agent_backend=None,
        acceptance_criteria=["criterion"],
        base_branch="main",
        created_at=now,
        updated_at=now,
    )


async def test_delete_task_uses_workspace_service_cleanup() -> None:
    task = SimpleNamespace(id="task-1")
    task_service = SimpleNamespace(get_task=AsyncMock(return_value=task))
    workspace_service = SimpleNamespace(
        delete_task=AsyncMock(return_value=(True, "Deleted successfully"))
    )
    f = _ctx(task_service=task_service, workspace_service=workspace_service)

    result = await handle_task_delete(f, {"task_id": "task-1"})

    assert result == {"success": True, "task_id": "task-1", "message": "Deleted successfully"}
    workspace_service.delete_task.assert_awaited_once_with(task)


async def test_delete_task_returns_failure_for_missing_task() -> None:
    task_service = SimpleNamespace(get_task=AsyncMock(return_value=None))
    f = _ctx(task_service=task_service)

    result = await handle_task_delete(f, {"task_id": "task-1"})

    assert result["success"] is False
    assert "not found" in result["message"]


async def test_task_move_rejects_direct_done_transition() -> None:
    task = _task("task-1", status=TaskStatus.REVIEW)
    task_service = SimpleNamespace(
        get_task=AsyncMock(return_value=task),
        move=AsyncMock(return_value=task),
    )
    f = _ctx(task_service=task_service)

    result = await handle_task_move(f, {"task_id": "task-1", "status": "DONE"})

    assert result["success"] is False
    assert result["task_id"] == "task-1"
    assert result["code"] == "INVALID_STATUS_TRANSITION"
    task_service.move.assert_not_awaited()


async def test_task_context_falls_back_to_project_repos_on_workspace_failure() -> None:
    """When workspace repos fail, api falls back to project repos."""
    task = _task("task-1", status=TaskStatus.IN_PROGRESS)

    task_service = SimpleNamespace(
        get_task=AsyncMock(return_value=task),
        get_scratchpad=AsyncMock(return_value="scratch"),
        get_task_links=AsyncMock(return_value=[]),
    )
    workspace_service = SimpleNamespace(
        list_workspaces=AsyncMock(
            return_value=[
                SimpleNamespace(id="ws-1", branch_name="feature/task-1", path="/tmp/ws-1"),
            ]
        ),
        get_workspace_repos=AsyncMock(side_effect=OSError("workspace repos unavailable")),
    )
    project_repo = SimpleNamespace(
        id="repo-1", name="repo", path="/tmp/repo", default_branch="main"
    )
    project_service = SimpleNamespace(get_project_repos=AsyncMock(return_value=[project_repo]))
    f = _ctx(
        task_service=task_service,
        workspace_service=workspace_service,
        project_service=project_service,
    )

    result = await handle_task_context(f, {"task_id": "task-1"})

    assert result["repo_count"] == 1
    assert result["repos"][0]["repo_id"] == "repo-1"
    assert result["workspace_id"] == "ws-1"


async def test_task_context_returns_empty_repos_when_both_sources_fail() -> None:
    """When both workspace and project repos fail, repos list is empty."""
    task = _task("task-1", status=TaskStatus.IN_PROGRESS)

    task_service = SimpleNamespace(
        get_task=AsyncMock(return_value=task),
        get_scratchpad=AsyncMock(return_value="scratch"),
        get_task_links=AsyncMock(return_value=[]),
    )
    workspace_service = SimpleNamespace(
        list_workspaces=AsyncMock(
            return_value=[
                SimpleNamespace(id="ws-1", branch_name="feature/task-1", path="/tmp/ws-1"),
            ]
        ),
        get_workspace_repos=AsyncMock(side_effect=OSError("workspace repos unavailable")),
    )
    project_service = SimpleNamespace(
        get_project_repos=AsyncMock(side_effect=RuntimeError("project repos unavailable"))
    )
    f = _ctx(
        task_service=task_service,
        workspace_service=workspace_service,
        project_service=project_service,
    )

    result = await handle_task_context(f, {"task_id": "task-1"})

    assert result["repo_count"] == 0
    assert result["repos"] == []


async def test_task_logs_returns_empty_on_fetch_failures() -> None:
    """When execution log entries fail, logs list is empty."""
    execution = SimpleNamespace(id="exec-1", created_at=datetime.now(tz=UTC))
    execution_service = SimpleNamespace(
        list_executions_for_task=AsyncMock(return_value=[execution]),
        count_executions_for_task=AsyncMock(side_effect=RuntimeError("count unavailable")),
        get_execution_log_entries=AsyncMock(side_effect=RuntimeError("log storage unavailable")),
    )
    f = _ctx(execution_service=execution_service)

    result = await handle_task_logs(f, {"task_id": "task-1", "limit": 5})

    assert result["task_id"] == "task-1"
    assert result["count"] == 0
    assert result["logs"] == []


async def test_task_scratchpad_applies_transport_limit() -> None:
    task_service = SimpleNamespace(get_scratchpad=AsyncMock(return_value="x" * 1200))
    f = _ctx(task_service=task_service)

    result = await handle_task_scratchpad(
        f,
        {"task_id": "task-1", "content_char_limit": 256},
    )

    assert result["task_id"] == "task-1"
    assert result["truncated"] is True
    assert "[truncated " in result["content"]


async def test_task_logs_applies_transport_limits() -> None:
    execution = SimpleNamespace(id="exec-1", created_at=datetime.now(tz=UTC))
    execution_service = SimpleNamespace(
        list_executions_for_task=AsyncMock(return_value=[execution]),
        count_executions_for_task=AsyncMock(return_value=1),
        get_execution_log_entries=AsyncMock(return_value=[SimpleNamespace(logs="x" * 500)]),
    )
    f = _ctx(execution_service=execution_service)

    result = await handle_task_logs(
        f,
        {
            "task_id": "task-1",
            "limit": 5,
            "content_char_limit": 64,
            "total_char_limit": 256,
        },
    )

    assert result["task_id"] == "task-1"
    assert result["count"] == 1
    assert result["truncated"] is True
    assert "[truncated " in result["logs"][0]["content"]


async def test_task_logs_supports_offset_pagination() -> None:
    now = datetime.now(tz=UTC)
    executions_desc = [
        SimpleNamespace(id="exec-3", created_at=now),
        SimpleNamespace(id="exec-2", created_at=now),
        SimpleNamespace(id="exec-1", created_at=now),
    ]

    async def list_executions_for_task(task_id: str, *, limit: int = 5, offset: int = 0):
        assert task_id == "task-1"
        return executions_desc[offset : offset + limit]

    execution_service = SimpleNamespace(
        list_executions_for_task=AsyncMock(side_effect=list_executions_for_task),
        count_executions_for_task=AsyncMock(return_value=3),
        get_execution_log_entries=AsyncMock(
            side_effect=lambda execution_id: [
                SimpleNamespace(logs=f"log for {execution_id}"),
            ]
        ),
    )
    f = _ctx(execution_service=execution_service)

    first_page = await handle_task_logs(f, {"task_id": "task-1", "limit": 2, "offset": 0})
    second_page = await handle_task_logs(f, {"task_id": "task-1", "limit": 2, "offset": 2})

    assert [entry["run"] for entry in first_page["logs"]] == [2, 3]
    assert first_page["total_runs"] == 3
    assert first_page["has_more"] is True
    assert first_page["next_offset"] == 2
    assert [entry["run"] for entry in second_page["logs"]] == [1]
    assert second_page["has_more"] is False
    assert second_page["next_offset"] is None


async def test_task_logs_rejects_invalid_offset() -> None:
    f = _ctx()

    result = await handle_task_logs(f, {"task_id": "task-1", "offset": "bad"})

    assert result["success"] is False
    assert result["code"] == "INVALID_OFFSET"


async def test_delete_task_publishes_task_deleted_event(
    event_bus,
    state_manager,
    task_factory,
    task_service,
) -> None:
    task = await state_manager.create(task_factory(title="Delete me"))
    published: list[object] = []
    event_bus.add_handler(lambda event: published.append(event))

    deleted = await task_service.delete_task(task.id)

    assert deleted is True
    deleted_events = [event for event in published if isinstance(event, TaskDeleted)]
    assert len(deleted_events) == 1
    assert deleted_events[0].task_id == task.id


async def test_delete_missing_task_does_not_publish_task_deleted_event(
    event_bus,
    task_service,
) -> None:
    published: list[object] = []
    event_bus.add_handler(lambda event: published.append(event))

    deleted = await task_service.delete_task("missing-task-id")

    assert deleted is False
    assert not any(isinstance(event, TaskDeleted) for event in published)


@pytest.mark.parametrize(
    ("initial_status", "success", "expected"),
    [
        (TaskStatus.IN_PROGRESS, True, TaskStatus.REVIEW),
        (TaskStatus.IN_PROGRESS, False, TaskStatus.IN_PROGRESS),
        (TaskStatus.REVIEW, False, TaskStatus.REVIEW),
        (TaskStatus.BACKLOG, True, TaskStatus.BACKLOG),
        (TaskStatus.DONE, True, TaskStatus.DONE),
    ],
)
async def test_sync_status_from_agent_complete(
    state_manager,
    task_factory,
    task_service,
    initial_status: TaskStatus,
    success: bool,
    expected: TaskStatus,
) -> None:
    task = task_factory(title="Workflow test", status=initial_status)
    created = await state_manager.create(task)

    updated = await task_service.sync_status_from_agent_complete(created.id, success=success)
    assert updated is not None
    assert updated.status is expected


@pytest.mark.parametrize(
    ("initial_status", "expected"),
    [
        (TaskStatus.REVIEW, TaskStatus.DONE),
        (TaskStatus.BACKLOG, TaskStatus.BACKLOG),
        (TaskStatus.DONE, TaskStatus.DONE),
    ],
)
async def test_sync_status_from_review_pass(
    state_manager,
    task_factory,
    task_service,
    initial_status: TaskStatus,
    expected: TaskStatus,
) -> None:
    task = task_factory(title="Review pass transition", status=initial_status)
    created = await state_manager.create(task)

    updated = await task_service.sync_status_from_review_pass(created.id)
    assert updated is not None
    assert updated.status is expected


@pytest.mark.parametrize(
    ("initial_status", "expected"),
    [
        (TaskStatus.REVIEW, TaskStatus.IN_PROGRESS),
        (TaskStatus.BACKLOG, TaskStatus.BACKLOG),
        (TaskStatus.DONE, TaskStatus.DONE),
    ],
)
async def test_sync_status_from_review_reject(
    state_manager,
    task_factory,
    task_service,
    initial_status: TaskStatus,
    expected: TaskStatus,
) -> None:
    task = task_factory(title="Review reject transition", status=initial_status)
    created = await state_manager.create(task)

    updated = await task_service.sync_status_from_review_reject(created.id, reason="needs work")
    assert updated is not None
    assert updated.status is expected
