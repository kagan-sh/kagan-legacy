"""Server test helpers — request/response factories for route-level tests.

Extracted from test_integration.py and test_access_control.py to avoid
copy-pasting 30 lines of request scaffolding across server test files.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING, Any, cast

from starlette.requests import Request

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.fastmcp import FastMCP
    from starlette.responses import JSONResponse


def get_http_endpoint(
    mcp: FastMCP,
    path: str,
    method: str,
) -> Callable[[Request], Awaitable[object]]:
    """Look up a registered HTTP route handler by path and method."""
    route = next(
        route
        for route in mcp._custom_starlette_routes
        if route.path == path and route.methods is not None and method in route.methods
    )
    return route.endpoint


def make_request(
    method: str,
    path: str,
    *,
    body: object | None = None,
    headers: dict[str, str] | None = None,
    path_params: dict[str, str] | None = None,
) -> Request:
    """Build a Starlette Request for direct route handler invocation."""
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


def json_body(response: object) -> dict[str, Any]:
    """Extract parsed JSON from a JSONResponse."""
    body = bytes(cast("JSONResponse", response).body)
    return cast("dict[str, Any]", json.loads(body))


def make_ws_message(msg_type: str, **payload: object) -> dict[str, object]:
    """Build a WebSocket message dict with the given type and payload."""
    return {"t": msg_type, **payload}


__all__ = [
    "get_http_endpoint",
    "json_body",
    "make_request",
    "make_ws_message",
]
