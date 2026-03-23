"""Behavioral tests for managed-run MCP tools."""

import json

import pytest
from mcp.types import CallToolResult, TextContent

from mcp import ClientSession

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


def _text(result: CallToolResult) -> dict:
    block = result.content[0]
    assert isinstance(block, TextContent), f"Expected TextContent, got {type(block)}"
    return json.loads(block.text)


async def _create_task(mcp_board: ClientSession, title: str) -> str:
    create_result = await mcp_board.call_tool("task_create", {"title": title})
    assert not create_result.isError
    return _text(create_result)["id"]


async def test_session_tools_visible_on_default_server(mcp_board: ClientSession) -> None:
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "run_start" in names
    assert "run_summary" in names
    assert "run_cancel" in names
    assert "run_exists" in names
    assert "run_create" in names
    assert "run_get" in names
    assert "run_kill" in names
    assert "run_detach" in names
    assert "run_wait" not in names


async def test_session_report_visible_on_default_server(mcp_board: ClientSession) -> None:
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "run_summary" in names


async def test_session_start_returns_error_without_workspace(mcp_board: ClientSession) -> None:
    task_id = await _create_task(mcp_board, "session start id")
    result = await mcp_board.call_tool("run_start", {"task_id": task_id})
    assert result.isError


async def test_session_start_rejects_unknown_action(mcp_board: ClientSession) -> None:
    task_id = await _create_task(mcp_board, "session start bad action")
    result = await mcp_board.call_tool(
        "run_start",
        {"task_id": task_id, "launcher": 123},
    )
    assert result.isError


async def test_session_start_accepts_persona_argument(mcp_board: ClientSession) -> None:
    task_id = await _create_task(mcp_board, "session start persona")
    result = await mcp_board.call_tool(
        "run_start",
        {"task_id": task_id, "persona": "analyst"},
    )
    assert result is not None


async def test_session_report_returns_expected_columns(mcp_board: ClientSession) -> None:
    task_id = await _create_task(mcp_board, "session report task")
    report_result = await mcp_board.call_tool("run_summary", {"task_ids": [task_id]})
    assert not report_result.isError
    payload = _text(report_result)
    assert "rows" in payload
    rows = payload["rows"]
    assert isinstance(rows, list)
    assert rows
    row = rows[0]
    assert row["task_id"] == task_id
    assert "status" in row
    assert "agent_backend" in row
    assert "session_id" in row
    assert "session_backend" in row


async def test_session_cancel_returns_success(mcp_board: ClientSession) -> None:
    task_id = await _create_task(mcp_board, "session cancel")
    session_id = "synthetic-session-id"
    cancel_result = await mcp_board.call_tool(
        "run_cancel", {"session_id": session_id, "task_id": task_id}
    )
    assert not cancel_result.isError
    payload = _text(cancel_result)
    assert payload.get("session_id") == session_id
    assert payload.get("task_id") == task_id
    assert payload.get("cancelled") is True


async def test_session_cancel_unknown_session_returns_error(mcp_board: ClientSession) -> None:
    result = await mcp_board.call_tool(
        "run_cancel", {"session_id": "nonexistent-session", "task_id": "task-abc"}
    )
    assert result.isError
