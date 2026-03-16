from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocketDisconnect

import kagan.server._auth as auth_module
import kagan.server._websocket as websocket_module
from kagan.mcp.server import ServerOptions
from kagan.server.server import ApiServerOptions, create_api_server
from kagan.wire.models import utc_iso

if TYPE_CHECKING:
    from collections.abc import Iterator

    from mcp.server.fastmcp import FastMCP


class FakeWebSocket:
    def __init__(self, incoming: list[dict[str, object] | Exception] | None = None) -> None:
        self.accepted = False
        self.sent_json: list[dict[str, object]] = []
        self.close_calls: list[tuple[int, str]] = []
        self.auth_ok_sent = asyncio.Event()
        self.pong_sent = asyncio.Event()
        self.event_sent = asyncio.Event()
        self._incoming: asyncio.Queue[dict[str, object] | Exception] = asyncio.Queue()
        for item in incoming or []:
            self._incoming.put_nowait(item)

    async def accept(self) -> None:
        self.accepted = True

    async def receive_json(self) -> dict[str, object]:
        item = await self._incoming.get()
        if isinstance(item, Exception):
            raise item
        return item

    async def send_json(self, payload: dict[str, object]) -> None:
        self.sent_json.append(payload)
        if payload.get("t") == "AUTH_OK":
            self.auth_ok_sent.set()
        if payload.get("t") == "PONG":
            self.pong_sent.set()
        if payload.get("t") == "TASK_UPDATED":
            self.event_sent.set()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_calls.append((code, reason))

    async def push(self, item: dict[str, object] | Exception) -> None:
        await self._incoming.put(item)


class _FakeTasksClient:
    def __init__(self) -> None:
        self._tasks: list[Any] = []
        self._run_session_id = "session-1"
        self.run_calls: list[dict[str, str]] = []
        self.cancel_calls: list[str] = []

    async def list(self) -> list[Any]:
        return self._tasks

    async def get(self, task_id: str) -> Any:
        for task in self._tasks:
            if task.id == task_id:
                return task
        raise ValueError("Task not found")

    async def runtime_summaries(self, task_ids: list[str]) -> dict[str, dict[str, Any]]:
        return {
            task_id: {"has_workspace": False, "last_event_at": None, "active_session": None}
            for task_id in task_ids
        }

    async def run(self, task_id: str, *, agent_backend: str) -> object:
        self.run_calls.append({"task_id": task_id, "agent_backend": agent_backend})
        return SimpleNamespace(id=self._run_session_id)

    async def cancel(self, task_id: str) -> None:
        self.cancel_calls.append(task_id)


class _FakeSettingsClient:
    async def get(self) -> dict[str, str]:
        return {"default_agent_backend": "claude-code"}


class _FakeCoreClient:
    def __init__(self) -> None:
        self.tasks = _FakeTasksClient()
        self.settings = _FakeSettingsClient()


def _fake_task(task_id: str, *, title: str = "Task", agent_backend: str | None = None) -> object:
    return SimpleNamespace(
        id=task_id,
        title=title,
        description="",
        status=SimpleNamespace(value="BACKLOG"),
        priority=SimpleNamespace(name="MEDIUM"),
        execution_mode=SimpleNamespace(value="AUTO"),
        base_branch=None,
        acceptance_criteria=[],
        agent_backend=agent_backend,
        launcher=None,
        review_approved=False,
        review_verdicts=[],
        updated_at=datetime.now(UTC),
    )


def _make_api_server() -> FastMCP:
    return create_api_server(ApiServerOptions(mcp_opts=ServerOptions()))


def _get_ws_endpoint(mcp: FastMCP):
    route = next(
        route
        for route in mcp._custom_starlette_routes
        if isinstance(route, WebSocketRoute) and route.path == "/ws"
    )
    return route.endpoint


@pytest.fixture(autouse=True)
def _reset_websocket_state() -> Iterator[None]:
    websocket_module._ws_connections.clear()
    auth_module._paired_devices.clear()
    yield
    websocket_module._ws_connections.clear()
    auth_module._paired_devices.clear()


def test_create_api_server_registers_websocket_route() -> None:
    mcp = _make_api_server()

    assert any(
        isinstance(route, WebSocketRoute) and route.path == "/ws"
        for route in mcp._custom_starlette_routes
    )


@pytest.mark.asyncio
async def test_websocket_rejects_invalid_auth_token() -> None:
    mcp = _make_api_server()
    ws_handler = _get_ws_endpoint(mcp)
    websocket = FakeWebSocket([{"t": "AUTH", "token": "invalid-token"}])

    await ws_handler(websocket)

    assert websocket.accepted is True
    assert websocket.sent_json == [{"t": "AUTH_FAIL"}]
    assert websocket.close_calls == [(4003, "Unauthorized")]


