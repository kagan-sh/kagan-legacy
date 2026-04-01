from __future__ import annotations

from kagan.server.mcp.server import ServerOptions
from kagan.server.server import ApiServerOptions, create_api_server


def make_api_server():
    return create_api_server(ApiServerOptions(mcp_opts=ServerOptions()))
