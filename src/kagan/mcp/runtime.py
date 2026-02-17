"""Backward compatibility module - re-exports from server.py."""

from kagan.core.ipc.client import IPCClient
from kagan.mcp.server import (
    MCPRuntimeConfig,
    MCPStartupError,
    _build_plugin_registry,
    _create_mcp_server,
    _is_allowed,
    _mcp_lifespan,
    _require_bridge,
    _resolve_endpoint,
    _resolve_or_autostart_endpoint,
    _runtime_state_from_raw,
    main,
)

__all__ = [
    "IPCClient",
    "MCPRuntimeConfig",
    "MCPStartupError",
    "_build_plugin_registry",
    "_create_mcp_server",
    "_is_allowed",
    "_mcp_lifespan",
    "_require_bridge",
    "_resolve_endpoint",
    "_resolve_or_autostart_endpoint",
    "_runtime_state_from_raw",
    "main",
]