@pytest.mark.asyncio
async def test_websocket_tracks_connection_and_handles_ping_and_broadcast() -> None:
    mcp = _make_api_server()
    ws_handler = _get_ws_endpoint(mcp)
    auth_module._paired_devices["device-1"] = "valid-token"
    websocket = FakeWebSocket([{"t": "AUTH", "token": "valid-token"}])

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(websocket.auth_ok_sent.wait(), timeout=1.0)
    assert len(websocket_module._ws_connections) == 1

    websocket_module.broadcast({"t": "TASK_UPDATED", "task_id": "task-1"})
    await asyncio.wait_for(websocket.event_sent.wait(), timeout=1.0)

    await websocket.push({"t": "PING"})
    await asyncio.wait_for(websocket.pong_sent.wait(), timeout=1.0)

    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    assert {"t": "AUTH_OK"} in websocket.sent_json
    assert {"t": "TASK_UPDATED", "task_id": "task-1"} in websocket.sent_json
    assert {"t": "PONG"} in websocket.sent_json
    assert len(websocket_module._ws_connections) == 0


@pytest.mark.asyncio
async def test_websocket_board_subscribe_returns_board_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = _make_api_server()
    ws_handler = _get_ws_endpoint(mcp)
    auth_module._paired_devices["device-1"] = "valid-token"

    fake_client = _FakeCoreClient()
    fake_client.tasks._tasks = [_fake_task("task-1", title="Ship feature")]
    fake_ctx = SimpleNamespace(client=fake_client)
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: fake_ctx)

    websocket = FakeWebSocket(
        [
            {"t": "AUTH", "token": "valid-token"},
            {"t": "BOARD_SUBSCRIBE"},
        ]
    )

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(websocket.auth_ok_sent.wait(), timeout=1.0)
    await asyncio.wait_for(
        _wait_for_payload_type(websocket, payload_type="BOARD_SYNC"),
        timeout=1.0,
    )
    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    board_sync = next(
        payload for payload in websocket.sent_json if payload.get("t") == "BOARD_SYNC"
    )
    assert board_sync["tasks"] == [
        {
            "id": "task-1",
            "title": "Ship feature",
            "description": "",
            "status": "BACKLOG",
            "priority": "MEDIUM",
            "execution_mode": "AUTO",
            "base_branch": None,
            "acceptance_criteria": [],
            "agent_backend": None,
            "launcher": None,
            "review_approved": False,
            "review_verdicts": [],
            "updated_at": utc_iso(fake_client.tasks._tasks[0].updated_at),
            "last_event_at": None,
            "has_workspace": False,
            "review_running": False,
            "active_session": None,
        }
    ]


@pytest.mark.asyncio
async def test_websocket_run_start_starts_session_and_acks(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = _make_api_server()
    ws_handler = _get_ws_endpoint(mcp)
    auth_module._paired_devices["device-1"] = "valid-token"

    fake_client = _FakeCoreClient()
    fake_client.tasks._tasks = [_fake_task("task-1", agent_backend="cursor-agent")]
    fake_ctx = SimpleNamespace(client=fake_client)
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: fake_ctx)

    websocket = FakeWebSocket(
        [
            {"t": "AUTH", "token": "valid-token"},
            {"t": "RUN_START", "task_id": "task-1", "mode": "AUTO"},
        ]
    )

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(websocket.auth_ok_sent.wait(), timeout=1.0)
    await asyncio.wait_for(
        _wait_for_payload_type(websocket, payload_type="RUN_STARTED"),
        timeout=1.0,
    )
    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    assert {
        "t": "RUN_STARTED",
        "session_id": "session-1",
        "task_id": "task-1",
    } in websocket.sent_json
    assert {"t": "TASK_UPDATED", "task_id": "task-1"} in websocket.sent_json
    assert fake_client.tasks.run_calls == [{"task_id": "task-1", "agent_backend": "cursor-agent"}]


@pytest.mark.asyncio
async def test_websocket_run_cancel_cancels_session_and_acks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = _make_api_server()
    ws_handler = _get_ws_endpoint(mcp)
    auth_module._paired_devices["device-1"] = "valid-token"

    fake_client = _FakeCoreClient()
    fake_ctx = SimpleNamespace(client=fake_client)
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: fake_ctx)

    websocket = FakeWebSocket(
        [
            {"t": "AUTH", "token": "valid-token"},
            {"t": "RUN_CANCEL", "task_id": "task-1"},
        ]
    )

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(websocket.auth_ok_sent.wait(), timeout=1.0)
    await asyncio.wait_for(
        _wait_for_payload_type(websocket, payload_type="RUN_CANCELLED"),
        timeout=1.0,
    )
    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    assert {"t": "RUN_CANCELLED", "task_id": "task-1"} in websocket.sent_json
    assert {"t": "TASK_UPDATED", "task_id": "task-1"} in websocket.sent_json
    assert fake_client.tasks.cancel_calls == ["task-1"]


