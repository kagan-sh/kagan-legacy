"""Feature tests: AUTO Execution — docs/internal/features/core.md §6."""

import pytest

from kagan.core import TaskStatus, WorkMode
from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import make_git_repo

pytestmark = [pytest.mark.core, pytest.mark.slow]


@pytest.fixture
async def git_board(tmp_path):
    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Auto Execution Project", repo_path=str(repo_path))
    yield driver
    await driver.teardown()


async def test_start_auto_provisions_workspace_before_launch(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Unprepared Task", task_type=WorkMode.AUTO)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)

    started = await git_board.start_auto(task.id)

    assert started is False
    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None


async def test_start_auto_with_workspace_attempts_launch(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Prepared Task", task_type=WorkMode.AUTO)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    started = await git_board.start_auto(task.id)

    assert started is False
    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None


async def test_cancel_auto_moves_task_to_backlog(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Cancellable Auto Task", task_type=WorkMode.AUTO)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    await git_board.stop_auto(task.id)

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.BACKLOG


async def test_execution_logs_empty_before_any_run(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Fresh Task", task_type=WorkMode.AUTO)

    logs = await git_board.task_get_logs(task.id)

    assert logs["items"] == []


async def test_run_transitions_backlog_to_in_progress(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Transition Task", task_type=WorkMode.AUTO)
    await git_board.provision_workspace(task.id)
    assert task.status == TaskStatus.BACKLOG

    started = await git_board.start_auto(task.id)
    assert started is False

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.IN_PROGRESS


async def test_run_already_in_progress_stays_in_progress(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Already Started", task_type=WorkMode.AUTO)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    started = await git_board.start_auto(task.id)
    assert started is False

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.IN_PROGRESS
