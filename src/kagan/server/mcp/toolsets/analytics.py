"""kagan.server.mcp.toolsets.analytics — Analytics MCP tools."""

from mcp.server.fastmcp import Context, FastMCP

from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register analytics tools on mcp, filtered by opts."""
    if is_tool_allowed("analytics_backend_stats", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def analytics_backend_stats(ctx: Context) -> dict:
            """Per-backend session stats: count, success rate, avg duration, retry rate."""
            app = get_context(ctx)
            project_id = app.client.active_project_id
            if not project_id:
                return {"backends": []}
            stats = await app.client.analytics.backend_stats(project_id)
            return {"backends": stats}

    if is_tool_allowed("analytics_session_timeline", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def analytics_session_timeline(ctx: Context, days: int = 30) -> dict:
            """Daily session counts by status over a given period."""
            app = get_context(ctx)
            project_id = app.client.active_project_id
            if not project_id:
                return {"timeline": []}
            timeline = await app.client.analytics.session_timeline(project_id, days=days)
            return {"timeline": timeline}
