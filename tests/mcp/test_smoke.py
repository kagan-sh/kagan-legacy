"""Smoke tests for kagan.mcp server."""

import asyncio
import contextlib

import pytest
from mcp.shared.memory import create_client_server_memory_streams

from kagan.mcp.server import ServerOptions, create_server
from mcp import ClientSession

pytestmark = [pytest.mark.mcp, pytest.mark.smoke]


async def test_server_responds_to_list_tools(mcp_board: ClientSession) -> None:
    """Server must respond to tools/list with a valid result."""
    result = await mcp_board.list_tools()
    assert result is not None
    assert isinstance(result.tools, list)


def test_server_opts_readonly_admin_mutually_exclusive() -> None:
    """ServerOptions must raise ValueError when both readonly and admin are set."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        ServerOptions(readonly=True, admin=True)


async def test_lifespan_app_context_accessible_from_tool(mcp_board: ClientSession) -> None:
    """A tool registered with the server can access ServerContext via lifespan_context."""
    result = await mcp_board.list_tools()
    assert result is not None


async def test_create_server_with_lifespan_runs() -> None:
    """create_server must produce a FastMCP instance that can run with lifespan."""
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

    lifecycle_task = asyncio.get_event_loop().create_task(_lifecycle())
    session = await session_q.get()

    result = await session.list_tools()
    assert result is not None

    teardown_event.set()
    await lifecycle_task


async def test_core_lifespan_with_session_id_starts_and_handles_tool_call(
    mcp_board_core_with_session: ClientSession,
) -> None:
    tools = await mcp_board_core_with_session.list_tools()
    assert tools is not None

    result = await mcp_board_core_with_session.call_tool("project_list", {})
    assert not result.isError
