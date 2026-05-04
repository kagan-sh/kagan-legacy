"""Feature tests: Reviews — docs/internal/features/core.md §8."""

from pathlib import Path

import pytest

from kagan.core import PreflightError, TaskStatus
from kagan.core.errors import MergeConflictError
from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import commit_file

pytestmark = [pytest.mark.core, pytest.mark.slow]


async def test_merge_moves_task_to_done_and_removes_workspace(
    git_board: KaganDriver, tmp_path
) -> None:
    task = await git_board.create_task("Mergeable Task")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)
    committed = await git_board.commit_in_workspace(
        task.id,
        "calculator.py",
        "def add(a: int, b: int) -> int:\n    return a + b\n",
        message="feat: add calculator module",
    )
    assert committed is True
    await git_board.move_task(task.id, TaskStatus.REVIEW)

    result = await git_board.merge_task(task.id)

    assert result["status"] == TaskStatus.DONE

    workspaces = await git_board.list_workspaces(task_id=task.id)
    assert len(workspaces) == 0

    logs = await git_board.task_get_logs(task.id, limit=20)
    items = logs.get("items", [])
    assert isinstance(items, list)
    event_types = {str(item.get("event_type")) for item in items if isinstance(item, dict)}
    assert "merge_completed" in event_types
    assert "task_status_changed" in event_types

    merged_file = tmp_path / "repo" / "calculator.py"
    assert merged_file.exists()
    assert "def add" in merged_file.read_text(encoding="utf-8")


async def test_merge_fails_when_workspace_has_uncommitted_or_untracked_changes(
    git_board: KaganDriver,
) -> None:
    task = await git_board.create_task("Merge Blocked Pending Changes")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)
    committed = await git_board.commit_in_workspace(
        task.id,
        "ready.py",
        "value = 1\n",
        message="feat: add ready module",
    )
    assert committed is True

    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None
    workspace_path = Path(ws_path)
    (workspace_path / "leftover.py").write_text("value = 2\n", encoding="utf-8")

    await git_board.move_task(task.id, TaskStatus.REVIEW)

    with pytest.raises(PreflightError):
        await git_board.merge_task(task.id)

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.REVIEW


async def test_merge_fails_when_task_branch_has_no_commits(
    git_board: KaganDriver,
) -> None:
    task = await git_board.create_task("Merge Blocked Empty Branch")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)
    await git_board.move_task(task.id, TaskStatus.REVIEW)

    with pytest.raises(PreflightError):
        await git_board.merge_task(task.id)

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.REVIEW

    workspaces = await git_board.list_workspaces(task_id=task.id)
    assert len(workspaces) == 1


async def test_merge_requires_approval_when_setting_enabled(git_board: KaganDriver) -> None:
    await git_board.settings_update({"require_review_approval": "true"})

    task = await git_board.create_task("Merge Requires Approval")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)
    committed = await git_board.commit_in_workspace(
        task.id,
        "approved.py",
        "flag = True\n",
        message="feat: add approved module",
    )
    assert committed is True
    await git_board.move_task(task.id, TaskStatus.REVIEW)

    with pytest.raises(PreflightError):
        await git_board.merge_task(task.id)

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.REVIEW


async def test_merge_conflict_emits_event_with_suggested_feedback(
    git_board: KaganDriver, tmp_path
) -> None:
    """Merge conflict emits MERGE_FAILED event containing suggested_feedback."""
    task = await git_board.create_task("Merge Conflict Feedback")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)
    committed = await git_board.commit_in_workspace(
        task.id,
        "shared.py",
        "value = 1\n",
        message="feat: add shared module",
    )
    assert committed is True

    repo_path = tmp_path / "repo"
    await commit_file(
        repo_path,
        "shared.py",
        "# base branch version\nvalue = 999\n",
        message="feat: conflicting base change",
    )

    await git_board.move_task(task.id, TaskStatus.REVIEW)

    with pytest.raises(MergeConflictError):
        await git_board.merge_task(task.id)

    logs = await git_board.task_get_logs(task.id, limit=20)
    items = logs.get("items", [])
    assert isinstance(items, list)

    merge_failed_events = [
        item
        for item in items
        if isinstance(item, dict) and str(item.get("event_type")) == "merge_failed"
    ]
    assert len(merge_failed_events) >= 1

    payload = merge_failed_events[-1].get("payload", {})
    assert isinstance(payload, dict)
    assert "conflict_files" in payload
    assert "suggested_feedback" in payload
    assert "shared.py" in str(payload["conflict_files"])
    assert "rebase" in payload["suggested_feedback"].lower()
