"""kagan.server.server — HTTP/StreamableHTTP API server factory."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import signal
import threading
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import uvicorn
from loguru import logger
from starlette.responses import JSONResponse
from uvicorn.server import HANDLED_SIGNALS

from kagan.server._analytics_routes import register_analytics_routes
from kagan.server._chat_routes import register_chat_routes
from kagan.server._integration_routes import register_integration_routes
from kagan.server._project_routes import register_project_routes
from kagan.server._session_routes import register_session_routes
from kagan.server._system_routes import register_system_routes
from kagan.server._task_routes import register_task_routes
from kagan.server._web_ui import register_web_ui
from kagan.server.mcp.server import ServerContext, ServerOptions, _set_server_context, create_server

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request


@dataclass(frozen=True, slots=True)
class ApiServerOptions:
    """Configuration for the HTTP API server.

    Wraps the existing MCP ``ServerOptions`` and adds network/auth settings
    needed for the StreamableHTTP transport.
    """

    mcp_opts: ServerOptions
    host: str = "127.0.0.1"
    port: int = 8765
    enable_tls: bool = False  # generate self-signed cert and serve HTTPS
    web_ui: bool = False  # mount bundled local web UI at /
    dev_mode: bool = False
    fake_agent: bool = False  # register fake-agent backend and control routes


class _KaganUvicornServer(uvicorn.Server):
    """Uvicorn server variant that exits cleanly after handled signals.

    Uvicorn's default signal context restores the previous handlers and then
    re-raises captured signals. That is correct for framework-level defaults,
    but for the `kg web` CLI it turns a successful Ctrl-C shutdown into an
    asyncio.run KeyboardInterrupt traceback. We keep uvicorn's `handle_exit`
    behavior and skip only the signal replay.
    """

    def __init__(self, config: uvicorn.Config, *, shutdown_event: Any | None = None) -> None:
        super().__init__(config)
        self._kagan_shutdown_event = shutdown_event

    def handle_exit(self, sig: int, frame: Any | None) -> None:
        if self._kagan_shutdown_event is not None:
            self._kagan_shutdown_event.set()
        super().handle_exit(sig, frame)

    @contextlib.contextmanager
    def capture_signals(self):
        if threading.current_thread() is not threading.main_thread():
            yield
            return

        original_handlers = {sig: signal.signal(sig, self.handle_exit) for sig in HANDLED_SIGNALS}
        try:
            yield
        finally:
            for sig, handler in original_handlers.items():
                signal.signal(sig, handler)


def create_api_server(opts: ApiServerOptions) -> FastMCP:
    """Create a FastMCP server configured for HTTP transport.

    Delegates to :func:`kagan.server.mcp.server.create_server` for core MCP setup,
    then layers on routes, auth, and websocket stubs.

    Args:
        opts: API server configuration options.

    Returns:
        A fully configured :class:`FastMCP` instance.
    """
    mcp = create_server(opts.mcp_opts)

    mcp.settings.host = opts.host
    mcp.settings.port = opts.port

    @mcp.custom_route("/health", methods=["GET"])
    async def health(_request: Request) -> JSONResponse:
        from importlib.metadata import version

        return JSONResponse({"status": "ok", "version": version("kagan")})

    @mcp.custom_route("/api/shutdown", methods=["POST"])
    async def shutdown(request: Request) -> JSONResponse:
        client_host = request.client.host if request.client else None
        if client_host not in ("127.0.0.1", "::1"):
            return JSONResponse({"error": "forbidden"}, status_code=403)
        logger.info("Shutdown requested via /api/shutdown")

        import os
        import signal

        async def _deferred_kill() -> None:
            import asyncio

            await asyncio.sleep(0.1)
            os.kill(os.getpid(), signal.SIGTERM)

        import asyncio

        asyncio.get_event_loop().create_task(_deferred_kill())
        return JSONResponse({"status": "shutting_down"})

    register_task_routes(mcp)
    register_project_routes(mcp)
    register_system_routes(mcp)
    register_analytics_routes(mcp)
    register_chat_routes(mcp)
    register_integration_routes(mcp)
    register_session_routes(mcp)

    if opts.fake_agent:
        from kagan.server._fake_agent_routes import register_fake_agent_routes

        register_fake_agent_routes(mcp)

    # Web UI must be last — it mounts a catch-all SPA fallback at /
    if opts.web_ui:
        register_web_ui(mcp)
    return mcp


async def serve_http(
    opts: ApiServerOptions,
    host: str | None = None,
    port: int | None = None,
) -> None:
    """Create and run the API server over StreamableHTTP transport.

    Initialises a :class:`~kagan.core.KaganCore` instance for REST routes
    (the MCP lifespan only runs when an MCP client connects, not for plain
    HTTP requests) and starts the Uvicorn server.

    Args:
        opts: API server configuration options.
        host: Override host from *opts* (defaults to ``opts.host``).
        port: Override port from *opts* (defaults to ``opts.port``).
    """
    effective_host = host or opts.host
    effective_port = port or opts.port

    logging.getLogger("uvicorn").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)

    # Override opts so create_api_server sees the effective host/port
    opts = ApiServerOptions(
        mcp_opts=opts.mcp_opts,
        host=effective_host,
        port=effective_port,
        enable_tls=opts.enable_tls,
        web_ui=opts.web_ui,
        dev_mode=opts.dev_mode,
        fake_agent=opts.fake_agent,
    )
    mcp = create_api_server(opts)

    # Initialise KaganCore for REST API routes.
    from kagan.core import (
        KaganCore,
        install_asyncio_subprocess_exception_filter,
        reap_orphan_sessions,
    )

    install_asyncio_subprocess_exception_filter()
    client = KaganCore(db_path=opts.mcp_opts.db_path)

    # Reap any sessions that were RUNNING when the previous server process died.
    reaped = await reap_orphan_sessions(client.engine)
    if reaped:
        logger.info("Server startup: reaped {} orphan session(s)", reaped)

    project_id = opts.mcp_opts.project_id
    if project_id:
        await client.projects.set_active(project_id)
    else:
        projects = await client.projects.list()
        if projects:
            await client.projects.set_active(projects[0].id)

    from kagan.server._presence import PresenceTracker

    shutdown_event = asyncio.Event()
    ctx = ServerContext(
        client=client,
        opts=opts.mcp_opts,
        presence=PresenceTracker(),
        shutdown_event=shutdown_event,
    )
    _set_server_context(mcp, ctx)
    # TLS: pass cert/key paths to uvicorn if enabled.
    ssl_certfile: str | None = None
    ssl_keyfile: str | None = None
    if opts.enable_tls:
        from kagan.server.crypto import ensure_tls_cert

        cert_path, key_path = ensure_tls_cert(effective_host)
        ssl_certfile = str(cert_path)
        ssl_keyfile = str(key_path)
        logger.info("TLS enabled \u2014 cert: {}, key: {}", cert_path, key_path)

    logger.info(
        "API server starting on {}://{}:{}",
        "https" if opts.enable_tls else "http",
        effective_host,
        effective_port,
    )

    try:
        starlette_app = mcp.streamable_http_app()

        from kagan.server._middleware import install_security_middleware

        install_security_middleware(starlette_app)

        config = uvicorn.Config(
            starlette_app,
            host=mcp.settings.host,
            port=mcp.settings.port,
            log_level="error",
            timeout_graceful_shutdown=5,
            ssl_certfile=ssl_certfile,
            ssl_keyfile=ssl_keyfile,
        )
        server = _KaganUvicornServer(config, shutdown_event=shutdown_event)
        await server.serve()
    except OSError as exc:
        is_addr_in_use = exc.errno in (48, 98) or "address already in use" in str(exc).lower()
        if is_addr_in_use:
            import click

            raise click.ClickException(
                f"Port {effective_port} is already in use.\n"
                f"  -> Stop the existing server or use --port {effective_port + 1}"
            ) from None
        raise
    finally:
        shutdown_event.set()
        _set_server_context(mcp, None)
        await client.aclose()
