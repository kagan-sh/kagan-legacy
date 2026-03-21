"""Feature tests: managed runs — docs/internal/features/core.md §6."""

import pytest

from kagan.core import TaskStatus
from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import make_git_repo

pytestmark = [pytest.mark.core, pytest.mark.slow]


@pytest.fixture
async def git_board(tmp_path):
    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Detached Execution Project", repo_path=str(repo_path))
    yield driver
    await driver.teardown()


async def test_start_detached_provisions_workspace_before_launch(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Unprepared Task")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)

    session = await git_board.run_task(task.id)

    assert session is None
    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None


async def test_start_detached_with_workspace_attempts_launch(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Prepared Task")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    session = await git_board.run_task(task.id)

    assert session is None
    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None


async def test_cancel_detached_moves_task_to_backlog(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Cancellable Detached Task")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    await git_board.cancel_task(task.id)

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.BACKLOG


async def test_execution_logs_empty_before_any_run(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Fresh Task")

    logs = await git_board.task_get_logs(task.id)

    assert logs["items"] == []


async def test_run_transitions_backlog_to_in_progress(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Transition Task")
    await git_board.provision_workspace(task.id)
    assert task.status == TaskStatus.BACKLOG

    session = await git_board.run_task(task.id)
    assert session is None

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.IN_PROGRESS


async def test_run_already_in_progress_stays_in_progress(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Already Started")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    session = await git_board.run_task(task.id)
    assert session is None

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.IN_PROGRESS
