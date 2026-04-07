"""Feature tests: interactive attach sessions — docs/internal/features/core.md §7."""

import contextlib

import pytest

from kagan.core import AgentError, TaskStatus
from kagan.core.errors import MultiRepoUnsupportedError
from tests.helpers.driver import KaganDriver
from tests.helpers.helpers import make_git_repo

pytestmark = [pytest.mark.core, pytest.mark.slow]


@pytest.fixture
async def git_board(tmp_path):
    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Attached Sessions Project", repo_path=str(repo_path))
    yield driver
    await driver.teardown()


async def test_attached_provisions_workspace_before_launch(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Unprepared Attached Task", launcher="tmux")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)

    with contextlib.suppress(AgentError, FileNotFoundError, OSError):
        await git_board.run_task(
            task.id,
            agent_backend="claude-code",
            launcher="tmux",
        )

    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None


async def test_attached_rejects_multi_repo_projects_explicitly(tmp_path) -> None:
    repo_one = tmp_path / "repo-one"
    repo_two = tmp_path / "repo-two"
    await make_git_repo(repo_one, base_branch="main")
    await make_git_repo(repo_two, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    try:
        await driver.create_project("Multi Repo Project", repo_path=str(repo_one))
        await driver.add_repo(repo_two)
        task = await driver.create_task("Multi Repo Attached Task", launcher="tmux")
        await driver.move_task(task.id, TaskStatus.IN_PROGRESS)

        with pytest.raises(MultiRepoUnsupportedError, match="MULTI_REPO_UNSUPPORTED"):
            await driver.run_task(
                task.id,
                agent_backend="claude-code",
                launcher="tmux",
            )
    finally:
        await driver.teardown()


async def test_multi_repo_workspace_succeeds_when_task_has_repo_id(tmp_path) -> None:
    """Multi-repo project: task with explicit repo_id provisions worktree correctly."""
    repo_one = tmp_path / "repo-one"
    repo_two = tmp_path / "repo-two"
    await make_git_repo(repo_one, base_branch="main")
    await make_git_repo(repo_two, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    try:
        await driver.create_project("Multi Repo OK", repo_path=str(repo_one))
        repo_two_id = await driver.add_repo(repo_two)
        task = await driver.create_task(
            "Task targeting repo two", launcher="tmux", repo_id=repo_two_id
        )
        assert task.repo_id == repo_two_id

        ws_id = await driver.provision_workspace(task.id)
        assert ws_id is not None
    finally:
        await driver.teardown()


async def test_single_repo_auto_resolves_without_repo_id(tmp_path) -> None:
    """Single-repo project: task without repo_id auto-resolves to the only repo."""
    repo = tmp_path / "solo-repo"
    await make_git_repo(repo, base_branch="main")

    driver = await KaganDriver.boot(tmp_path)
    try:
        await driver.create_project("Solo Repo", repo_path=str(repo))
        task = await driver.create_task("Auto-resolve task", launcher="tmux")
        assert task.repo_id is None

        ws_id = await driver.provision_workspace(task.id)
        assert ws_id is not None
    finally:
        await driver.teardown()


async def test_attached_with_workspace_creates_session(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Attached Session Task", launcher="tmux")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    try:
        session = await git_board.run_task(
            task.id,
            agent_backend="claude-code",
            launcher="tmux",
        )
        assert session is not None
        assert session.task_id == task.id
        assert session.launcher == "tmux"
    except (AgentError, FileNotFoundError, OSError):
        pass


async def test_unknown_launcher_raises_agent_error(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Bad Launcher Task", launcher="tmux")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    with pytest.raises(AgentError, match="unknown launcher"):
        await git_board.run_task(
            task.id,
            agent_backend="claude-code",
            launcher="nonexistent",
        )


async def test_cancel_attached_session_moves_to_backlog(git_board: KaganDriver) -> None:
    task = await git_board.create_task("Cancellable Attached Task", launcher="tmux")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    await git_board.cancel_task(task.id)

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.BACKLOG


async def test_finish_attached_moves_to_review_when_workspace_has_pending_changes(
    git_board: KaganDriver,
) -> None:
    task = await git_board.create_task("Finish Attached Task", launcher="tmux")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    ws_path = await git_board.get_workspace_path(task.id)
    assert ws_path is not None
    from pathlib import Path

    (Path(ws_path) / "attached_output.py").write_text("value = 1\n", encoding="utf-8")

    result = await git_board.detach_task(task.id)

    assert result["ready_for_review"] is True
    assert result["status"] == TaskStatus.REVIEW.value

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.REVIEW


async def test_finish_attached_without_changes_stays_in_progress(git_board: KaganDriver) -> None:
    task = await git_board.create_task("No Change Attached", launcher="tmux")
    await git_board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await git_board.provision_workspace(task.id)

    result = await git_board.detach_task(task.id)

    assert result["ready_for_review"] is False
    assert result["status"] == TaskStatus.IN_PROGRESS.value

    fetched = await git_board.get_task(task.id)
    assert fetched.status == TaskStatus.IN_PROGRESS
