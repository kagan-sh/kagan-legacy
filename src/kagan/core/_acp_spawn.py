"""ACP subprocess spawning helpers."""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Any, cast

from acp.client.connection import ClientSideConnection
from acp.transports import spawn_stdio_transport

from kagan.core._acp_streams import JsonRpcObjectStreamReader

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Awaitable, Callable, Mapping
    from pathlib import Path

    import acp


async def _terminate_stdio_process(process: Any) -> None:
    if getattr(process, "returncode", None) is not None:
        return
    terminate = getattr(process, "terminate", None)
    if callable(terminate):
        with contextlib.suppress(ProcessLookupError):
            terminate()
    wait = getattr(process, "wait", None)
    if not callable(wait):
        return
    try:
        wait_result = cast("Awaitable[Any]", wait())
        await asyncio.wait_for(wait_result, timeout=5.0)
    except TimeoutError:
        kill = getattr(process, "kill", None)
        if callable(kill):
            with contextlib.suppress(ProcessLookupError):
                kill()
        wait_result = cast("Awaitable[Any]", wait())
        await wait_result


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
            await conn.close()
            await _terminate_stdio_process(process)
