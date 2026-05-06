"""TCP-loopback fixture yielding real ``asyncio`` stream pairs.

Ported from ``references/acp/tests/conftest.py::_Server`` (anthropics/agent-protocol).
Lets tests construct the real ``acp.client.connection.ClientSideConnection`` over
honest ``asyncio.StreamReader``/``asyncio.StreamWriter`` instances without
spawning a subprocess. Catches contracts the SDK enforces at construction time
(``isinstance`` gates) and at runtime (read-method shape) that hand-rolled
fakes routinely under-specify.
"""

from __future__ import annotations

import asyncio
import contextlib


class AcpLoopback:
    """Async context manager that yields two end-to-end connected stream pairs.

    On enter, opens a TCP server bound to ``127.0.0.1:0`` and a client
    connection to it. The "server" side acts as the agent (writes responses,
    reads requests); the "client" side is what Kagan would normally hand to
    ``ClientSideConnection``.
    """

    def __init__(self) -> None:
        self._server: asyncio.AbstractServer | None = None
        self._server_reader: asyncio.StreamReader | None = None
        self._server_writer: asyncio.StreamWriter | None = None
        self._client_reader: asyncio.StreamReader | None = None
        self._client_writer: asyncio.StreamWriter | None = None

    async def __aenter__(self) -> AcpLoopback:
        ready = asyncio.Event()

        async def handle(
            reader: asyncio.StreamReader, writer: asyncio.StreamWriter
        ) -> None:
            self._server_reader = reader
            self._server_writer = writer
            ready.set()

        self._server = await asyncio.start_server(handle, host="127.0.0.1", port=0)
        host, port = self._server.sockets[0].getsockname()[:2]
        self._client_reader, self._client_writer = await asyncio.open_connection(
            host, port
        )
        await asyncio.wait_for(ready.wait(), timeout=2.0)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        del exc_type, exc, tb
        for writer in (self._client_writer, self._server_writer):
            if writer is None:
                continue
            writer.close()
            with contextlib.suppress(Exception):
                await writer.wait_closed()
        if self._server is not None:
            self._server.close()
            await self._server.wait_closed()

    @property
    def client_reader(self) -> asyncio.StreamReader:
        assert self._client_reader is not None
        return self._client_reader

    @property
    def client_writer(self) -> asyncio.StreamWriter:
        assert self._client_writer is not None
        return self._client_writer

    @property
    def server_reader(self) -> asyncio.StreamReader:
        assert self._server_reader is not None
        return self._server_reader

    @property
    def server_writer(self) -> asyncio.StreamWriter:
        assert self._server_writer is not None
        return self._server_writer
