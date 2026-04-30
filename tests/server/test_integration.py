from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any, cast

import pytest

import kagan.server._helpers as server_helpers
import kagan.server._task_routes as routes_module
from kagan.core import Priority, TaskStatus
from kagan.core import git as git_module
from kagan.core.models import Task
from kagan.server.mcp.server import ServerOptions
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server


class _FakeTasksClient:
    def __init__(self) -> None:
        self._seq = 0
        self._tasks: dict[str, Any] = {}

    async def list(self, status: TaskStatus | None = None, repo_id: str | None = None) -> list[Any]:
        tasks = list(self._tasks.values())
        if status is None:
            return tasks
        return [task for task in tasks if task.status == status]

    async def create(
        self,
        title: str,
        *,
        description: str = "",
        priority: Priority = Priority.MEDIUM,
        base_branch: str | None = None,
        acceptance_criteria: list[str] | None = None,
        agent_backend: str | None = None,
        launcher: str | None = None,
        repo_id: str | None = None,
    ) -> Any:
        self._seq += 1
        task = Task(
            id=f"task-{self._seq}",
            project_id="project-1",
            title=title,
            description=description,
            status=TaskStatus.BACKLOG,
            priority=priority,
            base_branch=base_branch,
            acceptance_criteria=acceptance_criteria or [],
            agent_backend=agent_backend,
            launcher=launcher,
            repo_id=repo_id,
            review_approved=False,
        )
        self._tasks[task.id] = task
        return task

    async def get(self, task_id: str) -> Any:
        return self._tasks[task_id]

    async def update(self, task_id: str, **updates: Any) -> Any:
        task = self._tasks[task_id]
        for field, value in updates.items():
            setattr(task, field, value)
        task.updated_at = datetime.now(UTC)
        return task

    async def set_status(self, task_id: str, status: TaskStatus) -> Any:
        self._tasks[task_id].status = status
        self._tasks[task_id].updated_at = datetime.now(UTC)
        return self._tasks[task_id]

    async def delete(self, task_id: str) -> None:
        del self._tasks[task_id]

    async def runtime_summaries(self, task_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {
            task_id: {"has_workspace": False, "last_event_at": None, "active_session": None}
            for task_id in task_ids
        }

    async def runtime_summary(self, task_id: str) -> dict[str, Any]:
        return {"has_workspace": False, "last_event_at": None, "active_session": None}


async def _no_repos(_project_id: str) -> list:
    return []


async def _no_repo_path(**_kwargs: Any) -> None:
    return None


def _ctx(
    tasks: _FakeTasksClient,
    *,
    settings_data: dict[str, str] | None = None,
    worktrees: Any | None = None,
    opts: ServerOptions | None = None,
) -> SimpleNamespace:
    async def _get_settings() -> dict[str, str]:
        return settings_data or {}

    settings = SimpleNamespace(get=_get_settings)
    return SimpleNamespace(
        client=SimpleNamespace(
            tasks=tasks,
            settings=settings,
            worktrees=worktrees or SimpleNamespace(),
            active_project_id=None,
            projects=SimpleNamespace(repos=_no_repos, resolve_repo_path=_no_repo_path),
        ),
        opts=opts or ServerOptions(),
    )


@pytest.mark.asyncio
async def test_list_tasks_without_active_project_returns_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    tasks = _FakeTasksClient()
    monkeypatch.setattr(
        server_helpers,
        "get_server_context",
        lambda _mcp: _ctx(tasks),
    )

    endpoint = get_http_endpoint(mcp, "/api/tasks", "GET")
    body = json_body(await endpoint(make_request("GET", "/api/tasks")))

    assert body["ok"] is True
    assert body["data"] == []


@pytest.mark.asyncio
async def test_rest_lifecycle_create_update_transition_delete(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    tasks = _FakeTasksClient()
    monkeypatch.setattr(
        server_helpers,
        "get_server_context",
        lambda _mcp: _ctx(tasks, opts=ServerOptions(admin=True)),
    )
    create = get_http_endpoint(mcp, "/api/tasks", "POST")
    created = json_body(
        await create(
            make_request(
                "POST",
                "/api/tasks",
                body={"title": "Ship"},
            )
        )
    )["data"]
    task_id = created["id"]
    update = get_http_endpoint(mcp, "/api/tasks/{task_id}", "PATCH")
    status = get_http_endpoint(mcp, "/api/tasks/{task_id}/status", "POST")
    delete = get_http_endpoint(mcp, "/api/tasks/{task_id}", "DELETE")
    assert (
        json_body(
            await update(
                make_request(
                    "PATCH",
                    f"/api/tasks/{task_id}",
                    path_params={"task_id": task_id},
                    body={"title": "Ship v2"},
                )
            )
        )["data"]["title"]
        == "Ship v2"
    )
    assert (
        json_body(
            await status(
                make_request(
                    "POST",
                    f"/api/tasks/{task_id}/status",
                    path_params={"task_id": task_id},
                    body={"status": "IN_PROGRESS"},
                )
            )
        )["data"]["status"]
        == "IN_PROGRESS"
    )
    assert (
        json_body(
            await delete(
                make_request("DELETE", f"/api/tasks/{task_id}", path_params={"task_id": task_id})
            )
        )["data"]["deleted"]
        is True
    )


@pytest.mark.asyncio
async def test_task_commits_route_returns_task_branch_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeWorktreesClient:
        async def get(self, _task_id: str) -> Any:
            return SimpleNamespace(
                worktree_path="/tmp/kagan-task-commits",
                branch_name="kagan/task-1",
            )

    class _FakeProc:
        returncode = 0

        async def communicate(self) -> tuple[bytes, bytes]:
            return (
                b"abc1234\tBootstrap session dashboard\n"
                b"def5678\tTighten commit list empty states\n",
                b"",
            )

    captured: dict[str, Any] = {}

    async def _fake_create_subprocess_exec(*args: Any, **kwargs: Any) -> _FakeProc:
        captured["args"] = args
        captured["kwargs"] = kwargs
        return _FakeProc()

    mcp = make_api_server()
    tasks = _FakeTasksClient()
    task = await tasks.create("Ship parity", base_branch="develop")
    monkeypatch.setattr(
        server_helpers,
        "get_server_context",
        lambda _mcp: _ctx(tasks, worktrees=_FakeWorktreesClient()),
    )
    monkeypatch.setattr(
        routes_module.asyncio, "create_subprocess_exec", _fake_create_subprocess_exec
    )

    commits = get_http_endpoint(mcp, "/api/tasks/{task_id}/commits", "GET")
    payload = json_body(
        await commits(
            make_request(
                "GET",
                f"/api/tasks/{task.id}/commits",
                path_params={"task_id": task.id},
            )
        )
    )

    assert payload["data"] == {
        "task_id": task.id,
        "branch": "kagan/task-1",
        "base_branch": "develop",
        "commits": [
            {
                "short_hash": "abc1234",
                "message": "Bootstrap session dashboard",
            },
            {
                "short_hash": "def5678",
                "message": "Tighten commit list empty states",
            },
        ],
    }
    assert captured["args"][:6] == (
        "git",
        "-C",
        "/tmp/kagan-task-commits",
        "log",
        "--pretty=format:%h%x09%s",
        "develop..HEAD",
    )
    assert captured["kwargs"]["stderr"] is asyncio.subprocess.DEVNULL


@pytest.mark.asyncio
async def test_missing_fields_return_error_envelopes(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = make_api_server()
    tasks = _FakeTasksClient()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: _ctx(tasks))
    create = get_http_endpoint(mcp, "/api/tasks", "POST")
    create_resp = await create(make_request("POST", "/api/tasks", body={"description": "x"}))
    create_payload = json_body(create_resp)
    assert cast("Any", create_resp).status_code == 422
    assert create_payload["ok"] is False
    assert "title" in create_payload["error"].lower()


@pytest.mark.asyncio
async def test_malformed_create_request_body_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = make_api_server()
    tasks = _FakeTasksClient()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: _ctx(tasks))
    create = get_http_endpoint(mcp, "/api/tasks", "POST")
    response = await create(make_request("POST", "/api/tasks", body=["not", "an", "object"]))
    import json

    payload = json.loads(bytes(cast("Any", response).body))
    assert cast("Any", response).status_code == 400
    assert payload["ok"] is False
    assert payload["error"] == "Request body must be a JSON object"


@pytest.mark.asyncio
async def test_resolved_settings_includes_workflow_wip_limits(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    tasks = _FakeTasksClient()
    monkeypatch.setattr(
        server_helpers,
        "get_server_context",
        lambda _mcp: _ctx(
            tasks,
            settings_data={"workflow.wip_limits": '{"IN_PROGRESS":3,"REVIEW":1,"BACKLOG":0}'},
        ),
    )

    async def _fake_git_identity(_settings: dict[str, str]) -> tuple[str, str]:
        return ("Kagan Agent", "agent@kagan.dev")

    monkeypatch.setattr(git_module, "get_git_user_identity", _fake_git_identity)

    resolved = get_http_endpoint(mcp, "/api/settings/resolved", "GET")
    payload = json_body(await resolved(make_request("GET", "/api/settings/resolved")))

    assert payload["data"]["git_user_name"] == "Kagan Agent"
    assert payload["data"]["workflow"]["wip_limits"] == {
        "BACKLOG": 0,
        "IN_PROGRESS": 3,
        "REVIEW": 1,
        "DONE": 0,
    }
