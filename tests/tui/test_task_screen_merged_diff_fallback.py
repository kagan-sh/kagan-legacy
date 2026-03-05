import pytest
from tests.helpers.driver import KaganDriver

from kagan.core import TaskStatus

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Merged Diff Project", repo_path=str(tmp_path / "repo"))
    yield driver
    await driver.teardown()


async def test_task_screen_shows_merged_diff_when_workspace_cleaned(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen

    task = await board.create_task("Merged diff fallback")
    await board.provision_workspace(task.id)
    committed = await board.commit_in_workspace(
        task.id,
        "main.go",
        "package main\n\nfunc main() {\n}\n",
        message="feat: add main",
    )
    assert committed

    await board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await board.move_task(task.id, TaskStatus.REVIEW)
    await board.merge_task(task.id)
    assert await board.get_workspace_path(task.id) is None

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id, initial_tab="changes"))
        await pilot.pause()
        await pilot.pause()

        snapshot = str(app.screen.query_one("#ts-workspace-snapshot", Static).content)
        changed = str(app.screen.query_one("#ts-changed-files", Static).content)
        review_files_label = str(app.screen.query_one("#ts-review-files-label", Static).content)

        assert "No worktree provisioned" not in snapshot
        assert "Merged " in snapshot
        assert "changed" in changed
        assert review_files_label != "No changes available"
