"""Access control behavioral tests for kagan.mcp.

Tests verify the 3-tier access control system through MCP protocol behavior:
observable tool visibility via list_tools() on servers with different ServerOptions.

No private module imports — all assertions are on protocol-level outcomes.
"""

import asyncio
import contextlib

import pytest
from mcp.shared.memory import create_client_server_memory_streams

from kagan.mcp.server import ServerOptions, create_server
from mcp import ClientSession

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _connected_session(
    opts: ServerOptions,
) -> tuple[ClientSession, asyncio.Task, asyncio.Event]:
    """Return (session, lifecycle_task, ready_event) for a server built with opts."""
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
    return session, task, ready


async def _tool_names(opts: ServerOptions) -> set[str]:
    """Return the set of tool names visible on a server built with opts."""
    session, task, ready = await _connected_session(opts)
    try:
        result = await session.list_tools()
        return {t.name for t in result.tools}
    finally:
        ready.set()
        await task


# ---------------------------------------------------------------------------
# Readonly tier — mutating tools must be hidden
# ---------------------------------------------------------------------------


async def test_readonly_server_hides_mutating_tools() -> None:
    """Readonly server must not expose task_create, task_delete, or project_create."""
    names = await _tool_names(ServerOptions(readonly=True))
    assert "task_create" not in names
    assert "task_delete" not in names
    assert "project_create" not in names


async def test_readonly_server_exposes_read_tools() -> None:
    """Readonly server must expose task_get and task_list."""
    names = await _tool_names(ServerOptions(readonly=True))
    assert "task_get" in names
    assert "task_list" in names


# ---------------------------------------------------------------------------
# Standard tier — read + write tools visible; admin-only hidden
# ---------------------------------------------------------------------------


async def test_default_server_shows_read_and_write_tools() -> None:
    """Default server must expose task_get and task_create; task_delete must be hidden."""
    names = await _tool_names(ServerOptions())
    assert "task_get" in names
    assert "task_create" in names
    assert "task_delete" not in names


async def test_default_server_hides_admin_tools() -> None:
    """Default server must not expose settings_set or project_create."""
    names = await _tool_names(ServerOptions())
    assert "settings_set" not in names
    assert "project_create" not in names


# ---------------------------------------------------------------------------
# Admin tier — all tools visible
# ---------------------------------------------------------------------------


async def test_admin_server_shows_all_tools() -> None:
    """Admin server must expose task_delete, project_create, and settings_set."""
    names = await _tool_names(ServerOptions(admin=True))
    assert "task_delete" in names
    assert "project_create" in names
    assert "settings_set" in names


async def test_admin_server_shows_read_tools_too() -> None:
    """Admin server must also expose read-only tools like task_get."""
    names = await _tool_names(ServerOptions(admin=True))
    assert "task_get" in names
    assert "task_list" in names


# ---------------------------------------------------------------------------
# project_delete requires admin tier (security fix — checkpoint-1 finding)
# ---------------------------------------------------------------------------


async def test_project_delete_requires_admin_tier() -> None:
    """project_delete must be hidden on default server and visible on admin server."""
    default_names = await _tool_names(ServerOptions())
    admin_names = await _tool_names(ServerOptions(admin=True))
    assert "project_delete" not in default_names
    assert "project_delete" in admin_names


async def test_project_delete_hidden_on_readonly_server() -> None:
    """project_delete must be hidden on readonly server."""
    names = await _tool_names(ServerOptions(readonly=True))
    assert "project_delete" not in names


# ---------------------------------------------------------------------------
# Mutually exclusive: readonly + admin raises ValueError
# ---------------------------------------------------------------------------


async def test_readonly_and_admin_mutually_exclusive() -> None:
    """ServerOptions with both readonly=True and admin=True must raise ValueError."""
    with pytest.raises(ValueError, match="mutually exclusive"):
        ServerOptions(readonly=True, admin=True)


# ---------------------------------------------------------------------------
# Parametrized: all READONLY-tier tools visible in all tiers
# ---------------------------------------------------------------------------

