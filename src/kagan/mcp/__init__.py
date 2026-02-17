"""MCP server entry point for Kagan."""

from __future__ import annotations

from kagan.mcp.server import (
    MCPRuntimeConfig,
    MCPStartupError,
    _create_mcp_server,
    _mcp_lifespan,
    main,
)
from kagan.mcp.tools import CoreClientBridge, MCPBridgeError

__all__ = [
    "CoreClientBridge",
    "MCPBridgeError",
    "MCPRuntimeConfig",
    "MCPStartupError",
    "_create_mcp_server",
    "_mcp_lifespan",
    "main",
]

import kagan.mcp.server as runtime  # noqa: F401  # backward compatibility
