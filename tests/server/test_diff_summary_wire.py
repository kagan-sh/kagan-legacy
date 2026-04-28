"""Test that GET /api/tasks returns diff_summary for tasks in REVIEW with a worktree.

One test is sufficient — we verify the end-to-end wire shape via a fake
worktrees client whose diff_stats() returns a known value.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

import kagan.server._helpers as server_helpers
from kagan.core import TaskStatus
from kagan.core.models import Task
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server


class _FakeWorktreesClient:
    """Returns canned diff stats; tracks which task IDs were queried."""

    def __init__(self, stats: dict[str, int]) -> None:
        self._stats = stats
        self.queried: list[str] = []

    async def diff_stats(self, task_id: str) -> dict[str, int]:
        self.queried.append(task_id)
        return self._stats


class _FakeTasksClient:
    def __init__(self, tasks: list[Any]) -> None:
        self._tasks = {t.id: t for t in tasks}

    async def list(self, status: Any = None, repo_id: Any = None) -> list[Any]:
        tasks = list(self._tasks.values())
        if status is None:
            return tasks
        return [t for t in tasks if t.status == status]

    async def get(self, task_id: str) -> Any:
        return self._tasks[task_id]

    async def runtime_summaries(self, task_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {
            tid: {
                "has_workspace": True,
                "last_event_at": None,
                "active_session": None,
            }
            for tid in task_ids
        }

    async def runtime_summary(self, task_id: str) -> dict[str, Any]:
        return {"has_workspace": True, "last_event_at": None, "active_session": None}


def _make_task(task_id: str, status: TaskStatus) -> Task:
    return Task(
        id=task_id,
        project_id="project-1",
        title="Test task",
        description="",
        status=status,
        priority=1,
        review_approved=False,
    )


def _ctx(tasks_client: Any, worktrees_client: Any) -> SimpleNamespace:
    return SimpleNamespace(
        client=SimpleNamespace(
            tasks=tasks_client,
            worktrees=worktrees_client,
            settings=SimpleNamespace(get=lambda: {}),
        ),
    )


@pytest.mark.asyncio
async def test_list_tasks_includes_diff_summary_for_review_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A REVIEW task with a worktree must include diff_summary in the wire response."""
    mcp = make_api_server()
    known_stats = {"files": 3, "insertions": 47, "deletions": 12}
    worktrees = _FakeWorktreesClient(known_stats)

    review_task = _make_task("task-review", TaskStatus.REVIEW)
    backlog_task = _make_task("task-backlog", TaskStatus.BACKLOG)
    tasks_client = _FakeTasksClient([review_task, backlog_task])

    monkeypatch.setattr(
        server_helpers,
        "get_server_context",
        lambda _mcp: _ctx(tasks_client, worktrees),
    )

    list_endpoint = get_http_endpoint(mcp, "/api/tasks", "GET")
    response = json_body(await list_endpoint(make_request("GET", "/api/tasks")))
    assert response["ok"] is True

    tasks_by_id = {t["id"]: t for t in response["data"]}

    review = tasks_by_id["task-review"]
    assert review["diff_summary"] is not None
    assert review["diff_summary"]["files_changed"] == 3
    assert review["diff_summary"]["additions"] == 47
    assert review["diff_summary"]["deletions"] == 12

    # diff_stats must only have been called for the REVIEW task
    assert worktrees.queried == ["task-review"]

    # BACKLOG task must not have a diff_summary
    backlog = tasks_by_id["task-backlog"]
    assert backlog.get("diff_summary") is None
