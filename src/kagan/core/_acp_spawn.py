"""ACP subprocess spawning helpers."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any

from acp.client.connection import ClientSideConnection
from acp.transports import spawn_stdio_transport

from kagan.core._acp_streams import JsonRpcObjectStreamReader
from kagan.core._subprocess import terminate_process

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Callable, Mapping
    from pathlib import Path

    import acp


@asynccontextmanager
async def spawn_filtered_agent_process(
    to_client: Callable[[acp.Agent], acp.Client] | acp.Client,
    command: str,
    *args: str,
    backend_name: str,
    env: Mapping[str, str] | None = None,
    cwd: str | Path | None = None,
    transport_kwargs: Mapping[str, Any] | None = None,
    **connection_kwargs: Any,
) -> AsyncIterator[tuple[ClientSideConnection, Any]]:
    """Spawn an ACP agent with stdout noise filtered before SDK parsing."""
    async with spawn_stdio_transport(
        command,
        *args,
        env=env,
        cwd=cwd,
        **(dict(transport_kwargs) if transport_kwargs else {}),
    ) as (reader, writer, process):
        filtered_reader = JsonRpcObjectStreamReader(reader, backend_name=backend_name)
        conn = ClientSideConnection(to_client, writer, filtered_reader, **connection_kwargs)
        try:
            yield conn, process
        finally:
            try:
                await conn.close()
            finally:
                await terminate_process(process)
