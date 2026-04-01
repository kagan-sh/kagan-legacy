"""kagan.server.mcp — MCP server exposing kagan.core as MCP tools, resources, and prompts.

Entry point: create_server(opts) -> FastMCP
"""

from kagan.server.mcp.server import ServerOptions, create_server

__all__ = ["ServerOptions", "create_server"]
