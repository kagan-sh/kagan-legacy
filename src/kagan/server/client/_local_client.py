"""LocalClient implementation using embedded server + Unix socket.

Clean architecture: TUI starts embedded server, connects via Unix socket.
Same interface as RemoteClient (HTTP). Server is source of truth.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx
from loguru import logger

from kagan.server.client.base import KaganClient
from kagan.server.client.events import (
    AnyEvent,
    SessionEndedEvent,
    SessionOutputEvent,
    SettingsChangedEvent,
    TaskCreatedEvent,
    TaskDeletedEvent,
    TaskUpdatedEvent,
)
from kagan.server.mcp.server import ServerOptions
from kagan.server.server import ApiServerOptions, create_api_server

if TYPE_CHECKING:
    from collections.abc import AsyncIterator


class EmbeddedServer:
    """Runs kagan server in-process on a Unix socket.

    The server runs in a background thread and handles HTTP requests
    over a Unix domain socket. This provides process-level isolation
    while avoiding TCP overhead and port conflicts.
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self.db_path = db_path
        self.socket_path = self._make_socket_path()
        self._server_thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._started = False
        self._mcp: Any = None

    def _make_socket_path(self) -> str:
        """Generate a unique socket path in temp directory."""
        pid = os.getpid()
        ts = int(time.time() * 1000)
        return str(Path(tempfile.gettempdir()) / f"kagan-{pid}-{ts}.sock")

    def _run_server(self) -> None:
        """Server thread entry point."""
        try:
            # Create uvicorn config for Unix socket
            import uvicorn

            mcp_opts = ServerOptions(
                db_path=str(self.db_path) if self.db_path else None,
            )
            opts = ApiServerOptions(
                mcp_opts=mcp_opts,
                host="127.0.0.1",  # Not used for Unix socket
                port=0,  # Not used for Unix socket
                web_ui=False,  # Local client doesn't need web UI
                dev_mode=False,
            )

            self._mcp = create_api_server(opts)

            # Initialize KaganCore for REST routes
            from kagan.core import KaganCore, install_asyncio_subprocess_exception_filter
            from kagan.server._presence import PresenceTracker
            from kagan.server.mcp.server import ServerContext, _set_server_context

            install_asyncio_subprocess_exception_filter()
            client = KaganCore(db_path=opts.mcp_opts.db_path)

            # Set active project
            projects = asyncio.run(client.projects.list())
            if projects:
                asyncio.run(client.projects.set_active(projects[0].id))

            ctx = ServerContext(client=client, opts=opts.mcp_opts, presence=PresenceTracker())
            _set_server_context(self._mcp, ctx)

            starlette_app = self._mcp.streamable_http_app()
            from kagan.server._middleware import install_security_middleware

            install_security_middleware(starlette_app)

            config = uvicorn.Config(
                starlette_app,
                uds=self.socket_path,
                log_level="error",
                timeout_graceful_shutdown=5,
            )
            server = uvicorn.Server(config)

            # Run server until shutdown requested
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

            async def serve_with_shutdown() -> None:
                serve_task = loop.create_task(server.serve())
                shutdown_task = loop.create_task(self._wait_shutdown())
                _done, pending = await asyncio.wait(
                    [serve_task, shutdown_task],
                    return_when=asyncio.FIRST_COMPLETED,
                )
                for task in pending:
                    task.cancel()
                server.should_exit = True
                await serve_task

            loop.run_until_complete(serve_with_shutdown())

            # Cleanup
            _set_server_context(self._mcp, None)
            client.close()

        except Exception as e:
            logger.error("EmbeddedServer error: {}", e)
        finally:
            # Cleanup socket file
            with contextlib.suppress(FileNotFoundError):
                os.unlink(self.socket_path)

    async def _wait_shutdown(self) -> None:
        """Wait for shutdown signal in async context."""
        while not self._shutdown_event.is_set():
            await asyncio.sleep(0.1)

    def start(self) -> None:
        """Start the embedded server in a background thread."""
        if self._started:
            return

        self._server_thread = threading.Thread(target=self._run_server, daemon=True)
        self._server_thread.start()
        self._started = True

        # Wait for socket to be created
        for _ in range(100):  # Max 10 seconds
            if os.path.exists(self.socket_path):
                break
            time.sleep(0.1)
        else:
            raise RuntimeError("Server failed to start - socket not created")

        logger.debug("EmbeddedServer started on {}", self.socket_path)

    def stop(self) -> None:
        """Stop the embedded server."""
        if not self._started:
            return

        self._shutdown_event.set()

        if self._server_thread and self._server_thread.is_alive():
            self._server_thread.join(timeout=10)

        # Cleanup socket file
        with contextlib.suppress(FileNotFoundError):
            os.unlink(self.socket_path)

        self._started = False
        logger.debug("EmbeddedServer stopped")


