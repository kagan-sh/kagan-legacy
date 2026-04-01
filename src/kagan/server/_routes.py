from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.server._project_routes import register_project_routes
from kagan.server._system_routes import register_system_routes
from kagan.server._task_routes import register_task_routes

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP


def register_routes(mcp: FastMCP) -> None:
    register_task_routes(mcp)
    register_project_routes(mcp)
    register_system_routes(mcp)
