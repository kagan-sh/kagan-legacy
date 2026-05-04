"""Feature tests: Workspaces — docs/internal/features/core.md §5."""

from pathlib import Path

import pytest

from kagan.core import TaskStatus
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.core, pytest.mark.slow]


async def test_provision_creates_git_worktree(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Worktree Task")

    ws_id = await git_board.provision_workspace(task.id)

    assert ws_id is not None
    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None
    assert Path(ws_path).is_dir()


async def test_worktree_branches_from_default_branch(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Branch Task")

    await git_board.provision_workspace(task.id)

    workspaces = await git_board.list_workspaces(task_id=task.id)
    assert len(workspaces) == 1
    ws = workspaces[0]
    assert task.id in ws["branch_name"]


async def test_diff_shows_changes_in_worktree(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Diff Task")
    await git_board.provision_workspace(task.id)

    committed = await git_board.commit_in_workspace(
        task.id, "feature.py", "x = 1\n", message="feat: add feature"
    )
    assert committed

    diff_result = await git_board.get_workspace_diff(task.id)
    assert diff_result["diff"]


async def test_merge_removes_workspace(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Merge Workspace Task")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)
    await git_board.commit_in_workspace(
        task.id, "merge_test.py", "x = 1\n", message="feat: add merge test"
    )
    await git_board.move_task(task.id, TaskStatus.REVIEW)

    await git_board.merge_task(task.id)

    workspaces = await git_board.list_workspaces(task_id=task.id)
    assert len(workspaces) == 0
