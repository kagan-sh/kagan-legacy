"""Access control behavioral tests for kagan.server.mcp.

Tests verify role-based access control through MCP protocol behavior:
observable tool visibility via list_tools() on servers with different AgentRole values.

No private module imports — all assertions are on protocol-level outcomes.
"""

import asyncio
import contextlib

import pytest
from mcp.shared.memory import create_client_server_memory_streams

from kagan.core.enums import AgentRole
from kagan.server.mcp.server import ServerOptions, create_server
from mcp import ClientSession

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _connected_session(
    opts: ServerOptions,
) -> tuple[ClientSession, asyncio.Task, asyncio.Event]:
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
    return session, task, ready


async def _tool_names(opts: ServerOptions) -> set[str]:
    session, task, ready = await _connected_session(opts)
    try:
        result = await session.list_tools()
        return {t.name for t in result.tools}
    finally:
        ready.set()
        await task


# ---------------------------------------------------------------------------
# Worker role — board awareness + own-task ops only
# ---------------------------------------------------------------------------


async def test_worker_hides_mutating_tools() -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.WORKER))
    assert "task_create" not in names
    assert "task_delete" not in names
    assert "project_setup" not in names
    assert "task_update" not in names
    assert "run_start" not in names
    assert "review_decide" not in names
    assert "review_merge" not in names
    assert "review_rebase" not in names


async def test_worker_exposes_read_tools() -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.WORKER))
    assert "task_get" in names
    assert "task_list" in names
    assert "task_events" in names
    assert "task_wait" in names
    assert "run_get" in names
    assert "run_cancel" in names
    assert "run_detach" in names
    assert "run_summary" in names
    assert "settings_get" in names
    assert "review_conflicts" in names


# ---------------------------------------------------------------------------
# Reviewer role — worker + verdict tools
# ---------------------------------------------------------------------------


async def test_reviewer_includes_worker_tools() -> None:
    worker_names = await _tool_names(ServerOptions(role=AgentRole.WORKER))
    reviewer_names = await _tool_names(ServerOptions(role=AgentRole.REVIEWER))
    assert worker_names < reviewer_names


async def test_reviewer_has_verdict_tools() -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.REVIEWER))
    assert "review_verdict" in names
    assert "review_clear_verdicts" in names


async def test_reviewer_cannot_decide_or_start() -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.REVIEWER))
    assert "review_decide" not in names
    assert "review_merge" not in names
    assert "review_rebase" not in names
    assert "run_start" not in names
    assert "task_create" not in names
    assert "task_delete" not in names


# ---------------------------------------------------------------------------
# Orchestrator role — full access
# ---------------------------------------------------------------------------


async def test_orchestrator_gets_all_tools() -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.ORCHESTRATOR))
    assert "task_get" in names
    assert "task_create" in names
    assert "task_delete" in names
    assert "task_update" in names
    assert "run_start" in names
    assert "run_cancel" in names
    assert "review_decide" in names
    assert "review_merge" in names
    assert "review_rebase" in names
    assert "project_list" in names
    assert "project_setup" in names
    assert "project_update" in names
    assert "settings_set" in names


async def test_orchestrator_includes_reviewer_tools() -> None:
    reviewer_names = await _tool_names(ServerOptions(role=AgentRole.REVIEWER))
    orchestrator_names = await _tool_names(ServerOptions(role=AgentRole.ORCHESTRATOR))
    assert reviewer_names < orchestrator_names


# ---------------------------------------------------------------------------
# Default (no role) — backward compat: orchestrator
# ---------------------------------------------------------------------------


async def test_default_server_is_orchestrator() -> None:
    default_names = await _tool_names(ServerOptions())
    orchestrator_names = await _tool_names(ServerOptions(role=AgentRole.ORCHESTRATOR))
    assert default_names == orchestrator_names


# ---------------------------------------------------------------------------
# Legacy flags: readonly → worker, admin → orchestrator
# ---------------------------------------------------------------------------


async def test_readonly_flag_maps_to_worker() -> None:
    readonly_names = await _tool_names(ServerOptions(readonly=True))
    worker_names = await _tool_names(ServerOptions(role=AgentRole.WORKER))
    assert readonly_names == worker_names


