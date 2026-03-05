"""kagan.mcp.toolsets — Domain toolset registry."""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import cast

from mcp.server.fastmcp import FastMCP

from kagan.core.errors import KaganError
from kagan.mcp.server import ServerOptions


def mcp_error_boundary[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def _wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        try:
            return await fn(*args, **kwargs)
        except (KaganError, OSError, RuntimeError, ValueError, TypeError) as exc:
            raise ValueError(str(exc)) from exc

    return cast("Callable[P, Awaitable[R]]", _wrapped)


def register_all_toolsets(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register all domain toolsets on the MCP server."""
    from kagan.mcp.toolsets.diagnostics import register as register_diagnostics
    from kagan.mcp.toolsets.plugins import register as register_plugins
    from kagan.mcp.toolsets.projects import register as register_projects
    from kagan.mcp.toolsets.review import register as register_review
    from kagan.mcp.toolsets.sessions import register as register_sessions
    from kagan.mcp.toolsets.settings import register as register_settings
    from kagan.mcp.toolsets.tasks import register as register_tasks

    register_tasks(mcp, opts)
    register_sessions(mcp, opts)
    register_projects(mcp, opts)
    register_review(mcp, opts)
    register_settings(mcp, opts)
    register_diagnostics(mcp, opts)
    register_plugins(mcp, opts)
