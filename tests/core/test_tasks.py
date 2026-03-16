"""Feature tests: Task CRUD — docs/internal/features/core.md §3."""

import pytest

from kagan.core import Priority, TaskStatus, WorkMode
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.core, pytest.mark.smoke]




async def test_create_task_appears_in_backlog_with_id(board: KaganDriver) -> None:
    task_a = await board.create_task("First Task")
    task_b = await board.create_task("Second Task")

    assert task_a.status == TaskStatus.BACKLOG
    assert task_b.status == TaskStatus.BACKLOG
    assert task_a.id
    assert task_b.id
    assert task_a.id != task_b.id





async def test_create_task_with_optional_fields(board: KaganDriver) -> None:
    task = await board.create_task(
        "Feature X",
        description="Implement feature X end-to-end",
        priority=Priority.HIGH,
        task_type=WorkMode.PAIR,
        base_branch="main",
        agent_backend="claude-code",
        launcher="vscode",
        acceptance_criteria=["AC1: works", "AC2: tested"],
    )

    fetched = await board.get_task(task.id)
    assert fetched.description == "Implement feature X end-to-end"
    assert fetched.priority == Priority.HIGH
    assert fetched.execution_mode == WorkMode.PAIR
    assert fetched.base_branch == "main"
    assert fetched.agent_backend == "claude-code"
    assert fetched.launcher == "vscode"
    assert fetched.acceptance_criteria == ["AC1: works", "AC2: tested"]





async def test_update_task_mutable_fields(board: KaganDriver) -> None:
    task = await board.create_task("Original Title", description="Original desc")

    updated = await board.update_task(
        task.id,
        title="Updated Title",
        description="Updated desc",
        priority=Priority.HIGH,
        launcher="nvim",
    )

    assert updated.title == "Updated Title"
    assert updated.description == "Updated desc"
    assert updated.priority == Priority.HIGH
    assert updated.launcher == "nvim"

    fetched = await board.get_task(task.id)
    assert fetched.title == "Updated Title"
    assert fetched.priority == Priority.HIGH
    assert fetched.launcher == "nvim"





async def test_delete_task_removes_it_from_list(board: KaganDriver) -> None:
    task = await board.create_task("Task to Delete")
    tasks_before = await board.list_tasks()
    assert any(t.id == task.id for t in tasks_before)

    deleted = await board.delete_task(task.id)
    assert deleted is True

    tasks_after = await board.list_tasks()
    assert not any(t.id == task.id for t in tasks_after)





async def test_list_tasks_filtered_by_status(board: KaganDriver) -> None:
    backlog_task = await board.create_task("Backlog Task")
    in_progress_task = await board.create_task("In Progress Task")
    await board.move_task(in_progress_task.id, TaskStatus.IN_PROGRESS)

    backlog_tasks = await board.list_tasks(status=TaskStatus.BACKLOG)
    in_progress_tasks = await board.list_tasks(status=TaskStatus.IN_PROGRESS)

    backlog_ids = {t.id for t in backlog_tasks}
    in_progress_ids = {t.id for t in in_progress_tasks}

    assert backlog_task.id in backlog_ids
    assert in_progress_task.id not in backlog_ids
    assert in_progress_task.id in in_progress_ids
    assert backlog_task.id not in in_progress_ids





async def test_search_tasks_by_title_and_description(board: KaganDriver) -> None:
    await board.create_task("Implement OAuth login", description="Add OAuth2 support")
    await board.create_task("Fix database migration", description="Schema update needed")
    await board.create_task("Write unit tests", description="Cover OAuth flows")

    oauth_results = await board.search_tasks("OAuth")
    oauth_titles = {t.title for t in oauth_results}
    assert "Implement OAuth login" in oauth_titles

    schema_results = await board.search_tasks("Schema")
    schema_titles = {t.title for t in schema_results}
    assert "Fix database migration" in schema_titles

    no_results = await board.search_tasks("xyzzy_nonexistent_keyword")
    assert len(no_results) == 0





async def test_add_and_read_notes_chronologically(board: KaganDriver) -> None:
    task = await board.create_task("Annotated Task")

    await board.annotate(task.id, "First note")
    await board.annotate(task.id, "Second note")

    notes = await board.list_notes(task.id)
    assert notes == ["First note", "Second note"]
