from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from starlette.requests import Request
from starlette.websockets import WebSocketDisconnect

import kagan.server._helpers as server_helpers
import kagan.server._routes as routes_module
import kagan.server._websocket as websocket_module
from kagan.core import Priority, TaskStatus, WorkMode
from kagan.core import git as git_module
from kagan.mcp.server import ServerOptions
from tests.helpers.server_ws import FakeWebSocket, get_ws_endpoint, make_api_server

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Iterator

    from mcp.server.fastmcp import FastMCP
    from starlette.responses import JSONResponse


class _FakeTasksClient:
    def __init__(self) -> None:
        self._seq = 0
        self._tasks: dict[str, Any] = {}

    async def list(self, status: TaskStatus | None = None) -> list[Any]:
        tasks = list(self._tasks.values())
        if status is None:
            return tasks
        return [task for task in tasks if task.status == status]

    async def create(
        self,
        title: str,
        *,
        description: str = "",
        execution_mode: WorkMode = WorkMode.AUTO,
        priority: Priority = Priority.MEDIUM,
        base_branch: str | None = None,
        acceptance_criteria: list[str] | None = None,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> Any:
        self._seq += 1
        task = SimpleNamespace(
            id=f"task-{self._seq}",
            title=title,
            description=description,
            status=TaskStatus.BACKLOG,
            priority=priority,
            execution_mode=execution_mode,
            base_branch=base_branch,
            acceptance_criteria=acceptance_criteria or [],
            agent_backend=agent_backend,
            launcher=launcher,
            review_approved=False,
            updated_at=datetime.now(UTC),
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


def _get_http_endpoint(
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
    body: object | None = None,
    headers: dict[str, str] | None = None,
    path_params: dict[str, str] | None = None,
) -> Request:
    payload = json.dumps(body).encode() if body is not None else b""
    raw_headers = [(key.lower().encode(), value.encode()) for key, value in (headers or {}).items()]
    scope = {
        "type": "http",
        "http_version": "1.1",
        "method": method,
        "path": path,
        "raw_path": path.encode(),
        "headers": raw_headers,
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


def _as_json_response(response: object) -> JSONResponse:
    return cast("JSONResponse", response)


def _json_data(response: object) -> dict[str, Any]:
    body = bytes(_as_json_response(response).body)
    return cast("dict[str, Any]", json.loads(body))


async def _wait_for_payload_type(websocket: FakeWebSocket, *, payload_type: str) -> None:
    while True:
        if any(payload.get("t") == payload_type for payload in websocket.sent_json):
            return
        await asyncio.sleep(0)


async def _wait_for_board_sync_count(websocket: FakeWebSocket, *, count: int) -> None:
    while True:
        board_syncs = [
            payload for payload in websocket.sent_json if payload.get("t") == "BOARD_SYNC"
        ]
        if len(board_syncs) >= count:
            return
        await asyncio.sleep(0)


async def _wait_for_board_sync_task_title(websocket: FakeWebSocket, *, title: str) -> None:
    while True:
        board_syncs = [
            cast("dict[str, object]", payload)
            for payload in websocket.sent_json
            if payload.get("t") == "BOARD_SYNC"
        ]
        if board_syncs:
            tasks_payload = cast("list[dict[str, Any]]", board_syncs[-1]["tasks"])
            if any(task.get("title") == title for task in tasks_payload):
                return
        await asyncio.sleep(0)


@pytest.fixture(autouse=True)
def _reset_server_state() -> Iterator[None]:
    websocket_module._ws_connections.clear()
    yield
    websocket_module._ws_connections.clear()


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
    create = _get_http_endpoint(mcp, "/api/tasks", "POST")
    created = _json_data(
        await create(
            _make_request(
                "POST",
                "/api/tasks",
                body={"title": "Ship"},
            )
        )
    )["data"]
    task_id = created["id"]
    update = _get_http_endpoint(mcp, "/api/tasks/{task_id}", "PATCH")
    status = _get_http_endpoint(mcp, "/api/tasks/{task_id}/status", "POST")
    delete = _get_http_endpoint(mcp, "/api/tasks/{task_id}", "DELETE")
    assert (
        _json_data(
            await update(
                _make_request(
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
        _json_data(
            await status(
                _make_request(
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
        _json_data(
            await delete(
                _make_request("DELETE", f"/api/tasks/{task_id}", path_params={"task_id": task_id})
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

    commits = _get_http_endpoint(mcp, "/api/tasks/{task_id}/commits", "GET")
    payload = _json_data(
        await commits(
            _make_request(
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
async def test_websocket_board_subscribe_returns_board_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    tasks = _FakeTasksClient()
    await tasks.create("Task from API")
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: _ctx(tasks))
    websocket = FakeWebSocket([{"t": "BOARD_SUBSCRIBE"}])
    worker = asyncio.create_task(get_ws_endpoint(mcp)(websocket))
    await asyncio.wait_for(
        _wait_for_payload_type(websocket, payload_type="BOARD_SYNC"), timeout=1.0
    )
    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)
    board_sync = cast(
        "dict[str, object]",
        next(payload for payload in websocket.sent_json if payload.get("t") == "BOARD_SYNC"),
    )
    tasks_payload = cast("list[dict[str, Any]]", board_sync["tasks"])
    assert tasks_payload[0]["title"] == "Task from API"


@pytest.mark.asyncio
async def test_two_clients_see_board_sync_after_rest_create(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    tasks = _FakeTasksClient()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: _ctx(tasks))
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: _ctx(tasks))
    ws_handler = get_ws_endpoint(mcp)
    ws_a = FakeWebSocket([{"t": "BOARD_SUBSCRIBE"}])
    ws_b = FakeWebSocket([{"t": "BOARD_SUBSCRIBE"}])
    worker_a = asyncio.create_task(ws_handler(ws_a))
    worker_b = asyncio.create_task(ws_handler(ws_b))
    await asyncio.wait_for(_wait_for_board_sync_count(ws_b, count=1), timeout=1.0)
    create = _get_http_endpoint(mcp, "/api/tasks", "POST")
    await create(_make_request("POST", "/api/tasks", body={"title": "Shared task"}))
    await ws_b.push({"t": "BOARD_SUBSCRIBE"})
    await asyncio.wait_for(_wait_for_board_sync_count(ws_b, count=2), timeout=1.0)
    await asyncio.wait_for(_wait_for_board_sync_task_title(ws_b, title="Shared task"), timeout=1.0)
    board_sync = cast(
        "dict[str, object]",
        [payload for payload in ws_b.sent_json if payload.get("t") == "BOARD_SYNC"][-1],
    )
    tasks_payload = cast("list[dict[str, Any]]", board_sync["tasks"])
    assert any(task["title"] == "Shared task" for task in tasks_payload)
    await ws_a.push(WebSocketDisconnect(code=1000))
    await ws_b.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker_a, timeout=1.0)
    await asyncio.wait_for(worker_b, timeout=1.0)


@pytest.mark.asyncio
async def test_missing_fields_return_error_envelopes(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = make_api_server()
    tasks = _FakeTasksClient()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: _ctx(tasks))
    create = _get_http_endpoint(mcp, "/api/tasks", "POST")
    create_missing = _as_json_response(
        await create(_make_request("POST", "/api/tasks", body={"description": "x"}))
    )
    create_payload = _json_data(create_missing)
    assert create_missing.status_code == 400
    assert create_payload["ok"] is False
    assert create_payload["error"] == "Missing field: title"


@pytest.mark.asyncio
async def test_malformed_create_request_body_returns_400(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = make_api_server()
    tasks = _FakeTasksClient()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _mcp: _ctx(tasks))
    create = _get_http_endpoint(mcp, "/api/tasks", "POST")
    response = _as_json_response(
        await create(_make_request("POST", "/api/tasks", body=["not", "an", "object"]))
    )
    payload = json.loads(bytes(response.body))
    assert response.status_code == 400
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

    resolved = _get_http_endpoint(mcp, "/api/settings/resolved", "GET")
    payload = _json_data(await resolved(_make_request("GET", "/api/settings/resolved")))

    assert payload["data"]["git_user_name"] == "Kagan Agent"
    assert payload["data"]["workflow"]["wip_limits"] == {
        "BACKLOG": 0,
        "IN_PROGRESS": 3,
        "REVIEW": 1,
        "DONE": 0,
    }
