"""kagan.server.mcp.toolsets.settings — Settings MCP tools.

2 tools: settings_get, settings_set.
"""

from mcp.server.fastmcp import Context, FastMCP

from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register settings domain tools on mcp, filtered by opts."""
    if is_tool_allowed("settings_get", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def settings_get(ctx: Context) -> dict:
            """Read allowlisted runtime settings."""
            app = get_context(ctx)
            return await app.client.settings.get()

    if is_tool_allowed("settings_set", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def settings_set(key: str, value: str, ctx: Context) -> dict:
            """Update one allowlisted setting value."""
            app = get_context(ctx)
            await app.client.settings.set({key: value})
            return {"key": key, "value": value}
