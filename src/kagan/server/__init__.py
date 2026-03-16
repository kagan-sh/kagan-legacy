"""kagan.server — HTTP API server for the bundled dashboard and API clients.

Re-exports the public API surface:

- :class:`ApiServerOptions` — frozen dataclass for server configuration
- :func:`create_api_server` — factory that builds a configured FastMCP instance
- :func:`serve_http` — async entry point that runs StreamableHTTP transport
"""

from kagan.server.server import ApiServerOptions, create_api_server, serve_http

__all__ = ["ApiServerOptions", "create_api_server", "serve_http"]
