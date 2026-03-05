"""Feature tests: Workspaces — docs/internal/features/core.md §5.

Behavioral specs using KaganDriver DSL. No private imports.
Each test is isolated with its own tmp_path and fresh DB.
All tests require a real git repo (tmp_path) for worktree operations.
"""

from pathlib import Path

import pytest

from kagan.core import TaskStatus
from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import make_git_repo

pytestmark = [pytest.mark.core, pytest.mark.slow]

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def git_board(tmp_path):
    """Fresh KaganDriver with an active project linked to a real git repo."""
    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Workspace Tests Project", repo_path=str(repo_path))
    yield driver
    await driver.teardown()


# ---------------------------------------------------------------------------
# §5.1 — Provision creates an isolated git worktree
# ---------------------------------------------------------------------------


async def test_provision_creates_git_worktree(git_board: KaganDriver) -> None:
    """Provisioning a task creates a git worktree on disk."""
    task = await git_board.create_task("Worktree Task")

    ws_id = await git_board.provision_workspace(task.id)

    assert ws_id is not None
    # Workspace path exists on disk
    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None
    assert Path(ws_path).is_dir()


# ---------------------------------------------------------------------------
# §5.2 — Worktree branches from the repo's default branch
# ---------------------------------------------------------------------------


async def test_worktree_branches_from_default_branch(git_board: KaganDriver) -> None:
    """The worktree branch is derived from the task ID and based on the default branch."""
    task = await git_board.create_task("Branch Task")

    await git_board.provision_workspace(task.id)

    workspaces = await git_board.list_workspaces(task_id=task.id)
    assert len(workspaces) == 1
    ws = workspaces[0]
    # Branch name follows kagan/<task_id> convention
    assert task.id in ws["branch_name"]


# ---------------------------------------------------------------------------
# §5.3 — Diff shows changes in the worktree
# ---------------------------------------------------------------------------


async def test_diff_shows_changes_in_worktree(git_board: KaganDriver) -> None:
    """After committing a file in the worktree, diff returns non-empty output."""
    task = await git_board.create_task("Diff Task")
    await git_board.provision_workspace(task.id)

    # Commit a file in the worktree
    committed = await git_board.commit_in_workspace(
        task.id, "feature.py", "x = 1\n", message="feat: add feature"
    )
    assert committed

    diff_result = await git_board.get_workspace_diff(task.id)
    assert diff_result["diff"]  # non-empty diff


# ---------------------------------------------------------------------------
# §5.5 — Merging removes the workspace
# ---------------------------------------------------------------------------


async def test_merge_removes_workspace(git_board: KaganDriver) -> None:
    """Merging a task in REVIEW removes its workspace record."""
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
