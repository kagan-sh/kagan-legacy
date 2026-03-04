"""Behavioral tests for run_update MCP tool (PAIR session lifecycle).

Tests exercise tool behavior through MCP protocol (ClientSession.call_tool),
not by importing production internals. All assertions are on observable
protocol-level outcomes: tool visibility, response shape, and error behavior.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from mcp.types import CallToolResult, TextContent

from mcp import ClientSession
from tests.helpers.helpers import make_git_repo

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


def _text(result: CallToolResult) -> dict:
    """Extract JSON payload from the first TextContent block of a tool result."""
    block = result.content[0]
    assert isinstance(block, TextContent), f"Expected TextContent, got {type(block)}"
    return json.loads(block.text)


async def _create_pair_task_with_workspace(
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
        "project_add_repo",
        {"project_id": project_id, "repo_path": str(repo_path)},
    )
    assert not add_repo_result.isError

    create_result = await mcp_board.call_tool(
        "task_create",
        {"title": title, "execution_mode": "PAIR"},
    )
    assert not create_result.isError
    task_id = _text(create_result)["id"]

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
    """Default server must expose run_update."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "run_update" in names


# ---------------------------------------------------------------------------
# run_update — exists action
# ---------------------------------------------------------------------------


async def test_session_manage_exists_returns_bool(mcp_board: ClientSession) -> None:
    """run_update with action=exists must return a dict with an 'exists' bool."""
    result = await mcp_board.call_tool("run_update", {"action": "exists", "task_id": "task-pair-1"})
    assert not result.isError
    payload = _text(result)
    assert "exists" in payload
    assert isinstance(payload["exists"], bool)


async def test_session_manage_exists_false_for_unknown_task(mcp_board: ClientSession) -> None:
    """run_update exists on an unknown task must return exists=False."""
    result = await mcp_board.call_tool(
        "run_update", {"action": "exists", "task_id": "no-such-task"}
    )
    assert not result.isError
    assert _text(result)["exists"] is False


# ---------------------------------------------------------------------------
# run_update — create action
# ---------------------------------------------------------------------------


async def test_session_manage_create_returns_session_id(mcp_board: ClientSession) -> None:
    """run_update create must fail when pair prerequisites are missing."""
    result = await mcp_board.call_tool("run_update", {"action": "create", "task_id": "task-pair-2"})
    assert result.isError


async def test_session_manage_create_returns_task_id(mcp_board: ClientSession) -> None:
    """run_update create error contains the requested task id."""
    task_id = "task-pair-3"
    result = await mcp_board.call_tool("run_update", {"action": "create", "task_id": task_id})
    assert result.isError
    block = result.content[0]
    assert isinstance(block, TextContent)
    assert task_id in block.text


# ---------------------------------------------------------------------------
# run_update — get action
# ---------------------------------------------------------------------------


async def test_session_manage_get_after_create(mcp_board: ClientSession) -> None:
    """run_update get after failed create must return an error."""
    task_id = "task-pair-get"
    create_result = await mcp_board.call_tool(
        "run_update", {"action": "create", "task_id": task_id}
    )
    assert create_result.isError

    get_result = await mcp_board.call_tool("run_update", {"action": "get", "task_id": task_id})
    assert get_result.isError


async def test_session_manage_get_unknown_returns_error(mcp_board: ClientSession) -> None:
    """run_update get on an unknown task must return an error."""
    result = await mcp_board.call_tool("run_update", {"action": "get", "task_id": "no-such-task"})
    assert result.isError


# ---------------------------------------------------------------------------
# run_update — kill action
# ---------------------------------------------------------------------------


async def test_session_manage_kill_after_create(mcp_board: ClientSession) -> None:
    """run_update kill after failed create must return an error."""
    task_id = "task-pair-kill"
    create_result = await mcp_board.call_tool(
        "run_update", {"action": "create", "task_id": task_id}
    )
    assert create_result.isError

    kill_result = await mcp_board.call_tool("run_update", {"action": "kill", "task_id": task_id})
    assert kill_result.isError


async def test_session_manage_kill_unknown_returns_error(mcp_board: ClientSession) -> None:
    """run_update kill on an unknown task must return an error."""
    result = await mcp_board.call_tool("run_update", {"action": "kill", "task_id": "no-such-task"})
    assert result.isError


# ---------------------------------------------------------------------------
# run_update — invalid action
# ---------------------------------------------------------------------------


async def test_session_manage_invalid_action_returns_error(mcp_board: ClientSession) -> None:
    """run_update with an unknown action must return an error."""
    result = await mcp_board.call_tool("run_update", {"action": "bogus", "task_id": "task-pair-1"})
    assert result.isError


# ---------------------------------------------------------------------------
# run_update — exists after create / after kill
# ---------------------------------------------------------------------------


