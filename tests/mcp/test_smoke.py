"""Smoke tests for kagan.server.mcp server."""

import asyncio
import contextlib

import pytest
from mcp.shared.memory import create_client_server_memory_streams

from kagan.server.mcp.server import ServerOptions, create_server
from mcp import ClientSession

pytestmark = [pytest.mark.mcp, pytest.mark.smoke]


async def test_server_responds_to_list_tools(mcp_board: ClientSession) -> None:
    result = await mcp_board.list_tools()
    assert isinstance(result.tools, list)
    assert len(result.tools) > 0
    tool_names = [t.name for t in result.tools]
    assert "project_list" in tool_names


async def test_create_server_with_lifespan_runs() -> None:
    opts = ServerOptions()
    mcp = create_server(opts)

    session_q: asyncio.Queue[ClientSession] = asyncio.Queue()
    teardown_event = asyncio.Event()

    async def _lifecycle() -> None:
        async with create_client_server_memory_streams() as (client_streams, server_streams):
            client_read, client_write = client_streams
            server_read, server_write = server_streams

            server_task = asyncio.create_task(
                mcp._mcp_server.run(
                    server_read,
                    server_write,
                    mcp._mcp_server.create_initialization_options(),
                )
            )
            try:
                async with ClientSession(client_read, client_write) as session:
                    await session.initialize()
                    await session_q.put(session)
                    await teardown_event.wait()
            finally:
                server_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await server_task

    lifecycle_task = asyncio.create_task(_lifecycle())
    session = await session_q.get()

    result = await session.list_tools()
    assert isinstance(result.tools, list)
    assert len(result.tools) > 0

    teardown_event.set()
    await lifecycle_task


async def test_core_lifespan_with_session_id_starts_and_handles_tool_call(
    mcp_board_core_with_session: ClientSession,
) -> None:
    tools = await mcp_board_core_with_session.list_tools()
    assert isinstance(tools.tools, list)
    assert len(tools.tools) > 0

    result = await mcp_board_core_with_session.call_tool("project_list", {})
    assert not result.isError
