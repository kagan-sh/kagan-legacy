"""Behavioral tests for project and repo domain MCP tools.

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

from kagan.server.mcp.server import ServerOptions, create_server
from mcp import ClientSession

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


def _text(result: CallToolResult) -> dict:
    """Extract JSON payload from the first TextContent block of a tool result."""
    block = result.content[0]
    assert isinstance(block, TextContent), f"Expected TextContent, got {type(block)}"
    return json.loads(block.text)


async def _first_project_id(mcp_board: ClientSession) -> str:
    result = await mcp_board.call_tool("project_list", {})
    assert not result.isError
    projects = _text(result)["projects"]
    assert projects
    return projects[0]["id"]


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


async def test_project_read_tools_visible_on_default_server(mcp_board: ClientSession) -> None:
    """Default server must expose project_list and repo_list."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "project_list" in names
    assert "repo_list" in names


async def test_project_write_tools_visible_on_default_server(mcp_board: ClientSession) -> None:
    """Default server must expose project write tools."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "project_set_active" in names
    assert "project_add_repo" in names
    assert "project_set_repo_default_branch" in names


async def test_project_create_visible_on_default_server(mcp_board: ClientSession) -> None:
    """project_create is visible on default server (orchestrator role)."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "project_create" in names


# ---------------------------------------------------------------------------
# Tool visibility — readonly server
# ---------------------------------------------------------------------------


async def test_project_list_hidden_on_worker_role() -> None:
    """project_list is orchestrator-only and hidden for worker (readonly) role."""
    names = await _tool_names_for(ServerOptions(readonly=True))
    assert "project_list" not in names
    assert "repo_list" not in names


async def test_project_write_tools_hidden_on_readonly_server() -> None:
    """project_set_active and project_add_repo must be hidden on readonly server."""
    names = await _tool_names_for(ServerOptions(readonly=True))
    assert "project_set_active" not in names
    assert "project_add_repo" not in names
    assert "project_create" not in names


# ---------------------------------------------------------------------------
# Tool visibility — admin server
# ---------------------------------------------------------------------------


async def test_project_create_visible_on_admin_server() -> None:
    """project_create must be visible on admin server."""
    names = await _tool_names_for(ServerOptions(admin=True))
    assert "project_create" in names


async def test_admin_server_shows_all_project_tools() -> None:
    """Admin server must expose all project and repo tools."""
    names = await _tool_names_for(ServerOptions(admin=True))
    assert "project_list" in names
    assert "project_create" in names
    assert "project_set_active" in names
    assert "project_add_repo" in names
    assert "project_set_repo_default_branch" in names
    assert "repo_list" in names


# ---------------------------------------------------------------------------
# project_list — returns list of projects
# ---------------------------------------------------------------------------


async def test_project_list_returns_projects_key(mcp_board: ClientSession) -> None:
    """project_list must return a dict with a 'projects' key."""
    result = await mcp_board.call_tool("project_list", {})
    assert not result.isError
    payload = _text(result)
    assert "projects" in payload
    assert isinstance(payload["projects"], list)


# ---------------------------------------------------------------------------
# project_set_active — returns project_id
# ---------------------------------------------------------------------------


async def test_project_open_returns_project_id(mcp_board: ClientSession) -> None:
    """project_set_active must return a dict containing the project_id."""
    project_id = await _first_project_id(mcp_board)
    result = await mcp_board.call_tool("project_set_active", {"project_id": project_id})
    assert not result.isError
    payload = _text(result)
    assert payload.get("project_id") == project_id


# ---------------------------------------------------------------------------
# project_add_repo — returns project_id
# ---------------------------------------------------------------------------


async def test_project_add_repo_returns_project_id(mcp_board: ClientSession, tmp_path) -> None:
    """project_add_repo must return a dict containing the project_id."""
    project_id = await _first_project_id(mcp_board)
    repo_path = str(tmp_path / "repo_for_add")
    result = await mcp_board.call_tool(
        "project_add_repo", {"project_id": project_id, "repo_path": repo_path}
    )
    assert not result.isError
    payload = _text(result)
    assert payload.get("project_id") == project_id


