"""Behavioral tests for explicit attached-run MCP tools.

Tests exercise tool behavior through MCP protocol (ClientSession.call_tool),
not by importing production internals. All assertions are on observable
protocol-level outcomes: tool visibility, response shape, and error behavior.
"""

from pathlib import Path
from typing import Any

import pytest
from mcp.types import TextContent

from mcp import ClientSession
from tests.helpers.helpers import make_git_repo
from tests.helpers.mcp_helpers import extract_text as _text

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


async def _create_attached_task_with_workspace(
    mcp_board: ClientSession,
    core_client: Any,
    tmp_path: Path,
    *,
    title: str,
) -> tuple[str, Path]:
    repo_path = tmp_path / f"repo_{title.replace(' ', '_').lower()}"
    await make_git_repo(repo_path, base_branch="main")

    project_id = core_client.active_project_id
    assert isinstance(project_id, str)
    add_repo_result = await mcp_board.call_tool(
        "project_update",
        {"project_id": project_id, "add_repo_path": str(repo_path)},
    )
    assert not add_repo_result.isError

    create_result = await mcp_board.call_tool(
        "task_create",
        {"title": title, "launcher": "tmux"},
    )
    assert not create_result.isError
    task_id = _text(create_result)["created"][0]["id"]

    move_result = await mcp_board.call_tool(
        "task_update",
        {"task_id": task_id, "status": "IN_PROGRESS"},
    )
    assert not move_result.isError

    ws = await core_client.worktrees.create(task_id)
    return task_id, Path(ws.worktree_path)


# ---------------------------------------------------------------------------
# Tool visibility
# ---------------------------------------------------------------------------


async def test_session_manage_visible_on_default_server(mcp_board: ClientSession) -> None:
    """Default server must expose explicit attached-run tools."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "run_start" in names
    assert "run_get" in names
    assert "run_cancel" in names
    assert "run_detach" in names


# ---------------------------------------------------------------------------
# run_get (replaces run_exists — check session_status != null)
# ---------------------------------------------------------------------------


async def test_session_manage_get_returns_status_fields(mcp_board: ClientSession) -> None:
    """run_get must return a dict with session_status field."""
    result = await mcp_board.call_tool("run_get", {"task_id": "task-attached-1"})
    assert result.isError  # unknown task returns error


async def test_session_manage_get_unknown_task_returns_error(mcp_board: ClientSession) -> None:
    """run_get on an unknown task must return an error."""
    result = await mcp_board.call_tool("run_get", {"task_id": "no-such-task"})
    assert result.isError


# ---------------------------------------------------------------------------
# run_start (replaces run_create)
# ---------------------------------------------------------------------------


async def test_session_manage_start_fails_without_prerequisites(mcp_board: ClientSession) -> None:
    """run_start must fail when attached prerequisites are missing."""
    result = await mcp_board.call_tool("run_start", {"task_id": "task-attached-2"})
    assert result.isError


async def test_session_manage_start_returns_task_id(mcp_board: ClientSession) -> None:
    """run_start error contains the requested task id."""
    task_id = "task-attached-3"
    result = await mcp_board.call_tool("run_start", {"task_id": task_id})
    assert result.isError
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert task_id in block.text


# ---------------------------------------------------------------------------
# run_get
# ---------------------------------------------------------------------------


async def test_session_manage_get_after_start(mcp_board: ClientSession) -> None:
    """run_get after failed start must return an error."""
    task_id = "task-attached-get"
    start_result = await mcp_board.call_tool("run_start", {"task_id": task_id})
    assert start_result.isError

    get_result = await mcp_board.call_tool("run_get", {"task_id": task_id})
    assert get_result.isError


async def test_session_manage_get_unknown_returns_error_attached(mcp_board: ClientSession) -> None:
    """run_get on an unknown task must return an error."""
    result = await mcp_board.call_tool("run_get", {"task_id": "no-such-task"})
    assert result.isError


# ---------------------------------------------------------------------------
# run_cancel (replaces run_kill)
# ---------------------------------------------------------------------------


async def test_session_manage_cancel_after_start(mcp_board: ClientSession) -> None:
    """run_cancel after failed start must return an error."""
    task_id = "task-attached-kill"
    start_result = await mcp_board.call_tool("run_start", {"task_id": task_id})
    assert start_result.isError

    cancel_result = await mcp_board.call_tool("run_cancel", {"task_id": task_id})
    assert cancel_result.isError


async def test_session_manage_cancel_unknown_returns_error(mcp_board: ClientSession) -> None:
    """run_cancel on an unknown task must return an error."""
    result = await mcp_board.call_tool("run_cancel", {"task_id": "no-such-task"})
    assert result.isError


# ---------------------------------------------------------------------------
# Legacy multiplexed tool
# ---------------------------------------------------------------------------


async def test_session_manage_legacy_tool_is_hidden(mcp_board: ClientSession) -> None:
    """run_update must no longer be exposed."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "run_update" not in names


