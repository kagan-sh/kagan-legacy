from __future__ import annotations

import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from starlette.requests import Request

import kagan.server._helpers as server_helpers
from kagan.core.models import Project
from kagan.mcp.server import ServerOptions
from kagan.server.server import ApiServerOptions, create_api_server

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

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


def _get_endpoint(
    mcp: FastMCP,
    path: str,
    method: str,
) -> Callable[[Request], Awaitable[object]]:
    route = next(
        route
        for route in mcp._custom_starlette_routes
        if route.path == path and route.methods is not None and method in route.methods
    )
    return route.endpoint


def _make_request(
    method: str,
    path: str,
    *,
    body: dict[str, object] | None = None,
    path_params: dict[str, str] | None = None,
) -> Request:
    payload = json.dumps(body).encode() if body is not None else b""
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "headers": [],
        "query_string": b"",
        "scheme": "http",
        "server": ("127.0.0.1", 8765),
        "client": ("127.0.0.1", 12345),
        "path_params": path_params or {},
    }
    sent = False

    async def receive() -> dict[str, object]:
        nonlocal sent
        if sent:
            return {"type": "http.request", "body": b"", "more_body": False}
        sent = True
        return {"type": "http.request", "body": payload, "more_body": False}

    return Request(scope, receive)


def _response_json(response: object) -> dict[str, Any]:
    body = bytes(cast("JSONResponse", response).body)
    return cast("dict[str, Any]", json.loads(body))


@pytest.mark.asyncio
async def test_readonly_server_rejects_task_creation(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = _make_api_server(ServerOptions(readonly=True))
    endpoint = _get_endpoint(mcp, "/api/tasks", "POST")
    fake_ctx = SimpleNamespace(client=SimpleNamespace(), opts=ServerOptions(readonly=True))
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(_make_request("POST", "/api/tasks", body={"title": "Blocked"}))
    payload = _response_json(response)

    assert cast("JSONResponse", response).status_code == 403
    assert payload["ok"] is False
    assert payload["error_code"] == "ACCESS_TIER_FORBIDDEN"


@pytest.mark.asyncio
async def test_default_server_rejects_settings_changes(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = _make_api_server(ServerOptions())
    endpoint = _get_endpoint(mcp, "/api/settings", "POST")
    fake_ctx = SimpleNamespace(client=SimpleNamespace(), opts=ServerOptions())
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(_make_request("POST", "/api/settings", body={"key": "value"}))
    payload = _response_json(response)

    assert cast("JSONResponse", response).status_code == 403
    assert payload["ok"] is False
    assert payload["error_code"] == "ACCESS_TIER_FORBIDDEN"


@pytest.mark.asyncio
async def test_default_server_allows_project_creation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = _make_api_server(ServerOptions())
    endpoint = _get_endpoint(mcp, "/api/projects", "POST")
    projects = _FakeProjectsClient()
    fake_ctx = SimpleNamespace(
        client=SimpleNamespace(projects=projects, active_project_id=None),
        opts=ServerOptions(),
    )
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(_make_request("POST", "/api/projects", body={"name": "Web Project"}))
    payload = _response_json(response)

    assert cast("JSONResponse", response).status_code == 200
    assert payload["ok"] is True
    assert payload["data"]["name"] == "Web Project"
    assert projects.created == ["Web Project"]


@pytest.mark.asyncio
async def test_admin_server_allows_task_deletion(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = _make_api_server(ServerOptions(admin=True))
    endpoint = _get_endpoint(mcp, "/api/tasks/{task_id}", "DELETE")
    tasks = _FakeTasksClient()
    fake_ctx = SimpleNamespace(client=SimpleNamespace(tasks=tasks), opts=ServerOptions(admin=True))
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(
        _make_request(
            "DELETE",
            "/api/tasks/task-1",
            path_params={"task_id": "task-1"},
        )
    )
    payload = _response_json(response)

    assert cast("JSONResponse", response).status_code == 200
    assert payload["ok"] is True
    assert payload["data"] == {"task_id": "task-1", "deleted": True}
    assert tasks.deleted == ["task-1"]


@pytest.mark.asyncio
async def test_review_decide_returns_structured_manual_review_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = _make_api_server(ServerOptions())
    endpoint = _get_endpoint(mcp, "/api/tasks/{task_id}/review/decide", "POST")
    tasks = _FakeTasksClient()
    fake_client = SimpleNamespace(tasks=tasks, reviews=SimpleNamespace())
    fake_ctx = SimpleNamespace(client=fake_client, opts=ServerOptions())
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: fake_ctx)

    response = await endpoint(
        _make_request(
            "POST",
            "/api/tasks/task-review/review/decide",
            body={"action": "approve"},
            path_params={"task_id": "task-review"},
        )
    )
    payload = _response_json(response)

    assert cast("JSONResponse", response).status_code == 200
    assert payload["ok"] is True
    assert payload["data"]["action"] == "blocked"
    assert payload["data"]["reason_code"] == "MANUAL_REVIEW_REQUIRED"