# ---------------------------------------------------------------------------
# project_set_repo_default_branch — returns project_id
# ---------------------------------------------------------------------------


async def test_project_update_repo_default_branch_returns_project_id(
    mcp_board: ClientSession, tmp_path
) -> None:
    """project_set_repo_default_branch must return a dict containing the project_id."""
    project_id = await _first_project_id(mcp_board)
    repo_path = str(tmp_path / "repo_for_branch")
    add_result = await mcp_board.call_tool(
        "project_add_repo", {"project_id": project_id, "repo_path": repo_path}
    )
    assert not add_result.isError
    repos_result = await mcp_board.call_tool("repo_list", {"project_id": project_id})
    assert not repos_result.isError
    repo_id = _text(repos_result)["repos"][0]["id"]

    result = await mcp_board.call_tool(
        "project_set_repo_default_branch",
        {"project_id": project_id, "repo_id": repo_id, "branch": "main"},
    )
    assert not result.isError
    payload = _text(result)
    assert payload.get("project_id") == project_id


# ---------------------------------------------------------------------------
# repo_list — returns list of repos
# ---------------------------------------------------------------------------


async def test_repo_list_returns_repos_key(mcp_board: ClientSession) -> None:
    """repo_list must return a dict with a 'repos' key."""
    result = await mcp_board.call_tool("repo_list", {"project_id": "proj-123"})
    assert not result.isError
    payload = _text(result)
    assert "repos" in payload
    assert isinstance(payload["repos"], list)


# ---------------------------------------------------------------------------
# project_create — admin only, returns name
# ---------------------------------------------------------------------------


async def test_project_create_returns_name_on_admin_server(tmp_path) -> None:
    """project_create must return a dict with the project name on admin server."""
    mcp = create_server(ServerOptions(admin=True, db_path=str(tmp_path / "admin_create.db")))
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
        result = await session.call_tool("project_create", {"name": "My Project"})
        assert not result.isError
        payload = _text(result)
        assert payload.get("name") == "My Project"
    finally:
        ready.set()
        await task


# ---------------------------------------------------------------------------
# project_delete — admin only, removes project
# ---------------------------------------------------------------------------


async def test_project_delete_removes_project_on_admin_server(tmp_path) -> None:
    """project_delete must remove a project and return deleted=True on admin server."""
    mcp = create_server(ServerOptions(admin=True, db_path=str(tmp_path / "admin_delete.db")))
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
        create_result = await session.call_tool("project_create", {"name": "Delete me"})
        assert not create_result.isError
        project_id = _text(create_result)["id"]

        delete_result = await session.call_tool("project_delete", {"project_id": project_id})
        assert not delete_result.isError
        payload = _text(delete_result)
        assert payload.get("deleted") is True
        assert payload.get("project_id") == project_id
    finally:
        ready.set()
        await task


async def test_project_delete_unknown_project_returns_error(tmp_path) -> None:
    """project_delete with an unknown project_id must return an error."""
    mcp = create_server(ServerOptions(admin=True, db_path=str(tmp_path / "admin_unknown.db")))
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
        result = await session.call_tool("project_delete", {"project_id": "nonexistent-proj"})
        assert result.isError
    finally:
        ready.set()
        await task


# ---------------------------------------------------------------------------
# project_list — multiple calls (branch coverage for store re-use)
# ---------------------------------------------------------------------------


async def test_project_list_called_twice_returns_consistent_results(
    mcp_board: ClientSession,
) -> None:
    """project_list called twice must return consistent results (store re-use path)."""
    result1 = await mcp_board.call_tool("project_list", {})
    result2 = await mcp_board.call_tool("project_list", {})
    assert not result1.isError
    assert not result2.isError
    assert _text(result1)["projects"] == _text(result2)["projects"]


