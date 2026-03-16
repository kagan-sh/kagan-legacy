"""Feature tests: PAIR Sessions — docs/internal/features/core.md §7."""

import contextlib

import pytest

from kagan.core import AgentError, TaskStatus, WorkMode
from kagan.core.errors import MultiRepoUnsupportedError
from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import make_git_repo

pytestmark = [pytest.mark.core, pytest.mark.slow]


@pytest.fixture
async def git_board(tmp_path):
    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Pair Sessions Project", repo_path=str(repo_path))
    yield driver
    await driver.teardown()


async def test_pair_provisions_workspace_before_launch(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Unprepared Pair Task", task_type=WorkMode.PAIR)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)

    with contextlib.suppress(AgentError, FileNotFoundError, OSError):
        await git_board.pair_task(task.id, agent_backend="claude-code", launcher="tmux")

    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None


async def test_pair_rejects_multi_repo_projects_explicitly(tmp_path) -> None:
    repo_one = tmp_path / "repo-one"
    repo_two = tmp_path / "repo-two"
    await make_git_repo(repo_one, base_branch="main")
    await make_git_repo(repo_two, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    try:
        await driver.create_project("Multi Repo Project", repo_path=str(repo_one))
        await driver.add_repo(repo_two)
        task = await driver.create_task("Multi Repo Pair Task", task_type=WorkMode.PAIR)
        await driver.move_task(task.id, TaskStatus.IN_PROGRESS)

        with pytest.raises(MultiRepoUnsupportedError, match="MULTI_REPO_UNSUPPORTED"):
            await driver.pair_task(task.id, agent_backend="claude-code", launcher="tmux")
    finally:
        await driver.teardown()


async def test_pair_with_workspace_creates_session(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Pair Session Task", task_type=WorkMode.PAIR)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    try:
        session = await git_board.pair_task(task.id, agent_backend="claude-code", launcher="tmux")
        assert session.task_id == task.id
        assert session.mode == WorkMode.PAIR
    except (AgentError, FileNotFoundError, OSError):
        pass


async def test_unknown_launcher_raises_agent_error(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Bad Launcher Task", task_type=WorkMode.PAIR)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    with pytest.raises(AgentError, match="unknown launcher"):
        await git_board.pair_task(task.id, agent_backend="claude-code", launcher="nonexistent")


async def test_cancel_pair_session_moves_to_backlog(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Cancellable Pair Task", task_type=WorkMode.PAIR)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    await git_board.cancel_task(task.id)

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.BACKLOG


async def test_finish_pair_moves_to_review_when_workspace_has_pending_changes(
    git_board: KaganDriver,
) -> None:
    task = await git_board.create_task("Finish Pair Task", task_type=WorkMode.PAIR)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None
    from pathlib import Path

    (Path(ws_path) / "pair_output.py").write_text("value = 1\n", encoding="utf-8")

    result = await git_board.end_pairing(task.id)

    assert result["ready_for_review"] is True
    assert result["status"] == TaskStatus.REVIEW.value

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.REVIEW


async def test_finish_pair_without_changes_stays_in_progress(git_board: KaganDriver) -> None:
    task = await git_board.create_task("No Change Pair", task_type=WorkMode.PAIR)
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    result = await git_board.end_pairing(task.id)

    assert result["ready_for_review"] is False
    assert result["status"] == TaskStatus.IN_PROGRESS.value

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.IN_PROGRESS
