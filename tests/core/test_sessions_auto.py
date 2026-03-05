"""Feature tests: AUTO Execution — docs/internal/features/core.md §6.

Behavioral specs using KaganDriver DSL. No private imports.
Each test is isolated with its own tmp_path and fresh DB.
"""

import pytest

from kagan.core import TaskStatus, WorkMode
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
    await driver.create_project("Auto Execution Project", repo_path=str(repo_path))
    yield driver
    await driver.teardown()


# ---------------------------------------------------------------------------
# §6.1 — Run provisions worktree and returns session
# ---------------------------------------------------------------------------


async def test_start_auto_requires_workspace(git_board: KaganDriver) -> None:
    """Starting AUTO on a task without a workspace returns False (cannot run)."""
    task = await git_board.create_task("Unprepared Task", task_type=WorkMode.AUTO)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)

    started = await git_board.start_auto(task.id)

    assert started is False


async def test_start_auto_with_workspace_attempts_launch(git_board: KaganDriver) -> None:
    """Starting AUTO on a task with a provisioned workspace attempts agent launch.

    The agent backend is unavailable in test, so start_auto returns False,
    but the workspace remains intact — no side-effect damage.
    """
    task = await git_board.create_task("Prepared Task", task_type=WorkMode.AUTO)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    started = await git_board.start_auto(task.id)

    # Agent backend "fake" is not a real executable — start returns False
    assert started is False
    # Workspace survives the failed launch
    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None


# ---------------------------------------------------------------------------
# §6.6 — Cancel kills the agent process and moves task to BACKLOG
# ---------------------------------------------------------------------------


async def test_cancel_auto_moves_task_to_backlog(git_board: KaganDriver) -> None:
    """Cancelling an in-progress AUTO task moves it back to BACKLOG."""
    task = await git_board.create_task("Cancellable Auto Task", task_type=WorkMode.AUTO)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    await git_board.stop_auto(task.id)

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.BACKLOG


# ---------------------------------------------------------------------------
# §6 — Execution logs are queryable after a run attempt
# ---------------------------------------------------------------------------


async def test_execution_logs_empty_before_any_run(git_board: KaganDriver) -> None:
    """A freshly created task has no execution log entries."""
    task = await git_board.create_task("Fresh Task", task_type=WorkMode.AUTO)

    logs = await git_board.task_get_logs(task.id)

    assert logs["items"] == []


# ---------------------------------------------------------------------------
# §6 — run() transitions BACKLOG → IN_PROGRESS before spawn
# ---------------------------------------------------------------------------


async def test_run_transitions_backlog_to_in_progress(git_board: KaganDriver) -> None:
    """task.run() moves a BACKLOG task to IN_PROGRESS even when agent spawn fails.

    The status transition is committed to DB before the agent binary is exec'd,
    so even a failed launch leaves the task in IN_PROGRESS (not BACKLOG).
    """
    task = await git_board.create_task("Transition Task", task_type=WorkMode.AUTO)
    await git_board.provision_workspace(task.id)
    assert task.status == TaskStatus.BACKLOG

    # start_auto returns False because the agent binary isn't available,
    # but the BACKLOG → IN_PROGRESS transition has already committed.
    started = await git_board.start_auto(task.id)
    assert started is False

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.IN_PROGRESS


async def test_run_already_in_progress_stays_in_progress(git_board: KaganDriver) -> None:
    """task.run() on an IN_PROGRESS task keeps the status unchanged."""
    task = await git_board.create_task("Already Started", task_type=WorkMode.AUTO)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    started = await git_board.start_auto(task.id)
    assert started is False

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.IN_PROGRESS
