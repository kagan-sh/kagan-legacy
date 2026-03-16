from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.mcp.server import ServerOptions
from kagan.server.server import ApiServerOptions, create_api_server

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def _make_api_server() -> FastMCP:
    return create_api_server(ApiServerOptions(mcp_opts=ServerOptions()))


def _has_route(mcp: FastMCP, path: str, method: str) -> bool:
    return any(
        route.path == path and route.methods is not None and method in route.methods
        for route in mcp._custom_starlette_routes
    )


def test_registers_review_status_route() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/tasks/{task_id}/review", "GET")


def test_registers_review_decide_route() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/tasks/{task_id}/review/decide", "POST")


def test_registers_review_conflicts_route() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/tasks/{task_id}/review/conflicts", "GET")