async def test_admin_flag_maps_to_orchestrator() -> None:
    admin_names = await _tool_names(ServerOptions(admin=True))
    orchestrator_names = await _tool_names(ServerOptions(role=AgentRole.ORCHESTRATOR))
    assert admin_names == orchestrator_names


# ---------------------------------------------------------------------------
# Mutually exclusive: readonly + admin raises ValueError
# ---------------------------------------------------------------------------


async def test_readonly_and_admin_mutually_exclusive() -> None:
    with pytest.raises(ValueError, match="mutually exclusive"):
        ServerOptions(readonly=True, admin=True)


# ---------------------------------------------------------------------------
# Parametrized: worker tools visible in all roles
# ---------------------------------------------------------------------------

_WORKER_TOOLS = [
    "task_get",
    "task_list",
    "task_events",
    "task_wait",
    "run_get",
    "run_cancel",
    "run_detach",
    "run_summary",
    "settings_get",
    "review_conflicts",
    "integration_preflight",
    "integration_preview",
    "mention_search",
    "verify_step",
    "verification_summary",
    "checkpoint_create",
    "checkpoint_list",
    "session_rewind",
    "insight_add",
    "insight_list",
]


@pytest.mark.parametrize("tool_name", _WORKER_TOOLS)
async def test_worker_tool_visible_in_worker_role(tool_name: str) -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.WORKER))
    assert tool_name in names, f"{tool_name!r} must be visible for WORKER"


@pytest.mark.parametrize("tool_name", _WORKER_TOOLS)
async def test_worker_tool_visible_in_reviewer_role(tool_name: str) -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.REVIEWER))
    assert tool_name in names, f"{tool_name!r} must be visible for REVIEWER"


@pytest.mark.parametrize("tool_name", _WORKER_TOOLS)
async def test_worker_tool_visible_in_orchestrator_role(tool_name: str) -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.ORCHESTRATOR))
    assert tool_name in names, f"{tool_name!r} must be visible for ORCHESTRATOR"


# ---------------------------------------------------------------------------
# Parametrized: orchestrator-only tools hidden from worker/reviewer
# ---------------------------------------------------------------------------

_ORCHESTRATOR_ONLY_TOOLS = [
    "task_create",
    "task_update",
    "task_delete",
    "run_start",
    "review_decide",
    "review_merge",
    "review_rebase",
    "project_list",
    "project_setup",
    "project_update",
    "settings_set",
    "audit_list",
    "integration_sync",
    "persona_inspect",
    "persona_import",
    "persona_export",
    "persona_trust",
    "insight_remove",
]


@pytest.mark.parametrize("tool_name", _ORCHESTRATOR_ONLY_TOOLS)
async def test_orchestrator_tool_hidden_from_worker(tool_name: str) -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.WORKER))
    assert tool_name not in names, f"{tool_name!r} must be hidden from WORKER"


@pytest.mark.parametrize("tool_name", _ORCHESTRATOR_ONLY_TOOLS)
async def test_orchestrator_tool_visible_for_orchestrator(tool_name: str) -> None:
    names = await _tool_names(ServerOptions(role=AgentRole.ORCHESTRATOR))
    assert tool_name in names, f"{tool_name!r} must be visible for ORCHESTRATOR"


# ---------------------------------------------------------------------------
# Call-level enforcement
# ---------------------------------------------------------------------------


async def test_worker_cannot_call_task_create() -> None:
    session, task, ready = await _connected_session(ServerOptions(role=AgentRole.WORKER))
    try:
        result = await session.list_tools()
        tool_names = {t.name for t in result.tools}
        assert "task_create" not in tool_names
    finally:
        ready.set()
        await task


async def test_orchestrator_can_call_task_create() -> None:
    session, task, ready = await _connected_session(ServerOptions(role=AgentRole.ORCHESTRATOR))
    try:
        call_result = await session.call_tool("task_create", {"title": "test-task"})
        assert call_result is not None
        assert not call_result.isError, f"task_create failed: {call_result.content}"
    finally:
        ready.set()
        await task


async def test_worker_can_call_task_list() -> None:
    session, task, ready = await _connected_session(ServerOptions(role=AgentRole.WORKER))
    try:
        call_result = await session.call_tool("task_list", {})
        assert call_result is not None
        assert not call_result.isError, f"task_list failed: {call_result.content}"
    finally:
        ready.set()
        await task
