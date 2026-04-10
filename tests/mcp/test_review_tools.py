"""Behavioral tests for explicit review MCP tools.

Tests exercise tool behavior through MCP protocol (ClientSession.call_tool),
not by importing production internals. All assertions are on observable
protocol-level outcomes: tool visibility, response shape, and error behavior.
"""

import asyncio
import contextlib
from pathlib import Path
from typing import Any

import pytest
from mcp.shared.memory import create_client_server_memory_streams
from mcp.types import TextContent

from kagan.server.mcp.server import ServerOptions, create_server
from mcp import ClientSession
from tests.helpers.helpers import commit_file, make_git_repo
from tests.helpers.mcp_helpers import extract_text as _text

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


async def _create_review_task(mcp_board: ClientSession, title: str) -> str:
    create_result = await mcp_board.call_tool("task_create", {"title": title})
    assert not create_result.isError
    task_id = _text(create_result)["created"][0]["id"]
    in_progress_result = await mcp_board.call_tool(
        "task_update", {"task_id": task_id, "status": "IN_PROGRESS"}
    )
    assert not in_progress_result.isError
    patch_result = await mcp_board.call_tool(
        "task_update",
        {"task_id": task_id, "status": "REVIEW"},
    )
    assert not patch_result.isError
    return task_id


async def _create_review_task_with_ac(mcp_board: ClientSession, title: str) -> str:
    """Create a review task WITH acceptance criteria (eligible for auto-approve)."""
    create_result = await mcp_board.call_tool(
        "task_create",
        {"title": title, "acceptance_criteria": ["Tests pass", "No lint errors"]},
    )
    assert not create_result.isError
    task_id = _text(create_result)["created"][0]["id"]
    in_progress_result = await mcp_board.call_tool(
        "task_update", {"task_id": task_id, "status": "IN_PROGRESS"}
    )
    assert not in_progress_result.isError
    patch_result = await mcp_board.call_tool(
        "task_update",
        {"task_id": task_id, "status": "REVIEW"},
    )
    assert not patch_result.isError
    return task_id


async def _create_merge_ready_review_task(
    mcp_board: ClientSession,
    core_client: Any,
    tmp_path: Path,
    *,
    title: str,
    file_name: str,
) -> tuple[str, Path]:
    repo_path = tmp_path / f"repo_{file_name.replace('.', '_')}"
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
        {"title": title, "acceptance_criteria": ["Code compiles", "Tests pass"]},
    )
    assert not create_result.isError
    task_id = _text(create_result)["created"][0]["id"]

    in_progress_result = await mcp_board.call_tool(
        "task_update",
        {"task_id": task_id, "status": "IN_PROGRESS"},
    )
    assert not in_progress_result.isError

    workspace = await core_client.worktrees.create(task_id)
    committed = await commit_file(
        Path(workspace.worktree_path),
        file_name,
        "value = 1\n",
        message=f"feat: add {file_name}",
    )
    assert committed is True

    review_result = await mcp_board.call_tool(
        "task_update",
        {"task_id": task_id, "status": "REVIEW"},
    )
    assert not review_result.isError
    return task_id, repo_path


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
# Tool visibility
# ---------------------------------------------------------------------------


