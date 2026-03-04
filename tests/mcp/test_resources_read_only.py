"""Behavioral tests for kagan MCP resources.

Tests exercise resource behavior through MCP protocol (ClientSession.read_resource
and list_resources/list_resource_templates), not by importing production internals.
All assertions are on observable protocol-level outcomes.
"""

import json

import pytest
from mcp.shared.exceptions import McpError
from mcp.types import TextResourceContents

from mcp import ClientSession

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


def _json(contents: list) -> dict:
    """Extract JSON from the first TextResourceContents block."""
    block = contents[0]
    assert isinstance(block, TextResourceContents), (
        f"Expected TextResourceContents, got {type(block)}"
    )
    return json.loads(block.text)


# ---------------------------------------------------------------------------
# Resource visibility
# ---------------------------------------------------------------------------


async def test_ping_resource_is_listed(mcp_board: ClientSession) -> None:
    """kagan://ping must appear in list_resources."""
    result = await mcp_board.list_resources()
    uris = {str(r.uri) for r in result.resources}
    assert "kagan://ping" in uris


async def test_settings_resource_is_listed(mcp_board: ClientSession) -> None:
    """kagan://settings must appear in list_resources."""
    result = await mcp_board.list_resources()
    uris = {str(r.uri) for r in result.resources}
    assert "kagan://settings" in uris


async def test_projects_resource_is_listed(mcp_board: ClientSession) -> None:
    """kagan://projects must appear in list_resources."""
    result = await mcp_board.list_resources()
    uris = {str(r.uri) for r in result.resources}
    assert "kagan://projects" in uris


async def test_runtime_resource_is_listed(mcp_board: ClientSession) -> None:
    """kagan://runtime must appear in list_resources."""
    result = await mcp_board.list_resources()
    uris = {str(r.uri) for r in result.resources}
    assert "kagan://runtime" in uris


async def test_task_detail_template_is_listed(mcp_board: ClientSession) -> None:
    """kagan://tasks/{task_id} must appear in list_resource_templates."""
    result = await mcp_board.list_resource_templates()
    templates = {t.uriTemplate for t in result.resourceTemplates}
    assert "kagan://tasks/{task_id}" in templates


# ---------------------------------------------------------------------------
# kagan://ping — health check
# ---------------------------------------------------------------------------


async def test_ping_returns_status_ok(mcp_board: ClientSession) -> None:
    """kagan://ping must return {status: 'ok'}."""
    result = await mcp_board.read_resource("kagan://ping")
    payload = _json(result.contents)
    assert payload.get("status") == "ok"


# ---------------------------------------------------------------------------
# kagan://settings — settings snapshot
# ---------------------------------------------------------------------------


async def test_settings_returns_dict(mcp_board: ClientSession) -> None:
    """kagan://settings must return a dict (settings snapshot)."""
    result = await mcp_board.read_resource("kagan://settings")
    payload = _json(result.contents)
    assert isinstance(payload, dict)


# ---------------------------------------------------------------------------
# kagan://projects — project list
# ---------------------------------------------------------------------------


async def test_projects_returns_list(mcp_board: ClientSession) -> None:
    """kagan://projects must return a dict with a 'projects' list."""
    result = await mcp_board.read_resource("kagan://projects")
    payload = _json(result.contents)
    assert "projects" in payload
    assert isinstance(payload["projects"], list)


# ---------------------------------------------------------------------------
# kagan://tasks/{task_id} — task detail template
# ---------------------------------------------------------------------------


async def test_task_detail_returns_task_dict(mcp_board: ClientSession) -> None:
    """kagan://tasks/{task_id} must return a task dict for a created task."""
    create_result = await mcp_board.call_tool("task_create", {"title": "Resource task"})
    block = create_result.content[0]
    task_id = json.loads(block.text)["id"]

    result = await mcp_board.read_resource(f"kagan://tasks/{task_id}")
    payload = _json(result.contents)
    assert payload.get("id") == task_id
    assert payload.get("title") == "Resource task"


async def test_task_detail_unknown_id_returns_error(mcp_board: ClientSession) -> None:
    """kagan://tasks/{task_id} with unknown id must raise an error."""
    with pytest.raises(McpError):
        await mcp_board.read_resource("kagan://tasks/nonexistent-id-xyz")


# ---------------------------------------------------------------------------
# kagan://runtime — active sessions and agent processes
# ---------------------------------------------------------------------------


async def test_runtime_returns_dict(mcp_board: ClientSession) -> None:
    """kagan://runtime must return a dict with runtime info."""
    result = await mcp_board.read_resource("kagan://runtime")
    payload = _json(result.contents)
    assert isinstance(payload, dict)


async def test_projects_resource_returns_empty_list_on_fresh_server(
    mcp_board: ClientSession,
) -> None:
    """kagan://projects on a fresh server must include default active project."""
    result = await mcp_board.read_resource("kagan://projects")
    payload = _json(result.contents)
    projects = payload.get("projects")
    assert isinstance(projects, list)
    assert len(projects) >= 1
    assert any(p.get("name") == "Default Project" for p in projects)


async def test_settings_resource_returns_empty_dict_on_fresh_server(
    mcp_board: ClientSession,
) -> None:
    """kagan://settings on a fresh server must return an empty dict."""
    result = await mcp_board.read_resource("kagan://settings")
    payload = _json(result.contents)
    assert payload == {}


async def test_runtime_returns_sessions_and_agents_keys(mcp_board: ClientSession) -> None:
    """kagan://runtime must return a dict with 'sessions' and 'agents' keys."""
    result = await mcp_board.read_resource("kagan://runtime")
    payload = _json(result.contents)
    assert "sessions" in payload
    assert "agents" in payload


# ---------------------------------------------------------------------------
# Core-client path tests — exercise client is not None branches
# ---------------------------------------------------------------------------


async def test_core_settings_resource_returns_dict(mcp_board_with_core: ClientSession) -> None:
    """kagan://settings via core client must return a dict."""
    result = await mcp_board_with_core.read_resource("kagan://settings")
    payload = _json(result.contents)
    assert isinstance(payload, dict)


async def test_core_projects_resource_returns_list(mcp_board_with_core: ClientSession) -> None:
    """kagan://projects via core client must return a dict with 'projects' list."""
    result = await mcp_board_with_core.read_resource("kagan://projects")
    payload = _json(result.contents)
    assert "projects" in payload
    assert isinstance(payload["projects"], list)


async def test_core_task_detail_resource_returns_task(mcp_board_with_core: ClientSession) -> None:
    """kagan://tasks/{task_id} via core client must return a task dict."""
    create_result = await mcp_board_with_core.call_tool(
        "task_create", {"title": "Core resource task"}
    )
    task_id = json.loads(create_result.content[0].text)["id"]

    result = await mcp_board_with_core.read_resource(f"kagan://tasks/{task_id}")
    payload = _json(result.contents)
    assert payload.get("id") == task_id
    assert payload.get("title") == "Core resource task"
