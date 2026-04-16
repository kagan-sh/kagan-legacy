"""Behavioral tests for diagnostics_get_instrumentation MCP tool.

Tests exercise tool behavior through MCP protocol (ClientSession.call_tool),
not by importing production internals. All assertions are on observable
protocol-level outcomes: tool visibility, response shape, and data content.

The diagnostics_instrumentation tool is opt-in: registered only when
ServerOptions.enable_instrumentation is True.
"""

import asyncio
import contextlib

import pytest
from mcp.shared.memory import create_client_server_memory_streams

from kagan.server.mcp.server import ServerOptions, create_server
from mcp import ClientSession
from tests.helpers.mcp_helpers import extract_text as _text

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


async def _tool_names_for(opts: ServerOptions) -> set[str]:
    """Return the set of tool names visible on a server built with opts."""
    mcp = create_server(opts)
    session_q: asyncio.Queue[ClientSession] = asyncio.Queue()
    ready = asyncio.Event()

    async def _run() -> None:
        async with create_client_server_memory_streams() as (cs, ss):
            client_read, client_write = cs
            server_read, server_write = ss
            srv = asyncio.create_task(
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
                    await ready.wait()
            finally:
                srv.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await srv

    task = asyncio.create_task(_run())
    session = await session_q.get()
    try:
        result = await session.list_tools()
        return {t.name for t in result.tools}
    finally:
        ready.set()
        await task


async def _instrumentation_session() -> tuple[ClientSession, asyncio.Task, asyncio.Event]:
    """Create an instrumentation-enabled MCP session."""
    mcp = create_server(ServerOptions(enable_instrumentation=True))
    session_q: asyncio.Queue[ClientSession] = asyncio.Queue()
    ready = asyncio.Event()

    async def _run() -> None:
        async with create_client_server_memory_streams() as (cs, ss):
            client_read, client_write = cs
            server_read, server_write = ss
            srv = asyncio.create_task(
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
                    await ready.wait()
            finally:
                srv.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await srv

    task = asyncio.create_task(_run())
    session = await session_q.get()
    return session, task, ready


# ---------------------------------------------------------------------------
# Tool visibility — opt-in gate
# ---------------------------------------------------------------------------


async def test_diagnostics_absent_when_instrumentation_disabled(mcp_board: ClientSession) -> None:
    """diagnostics_get_instrumentation must NOT appear when enable_instrumentation=False."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "diagnostics_get_instrumentation" not in names


async def test_diagnostics_absent_on_default_server() -> None:
    """Default server (no instrumentation flag) must not expose diagnostics_instrumentation."""
    names = await _tool_names_for(ServerOptions())
    assert "diagnostics_get_instrumentation" not in names


async def test_diagnostics_absent_on_readonly_server() -> None:
    """Readonly server without instrumentation must not expose diagnostics_instrumentation."""
    names = await _tool_names_for(ServerOptions(readonly=True))
    assert "diagnostics_get_instrumentation" not in names


async def test_diagnostics_absent_on_admin_server() -> None:
    """Admin server without instrumentation must not expose diagnostics_instrumentation."""
    names = await _tool_names_for(ServerOptions(admin=True))
    assert "diagnostics_get_instrumentation" not in names


async def test_diagnostics_present_when_instrumentation_enabled() -> None:
    """diagnostics_get_instrumentation must appear when enable_instrumentation=True."""
    names = await _tool_names_for(ServerOptions(enable_instrumentation=True))
    assert "diagnostics_get_instrumentation" in names


async def test_diagnostics_present_on_admin_with_instrumentation() -> None:
    """Admin server with instrumentation must expose diagnostics_instrumentation."""
    names = await _tool_names_for(ServerOptions(admin=True, enable_instrumentation=True))
    assert "diagnostics_get_instrumentation" in names


async def test_diagnostics_present_on_readonly_with_instrumentation() -> None:
    """Readonly server with instrumentation must expose diagnostics_instrumentation."""
    names = await _tool_names_for(ServerOptions(readonly=True, enable_instrumentation=True))
    assert "diagnostics_get_instrumentation" in names


# ---------------------------------------------------------------------------
# diagnostics_instrumentation — response shape
# ---------------------------------------------------------------------------


async def test_diagnostics_returns_active_sessions_key() -> None:
    """diagnostics_get_instrumentation must return a dict with 'active_sessions' key."""
    session, task, ready = await _instrumentation_session()
    try:
        result = await session.call_tool("diagnostics_get_instrumentation", {})
        assert not result.isError
        payload = _text(result)
        assert "active_sessions" in payload
    finally:
        ready.set()
        await task


async def test_diagnostics_returns_db_stats_key() -> None:
    """diagnostics_get_instrumentation must return a dict with 'db_stats' key."""
    session, task, ready = await _instrumentation_session()
    try:
        result = await session.call_tool("diagnostics_get_instrumentation", {})
        assert not result.isError
        payload = _text(result)
        assert "db_stats" in payload
    finally:
        ready.set()
        await task


async def test_diagnostics_returns_agent_processes_key() -> None:
    """diagnostics_get_instrumentation must return a dict with 'agent_processes' key."""
    session, task, ready = await _instrumentation_session()
    try:
        result = await session.call_tool("diagnostics_get_instrumentation", {})
        assert not result.isError
        payload = _text(result)
        assert "agent_processes" in payload
    finally:
        ready.set()
        await task


async def test_diagnostics_active_sessions_is_list() -> None:
    """diagnostics_instrumentation 'active_sessions' value must be a list."""
    session, task, ready = await _instrumentation_session()
    try:
        result = await session.call_tool("diagnostics_get_instrumentation", {})
        assert not result.isError
        payload = _text(result)
        assert isinstance(payload["active_sessions"], list)
    finally:
        ready.set()
        await task


async def test_diagnostics_agent_processes_is_list() -> None:
    """diagnostics_instrumentation 'agent_processes' value must be a list."""
    session, task, ready = await _instrumentation_session()
    try:
        result = await session.call_tool("diagnostics_get_instrumentation", {})
        assert not result.isError
        payload = _text(result)
        assert isinstance(payload["agent_processes"], list)
    finally:
        ready.set()
        await task


async def test_diagnostics_db_stats_is_dict() -> None:
    """diagnostics_instrumentation 'db_stats' value must be a dict."""
    session, task, ready = await _instrumentation_session()
    try:
        result = await session.call_tool("diagnostics_get_instrumentation", {})
        assert not result.isError
        payload = _text(result)
        assert isinstance(payload["db_stats"], dict)
    finally:
        ready.set()
        await task


async def test_diagnostics_with_core_instrumentation_uses_core_path(
    mcp_board_core_instrumented: ClientSession,
) -> None:
    result = await mcp_board_core_instrumented.call_tool("diagnostics_get_instrumentation", {})
    assert not result.isError
    payload = _text(result)
    assert "active_sessions" in payload
    assert "db_stats" in payload
    assert "agent_processes" in payload