async def test_repo_list_called_twice_returns_consistent_results(
    mcp_board: ClientSession,
) -> None:
    """repo_list called twice must return consistent results (store re-use path)."""
    result1 = await mcp_board.call_tool("repo_list", {"project_id": "proj-abc"})
    result2 = await mcp_board.call_tool("repo_list", {"project_id": "proj-abc"})
    assert not result1.isError
    assert not result2.isError
    assert _text(result1)["repos"] == _text(result2)["repos"]


# ---------------------------------------------------------------------------
# Core-client path tests — exercise client is not None branches
# ---------------------------------------------------------------------------


async def test_core_project_list_returns_projects(mcp_board_with_core: ClientSession) -> None:
    """project_list via core client must return a dict with a 'projects' key."""
    result = await mcp_board_with_core.call_tool("project_list", {})
    assert not result.isError
    payload = _text(result)
    assert "projects" in payload
    assert isinstance(payload["projects"], list)


async def test_core_project_list_includes_pre_created_project(
    mcp_board_with_core: ClientSession,
) -> None:
    """project_list via core client must include the pre-created project."""
    result = await mcp_board_with_core.call_tool("project_list", {})
    assert not result.isError
    payload = _text(result)
    assert len(payload["projects"]) >= 1


async def test_core_project_open_returns_project_id(mcp_board_with_core: ClientSession) -> None:
    """project_set_active via core client must return a dict with project_id."""
    # First get a project id from the list
    list_result = await mcp_board_with_core.call_tool("project_list", {})
    projects = _text(list_result)["projects"]
    assert projects, "Expected at least one project"
    project_id = projects[0]["id"]

    result = await mcp_board_with_core.call_tool("project_set_active", {"project_id": project_id})
    assert not result.isError
    assert _text(result).get("project_id") == project_id


async def test_core_repo_list_returns_repos(mcp_board_with_core: ClientSession) -> None:
    """repo_list via core client must return a dict with 'repos' key."""
    list_result = await mcp_board_with_core.call_tool("project_list", {})
    project_id = _text(list_result)["projects"][0]["id"]

    result = await mcp_board_with_core.call_tool("repo_list", {"project_id": project_id})
    assert not result.isError
    payload = _text(result)
    assert "repos" in payload
    assert isinstance(payload["repos"], list)


async def test_core_project_add_repo_returns_project_id(
    mcp_board_with_core: ClientSession, tmp_path
) -> None:
    """project_add_repo via core client must return a dict with project_id."""
    list_result = await mcp_board_with_core.call_tool("project_list", {})
    project_id = _text(list_result)["projects"][0]["id"]

    repo_path = str(tmp_path / "test_repo")
    result = await mcp_board_with_core.call_tool(
        "project_add_repo", {"project_id": project_id, "repo_path": repo_path}
    )
    assert not result.isError
    assert _text(result).get("project_id") == project_id


async def test_core_project_open_unknown_project_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool(
        "project_set_active",
        {"project_id": "missing-project"},
    )
    assert result.isError


async def test_core_project_add_repo_unknown_project_returns_error(
    mcp_board_with_core: ClientSession, tmp_path
) -> None:
    repo_path = str(tmp_path / "missing_project_repo")
    result = await mcp_board_with_core.call_tool(
        "project_add_repo", {"project_id": "missing-project", "repo_path": repo_path}
    )
    assert result.isError


async def test_core_repo_list_unknown_project_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool("repo_list", {"project_id": "missing-project"})
    assert not result.isError
    payload = _text(result)
    assert "repos" in payload
    assert isinstance(payload["repos"], list)


async def test_core_project_delete_unknown_project_returns_error(
    mcp_board_admin_with_core: ClientSession,
) -> None:
    result = await mcp_board_admin_with_core.call_tool(
        "project_delete", {"project_id": "missing-project"}
    )
    assert result.isError


async def test_core_project_create_returns_id_on_admin_server(
    mcp_board_admin_with_core: ClientSession,
) -> None:
    result = await mcp_board_admin_with_core.call_tool("project_create", {"name": "Core Created"})
    assert not result.isError
    payload = _text(result)
    assert payload.get("name") == "Core Created"
    assert payload.get("id")
