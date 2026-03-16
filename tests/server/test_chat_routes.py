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


def test_registers_chat_session_collection_routes() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/chat/sessions", "GET")
    assert _has_route(mcp, "/api/chat/sessions", "POST")


def test_registers_chat_session_detail_routes() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/chat/sessions/{session_id}", "GET")
    assert _has_route(mcp, "/api/chat/sessions/{session_id}", "DELETE")


def test_registers_chat_agents_route() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/chat/agents", "GET")


def test_does_not_register_chat_session_update_route() -> None:
    """Chat sessions have no PATCH endpoint — updates go through WebSocket."""
    mcp = _make_api_server()

    assert not _has_route(mcp, "/api/chat/sessions/{session_id}", "PATCH")