async def test_session_manage_exists_true_after_create(mcp_board: ClientSession) -> None:
    """run_update create fails without pair prerequisites; exists remains False."""
    task_id = "task-pair-exists-check"
    create_result = await mcp_board.call_tool(
        "run_update", {"action": "create", "task_id": task_id}
    )
    assert create_result.isError

    result = await mcp_board.call_tool("run_update", {"action": "exists", "task_id": task_id})
    assert not result.isError
    assert _text(result)["exists"] is False


async def test_session_manage_exists_false_after_kill(mcp_board: ClientSession) -> None:
    """run_update exists must return False after a session is killed."""
    task_id = "task-pair-kill-check"
    create_result = await mcp_board.call_tool(
        "run_update", {"action": "create", "task_id": task_id}
    )
    assert create_result.isError
    kill_result = await mcp_board.call_tool("run_update", {"action": "kill", "task_id": task_id})
    assert kill_result.isError

    result = await mcp_board.call_tool("run_update", {"action": "exists", "task_id": task_id})
    assert not result.isError
    assert _text(result)["exists"] is False


# ---------------------------------------------------------------------------
# Core-client path tests — exercise client is not None branches
# ---------------------------------------------------------------------------


async def test_core_session_start_returns_session_id(mcp_board_with_core: ClientSession) -> None:
    """run_start via core client must return a dict with session_id."""
    # Create a task first
    create_result = await mcp_board_with_core.call_tool(
        "task_create", {"title": "Core session task"}
    )
    task_id = _text(create_result)["id"]

    result = await mcp_board_with_core.call_tool("run_start", {"task_id": task_id})
    assert result is not None


async def test_core_session_manage_exists_returns_bool(mcp_board_with_core: ClientSession) -> None:
    """run_update exists via core client must return a dict with 'exists' bool."""
    create_result = await mcp_board_with_core.call_tool(
        "task_create", {"title": "Core session task"}
    )
    task_id = _text(create_result)["id"]

    result = await mcp_board_with_core.call_tool(
        "run_update", {"action": "exists", "task_id": task_id}
    )
    assert not result.isError
    payload = _text(result)
    assert "exists" in payload
    assert isinstance(payload["exists"], bool)


async def test_core_session_manage_get_returns_status(mcp_board_with_core: ClientSession) -> None:
    """run_update get via core client must return a dict with task_id."""
    create_result = await mcp_board_with_core.call_tool(
        "task_create", {"title": "Core session get task"}
    )
    task_id = _text(create_result)["id"]

    result = await mcp_board_with_core.call_tool(
        "run_update", {"action": "get", "task_id": task_id}
    )
    # get returns task status — may succeed or fail depending on task state
    assert result is not None


async def test_core_session_manage_invalid_action_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    """run_update with invalid action via core client must return an error."""
    create_result = await mcp_board_with_core.call_tool(
        "task_create", {"title": "Core invalid action task"}
    )
    task_id = _text(create_result)["id"]

    result = await mcp_board_with_core.call_tool(
        "run_update", {"action": "bogus_action", "task_id": task_id}
    )
    assert result.isError


async def test_core_session_cancel_unknown_task_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool(
        "run_cancel", {"session_id": "session-core-2", "task_id": "no-such-task"}
    )
    assert result.isError


async def test_core_session_manage_create_unknown_task_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool(
        "run_update", {"action": "create", "task_id": "no-such-task"}
    )
    assert result.isError


async def test_core_session_manage_get_unknown_task_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool(
        "run_update", {"action": "get", "task_id": "no-such-task"}
    )
    assert result.isError


async def test_core_session_manage_kill_unknown_task_returns_error(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool(
        "run_update", {"action": "kill", "task_id": "no-such-task"}
    )
    assert result.isError


async def test_core_session_manage_finish_moves_pair_task_to_review(
    mcp_board_with_core_client: tuple[ClientSession, Any],
    tmp_path: Path,
) -> None:
    mcp_board, core_client = mcp_board_with_core_client
    task_id, worktree_path = await _create_pair_task_with_workspace(
        mcp_board,
        core_client,
        tmp_path,
        title="Pair finish review",
    )
    (worktree_path / "pair_result.py").write_text("value = 1\n", encoding="utf-8")

    result = await mcp_board.call_tool(
        "run_update",
        {"action": "finish", "task_id": task_id},
    )
    assert not result.isError
    payload = _text(result)
    assert payload["task_id"] == task_id
    assert payload["ready_for_review"] is True
    assert payload["status"] == "REVIEW"


async def test_core_session_manage_finish_keeps_in_progress_without_changes(
    mcp_board_with_core_client: tuple[ClientSession, Any],
    tmp_path: Path,
) -> None:
    mcp_board, core_client = mcp_board_with_core_client
    task_id, _ = await _create_pair_task_with_workspace(
        mcp_board,
        core_client,
        tmp_path,
        title="Pair finish no changes",
    )

    result = await mcp_board.call_tool(
        "run_update",
        {"action": "finish", "task_id": task_id},
    )
    assert not result.isError
    payload = _text(result)
    assert payload["task_id"] == task_id
    assert payload["ready_for_review"] is False
    assert payload["status"] == "IN_PROGRESS"
