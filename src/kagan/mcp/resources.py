"""kagan.mcp.resources — MCP resource registrations."""

from typing import Any

from loguru import logger
from mcp.server.fastmcp import FastMCP

from kagan.core.errors import KaganError
from kagan.mcp.server import ServerContext, ServerOptions, get_server_context
from kagan.server._access import AccessTier, is_access_allowed


def _require_server_context(mcp: FastMCP) -> ServerContext:
    app = get_server_context(mcp)
    if app is None:
        raise ValueError("MCP app context is not available")
    return app


def _check_access(ctx: ServerContext, *, resource: str, minimum_tier: AccessTier) -> None:
    """Raise ValueError if the current access tier is below the required minimum."""
    if not is_access_allowed(ctx, minimum_tier):
        logger.warning(
            "Access denied for resource {!r} (required: {})", resource, minimum_tier.name
        )
        raise ValueError(f"Insufficient access tier for resource {resource!r}")


async def _ping() -> dict[str, Any]:
    """Health check resource."""
    return {"status": "ok"}


async def _settings_snapshot(mcp: FastMCP) -> dict:
    """Current settings snapshot."""
    app = _require_server_context(mcp)
    _check_access(app, resource="kagan://settings", minimum_tier=AccessTier.READONLY)
    try:
        return await app.client.settings.get()
    except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc


async def _projects_list(mcp: FastMCP) -> dict[str, Any]:
    """List of all projects."""
    app = _require_server_context(mcp)
    _check_access(app, resource="kagan://projects", minimum_tier=AccessTier.READONLY)
    try:
        projects = await app.client.projects.list()
        return {"projects": [{"id": p.id, "name": p.name} for p in projects]}
    except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
        raise ValueError(str(exc)) from exc


async def _task_detail(task_id: str, mcp: FastMCP) -> dict[str, Any]:
    """Task detail by ID."""
    app = _require_server_context(mcp)
    _check_access(app, resource="kagan://tasks/{task_id}", minimum_tier=AccessTier.READONLY)
    try:
        task = await app.client.tasks.get(task_id)
        if app.bound_project_id and task.project_id != app.bound_project_id:
            raise ValueError("Task does not belong to the current project")
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
    app = _require_server_context(mcp)
    _check_access(app, resource="kagan://runtime", minimum_tier=AccessTier.READONLY)
    return {"sessions": [], "agents": []}


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register all kagan MCP resources.

    Access tier enforcement:
    - kagan://ping — unrestricted (health check)
    - All other resources — require at least READONLY access
    """

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