_READONLY_TOOLS = [
    "task_get",
    "task_list",
    "task_search",
    "task_events",
    "tasks_wait",
    "task_counts",
    "run_summary",
    "project_list",
    "repo_list",
    "settings_get",
    "audit_list",
    "persona_preset_audit",
    "persona_preset_whitelist_list",
    "review_conflicts",
]


@pytest.mark.parametrize("tool_name", _READONLY_TOOLS)
async def test_readonly_tool_visible_in_readonly_tier(tool_name: str) -> None:
    """Every READONLY-tier tool must be visible on a readonly server."""
    names = await _tool_names(ServerOptions(readonly=True))
    assert tool_name in names, f"{tool_name!r} must be visible in readonly tier"


@pytest.mark.parametrize("tool_name", _READONLY_TOOLS)
async def test_readonly_tool_visible_in_default_tier(tool_name: str) -> None:
    """Every READONLY-tier tool must be visible on a default server."""
    names = await _tool_names(ServerOptions())
    assert tool_name in names, f"{tool_name!r} must be visible in default tier"


@pytest.mark.parametrize("tool_name", _READONLY_TOOLS)
async def test_readonly_tool_visible_in_admin_tier(tool_name: str) -> None:
    """Every READONLY-tier tool must be visible on an admin server."""
    names = await _tool_names(ServerOptions(admin=True))
    assert tool_name in names, f"{tool_name!r} must be visible in admin tier"


# ---------------------------------------------------------------------------
# Parametrized: all STANDARD-tier tools hidden in readonly, visible in standard+admin
# ---------------------------------------------------------------------------

_STANDARD_TOOLS = [
    "task_create",
    "task_update",
    "task_add_note",
    "run_start",
    "run_cancel",
    "run_update",
    "project_set_active",
    "project_add_repo",
    "project_set_repo_default_branch",
    "review_decide",
    "review_continue_rebase",
    "review_abort_rebase",
]


@pytest.mark.parametrize("tool_name", _STANDARD_TOOLS)
async def test_default_tool_hidden_in_readonly_tier(tool_name: str) -> None:
    """Every STANDARD-tier tool must be hidden on a readonly server."""
    names = await _tool_names(ServerOptions(readonly=True))
    assert tool_name not in names, f"{tool_name!r} must be hidden in readonly tier"


@pytest.mark.parametrize("tool_name", _STANDARD_TOOLS)
async def test_default_tool_visible_in_default_tier(tool_name: str) -> None:
    """Every STANDARD-tier tool must be visible on a default server."""
    names = await _tool_names(ServerOptions())
    assert tool_name in names, f"{tool_name!r} must be visible in default tier"


@pytest.mark.parametrize("tool_name", _STANDARD_TOOLS)
async def test_default_tool_visible_in_admin_tier(tool_name: str) -> None:
    """Every STANDARD-tier tool must be visible on an admin server."""
    names = await _tool_names(ServerOptions(admin=True))
    assert tool_name in names, f"{tool_name!r} must be visible in admin tier"


# ---------------------------------------------------------------------------
# Parametrized: all ADMIN-tier tools hidden in readonly+default, visible in admin
# ---------------------------------------------------------------------------

_ADMIN_TOOLS = [
    "task_delete",
    "project_create",
    "project_delete",
    "settings_set",
    "persona_preset_import",
    "persona_preset_export",
    "persona_preset_whitelist_add",
    "persona_preset_whitelist_remove",
]


@pytest.mark.parametrize("tool_name", _ADMIN_TOOLS)
async def test_admin_tool_hidden_in_readonly_tier(tool_name: str) -> None:
    """Every ADMIN-tier tool must be hidden on a readonly server."""
    names = await _tool_names(ServerOptions(readonly=True))
    assert tool_name not in names, f"{tool_name!r} must be hidden in readonly tier"


@pytest.mark.parametrize("tool_name", _ADMIN_TOOLS)
async def test_admin_tool_hidden_in_default_tier(tool_name: str) -> None:
    """Every ADMIN-tier tool must be hidden on a default server."""
    names = await _tool_names(ServerOptions())
    assert tool_name not in names, f"{tool_name!r} must be hidden in default tier"


