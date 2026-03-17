from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from starlette.websockets import WebSocketDisconnect

import kagan.server._websocket as websocket_module
from kagan.core.enums import Priority, TaskStatus, WorkMode
from kagan.core.models import Task
from kagan.mcp.server import ServerOptions
from tests.helpers.server_ws import FakeWebSocket, get_ws_endpoint, make_api_server

if TYPE_CHECKING:
    from collections.abc import Iterator


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


def _fake_task(task_id: str, *, title: str = "Task", agent_backend: str | None = None) -> Task:
    return Task(
        id=task_id,
        project_id="project-1",
        title=title,
        description="",
        status=TaskStatus.BACKLOG,
        priority=Priority.MEDIUM,
        execution_mode=WorkMode.AUTO,
        base_branch=None,
        acceptance_criteria=[],
        agent_backend=agent_backend,
        launcher=None,
        review_approved=False,
        review_verdicts=[],
    )


@pytest.fixture(autouse=True)
def _reset_websocket_state() -> Iterator[None]:
    websocket_module._ws_connections.clear()
    yield
    websocket_module._ws_connections.clear()


@pytest.mark.asyncio
async def test_websocket_tracks_connection_and_handles_ping_and_broadcast() -> None:
    mcp = make_api_server()
    ws_handler = get_ws_endpoint(mcp)
    websocket = FakeWebSocket([])

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.sleep(0)
    assert len(websocket_module._ws_connections) == 1

    websocket_module.broadcast({"t": "TASK_UPDATED", "task_id": "task-1"})
    await asyncio.wait_for(websocket.event_sent.wait(), timeout=1.0)

    await websocket.push({"t": "PING"})
    await asyncio.wait_for(websocket.pong_sent.wait(), timeout=1.0)

    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    assert {"t": "TASK_UPDATED", "task_id": "task-1"} in websocket.sent_json
    assert {"t": "PONG"} in websocket.sent_json
    assert len(websocket_module._ws_connections) == 0


@pytest.mark.asyncio
async def test_websocket_board_subscribe_returns_board_sync(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp = make_api_server()
    ws_handler = get_ws_endpoint(mcp)

    fake_client = _FakeCoreClient()
    fake_client.tasks._tasks = [_fake_task("task-1", title="Ship feature")]
    fake_ctx = SimpleNamespace(client=fake_client)
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: fake_ctx)

    websocket = FakeWebSocket([{"t": "BOARD_SUBSCRIBE"}])

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(
        _wait_for_payload_type(websocket, payload_type="BOARD_SYNC"), timeout=1.0
    )
    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    board_sync = next(
        payload for payload in websocket.sent_json if payload.get("t") == "BOARD_SYNC"
    )
    assert len(board_sync["tasks"]) == 1
    task_data = board_sync["tasks"][0]
    assert task_data["id"] == "task-1"
    assert task_data["title"] == "Ship feature"
    assert task_data["status"] == "BACKLOG"
    assert task_data["priority"] == "MEDIUM"
    assert task_data["execution_mode"] == "AUTO"
    assert task_data["has_workspace"] is False
    assert task_data["active_session"] is None


@pytest.mark.asyncio
async def test_websocket_run_start_starts_session_and_acks(monkeypatch: pytest.MonkeyPatch) -> None:
    mcp = make_api_server()
    ws_handler = get_ws_endpoint(mcp)

    fake_client = _FakeCoreClient()
    fake_client.tasks._tasks = [_fake_task("task-1", agent_backend="cursor-agent")]
    fake_ctx = SimpleNamespace(client=fake_client)
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: fake_ctx)

    websocket = FakeWebSocket([{"t": "RUN_START", "task_id": "task-1", "mode": "AUTO"}])

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(
        _wait_for_payload_type(websocket, payload_type="RUN_STARTED"), timeout=1.0
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
    mcp = make_api_server()
    ws_handler = get_ws_endpoint(mcp)

    fake_client = _FakeCoreClient()
    fake_ctx = SimpleNamespace(client=fake_client)
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: fake_ctx)

    websocket = FakeWebSocket([{"t": "RUN_CANCEL", "task_id": "task-1"}])

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(
        _wait_for_payload_type(websocket, payload_type="RUN_CANCELLED"), timeout=1.0
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
    mcp = make_api_server()
    ws_handler = get_ws_endpoint(mcp)

    fake_client = _FakeCoreClient()
    fake_ctx = SimpleNamespace(client=fake_client, opts=ServerOptions(readonly=True))
    monkeypatch.setattr(websocket_module, "get_server_context", lambda _mcp: fake_ctx)

    websocket = FakeWebSocket([{"t": "RUN_START", "task_id": "task-1", "mode": "AUTO"}])

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(_wait_for_payload_type(websocket, payload_type="RUN_ERROR"), timeout=1.0)
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
