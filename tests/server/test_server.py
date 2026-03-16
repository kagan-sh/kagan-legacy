from __future__ import annotations

import json

import pytest
from mcp.server.fastmcp import FastMCP
from starlette.requests import Request

from kagan.mcp.server import ServerOptions
from kagan.server.server import ApiServerOptions, create_api_server


def _make_api_server() -> FastMCP:
    return create_api_server(ApiServerOptions(mcp_opts=ServerOptions()))


def test_create_api_server_returns_fastmcp_instance() -> None:
    mcp = _make_api_server()

    assert isinstance(mcp, FastMCP)


def test_create_api_server_registers_health_route() -> None:
    mcp = _make_api_server()

    assert any(
        route.path == "/health" and route.methods is not None and "GET" in route.methods
        for route in mcp._custom_starlette_routes
    )


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

    assert json.loads(response.body) == {"status": "ok", "version": "0.9.0"}
