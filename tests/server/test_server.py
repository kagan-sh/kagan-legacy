from __future__ import annotations

import json

import pytest
from starlette.requests import Request

from kagan.mcp.server import ServerOptions
from kagan.server.server import ApiServerOptions, create_api_server


def _make_api_server():
    return create_api_server(ApiServerOptions(mcp_opts=ServerOptions()))


@pytest.mark.asyncio
async def test_health_route_returns_status_and_version_json() -> None:
    mcp = _make_api_server()
    route = next(route for route in mcp._custom_starlette_routes if route.path == "/health")
    request = Request(
        {
            "type": "http",
            "http_version": "1.1",
            "method": "GET",
            "path": "/health",
            "raw_path": b"/health",
            "headers": [],
            "query_string": b"",
            "scheme": "http",
            "server": ("127.0.0.1", 8765),
            "client": ("127.0.0.1", 12345),
        }
    )

    response = await route.endpoint(request)

    payload = json.loads(response.body)
    assert payload["status"] == "ok"
    assert isinstance(payload.get("version"), str)
    assert payload["version"]
