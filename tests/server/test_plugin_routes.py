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


def test_registers_plugin_listing_route() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/plugins", "GET")


def test_registers_plugin_preflight_route() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/plugins/{name}/preflight", "GET")


def test_registers_plugin_detect_repo_route() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/plugins/{name}/detect-repo", "GET")


def test_registers_plugin_import_route() -> None:
    mcp = _make_api_server()

    assert _has_route(mcp, "/api/plugins/{name}/import", "POST")
