from __future__ import annotations

import asyncio
from typing import Any

from starlette.routing import WebSocketRoute

from kagan.mcp.server import ServerOptions
from kagan.server.server import ApiServerOptions, create_api_server


class FakeWebSocket:
    def __init__(self, incoming: list[dict[str, object] | Exception] | None = None) -> None:
        self.accepted = False
        self.sent_json: list[dict[str, object]] = []
        self.close_calls: list[tuple[int, str]] = []
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
        if payload.get("t") == "PONG":
            self.pong_sent.set()
        if payload.get("t") in {"TASK_UPDATED", "BOARD_SYNC"}:
            self.event_sent.set()

    async def close(self, code: int = 1000, reason: str = "") -> None:
        self.close_calls.append((code, reason))

    async def push(self, item: dict[str, object] | Exception) -> None:
        await self._incoming.put(item)


def make_api_server():
    return create_api_server(ApiServerOptions(mcp_opts=ServerOptions()))


def get_ws_endpoint(mcp: Any):
    route = next(
        route
        for route in mcp._custom_starlette_routes
        if isinstance(route, WebSocketRoute) and route.path == "/ws"
    )
    return route.endpoint
