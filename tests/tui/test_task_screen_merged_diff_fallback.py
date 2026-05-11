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

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        snapshot = str(app.screen.query_one("#ts-workspace-bar", Static).content)

        assert "No worktree provisioned" not in snapshot
        assert snapshot in {"Workspace", "Merged workspace"} or "Merged " in snapshot
        assert "changed" in snapshot


async def test_merged_diff_refresh_preserves_selected_file(board: KaganDriver) -> None:
    from typing import cast

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen
    from kagan.tui.widgets.diff import DiffView

    task = await board.create_task("Merged diff preserves selection")
    await board.provision_workspace(task.id)
    assert await board.commit_in_workspace(
        task.id,
        "alpha.py",
        "print('alpha')\n",
        message="feat: add alpha",
    )
    assert await board.commit_in_workspace(
        task.id,
        "beta.py",
        "print('beta')\n",
        message="feat: add beta",
    )

    await board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await board.move_task(task.id, TaskStatus.REVIEW)
    await board.merge_task(task.id)
    assert await board.get_workspace_path(task.id) is None

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        for _ in range(8):
            await pilot.pause()
            diff_view = app.screen.query_one(DiffView)
            if diff_view.current_file_path() is not None:
                break

        screen = cast("TaskScreen", app.screen)
        screen.action_tab_changes()
        await pilot.pause()

        diff_view = app.screen.query_one(DiffView)
        diff_view.select_next_file()
        await pilot.pause()
        selected = diff_view.current_file_path()

        await screen._hydrate_workspace_panels()
        await pilot.pause()

        assert selected == "beta.py"
        assert diff_view.current_file_path() == selected
