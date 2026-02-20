"""MCP server entry point for Kagan."""

from __future__ import annotations

from kagan.mcp.server import (
    MCPRuntimeConfig,
    MCPStartupError,
    _create_mcp_server,
    _mcp_lifespan,
    main,
)
from kagan.mcp.tools import MCPBridgeError

__all__ = [
    "MCPBridgeError",
    "MCPRuntimeConfig",
    "MCPStartupError",
    "_create_mcp_server",
    "_mcp_lifespan",
    "main",
]
