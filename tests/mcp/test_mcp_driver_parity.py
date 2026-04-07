"""Parity tests: McpDriver operations must produce consistent, equivalent results.

Tests verify that the MCP protocol interface (McpDriver) produces consistent
observable outcomes: create → get → list operations must agree on task fields.

Each test asserts DTO field equivalence across operations — not type membership.
"""

import pytest

from tests.helpers.mcp_driver import McpDriver

pytestmark = [pytest.mark.asyncio, pytest.mark.mcp]


# ---------------------------------------------------------------------------
# create_task → get_task parity — created and fetched task must agree
# ---------------------------------------------------------------------------


async def test_create_then_get_title_matches(mcp_driver: McpDriver) -> None:
    """task_get must return the same title as the task returned by task_create."""
    created = await mcp_driver.create_task("Parity title alpha")
    fetched = await mcp_driver.get_task(created.id)

    assert fetched.title == created.title


async def test_create_then_get_id_matches(mcp_driver: McpDriver) -> None:
    """task_get must return the same id as the task returned by task_create."""
    created = await mcp_driver.create_task("Parity id beta")
    fetched = await mcp_driver.get_task(created.id)

    assert fetched.id == created.id


async def test_create_then_get_status_matches(mcp_driver: McpDriver) -> None:
    """task_get must return the same status value as the task returned by task_create."""
    created = await mcp_driver.create_task("Parity status gamma")
    fetched = await mcp_driver.get_task(created.id)

    assert fetched.status.value == created.status.value


# ---------------------------------------------------------------------------
# create_task → list_tasks parity — created task must appear in list
# ---------------------------------------------------------------------------


async def test_create_then_list_includes_task_by_id(mcp_driver: McpDriver) -> None:
    """task_list must include the id of a task returned by task_create."""
    created = await mcp_driver.create_task("Listed parity delta")
    tasks = await mcp_driver.list_tasks()

    ids = [t.id for t in tasks]
    assert created.id in ids


async def test_create_then_list_includes_task_by_title(mcp_driver: McpDriver) -> None:
    """task_list must include the title of a task returned by task_create."""
    created = await mcp_driver.create_task("Unique listed parity epsilon xyz")
    tasks = await mcp_driver.list_tasks()

    titles = [t.title for t in tasks]
    assert created.title in titles


async def test_create_then_list_count_increases(mcp_driver: McpDriver) -> None:
    """task_list count must increase by 1 after task_create."""
    before = len(await mcp_driver.list_tasks())
    await mcp_driver.create_task("Count parity zeta")
    after = len(await mcp_driver.list_tasks())

    assert after == before + 1


# ---------------------------------------------------------------------------
# create_task initial state — status and id invariants
# ---------------------------------------------------------------------------


async def test_create_task_initial_status_is_backlog(mcp_driver: McpDriver) -> None:
    """task_create must return a task with BACKLOG status."""
    task = await mcp_driver.create_task("Initial status task")

    assert task.status.value.upper() == "BACKLOG"


async def test_create_task_id_is_non_empty(mcp_driver: McpDriver) -> None:
    """task_create must return a task with a non-empty id."""
    task = await mcp_driver.create_task("Non-empty id task")

    assert task.id
    assert len(task.id) > 0


async def test_create_task_title_is_preserved(mcp_driver: McpDriver) -> None:
    """task_create must return a task whose title matches the input."""
    title = "Preserved title eta"
    task = await mcp_driver.create_task(title)

    assert task.title == title