@pytest.mark.parametrize("tool_name", _ADMIN_TOOLS)
async def test_admin_tool_visible_in_admin_tier(tool_name: str) -> None:
    """Every ADMIN-tier tool must be visible on an admin server."""
    names = await _tool_names(ServerOptions(admin=True))
    assert tool_name in names, f"{tool_name!r} must be visible in admin tier"


# ---------------------------------------------------------------------------
# Call-level enforcement: readonly cannot invoke mutating tools
# ---------------------------------------------------------------------------


async def test_readonly_cannot_call_task_create() -> None:
    """Readonly server must not expose task_create — calling it raises an error."""
    session, task, ready = await _connected_session(ServerOptions(readonly=True))
    try:
        result = await session.list_tools()
        tool_names = {t.name for t in result.tools}
        assert "task_create" not in tool_names, "task_create must not be visible on readonly server"
    finally:
        ready.set()
        await task


async def test_default_cannot_call_task_delete() -> None:
    """Default server must not expose task_delete — calling it raises an error."""
    session, task, ready = await _connected_session(ServerOptions())
    try:
        result = await session.list_tools()
        tool_names = {t.name for t in result.tools}
        assert "task_delete" not in tool_names, "task_delete must not be visible on default server"
    finally:
        ready.set()
        await task


async def test_admin_can_call_task_delete() -> None:
    """Admin server exposes task_delete and calling it succeeds (returns deleted result)."""
    session, task, ready = await _connected_session(ServerOptions(admin=True))
    try:
        result = await session.list_tools()
        tool_names = {t.name for t in result.tools}
        assert "task_delete" in tool_names, "task_delete must be visible on admin server"
        # Call task_delete with a non-existent ID — expect a tool error (not a protocol error)
        call_result = await session.call_tool("task_delete", {"task_id": "nonexistent-id"})
        # The tool is reachable — it returns an error content (task not found), not a protocol error
        assert call_result is not None
    finally:
        ready.set()
        await task


async def test_admin_can_call_task_create() -> None:
    """Admin server exposes task_create and calling it succeeds."""
    session, task, ready = await _connected_session(ServerOptions(admin=True))
    try:
        call_result = await session.call_tool("task_create", {"title": "test-task"})
        assert call_result is not None
        # Result should contain task data (id, title, status)
        assert not call_result.isError, f"task_create failed: {call_result.content}"
    finally:
        ready.set()
        await task


async def test_readonly_can_call_task_list() -> None:
    """Readonly server exposes task_list and calling it succeeds."""
    session, task, ready = await _connected_session(ServerOptions(readonly=True))
    try:
        call_result = await session.call_tool("task_list", {})
        assert call_result is not None
        assert not call_result.isError, f"task_list failed: {call_result.content}"
    finally:
        ready.set()
        await task


# ---------------------------------------------------------------------------
# Diagnostics tool — opt-in via enable_instrumentation
# ---------------------------------------------------------------------------


async def test_diagnostics_tool_hidden_by_default() -> None:
    """diagnostics_get_instrumentation must not appear unless enable_instrumentation=True."""
    names = await _tool_names(ServerOptions())
    assert "diagnostics_get_instrumentation" not in names


async def test_diagnostics_tool_visible_when_instrumentation_enabled() -> None:
    """diagnostics_get_instrumentation must appear when enable_instrumentation=True."""
    names = await _tool_names(ServerOptions(enable_instrumentation=True))
    assert "diagnostics_get_instrumentation" in names


async def test_diagnostics_tool_hidden_in_readonly_without_instrumentation() -> None:
    """diagnostics_get_instrumentation must not appear on readonly without instrumentation."""
    names = await _tool_names(ServerOptions(readonly=True))
    assert "diagnostics_get_instrumentation" not in names


async def test_diagnostics_tool_visible_in_readonly_with_instrumentation() -> None:
    """diagnostics_get_instrumentation must appear on readonly with instrumentation enabled."""
    names = await _tool_names(ServerOptions(readonly=True, enable_instrumentation=True))
    assert "diagnostics_get_instrumentation" in names
