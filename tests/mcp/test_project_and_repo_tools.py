"""Behavioral tests for project and repo domain MCP tools.

Tests exercise tool behavior through MCP protocol (ClientSession.call_tool),
not by importing production internals. All assertions are on observable
protocol-level outcomes: tool visibility, response shape, and error behavior.

Consolidated toolset: project_list, project_setup, project_update.
"""

import asyncio
import contextlib

import pytest
from mcp.shared.memory import create_client_server_memory_streams
from kagan.server.mcp.server import ServerOptions, create_server
from mcp import ClientSession
from tests.helpers.mcp_helpers import extract_text as _text

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


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

    task = asyncio.create_task(_run())
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
    """Default server must expose project_list."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "project_list" in names


async def test_project_write_tools_visible_on_default_server(mcp_board: ClientSession) -> None:
    """Default server must expose project_setup and project_update."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "project_setup" in names
    assert "project_update" in names


async def test_old_tools_not_visible_on_default_server(mcp_board: ClientSession) -> None:
    """Old tool names must not be present on the default server."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    for old_name in (
        "project_create",
        "project_delete",
        "project_set_active",
        "project_add_repo",
        "project_set_repo_default_branch",
        "repo_list",
    ):
        assert old_name not in names


# ---------------------------------------------------------------------------
# Tool visibility — readonly server
# ---------------------------------------------------------------------------


async def test_project_tools_hidden_on_worker_role() -> None:
    """All project tools are orchestrator-only and hidden for worker (readonly) role."""
    names = await _tool_names_for(ServerOptions(readonly=True))
    assert "project_list" not in names
    assert "project_setup" not in names
    assert "project_update" not in names


# ---------------------------------------------------------------------------
# Tool visibility — admin server
# ---------------------------------------------------------------------------


async def test_project_setup_visible_on_admin_server() -> None:
    """project_setup must be visible on admin server."""
    names = await _tool_names_for(ServerOptions(admin=True))
    assert "project_setup" in names


async def test_admin_server_shows_all_project_tools() -> None:
    """Admin server must expose all project tools."""
    names = await _tool_names_for(ServerOptions(admin=True))
    assert "project_list" in names
    assert "project_setup" in names
    assert "project_update" in names


# ---------------------------------------------------------------------------
# project_list — returns list of projects with inlined repos
# ---------------------------------------------------------------------------


async def test_project_list_returns_projects_key(mcp_board: ClientSession) -> None:
    """project_list must return a dict with a 'projects' key."""
    result = await mcp_board.call_tool("project_list", {})
    assert not result.isError
    payload = _text(result)
    assert "projects" in payload
    assert isinstance(payload["projects"], list)


# ---------------------------------------------------------------------------
# project_update with set_active — returns project state
# ---------------------------------------------------------------------------


async def test_project_update_set_active_returns_id(mcp_board: ClientSession) -> None:
    """project_update with set_active=True must return a dict containing the project id."""
    project_id = await _first_project_id(mcp_board)
    result = await mcp_board.call_tool(
        "project_update", {"project_id": project_id, "set_active": True}
    )
    assert not result.isError
    payload = _text(result)
    assert payload.get("id") == project_id
    assert payload.get("is_active") is True


# ---------------------------------------------------------------------------
# project_update with add_repo_path — returns project state
# ---------------------------------------------------------------------------


async def test_project_update_add_repo_returns_id(mcp_board: ClientSession, tmp_path) -> None:
    """project_update with add_repo_path must return a dict containing the project id."""
    project_id = await _first_project_id(mcp_board)
    repo_path = str(tmp_path / "repo_for_add")
    result = await mcp_board.call_tool(
        "project_update", {"project_id": project_id, "add_repo_path": repo_path}
    )
    assert not result.isError
    payload = _text(result)
    assert payload.get("id") == project_id


# ---------------------------------------------------------------------------
# project_update with repo_id + default_branch — returns project state
# ---------------------------------------------------------------------------


async def test_project_update_repo_default_branch_returns_id(
    mcp_board: ClientSession, tmp_path
) -> None:
    """project_update with repo_id and default_branch must return a dict containing the project id."""
    project_id = await _first_project_id(mcp_board)
    repo_path = str(tmp_path / "repo_for_branch")

    # Add a repo first
    add_result = await mcp_board.call_tool(
        "project_update", {"project_id": project_id, "add_repo_path": repo_path}
    )
    assert not add_result.isError

    # Get the repo id from the project_list response (repos are now inlined)
    list_result = await mcp_board.call_tool("project_list", {})
    assert not list_result.isError
    projects = _text(list_result)["projects"]
    target = [p for p in projects if p["id"] == project_id]
    assert target
    repo_id = target[0]["repos"][0]["id"]

    result = await mcp_board.call_tool(
        "project_update",
        {"project_id": project_id, "repo_id": repo_id, "default_branch": "main"},
    )
    assert not result.isError
    payload = _text(result)
    assert payload.get("id") == project_id


# ---------------------------------------------------------------------------
# project_list — repos inlined (replaces old repo_list test)
# ---------------------------------------------------------------------------


async def test_project_list_includes_repos(mcp_board: ClientSession) -> None:
    """project_list must return projects with inlined repos lists."""
    result = await mcp_board.call_tool("project_list", {})
    assert not result.isError
    payload = _text(result)
    assert "projects" in payload
    for project in payload["projects"]:
        assert "repos" in project
        assert isinstance(project["repos"], list)


# ---------------------------------------------------------------------------
# project_setup — returns name and id
# ---------------------------------------------------------------------------


async def test_project_setup_returns_name_on_admin_server(tmp_path) -> None:
    """project_setup must return a dict with the project name on admin server."""
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

    task = asyncio.create_task(_run())
    session = await session_q.get()
    try:
        result = await session.call_tool("project_setup", {"name": "My Project"})
        assert not result.isError
        payload = _text(result)
        assert payload.get("name") == "My Project"
        assert payload.get("id")
        assert payload.get("is_active") is True
    finally:
        ready.set()
        await task


# ---------------------------------------------------------------------------
# project_update with delete=True — removes project
# ---------------------------------------------------------------------------


async def test_project_update_delete_removes_project_on_admin_server(tmp_path) -> None:
    """project_update with delete=True must remove a project and return deleted=True on admin server."""
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

    task = asyncio.create_task(_run())
    session = await session_q.get()
    try:
        create_result = await session.call_tool("project_setup", {"name": "Delete me"})
        assert not create_result.isError
        project_id = _text(create_result)["id"]

        delete_result = await session.call_tool(
            "project_update", {"project_id": project_id, "delete": True}
        )
        assert not delete_result.isError
        payload = _text(delete_result)
        assert payload.get("deleted") is True
        assert payload.get("project_id") == project_id
    finally:
        ready.set()
        await task


async def test_project_update_delete_unknown_project_returns_error(tmp_path) -> None:
    """project_update with delete=True and unknown project_id must return an error."""
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

    task = asyncio.create_task(_run())
    session = await session_q.get()
    try:
        result = await session.call_tool(
            "project_update", {"project_id": "nonexistent-proj", "delete": True}
        )
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


async def test_core_project_update_set_active_returns_id(
    mcp_board_with_core: ClientSession,
) -> None:
    """project_update with set_active via core client must return a dict with id."""
    list_result = await mcp_board_with_core.call_tool("project_list", {})
    projects = _text(list_result)["projects"]
    assert projects, "Expected at least one project"
    project_id = projects[0]["id"]

    result = await mcp_board_with_core.call_tool(
        "project_update", {"project_id": project_id, "set_active": True}
    )
    assert not result.isError
    assert _text(result).get("id") == project_id


async def test_core_project_list_includes_repos(mcp_board_with_core: ClientSession) -> None:
    """project_list via core client must return projects with inlined repos."""
    list_result = await mcp_board_with_core.call_tool("project_list", {})
    projects = _text(list_result)["projects"]
    assert projects
    project = projects[0]
    assert "repos" in project
    assert isinstance(project["repos"], list)


async def test_core_project_update_add_repo_returns_id(
    mcp_board_with_core: ClientSession, tmp_path
) -> None:
    """project_update with add_repo_path via core client must return a dict with id."""
    list_result = await mcp_board_with_core.call_tool("project_list", {})
    project_id = _text(list_result)["projects"][0]["id"]

    repo_path = str(tmp_path / "test_repo")
    result = await mcp_board_with_core.call_tool(
        "project_update", {"project_id": project_id, "add_repo_path": repo_path}
    )
    assert not result.isError
    assert _text(result).get("id") == project_id


async def test_core_project_update_set_active_unknown_project_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool(
        "project_update",
        {"project_id": "missing-project", "set_active": True},
    )
    assert result.isError


async def test_core_project_update_add_repo_unknown_project_returns_error(
    mcp_board_with_core: ClientSession, tmp_path
) -> None:
    repo_path = str(tmp_path / "missing_project_repo")
    result = await mcp_board_with_core.call_tool(
        "project_update", {"project_id": "missing-project", "add_repo_path": repo_path}
    )
    assert result.isError


async def test_core_project_update_delete_unknown_project_returns_error(
    mcp_board_admin_with_core: ClientSession,
) -> None:
    result = await mcp_board_admin_with_core.call_tool(
        "project_update", {"project_id": "missing-project", "delete": True}
    )
    assert result.isError


async def test_core_project_setup_returns_id_on_admin_server(
    mcp_board_admin_with_core: ClientSession,
) -> None:
    result = await mcp_board_admin_with_core.call_tool("project_setup", {"name": "Core Created"})
    assert not result.isError
    payload = _text(result)
    assert payload.get("name") == "Core Created"
    assert payload.get("id")
    assert payload.get("is_active") is True