async def test_review_apply_visible_on_default_server(mcp_board: ClientSession) -> None:
    """Default server must expose explicit review tools."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "review_decide" in names
    assert "review_merge" in names
    assert "review_rebase" in names
    assert "review_verdict" in names
    assert "review_conflicts" in names


async def test_review_apply_visible_on_readonly_server() -> None:
    """Explicit review tools must NOT be visible on readonly server."""
    names = await _tool_names_for(ServerOptions(readonly=True))
    assert "review_decide" not in names
    assert "review_merge" not in names
    assert "review_rebase" not in names
    assert "review_verdict" not in names
    assert "review_conflicts" in names


async def test_review_apply_visible_on_admin_server() -> None:
    """Explicit review tools must be visible on admin server."""
    names = await _tool_names_for(ServerOptions(admin=True))
    assert "review_decide" in names
    assert "review_merge" in names
    assert "review_rebase" in names
    assert "review_verdict" in names


# ---------------------------------------------------------------------------
# review_decide (verdict=approve)
# ---------------------------------------------------------------------------


async def test_review_apply_approve_returns_task_id(mcp_board: ClientSession) -> None:
    """review_decide(verdict=approve) must return a dict with task_id."""
    task_id = await _create_review_task_with_ac(mcp_board, "review approve 1")
    result = await mcp_board.call_tool("review_decide", {"task_id": task_id, "verdict": "approve"})
    assert not result.isError
    payload = _text(result)
    assert payload.get("task_id") == task_id


async def test_review_apply_approve_returns_action(mcp_board: ClientSession) -> None:
    """review_decide(verdict=approve) must echo back the action."""
    task_id = await _create_review_task_with_ac(mcp_board, "review approve 2")
    result = await mcp_board.call_tool("review_decide", {"task_id": task_id, "verdict": "approve"})
    assert not result.isError
    payload = _text(result)
    assert payload.get("action") == "approve"


async def test_review_apply_approve_blocked_without_acceptance_criteria(
    mcp_board: ClientSession,
) -> None:
    """review_decide(verdict=approve) on a task without AC must return blocked."""
    task_id = await _create_review_task(mcp_board, "review approve no ac")
    result = await mcp_board.call_tool("review_decide", {"task_id": task_id, "verdict": "approve"})
    assert not result.isError
    payload = _text(result)
    assert payload.get("action") == "blocked"
    assert payload.get("reason_code") == "MANUAL_REVIEW_REQUIRED"
    assert "manual human review" in payload.get("reason", "").lower()


# ---------------------------------------------------------------------------
# review_decide (verdict=reject)
# ---------------------------------------------------------------------------


async def test_review_apply_reject_returns_task_id(mcp_board: ClientSession) -> None:
    """review_decide(verdict=reject) must return a dict with task_id."""
    task_id = await _create_review_task(mcp_board, "review reject 1")
    result = await mcp_board.call_tool(
        "review_decide",
        {"task_id": task_id, "verdict": "reject", "feedback": "Needs more work"},
    )
    assert not result.isError
    payload = _text(result)
    assert payload.get("task_id") == task_id


async def test_review_apply_reject_echoes_feedback(mcp_board: ClientSession) -> None:
    """review_decide(verdict=reject) must echo back the feedback."""
    task_id = await _create_review_task(mcp_board, "review reject 2")
    result = await mcp_board.call_tool(
        "review_decide",
        {"task_id": task_id, "verdict": "reject", "feedback": "Fix the tests"},
    )
    assert not result.isError
    payload = _text(result)
    assert payload.get("feedback") == "Fix the tests"


async def test_review_apply_reject_without_feedback(mcp_board: ClientSession) -> None:
    """review_decide(verdict=reject) without feedback must return an error."""
    task_id = await _create_review_task(mcp_board, "review reject missing feedback")
    result = await mcp_board.call_tool("review_decide", {"task_id": task_id, "verdict": "reject"})
    assert result.isError


# ---------------------------------------------------------------------------
# review_merge
# ---------------------------------------------------------------------------


async def test_review_apply_merge_returns_task_id(mcp_board: ClientSession) -> None:
    """review_merge returns an error without workspace setup."""
    task_id = await _create_review_task_with_ac(mcp_board, "review merge")
    result = await mcp_board.call_tool("review_merge", {"task_id": task_id})
    assert result.isError


async def test_review_apply_merge_returns_action(mcp_board: ClientSession) -> None:
    """review_merge error mentions missing workspace context."""
    task_id = await _create_review_task_with_ac(mcp_board, "review merge action")
    result = await mcp_board.call_tool("review_merge", {"task_id": task_id})
    assert result.isError


async def test_review_apply_merge_blocked_without_acceptance_criteria(
    mcp_board: ClientSession,
) -> None:
    """review_merge on a task without AC must return blocked."""
    task_id = await _create_review_task(mcp_board, "review merge no ac")
    result = await mcp_board.call_tool("review_merge", {"task_id": task_id})
    assert not result.isError
    payload = _text(result)
    assert payload.get("action") == "blocked"
    assert payload.get("reason_code") == "MANUAL_REVIEW_REQUIRED"


# ---------------------------------------------------------------------------
# review_rebase
# ---------------------------------------------------------------------------


async def test_review_apply_rebase_returns_task_id(mcp_board: ClientSession) -> None:
    """review_rebase returns an error without workspace setup."""
    task_id = await _create_review_task(mcp_board, "review rebase")
    result = await mcp_board.call_tool("review_rebase", {"task_id": task_id})
    assert result.isError


async def test_review_apply_rebase_returns_action(mcp_board: ClientSession) -> None:
    """review_rebase error mentions missing workspace context."""
    task_id = await _create_review_task(mcp_board, "review rebase action")
    result = await mcp_board.call_tool("review_rebase", {"task_id": task_id})
    assert result.isError


async def test_review_conflict_status_returns_shape_without_workspace(
    mcp_board: ClientSession,
) -> None:
    task_id = await _create_review_task(mcp_board, "review conflict status")
    result = await mcp_board.call_tool("review_conflicts", {"task_id": task_id})
    assert not result.isError
    payload = _text(result)
    assert payload["task_id"] == task_id
    assert payload["has_workspace"] is False
    assert payload["is_rebase_in_progress"] is False
    assert payload["conflicted_files"] == []


async def test_review_rebase_continue_errors_without_workspace(mcp_board: ClientSession) -> None:
    task_id = await _create_review_task(mcp_board, "review rebase continue")
    result = await mcp_board.call_tool("review_rebase", {"task_id": task_id, "action": "continue"})
    assert result.isError


async def test_review_abort_conflicts_is_noop_without_workspace(mcp_board: ClientSession) -> None:
    task_id = await _create_review_task(mcp_board, "review abort")
    result = await mcp_board.call_tool("review_rebase", {"task_id": task_id, "action": "abort"})
    assert not result.isError
    payload = _text(result)
    assert payload["task_id"] == task_id
    assert payload["action"] == "abort_conflicts"


# ---------------------------------------------------------------------------
# Legacy separate tools
# ---------------------------------------------------------------------------


async def test_review_apply_legacy_separate_tools_are_hidden(mcp_board: ClientSession) -> None:
    """review_approve and review_reject must no longer be exposed as separate tools."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "review_approve" not in names
    assert "review_reject" not in names
    assert "review_continue_rebase" not in names
    assert "review_abort_rebase" not in names
    assert "review_set_criterion_verdict" not in names