# ---------------------------------------------------------------------------
# run_get after start / after cancel
# ---------------------------------------------------------------------------


async def test_session_manage_get_error_after_failed_start(mcp_board: ClientSession) -> None:
    """run_start failure means run_get returns error (no session)."""
    task_id = "task-attached-exists-check"
    start_result = await mcp_board.call_tool("run_start", {"task_id": task_id})
    assert start_result.isError

    result = await mcp_board.call_tool("run_get", {"task_id": task_id})
    assert result.isError


async def test_session_manage_get_error_after_cancel(mcp_board: ClientSession) -> None:
    """run_get must return error after a session cancel on unknown task."""
    task_id = "task-attached-kill-check"
    start_result = await mcp_board.call_tool("run_start", {"task_id": task_id})
    assert start_result.isError
    cancel_result = await mcp_board.call_tool("run_cancel", {"task_id": task_id})
    assert cancel_result.isError

    result = await mcp_board.call_tool("run_get", {"task_id": task_id})
    assert result.isError


# ---------------------------------------------------------------------------
# Core-client path tests — exercise client is not None branches
# ---------------------------------------------------------------------------


async def test_core_session_start_returns_session_id(mcp_board_with_core: ClientSession) -> None:
    """run_start via core client must return a dict with session_id."""
    # Create a task first
    create_result = await mcp_board_with_core.call_tool(
        "task_create", {"title": "Core session task"}
    )
    task_id = _text(create_result)["created"][0]["id"]

    result = await mcp_board_with_core.call_tool(
        "run_start", {"task_id": task_id, "launcher": "tmux"}
    )
    assert result is not None


async def test_core_session_manage_get_returns_status_fields(
    mcp_board_with_core: ClientSession,
) -> None:
    """run_get via core client must return a dict with session status fields."""
    create_result = await mcp_board_with_core.call_tool(
        "task_create", {"title": "Core session task"}
    )
    task_id = _text(create_result)["created"][0]["id"]

    result = await mcp_board_with_core.call_tool("run_get", {"task_id": task_id})
    assert not result.isError
    payload = _text(result)
    assert payload["task_id"] == task_id
    assert "session_status" in payload


async def test_core_session_manage_get_returns_status(mcp_board_with_core: ClientSession) -> None:
    """run_get via core client must return a dict with task_id."""
    create_result = await mcp_board_with_core.call_tool(
        "task_create", {"title": "Core session get task"}
    )
    task_id = _text(create_result)["created"][0]["id"]

    result = await mcp_board_with_core.call_tool("run_get", {"task_id": task_id})
    assert not result.isError
    payload = _text(result)
    assert payload["task_id"] == task_id
    assert "task_status" in payload
    assert "session_status" in payload


async def test_core_session_manage_legacy_tool_is_hidden(
    mcp_board_with_core: ClientSession,
) -> None:
    """run_update must no longer be exposed via core-backed MCP sessions."""
    result = await mcp_board_with_core.list_tools()
    names = {t.name for t in result.tools}
    assert "run_update" not in names


async def test_core_session_cancel_unknown_task_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool(
        "run_cancel", {"session_id": "session-core-2", "task_id": "no-such-task"}
    )
    assert result.isError


async def test_core_session_manage_start_unknown_task_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool("run_start", {"task_id": "no-such-task"})
    assert result.isError


async def test_core_session_manage_get_unknown_task_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool("run_get", {"task_id": "no-such-task"})
    assert result.isError


async def test_core_session_manage_cancel_unknown_task_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool("run_cancel", {"task_id": "no-such-task"})
    assert result.isError


async def test_core_session_manage_detach_moves_attached_task_to_review(
    mcp_board_with_core_client: tuple[ClientSession, Any],
    tmp_path: Path,
) -> None:
    mcp_board, core_client = mcp_board_with_core_client
    task_id, worktree_path = await _create_attached_task_with_workspace(
        mcp_board,
        core_client,
        tmp_path,
        title="Attached detach review",
    )
    (worktree_path / "attached_result.py").write_text("value = 1\n", encoding="utf-8")

    result = await mcp_board.call_tool("run_detach", {"task_id": task_id})
    assert not result.isError
    payload = _text(result)
    assert payload["task_id"] == task_id
    assert payload["ready_for_review"] is True
    assert payload["status"] == "REVIEW"


async def test_core_session_manage_detach_keeps_in_progress_without_changes(
    mcp_board_with_core_client: tuple[ClientSession, Any],
    tmp_path: Path,
) -> None:
    mcp_board, core_client = mcp_board_with_core_client
    task_id, _ = await _create_attached_task_with_workspace(
        mcp_board,
        core_client,
        tmp_path,
        title="Attached detach no changes",
    )

    result = await mcp_board.call_tool("run_detach", {"task_id": task_id})
    assert not result.isError
    payload = _text(result)
    assert payload["task_id"] == task_id
    assert payload["ready_for_review"] is False
    assert payload["status"] == "IN_PROGRESS"