@pytest.mark.asyncio
async def test_websocket_run_start_rejects_readonly_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = _make_api_server()
    ws_handler = _get_ws_endpoint(mcp)
    auth_module._paired_devices["device-1"] = "valid-token"

    fake_client = _FakeCoreClient()
    fake_ctx = SimpleNamespace(client=fake_client, opts=ServerOptions(readonly=True))
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: fake_ctx)

    websocket = FakeWebSocket(
        [
            {"t": "AUTH", "token": "valid-token"},
            {"t": "RUN_START", "task_id": "task-1", "mode": "AUTO"},
        ]
    )

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(websocket.auth_ok_sent.wait(), timeout=1.0)
    await asyncio.wait_for(
        _wait_for_payload_type(websocket, payload_type="RUN_ERROR"),
        timeout=1.0,
    )
    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    assert {
        "t": "RUN_ERROR",
        "error": "Task execution requires standard access.",
        "error_code": "ACCESS_TIER_FORBIDDEN",
    } in websocket.sent_json
    assert fake_client.tasks.run_calls == []


@pytest.mark.asyncio
async def test_handle_chat_send_uses_active_project_repo_as_cwd(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    class _FakeProjectsClient:
        async def repos(self, project_id: str) -> list[Any]:
            assert project_id == "project-1"
            return [SimpleNamespace(id="repo-1", path=str(tmp_path))]

        async def resolve_repo(
            self, project_id: str, *, selected_repo_id: str | None = None
        ) -> Any:
            repos = await self.repos(project_id)
            return repos[0]

        async def resolve_repo_path(
            self, *, project_id: str | None = None, settings: dict[str, str] | None = None
        ) -> Path | None:
            repo = await self.resolve_repo(project_id or "project-1")
            p = Path(repo.path)
            return p if p.is_dir() else None

    class _FakeSettingsWithSelectedRepo:
        async def get(self) -> dict[str, str]:
            return {
                "default_agent_backend": "claude-code",
                "ui.selected_repo.project-1": "repo-1",
            }

    fake_client = SimpleNamespace(
        tasks=_FakeTasksClient(),
        settings=_FakeSettingsWithSelectedRepo(),
        active_project_id="project-1",
        projects=_FakeProjectsClient(),
    )
    fake_ctx = SimpleNamespace(client=fake_client)
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: fake_ctx)

    import kagan.chat.acp as chat_acp
    import kagan.chat.sessions as chat_sessions

    captured: dict[str, Any] = {}

    async def _fake_run_orchestrator_turn(
        _client: Any,
        *,
        prompt: str,
        agent_backend: str,
        on_update: Any,
        attachments: Any,
        cwd: Any,
    ) -> str:
        captured["cwd"] = cwd
        captured["prompt"] = prompt
        captured["agent_backend"] = agent_backend
        del on_update, attachments
        return "done"

    session = {
        "id": "chat-1",
        "label": "Chat",
        "agent_backend": "claude-code",
        "orchestrator_history": [["user", "before"], ["assistant", "before"]],
    }

    async def _fake_get_chat_session(_client: Any, session_id: str) -> dict[str, Any] | None:
        return session if session_id == "chat-1" else None

    async def _fake_save_chat_session(_client: Any, updated: dict[str, Any]) -> None:
        session.update(updated)

    monkeypatch.setattr(chat_acp, "run_orchestrator_turn", _fake_run_orchestrator_turn)
    monkeypatch.setattr(chat_sessions, "get_chat_session", _fake_get_chat_session)
    monkeypatch.setattr(chat_sessions, "save_chat_session", _fake_save_chat_session)

    websocket = FakeWebSocket()
    await websocket_module._handle_chat_send(
        websocket=cast("Any", websocket),
        mcp=cast("Any", SimpleNamespace()),
        session_id="chat-1",
        text="continue",
        agent_backend=None,
        attachments=None,
    )

    assert captured["cwd"] == tmp_path
    assert captured["agent_backend"] == "claude-code"
    assert any(payload.get("t") == "CHAT_DONE" for payload in websocket.sent_json)


async def _wait_for_payload_type(websocket: FakeWebSocket, *, payload_type: str) -> None:
    while True:
        if any(payload.get("t") == payload_type for payload in websocket.sent_json):
            return
        await asyncio.sleep(0)


def test_broadcast_drops_oldest_event_when_queue_is_full() -> None:
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=2)
    queue.put_nowait({"seq": 1})
    queue.put_nowait({"seq": 2})
    websocket_module._ws_connections.add(queue)

    websocket_module.broadcast({"seq": 3})

    first = queue.get_nowait()
    second = queue.get_nowait()
    assert first == {"seq": 2}
    assert second == {"seq": 3}
