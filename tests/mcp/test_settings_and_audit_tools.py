"""Behavioral tests for settings and audit domain MCP tools.

Tests exercise tool behavior through MCP protocol (ClientSession.call_tool),
not by importing production internals. All assertions are on observable
protocol-level outcomes: tool visibility, response shape, and error behavior.
"""

import asyncio
import contextlib
import json

import pytest
from mcp.shared.memory import create_client_server_memory_streams
from mcp.types import CallToolResult, TextContent

from kagan.mcp.server import ServerOptions, create_server
from mcp import ClientSession

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


def _text(result: CallToolResult) -> dict:
    """Extract JSON payload from the first TextContent block of a tool result."""
    block = result.content[0]
    assert isinstance(block, TextContent), f"Expected TextContent, got {type(block)}"
    return json.loads(block.text)


async def _admin_session() -> tuple[ClientSession, asyncio.Task, asyncio.Event]:
    """Create an admin-tier MCP session. Returns (session, lifecycle_task, ready_event)."""
    mcp = create_server(ServerOptions(admin=True))
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

    task = asyncio.get_event_loop().create_task(_run())
    session = await session_q.get()
    return session, task, ready


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

    task = asyncio.get_event_loop().create_task(_run())
    session = await session_q.get()
    try:
        result = await session.list_tools()
        return {t.name for t in result.tools}
    finally:
        ready.set()
        await task


# ---------------------------------------------------------------------------
# Tool visibility — default server
# ---------------------------------------------------------------------------


async def test_settings_get_visible_on_default_server(mcp_board: ClientSession) -> None:
    """Default server must expose settings_get."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "settings_get" in names
    assert "persona_preset_audit" in names
    assert "persona_preset_whitelist_list" in names


async def test_audit_list_visible_on_default_server(mcp_board: ClientSession) -> None:
    """Default server must expose audit_list."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "audit_list" in names


