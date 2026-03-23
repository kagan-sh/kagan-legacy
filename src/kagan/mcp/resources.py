"""kagan.mcp.resources — MCP resource registrations."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from kagan.core.errors import KaganError
from kagan.mcp.server import ServerOptions, get_server_context


def _require_server_context(mcp: FastMCP):
    app = get_server_context(mcp)
    if app is None:
        raise ValueError("MCP app context is not available")
    return app


async def _ping() -> dict[str, Any]:
    """Health check resource."""
    return {"status": "ok"}


async def _settings_snapshot(mcp: FastMCP) -> dict:
    """Current settings snapshot."""
    app = _require_server_context(mcp)
    try:
        return await app.client.settings.get()
    except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc


async def _projects_list(mcp: FastMCP) -> dict[str, Any]:
    """List of all projects."""
    app = _require_server_context(mcp)
    try:
        projects = await app.client.projects.list()
        return {"projects": [{"id": p.id, "name": p.name} for p in projects]}
    except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc


async def _task_detail(task_id: str, mcp: FastMCP) -> dict[str, Any]:
    """Task detail by ID."""
    app = _require_server_context(mcp)
    try:
        task = await app.client.tasks.get(task_id)
        return {
            "id": task.id,
            "title": task.title,
            "description": getattr(task, "description", ""),
            "status": task.status.value,
        }
    except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc


async def _runtime_info(mcp: FastMCP) -> dict[str, Any]:
    """Active sessions and agent process info."""
    _require_server_context(mcp)
    return {"sessions": [], "agents": []}


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register all kagan MCP resources — always available regardless of access tier."""

    @mcp.resource("kagan://ping", description="Health check")
    async def ping() -> dict:
        return await _ping()

    @mcp.resource("kagan://settings", description="Settings snapshot")
    async def settings_snapshot() -> dict:
        return await _settings_snapshot(mcp)

    @mcp.resource("kagan://projects", description="Project list")
    async def projects_list() -> dict:
        return await _projects_list(mcp)

    @mcp.resource("kagan://tasks/{task_id}", description="Task detail")
    async def task_detail(task_id: str) -> dict:
        return await _task_detail(task_id, mcp)

    @mcp.resource("kagan://runtime", description="Active sessions and agent processes")
    async def runtime_info() -> dict:
        return await _runtime_info(mcp)