class UnixSocketClient:
    """HTTP client that connects via Unix socket.

    Uses httpx with a custom transport to communicate over
    Unix domain sockets instead of TCP.
    """

    def __init__(self, socket_path: str) -> None:
        self.socket_path = socket_path
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create the HTTP client."""
        if self._client is None:
            # Create transport that uses Unix socket
            transport = httpx.AsyncHTTPTransport(uds=self.socket_path)
            self._client = httpx.AsyncClient(transport=transport, base_url="http://localhost")
        return self._client

    async def request(
        self,
        method: str,
        path: str,
        json_data: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make an HTTP request and return JSON response."""
        client = await self._get_client()
        response = await client.request(method, path, json=json_data)
        response.raise_for_status()
        return response.json()

    async def stream_sse(self, path: str) -> AsyncIterator[dict[str, Any]]:
        """Stream SSE events from the server."""
        client = await self._get_client()
        async with client.stream("GET", path) as response:
            response.raise_for_status()
            async for line in response.aiter_lines():
                line = line.strip()
                if line.startswith("data: "):
                    data = line[6:]
                    try:
                        yield json.loads(data)
                    except json.JSONDecodeError:
                        continue
                elif line.startswith(": keepalive"):
                    continue

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


class LocalClient(KaganClient):
    """Client that connects to embedded server.

    Combines EmbeddedServer and UnixSocketClient to provide
    a clean local client interface. Same interface as RemoteClient.

    Usage:
        async with LocalClient() as client:
            task = await client.create_task("Fix bug")
            await client.run_task(task.id)
            async for event in client.subscribe_events():
                print(event)
    """

    def __init__(self, db_path: Path | str | None = None) -> None:
        self._server = EmbeddedServer(db_path)
        self._client: UnixSocketClient | None = None
        self._seq = 0
        self._closed = False

    def _next_seq(self) -> int:
        """Get next sequence number."""
        self._seq += 1
        return self._seq

    async def _ensure_client(self) -> UnixSocketClient:
        """Ensure server is started and client is connected."""
        if self._closed:
            raise RuntimeError("Client is closed")

        if self._client is None:
            # Start server in thread (sync operation)
            await asyncio.to_thread(self._server.start)
            self._client = UnixSocketClient(self._server.socket_path)

        return self._client

    async def create_task(
        self,
        title: str,
        *,
        description: str = "",
        status: str = "BACKLOG",
        priority: str = "MEDIUM",
        acceptance_criteria: list[str] | None = None,
    ) -> TaskCreatedEvent:
        """Create a new task in the active project."""
        client = await self._ensure_client()

        result = await client.request(
            "POST",
            "/api/tasks",
            json_data={
                "title": title,
                "description": description,
                "priority": priority,
                "acceptance_criteria": acceptance_criteria or [],
            },
        )

        task = result.get("data", {})
        return TaskCreatedEvent(
            seq=self._next_seq(),
            task_id=task.get("id", ""),
            title=task.get("title", ""),
            status=task.get("status", "BACKLOG"),
            project_id=task.get("project_id", ""),
        )

    async def run_task(
        self,
        task_id: str,
        *,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> None:
        """Start an agent session on a task."""
        client = await self._ensure_client()

        await client.request(
            "POST",
            f"/api/tasks/{task_id}/run",
            json_data={
                "agent_backend": agent_backend,
                "launcher": launcher,
            },
        )

    async def subscribe_events(self) -> AsyncIterator[AnyEvent]:
        """Subscribe to all real-time events via SSE."""
        client = await self._ensure_client()

        async for data in client.stream_sse("/api/events/stream"):
            event_type = data.get("type")

            if event_type == "TASK_CREATED":
                yield TaskCreatedEvent(
                    seq=self._next_seq(),
                    task_id=data.get("task_id", ""),
                    title="",  # SSE doesn't include title
                    status="BACKLOG",
                    project_id="",
                )
            elif event_type == "TASK_UPDATED":
                yield TaskUpdatedEvent(
                    seq=self._next_seq(),
                    task_id=data.get("task_id", ""),
                    changes={},
                )
            elif event_type == "TASK_DELETED":
                yield TaskDeletedEvent(
                    seq=self._next_seq(),
                    task_id=data.get("task_id", ""),
                )
            elif event_type == "SESSION_EVENT":
                event = data.get("event", {})
                event_type_inner = event.get("type", "")

                if event_type_inner in ("AGENT_COMPLETED", "AGENT_FAILED"):
                    yield SessionEndedEvent(
                        seq=self._next_seq(),
                        task_id=data.get("task_id", ""),
                        session_id=event.get("session_id", ""),
                        status="completed" if event_type_inner == "AGENT_COMPLETED" else "failed",
                    )
                else:
                    yield SessionOutputEvent(
                        seq=self._next_seq(),
                        task_id=data.get("task_id", ""),
                        session_id=event.get("session_id"),
                        chunk=event.get("payload", {}).get("chunk", ""),
                    )
            elif event_type == "SETTINGS_CHANGED":
                yield SettingsChangedEvent(
                    seq=self._next_seq(),
                    keys=data.get("keys", []),
                )

    async def close(self) -> None:
        """Close the client and cleanup resources."""
        if self._closed:
            return
        self._closed = True

        if self._client:
            await self._client.close()
            self._client = None

        # Stop server in thread (sync operation)
        await asyncio.to_thread(self._server.stop)
        logger.debug("LocalClient closed")


__all__ = ["EmbeddedServer", "LocalClient", "UnixSocketClient"]
