"""Behavioral tests for task domain MCP tools.

Tests exercise tool behavior through MCP protocol (ClientSession.call_tool),
not by importing production internals. All assertions are on observable
protocol-level outcomes: tool visibility, response shape, and error behavior.
"""

import json
from typing import Any

import pytest
from mcp.types import CallToolResult, TextContent

from mcp import ClientSession

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


def _text(result: CallToolResult) -> dict:
    """Extract JSON payload from the first TextContent block of a tool result."""
    block = result.content[0]
    assert isinstance(block, TextContent), f"Expected TextContent, got {type(block)}"
    return json.loads(block.text)


# ---------------------------------------------------------------------------
# Tool visibility
# ---------------------------------------------------------------------------


async def test_task_tools_visible_on_default_server(mcp_board: ClientSession) -> None:
    """Default server must expose all standard task tools."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "task_get" in names
    assert "task_list" in names
    assert "task_create" in names
    assert "task_update" in names
    assert "task_add_note" in names
    assert "task_search" in names
    assert "task_batch_create" in names
    assert "task_events" in names
    assert "tasks_wait" in names
    assert "task_counts" in names


async def test_task_delete_hidden_on_default_server(mcp_board: ClientSession) -> None:
    """task_delete must not be visible on default (non-admin) server."""
    result = await mcp_board.list_tools()
    names = {t.name for t in result.tools}
    assert "task_delete" not in names


# ---------------------------------------------------------------------------
# task_create — returns task dict with id and title
# ---------------------------------------------------------------------------


async def test_task_create_returns_task_with_title(mcp_board: ClientSession) -> None:
    """task_create must return a dict containing the task title."""
    result = await mcp_board.call_tool("task_create", {"title": "My new task"})
    assert not result.isError
    assert _text(result).get("title") == "My new task"


async def test_task_create_returns_task_id(mcp_board: ClientSession) -> None:
    """task_create must return a dict with a non-empty task id."""
    result = await mcp_board.call_tool("task_create", {"title": "Task with ID"})
    assert not result.isError
    payload = _text(result)
    assert "id" in payload
    assert payload["id"]


async def test_task_create_returns_status(mcp_board: ClientSession) -> None:
    """task_create must return a dict with a status field."""
    result = await mcp_board.call_tool("task_create", {"title": "Status task"})
    assert not result.isError
    assert "status" in _text(result)


async def test_task_batch_create_accepts_mixed_field_types(mcp_board: ClientSession) -> None:
    result = await mcp_board.call_tool(
        "task_batch_create",
        {
            "tasks": [
                {
                    "title": "Batch alpha",
                    "description": "alpha",
                    "priority": 2,
                    "execution_mode": "AUTO",
                    "acceptance_criteria": ["criterion one", "criterion two"],
                },
                {
                    "title": "Batch beta",
                    "priority": "1",
                    "execution_mode": "PAIR",
                },
            ]
        },
    )

    assert not result.isError
    payload = _text(result)
    assert payload["errors"] == []
    assert [task["title"] for task in payload["created"]] == ["Batch alpha", "Batch beta"]


# ---------------------------------------------------------------------------
# task_get — returns task dict for a known id
# ---------------------------------------------------------------------------


async def test_task_get_returns_task_dict(mcp_board: ClientSession) -> None:
    """task_get must return a dict with id and title for a created task."""
    create_result = await mcp_board.call_tool("task_create", {"title": "Fetch me"})
    task_id = _text(create_result)["id"]

    get_result = await mcp_board.call_tool("task_get", {"task_id": task_id})
    assert not get_result.isError
    payload = _text(get_result)
    assert payload["id"] == task_id
    assert payload["title"] == "Fetch me"


async def test_task_get_unknown_id_returns_error(mcp_board: ClientSession) -> None:
    """task_get with an unknown task_id must return an error result."""
    result = await mcp_board.call_tool("task_get", {"task_id": "nonexistent-id"})
    assert result.isError


# ---------------------------------------------------------------------------
# task_list — returns list of tasks
# ---------------------------------------------------------------------------


async def test_task_list_returns_list(mcp_board: ClientSession) -> None:
    """task_list must return a dict with a 'tasks' list."""
    result = await mcp_board.call_tool("task_list", {})
    assert not result.isError
    payload = _text(result)
    assert "tasks" in payload
    assert isinstance(payload["tasks"], list)


async def test_task_list_includes_created_task(mcp_board: ClientSession) -> None:
    """task_list must include a task that was just created."""
    await mcp_board.call_tool("task_create", {"title": "Listed task"})
    result = await mcp_board.call_tool("task_list", {})
    payload = _text(result)
    titles = [t["title"] for t in payload["tasks"]]
    assert "Listed task" in titles


# ---------------------------------------------------------------------------
# task_update — updates task fields
# ---------------------------------------------------------------------------


async def test_task_patch_updates_title(mcp_board: ClientSession) -> None:
    """task_update must update the task title and return the updated task."""
    create_result = await mcp_board.call_tool("task_create", {"title": "Original"})
    task_id = _text(create_result)["id"]

    patch_result = await mcp_board.call_tool(
        "task_update",
        {"task_id": task_id, "title": "Updated"},
    )
    assert not patch_result.isError
    assert _text(patch_result)["title"] == "Updated"


# ---------------------------------------------------------------------------
# task_add_note — adds a note to a task
# ---------------------------------------------------------------------------


async def test_task_annotate_returns_success(mcp_board: ClientSession) -> None:
    """task_add_note must return a success response with the task_id."""
    create_result = await mcp_board.call_tool("task_create", {"title": "Annotate me"})
    task_id = _text(create_result)["id"]

    annotate_result = await mcp_board.call_tool(
        "task_add_note", {"task_id": task_id, "note": "This is a note"}
    )
    assert not annotate_result.isError
    assert _text(annotate_result).get("task_id") == task_id


# ---------------------------------------------------------------------------
# task_search — returns matching tasks
# ---------------------------------------------------------------------------


async def test_task_search_returns_matching_tasks(mcp_board: ClientSession) -> None:
    """task_search must return tasks whose title matches the query."""
    await mcp_board.call_tool("task_create", {"title": "Searchable unique task xyz"})
    result = await mcp_board.call_tool("task_search", {"query": "unique task xyz"})
    assert not result.isError
    payload = _text(result)
    assert "tasks" in payload
    titles = [t["title"] for t in payload["tasks"]]
    assert any("unique task xyz" in t for t in titles)


# ---------------------------------------------------------------------------
# task_events — returns logs dict
# ---------------------------------------------------------------------------


async def test_task_logs_returns_logs_dict(mcp_board: ClientSession) -> None:
    """task_events must return a dict with a 'logs' key for a known task."""
    create_result = await mcp_board.call_tool("task_create", {"title": "Log task"})
    task_id = _text(create_result)["id"]

    logs_result = await mcp_board.call_tool("task_events", {"task_id": task_id})
    assert not logs_result.isError
    assert "logs" in _text(logs_result)


async def test_task_logs_default_hides_raw_payload_and_returns_preview(
    mcp_board_with_core_client: tuple[ClientSession, Any],
) -> None:
    mcp_session, core_client = mcp_board_with_core_client
    create_result = await mcp_session.call_tool("task_create", {"title": "Preview log task"})
    task_id = _text(create_result)["id"]

    await core_client.tasks.events.emit(
        task_id,
        "OUTPUT_CHUNK",
        {"message": "hello-world", "attempt": 1},
    )

    result = await mcp_session.call_tool("task_events", {"task_id": task_id, "limit": 50})
    assert not result.isError
    payload = _text(result)
    assert payload["task_id"] == task_id
    assert "returned" in payload
    assert payload["returned"] >= 1

    stream_entry = next(
        (item for item in payload["logs"] if item["event_type"] == "OUTPUT_CHUNK"), None
    )
    assert stream_entry is not None
    assert "payload" not in stream_entry
    assert stream_entry["payload_size_bytes"] > 0
    assert "payload_preview" in stream_entry


async def test_task_logs_include_payload_returns_small_payload(
    mcp_board_with_core_client: tuple[ClientSession, Any],
) -> None:
    mcp_session, core_client = mcp_board_with_core_client
    create_result = await mcp_session.call_tool(
        "task_create", {"title": "Include payload log task"}
    )
    task_id = _text(create_result)["id"]

    await core_client.tasks.events.emit(
        task_id,
        "OUTPUT_CHUNK",
        {"kind": "small", "ok": True},
    )

    result = await mcp_session.call_tool(
        "task_events", {"task_id": task_id, "limit": 50, "include_payload": True}
    )
    assert not result.isError
    payload = _text(result)

    stream_entry = next(
        (item for item in payload["logs"] if item["event_type"] == "OUTPUT_CHUNK"), None
    )
    assert stream_entry is not None
    assert stream_entry["payload_truncated"] is False
    assert stream_entry["payload"] == {"kind": "small", "ok": True}


async def test_task_logs_truncates_large_payload(
    mcp_board_with_core_client: tuple[ClientSession, Any],
) -> None:
    mcp_session, core_client = mcp_board_with_core_client
    create_result = await mcp_session.call_tool("task_create", {"title": "Large payload log task"})
    task_id = _text(create_result)["id"]

    large_payload = {"blob": "x" * 50000}
    await core_client.tasks.events.emit(task_id, "OUTPUT_CHUNK", large_payload)

    result = await mcp_session.call_tool(
        "task_events",
        {
            "task_id": task_id,
            "limit": 50,
            "include_payload": True,
            "max_payload_bytes": 512,
        },
    )
    assert not result.isError
    payload = _text(result)

    stream_entry = next(
        (item for item in payload["logs"] if item["event_type"] == "OUTPUT_CHUNK"), None
    )
    assert stream_entry is not None
    assert stream_entry["payload_truncated"] is True
    assert stream_entry["payload_size_bytes"] > 512
    assert len(stream_entry["payload_preview"].encode("utf-8")) <= 512
    assert stream_entry["payload"]["truncated"] is True


# ---------------------------------------------------------------------------
# task_counts — returns per-status counts
# ---------------------------------------------------------------------------


async def test_task_counts_returns_counts_dict(mcp_board: ClientSession) -> None:
    """task_counts must return a dict with status count fields."""
    result = await mcp_board.call_tool("task_counts", {})
    assert not result.isError
    assert isinstance(_text(result), dict)


# ---------------------------------------------------------------------------
# Session binding — tasks created on a session-bound server carry session context
# ---------------------------------------------------------------------------


async def test_session_bound_task_create_returns_session_id(
    mcp_board_with_session: ClientSession,
) -> None:
    """task_create on a session-bound server must return a task with session_id set."""
    result = await mcp_board_with_session.call_tool("task_create", {"title": "Session task"})
    assert not result.isError
    payload = _text(result)
    assert payload.get("session_id") == "test-session"


async def test_session_bound_task_list_scopes_to_session(
    mcp_board_with_session: ClientSession,
) -> None:
    """task_list on a session-bound server must return only tasks for that session."""
    await mcp_board_with_session.call_tool("task_create", {"title": "Session scoped task"})
    result = await mcp_board_with_session.call_tool("task_list", {})
    assert not result.isError
    payload = _text(result)
    assert "tasks" in payload
    # All returned tasks must carry the session_id
    for task in payload["tasks"]:
        assert task.get("session_id") == "test-session"


async def test_session_bound_task_get_returns_session_id(
    mcp_board_with_session: ClientSession,
) -> None:
    """task_get on a session-bound server must return a task with session_id set."""
    create_result = await mcp_board_with_session.call_tool(
        "task_create", {"title": "Get session task"}
    )
    task_id = _text(create_result)["id"]
    get_result = await mcp_board_with_session.call_tool("task_get", {"task_id": task_id})
    assert not get_result.isError
    assert _text(get_result).get("session_id") == "test-session"


# ---------------------------------------------------------------------------
# tasks_wait — long-poll for status change
# ---------------------------------------------------------------------------


async def test_tasks_wait_returns_status_for_known_task(mcp_board: ClientSession) -> None:
    """tasks_wait must return task status rows for a known task."""
    create_result = await mcp_board.call_tool("task_create", {"title": "Wait task"})
    task_id = _text(create_result)["id"]

    wait_result = await mcp_board.call_tool(
        "tasks_wait", {"task_ids": [task_id], "timeout_seconds": 0.01}
    )
    assert not wait_result.isError
    payload = _text(wait_result)
    assert payload["task_ids"] == [task_id]
    assert payload["tasks"][0]["task_id"] == task_id
    assert "status" in payload["tasks"][0]


async def test_tasks_wait_unknown_task_returns_error(mcp_board: ClientSession) -> None:
    """tasks_wait with an unknown task_id must return an error result."""
    result = await mcp_board.call_tool("tasks_wait", {"task_ids": ["nonexistent-wait-id"]})
    assert result.isError


async def test_tasks_wait_returns_timed_out_flag(mcp_board: ClientSession) -> None:
    """tasks_wait must return a timed_out field in the response."""
    create_result = await mcp_board.call_tool("task_create", {"title": "Timed out task"})
    task_id = _text(create_result)["id"]

    wait_result = await mcp_board.call_tool(
        "tasks_wait", {"task_ids": [task_id], "timeout_seconds": 0.01}
    )
    assert not wait_result.isError
    payload = _text(wait_result)
    assert "timed_out" in payload


async def test_tasks_wait_accepts_single_status_string(mcp_board: ClientSession) -> None:
    create_result = await mcp_board.call_tool("task_create", {"title": "String wait status task"})
    task_id = _text(create_result)["id"]

    move_result = await mcp_board.call_tool(
        "task_update", {"task_id": task_id, "status": "IN_PROGRESS"}
    )
    assert not move_result.isError

    wait_result = await mcp_board.call_tool(
        "tasks_wait",
        {
            "task_ids": [task_id],
            "wait_for_status": "IN_PROGRESS",
            "timeout_seconds": 0.01,
        },
    )
    assert not wait_result.isError
    payload = _text(wait_result)
    assert payload["tasks"][0]["status"] == "IN_PROGRESS"


async def test_tasks_wait_rejects_unknown_status_with_clear_message(
    mcp_board: ClientSession,
) -> None:
    create_result = await mcp_board.call_tool("task_create", {"title": "Bad wait status task"})
    task_id = _text(create_result)["id"]

    wait_result = await mcp_board.call_tool(
        "tasks_wait",
        {
            "task_ids": [task_id],
            "wait_for_status": ["FAILED"],
            "timeout_seconds": 0.01,
        },
    )
    assert wait_result.isError
    text = "\n".join(str(getattr(block, "text", "")) for block in wait_result.content)
    assert "wait_for_status" in text
    assert "Task statuses" in text or "Allowed values" in text


async def test_tasks_wait_resolve_when_any_returns_after_first_match(
    mcp_board: ClientSession,
) -> None:
    first_result = await mcp_board.call_tool("task_create", {"title": "Any wait first"})
    second_result = await mcp_board.call_tool("task_create", {"title": "Any wait second"})
    first_task_id = _text(first_result)["id"]
    second_task_id = _text(second_result)["id"]

    move_result = await mcp_board.call_tool(
        "task_update", {"task_id": first_task_id, "status": "IN_PROGRESS"}
    )
    assert not move_result.isError

    wait_result = await mcp_board.call_tool(
        "tasks_wait",
        {
            "task_ids": [first_task_id, second_task_id],
            "wait_for_status": ["IN_PROGRESS"],
            "resolve_when_any": True,
            "timeout_seconds": 0.01,
        },
    )
    assert not wait_result.isError
    payload = _text(wait_result)
    assert payload["resolve_when_any"] is True
    assert first_task_id in payload["resolved_task_ids"]


# ---------------------------------------------------------------------------
# task_counts — per-status counts with actual tasks
# ---------------------------------------------------------------------------


async def test_task_counts_reflects_created_tasks(mcp_board: ClientSession) -> None:
    """task_counts must reflect tasks that were just created."""
    await mcp_board.call_tool("task_create", {"title": "Count task alpha"})
    await mcp_board.call_tool("task_create", {"title": "Count task beta"})

    result = await mcp_board.call_tool("task_counts", {})
    assert not result.isError
    payload = _text(result)
    # At least 2 tasks in BACKLOG
    assert payload.get("BACKLOG", 0) >= 2


# ---------------------------------------------------------------------------
# task_update — status transition
# ---------------------------------------------------------------------------


async def test_task_patch_updates_status(mcp_board: ClientSession) -> None:
    """task_update must update the task status when status field is provided."""
    create_result = await mcp_board.call_tool("task_create", {"title": "Status transition task"})
    task_id = _text(create_result)["id"]

    patch_result = await mcp_board.call_tool(
        "task_update", {"task_id": task_id, "status": "IN_PROGRESS"}
    )
    assert not patch_result.isError
    assert _text(patch_result)["status"] == "IN_PROGRESS"


async def test_task_patch_unknown_task_returns_error(mcp_board: ClientSession) -> None:
    """task_update with an unknown task_id must return an error result."""
    result = await mcp_board.call_tool(
        "task_update", {"task_id": "nonexistent-patch-id", "title": "New title"}
    )
    assert result.isError


async def test_task_patch_updates_description(mcp_board: ClientSession) -> None:
    """task_update must update the task description when description field is provided."""
    create_result = await mcp_board.call_tool("task_create", {"title": "Desc task"})
    task_id = _text(create_result)["id"]

    patch_result = await mcp_board.call_tool(
        "task_update", {"task_id": task_id, "description": "Updated description"}
    )
    assert not patch_result.isError
    assert _text(patch_result)["description"] == "Updated description"


async def test_task_patch_updates_execution_metadata(mcp_board: ClientSession) -> None:
    create_result = await mcp_board.call_tool("task_create", {"title": "Execution metadata task"})
    task_id = _text(create_result)["id"]

    patch_result = await mcp_board.call_tool(
        "task_update",
        {
            "task_id": task_id,
            "priority": "HIGH",
            "execution_mode": "AUTO",
            "base_branch": "main",
            "acceptance_criteria": ["Criterion A", "Criterion B"],
            "agent_backend": "kimi-cli",
        },
    )
    assert not patch_result.isError
    payload = _text(patch_result)
    assert payload["priority"] == "HIGH"
    assert payload["execution_mode"] == "AUTO"
    assert payload["base_branch"] == "main"
    assert payload["acceptance_criteria"] == ["Criterion A", "Criterion B"]
    assert payload["agent_backend"] == "kimi-cli"


# ---------------------------------------------------------------------------
# task_add_note — error path
# ---------------------------------------------------------------------------


async def test_task_annotate_unknown_task_returns_error(mcp_board: ClientSession) -> None:
    """task_add_note with an unknown task_id must return an error result."""
    result = await mcp_board.call_tool(
        "task_add_note", {"task_id": "nonexistent-annotate-id", "note": "note"}
    )
    assert result.isError


# ---------------------------------------------------------------------------
# task_events — error path
# ---------------------------------------------------------------------------


async def test_task_logs_unknown_task_returns_error(mcp_board: ClientSession) -> None:
    """task_events with an unknown task_id must return an empty logs payload."""
    result = await mcp_board.call_tool("task_events", {"task_id": "nonexistent-logs-id"})
    assert not result.isError
    payload = _text(result)
    assert payload.get("task_id") == "nonexistent-logs-id"
    assert payload.get("logs") == []


# ---------------------------------------------------------------------------
# task_list — status filter
# ---------------------------------------------------------------------------


async def test_task_list_filters_by_status(mcp_board: ClientSession) -> None:
    """task_list with status filter must return only tasks with that status."""
    await mcp_board.call_tool("task_create", {"title": "Backlog task for filter"})

    result = await mcp_board.call_tool("task_list", {"status": "IN_PROGRESS"})
    assert not result.isError
    payload = _text(result)
    for task in payload["tasks"]:
        assert task["status"] == "IN_PROGRESS"


# ---------------------------------------------------------------------------
# Core-client path tests — exercise client is not None branches
# ---------------------------------------------------------------------------


async def test_core_task_create_returns_task_with_title(
    mcp_board_with_core: ClientSession,
) -> None:
    """task_create via core client must return a task with the given title."""
    result = await mcp_board_with_core.call_tool("task_create", {"title": "Core task alpha"})
    assert not result.isError
    assert _text(result).get("title") == "Core task alpha"


async def test_core_task_create_returns_task_id(mcp_board_with_core: ClientSession) -> None:
    """task_create via core client must return a non-empty task id."""
    result = await mcp_board_with_core.call_tool("task_create", {"title": "Core id task"})
    assert not result.isError
    payload = _text(result)
    assert payload.get("id")


async def test_core_task_get_returns_created_task(mcp_board_with_core: ClientSession) -> None:
    """task_get via core client must return the task that was created."""
    create_result = await mcp_board_with_core.call_tool("task_create", {"title": "Core get task"})
    task_id = _text(create_result)["id"]

    get_result = await mcp_board_with_core.call_tool("task_get", {"task_id": task_id})
    assert not get_result.isError
    payload = _text(get_result)
    assert payload["id"] == task_id
    assert payload["title"] == "Core get task"


async def test_core_task_get_unknown_id_returns_error(mcp_board_with_core: ClientSession) -> None:
    """task_get via core client with unknown id must return an error."""
    result = await mcp_board_with_core.call_tool("task_get", {"task_id": "nonexistent-core-id"})
    assert result.isError


async def test_core_task_list_includes_created_task(mcp_board_with_core: ClientSession) -> None:
    """task_list via core client must include a task that was just created."""
    await mcp_board_with_core.call_tool("task_create", {"title": "Core listed task"})
    result = await mcp_board_with_core.call_tool("task_list", {})
    assert not result.isError
    payload = _text(result)
    titles = [t["title"] for t in payload["tasks"]]
    assert "Core listed task" in titles


async def test_core_task_search_returns_matching_tasks(mcp_board_with_core: ClientSession) -> None:
    """task_search via core client must return tasks matching the query."""
    await mcp_board_with_core.call_tool("task_create", {"title": "Core searchable unique xyz"})
    result = await mcp_board_with_core.call_tool("task_search", {"query": "searchable unique xyz"})
    assert not result.isError
    payload = _text(result)
    assert "tasks" in payload


async def test_core_task_annotate_returns_success(mcp_board_with_core: ClientSession) -> None:
    """task_add_note via core client must return success."""
    create_result = await mcp_board_with_core.call_tool(
        "task_create", {"title": "Core annotate task"}
    )
    task_id = _text(create_result)["id"]

    result = await mcp_board_with_core.call_tool(
        "task_add_note", {"task_id": task_id, "note": "Core note"}
    )
    assert not result.isError
    assert _text(result).get("task_id") == task_id


async def test_core_task_logs_returns_logs(mcp_board_with_core: ClientSession) -> None:
    """task_events via core client must return a logs structure."""
    create_result = await mcp_board_with_core.call_tool("task_create", {"title": "Core logs task"})
    task_id = _text(create_result)["id"]

    result = await mcp_board_with_core.call_tool("task_events", {"task_id": task_id})
    assert not result.isError


async def test_core_task_counts_returns_dict(mcp_board_with_core: ClientSession) -> None:
    """task_counts via core client must return a dict."""
    await mcp_board_with_core.call_tool("task_create", {"title": "Core count task"})
    result = await mcp_board_with_core.call_tool("task_counts", {})
    assert not result.isError
    assert isinstance(_text(result), dict)


async def test_core_task_patch_updates_title(mcp_board_with_core: ClientSession) -> None:
    """task_update via core client must update the task title."""
    create_result = await mcp_board_with_core.call_tool("task_create", {"title": "Core patch task"})
    task_id = _text(create_result)["id"]

    patch_result = await mcp_board_with_core.call_tool(
        "task_update", {"task_id": task_id, "title": "Core patched title"}
    )
    assert not patch_result.isError
    assert _text(patch_result)["title"] == "Core patched title"


async def test_core_tasks_wait_returns_status(mcp_board_with_core: ClientSession) -> None:
    """tasks_wait via core client must return a response payload."""
    create_result = await mcp_board_with_core.call_tool("task_create", {"title": "Core wait task"})
    task_id = _text(create_result)["id"]

    wait_result = await mcp_board_with_core.call_tool(
        "tasks_wait", {"task_ids": [task_id], "timeout_seconds": 0.1}
    )
    assert wait_result is not None


async def test_core_admin_task_delete_removes_task(
    mcp_board_admin_with_core: ClientSession,
) -> None:
    """task_delete via core admin client must delete the task."""
    create_result = await mcp_board_admin_with_core.call_tool(
        "task_create", {"title": "Core delete task"}
    )
    task_id = _text(create_result)["id"]

    delete_result = await mcp_board_admin_with_core.call_tool("task_delete", {"task_id": task_id})
    assert not delete_result.isError
    payload = _text(delete_result)
    assert payload.get("deleted") is True
    assert payload.get("task_id") == task_id
