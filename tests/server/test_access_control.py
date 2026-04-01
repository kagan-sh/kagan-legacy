from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest

import kagan.server._helpers as server_helpers
from kagan.core.models import Project
from kagan.server.mcp.server import ServerOptions
from kagan.server.server import ApiServerOptions, create_api_server
from tests.helpers.server import get_http_endpoint, json_body, make_request

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.responses import JSONResponse


class _FakeTasksClient:
    def __init__(self) -> None:
        self.deleted: list[str] = []

    async def delete(self, task_id: str) -> None:
        self.deleted.append(task_id)

    async def get(self, task_id: str) -> Any:
        return SimpleNamespace(
            id=task_id,
            acceptance_criteria=[],
            status=SimpleNamespace(value="REVIEW"),
        )


class _FakeProjectsClient:
    def __init__(self) -> None:
        self.created: list[str] = []

    async def create(self, name: str) -> Any:
        self.created.append(name)
        return Project(id="project-1", name=name)


def _make_api_server(opts: ServerOptions | None = None) -> FastMCP:
    return create_api_server(ApiServerOptions(mcp_opts=opts or ServerOptions()))


@pytest.mark.asyncio
async def test_readonly_server_rejects_task_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = _make_api_server(ServerOptions(readonly=True))
    endpoint = get_http_endpoint(mcp, "/api/tasks", "POST")
    fake_ctx = SimpleNamespace(client=SimpleNamespace(), opts=ServerOptions(readonly=True))
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(make_request("POST", "/api/tasks", body={"title": "Blocked"}))
    payload = json_body(response)

    assert cast("JSONResponse", response).status_code == 403
    assert payload["ok"] is False
    assert payload["error_code"] == "ACCESS_TIER_FORBIDDEN"


@pytest.mark.asyncio
async def test_default_server_rejects_settings_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = _make_api_server(ServerOptions())
    endpoint = get_http_endpoint(mcp, "/api/settings", "POST")
    fake_ctx = SimpleNamespace(client=SimpleNamespace(), opts=ServerOptions())
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(make_request("POST", "/api/settings", body={"key": "value"}))
    payload = json_body(response)

    assert cast("JSONResponse", response).status_code == 403
    assert payload["ok"] is False
    assert payload["error_code"] == "ACCESS_TIER_FORBIDDEN"


@pytest.mark.asyncio
async def test_default_server_allows_project_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = _make_api_server(ServerOptions())
    endpoint = get_http_endpoint(mcp, "/api/projects", "POST")
    projects = _FakeProjectsClient()
    fake_ctx = SimpleNamespace(
        client=SimpleNamespace(projects=projects, active_project_id=None),
        opts=ServerOptions(),
    )
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(make_request("POST", "/api/projects", body={"name": "Web Project"}))
    payload = json_body(response)

    assert cast("JSONResponse", response).status_code == 200
    assert payload["ok"] is True
    assert payload["data"]["name"] == "Web Project"
    assert projects.created == ["Web Project"]


@pytest.mark.asyncio
async def test_admin_server_allows_task_deletion(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = _make_api_server(ServerOptions(admin=True))
    endpoint = get_http_endpoint(mcp, "/api/tasks/{task_id}", "DELETE")
    tasks = _FakeTasksClient()
    fake_ctx = SimpleNamespace(client=SimpleNamespace(tasks=tasks), opts=ServerOptions(admin=True))
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(
        make_request(
            "DELETE",
            "/api/tasks/task-1",
            path_params={"task_id": "task-1"},
        )
    )
    payload = json_body(response)

    assert cast("JSONResponse", response).status_code == 200
    assert payload["ok"] is True
    assert payload["data"] == {"task_id": "task-1", "deleted": True}
    assert tasks.deleted == ["task-1"]


@pytest.mark.asyncio
async def test_review_decide_returns_structured_manual_review_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = _make_api_server(ServerOptions())
    endpoint = get_http_endpoint(mcp, "/api/tasks/{task_id}/review/decide", "POST")
    tasks = _FakeTasksClient()
    fake_client = SimpleNamespace(tasks=tasks, reviews=SimpleNamespace())
    fake_ctx = SimpleNamespace(client=fake_client, opts=ServerOptions())
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(
        make_request(
            "POST",
            "/api/tasks/task-review/review/decide",
            body={"action": "approve"},
            path_params={"task_id": "task-review"},
        )
    )
    payload = json_body(response)

    assert cast("JSONResponse", response).status_code == 200
    assert payload["ok"] is True
    assert payload["data"]["action"] == "blocked"
    assert payload["data"]["reason_code"] == "MANUAL_REVIEW_REQUIRED"