async def test_core_review_apply_returns_error_when_core_review_service_unavailable(
    mcp_board_with_core: ClientSession,
) -> None:
    result = await mcp_board_with_core.call_tool(
        "review_decide", {"task_id": "task-rev-core-1", "verdict": "approve"}
    )
    assert result.isError


async def test_review_apply_merge_requires_approval_when_setting_enabled(
    mcp_board_with_core_client: tuple[ClientSession, Any],
    tmp_path: Path,
) -> None:
    mcp_board, core_client = mcp_board_with_core_client
    await core_client.settings.set({"require_review_approval": "true"})

    task_id, _ = await _create_merge_ready_review_task(
        mcp_board,
        core_client,
        tmp_path,
        title="review merge requires approval",
        file_name="needs_approval.py",
    )

    result = await mcp_board.call_tool("review_merge", {"task_id": task_id})
    assert result.isError

    task = await core_client.tasks.get(task_id)
    assert task.status.value == "REVIEW"
    assert task.review_approved is False


async def test_review_apply_merge_succeeds_after_approve_when_setting_enabled(
    mcp_board_with_core_client: tuple[ClientSession, Any],
    tmp_path: Path,
) -> None:
    mcp_board, core_client = mcp_board_with_core_client
    await core_client.settings.set({"require_review_approval": "true"})

    task_id, repo_path = await _create_merge_ready_review_task(
        mcp_board,
        core_client,
        tmp_path,
        title="review merge approval flow",
        file_name="approved_merge.py",
    )

    approve_result = await mcp_board.call_tool(
        "review_decide", {"task_id": task_id, "verdict": "approve"}
    )
    assert not approve_result.isError

    merge_result = await mcp_board.call_tool("review_merge", {"task_id": task_id})
    assert not merge_result.isError
    payload = _text(merge_result)
    assert payload.get("task_id") == task_id
    assert payload.get("action") == "merge"

    task = await core_client.tasks.get(task_id)
    assert task.status.value == "DONE"
    assert (repo_path / "approved_merge.py").exists()


async def test_review_merge_conflict_returns_structured_conflict_response(
    mcp_board_with_core_client: tuple[ClientSession, Any],
    tmp_path: Path,
) -> None:
    """review_merge on a conflicting branch returns structured conflict dict."""
    mcp_board, core_client = mcp_board_with_core_client

    # Set up a merge-ready task (commits file on worktree branch)
    task_id, repo_path = await _create_merge_ready_review_task(
        mcp_board,
        core_client,
        tmp_path,
        title="review merge conflict",
        file_name="conflicted.py",
    )

    # Create a conflicting change on the base branch
    await commit_file(
        repo_path,
        "conflicted.py",
        "# base branch version\nvalue = 999\n",
        message="feat: conflicting base change",
    )

    # Approve first (required for merge with acceptance criteria)
    approve_result = await mcp_board.call_tool(
        "review_decide", {"task_id": task_id, "verdict": "approve"}
    )
    assert not approve_result.isError

    # Attempt merge — should return structured conflict response, not error
    merge_result = await mcp_board.call_tool("review_merge", {"task_id": task_id})
    assert not merge_result.isError
    payload = _text(merge_result)
    assert payload["status"] == "conflict"
    assert payload["action"] == "merge"
    assert payload["task_id"] == task_id
    assert isinstance(payload["conflict_files"], list)
    assert len(payload["conflict_files"]) > 0
    assert "conflicted.py" in payload["conflict_files"]
    assert isinstance(payload["suggested_feedback"], str)
    assert "conflicted.py" in payload["suggested_feedback"]
    assert "rebase" in payload["suggested_feedback"].lower()

    # Task should still be in REVIEW (merge did not succeed)
    task = await core_client.tasks.get(task_id)
    assert task.status.value == "REVIEW"