async def test_settings_set_hidden_on_default_server(mcp_board: ClientSession) -> None:
    """settings_set must not be visible on default (non-admin) server."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "settings_set" not in names
    assert "persona_preset_import" not in names
    assert "persona_preset_export" not in names


# ---------------------------------------------------------------------------
# Tool visibility — readonly server
# ---------------------------------------------------------------------------


async def test_settings_get_visible_on_readonly_server() -> None:
    """settings_get is read-only and must be visible on readonly server."""
    names = await _tool_names_for(ServerOptions(readonly=True))
    assert "settings_get" in names
    assert "audit_list" in names
    assert "persona_preset_audit" in names
    assert "persona_preset_whitelist_list" in names


async def test_settings_set_hidden_on_readonly_server() -> None:
    """settings_set must be hidden on readonly server."""
    names = await _tool_names_for(ServerOptions(readonly=True))
    assert "settings_set" not in names
    assert "persona_preset_import" not in names
    assert "persona_preset_export" not in names


# ---------------------------------------------------------------------------
# Tool visibility — admin server
# ---------------------------------------------------------------------------


async def test_settings_set_visible_on_admin_server() -> None:
    """settings_set must be visible on admin server."""
    names = await _tool_names_for(ServerOptions(admin=True))
    assert "settings_set" in names
    assert "persona_preset_import" in names
    assert "persona_preset_export" in names
    assert "persona_preset_whitelist_add" in names
    assert "persona_preset_whitelist_remove" in names


async def test_admin_server_shows_all_settings_tools() -> None:
    """Admin server must expose settings_get, settings_set, and audit_list."""
    names = await _tool_names_for(ServerOptions(admin=True))
    assert "settings_get" in names
    assert "settings_set" in names
    assert "audit_list" in names
    assert "persona_preset_audit" in names
    assert "persona_preset_whitelist_list" in names
    assert "persona_preset_import" in names
    assert "persona_preset_export" in names


# ---------------------------------------------------------------------------
# settings_get — returns settings snapshot
# ---------------------------------------------------------------------------


async def test_settings_get_returns_dict(mcp_board: ClientSession) -> None:
    """settings_get must return a dict (possibly empty)."""
    result = await mcp_board.call_tool("settings_get", {})
    assert not result.isError
    payload = _text(result)
    assert isinstance(payload, dict)


# ---------------------------------------------------------------------------
# settings_set — updates a setting (admin only), readable via settings_get
# ---------------------------------------------------------------------------


async def test_settings_set_returns_confirmation_on_admin_server() -> None:
    """settings_set must return a confirmation dict with key."""
    session, task, ready = await _admin_session()
    try:
        result = await session.call_tool(
            "settings_set",
            {"section": "general", "key": "default_agent_backend", "value": "claude-code"},
        )
        assert not result.isError
        payload = _text(result)
        assert "key" in payload
        assert payload["key"] == "default_agent_backend"
    finally:
        ready.set()
        await task


async def test_settings_set_persists_value_readable_via_settings_get() -> None:
    """settings_set must persist a value that is then visible via settings_get."""
    session, task, ready = await _admin_session()
    try:
        set_result = await session.call_tool(
            "settings_set",
            {"section": "general", "key": "my_setting", "value": "my_value"},
        )
        assert not set_result.isError

        get_result = await session.call_tool("settings_get", {})
        assert not get_result.isError
        payload = _text(get_result)
        assert payload.get("my_setting") == "my_value"
    finally:
        ready.set()
        await task


# ---------------------------------------------------------------------------
# audit_list — returns paginated audit entries
# ---------------------------------------------------------------------------


async def test_audit_list_returns_entries_key(mcp_board: ClientSession) -> None:
    """audit_list must return a dict with an 'entries' key."""
    result = await mcp_board.call_tool("audit_list", {})
    assert not result.isError
    payload = _text(result)
    assert "entries" in payload
    assert isinstance(payload["entries"], list)


async def test_audit_list_accepts_limit_param(mcp_board: ClientSession) -> None:
    """audit_list must accept a limit parameter without error."""
    result = await mcp_board.call_tool("audit_list", {"limit": 5})
    assert not result.isError
    payload = _text(result)
    assert "entries" in payload


async def test_audit_list_limit_zero_returns_empty(mcp_board: ClientSession) -> None:
    """audit_list with limit=0 must return an empty entries list."""
    result = await mcp_board.call_tool("audit_list", {"limit": 0})
    assert not result.isError
    payload = _text(result)
    assert payload["entries"] == []


async def test_settings_get_returns_empty_dict_on_fresh_server(mcp_board: ClientSession) -> None:
    """settings_get on a fresh server must return an empty dict."""
    result = await mcp_board.call_tool("settings_get", {})
    assert not result.isError
    payload = _text(result)
    assert payload == {}


# ---------------------------------------------------------------------------
# Core-client path tests — exercise client is not None branches
# ---------------------------------------------------------------------------


async def test_core_settings_get_returns_dict(mcp_board_with_core: ClientSession) -> None:
    """settings_get via core client must return a dict."""
    result = await mcp_board_with_core.call_tool("settings_get", {})
    assert not result.isError
    assert isinstance(_text(result), dict)


async def test_core_audit_list_returns_entries(mcp_board_with_core: ClientSession) -> None:
    """audit_list via core client must return a dict with 'entries' key."""
    result = await mcp_board_with_core.call_tool("audit_list", {})
    assert not result.isError
    payload = _text(result)
    assert "entries" in payload
    assert isinstance(payload["entries"], list)


async def test_core_settings_set_returns_confirmation(
    mcp_board_admin_with_core: ClientSession,
) -> None:
    """settings_set via core admin client must return a confirmation dict."""
    result = await mcp_board_admin_with_core.call_tool(
        "settings_set", {"section": "general", "key": "test_key", "value": "test_value"}
    )
    assert not result.isError
    payload = _text(result)
    assert payload.get("key") == "test_key"
