from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING

import pytest
from starlette.websockets import WebSocketDisconnect

import kagan.server._auth as auth_module
import kagan.server._websocket as websocket_module
from tests.server.test_websocket import FakeWebSocket, _get_ws_endpoint, _make_api_server

if TYPE_CHECKING:
    from collections.abc import Iterator


@pytest.fixture(autouse=True)
def _reset_websocket_state() -> Iterator[None]:
    websocket_module._ws_connections.clear()
    auth_module._paired_devices.clear()
    yield
    websocket_module._ws_connections.clear()
    auth_module._paired_devices.clear()


@pytest.mark.asyncio
async def test_websocket_disconnect_removes_connection_and_completes_handler() -> None:
    mcp = _make_api_server()
    ws_handler = _get_ws_endpoint(mcp)
    auth_module._paired_devices["device-1"] = "valid-token"
    websocket = FakeWebSocket([{"t": "AUTH", "token": "valid-token"}])

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(websocket.auth_ok_sent.wait(), timeout=1.0)
    assert len(websocket_module._ws_connections) == 1

    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    assert worker.done() is True
    assert len(websocket_module._ws_connections) == 0


@pytest.mark.asyncio
async def test_websocket_malformed_json_does_not_crash_handler() -> None:
    mcp = _make_api_server()
    ws_handler = _get_ws_endpoint(mcp)
    auth_module._paired_devices["device-1"] = "valid-token"
    websocket = FakeWebSocket([{"t": "AUTH", "token": "valid-token"}])

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(websocket.auth_ok_sent.wait(), timeout=1.0)

    await websocket.push(json.JSONDecodeError("invalid", "{", 0))
    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    assert {"t": "AUTH_OK"} in websocket.sent_json
    assert len(websocket_module._ws_connections) == 0


@pytest.mark.asyncio
async def test_websocket_heartbeat_sends_ping_and_accepts_pong(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(websocket_module, "_WS_HEARTBEAT_INTERVAL_SECONDS", 0.01)
    monkeypatch.setattr(websocket_module, "_WS_HEARTBEAT_TIMEOUT_SECONDS", 0.2)

    mcp = _make_api_server()
    ws_handler = _get_ws_endpoint(mcp)
    auth_module._paired_devices["device-1"] = "valid-token"
    websocket = FakeWebSocket([{"t": "AUTH", "token": "valid-token"}])

    worker = asyncio.create_task(ws_handler(websocket))
    await asyncio.wait_for(websocket.auth_ok_sent.wait(), timeout=1.0)
    await asyncio.wait_for(_wait_for_payload_type(websocket, payload_type="PING"), timeout=1.0)

    await websocket.push({"t": "PONG"})
    await websocket.push(WebSocketDisconnect(code=1000))
    await asyncio.wait_for(worker, timeout=1.0)

    assert {"t": "PING"} in websocket.sent_json


def test_websocket_backpressure_drops_oldest_when_queue_full() -> None:
    queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=2)
    queue.put_nowait({"seq": 1})
    queue.put_nowait({"seq": 2})
    websocket_module._ws_connections.add(queue)

    websocket_module.broadcast({"seq": 3})

    assert queue.qsize() == 2
    assert queue.get_nowait() == {"seq": 2}
    assert queue.get_nowait() == {"seq": 3}


async def _wait_for_payload_type(websocket: FakeWebSocket, *, payload_type: str) -> None:
    while True:
        if any(payload.get("t") == payload_type for payload in websocket.sent_json):
            return
        await asyncio.sleep(0)
