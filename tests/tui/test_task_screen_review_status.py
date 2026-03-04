import pytest
from tests.helpers.driver import KaganDriver

from kagan.core import TaskStatus

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Review Status Project")
    task = await driver.create_task("Status should not flip to workspace-diff warning")
    await driver.move_task(task.id, TaskStatus.IN_PROGRESS)
    yield driver
    await driver.teardown()


async def test_review_status_prefers_task_lifecycle_over_empty_diff(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await board.list_tasks())[0]

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id, initial_tab="review"))
        await pilot.pause()
        await pilot.pause()

        screen_status = str(app.screen.query_one("#ts-status", Static).content)
        review_status = str(app.screen.query_one("#ts-review-status", Static).content)
        source = str(app.screen.query_one("#ts-review-stream-source", Static).content)

        assert "No workspace diff available" not in screen_status
        assert "No workspace diff available" not in review_status
        assert "IN_PROGRESS" in review_status
        assert "Stream Source: WORKER" in source


async def test_review_stream_source_prefers_reviewer_for_review_tasks(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await board.list_tasks())[0]
    await board.move_task(task.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id, initial_tab="review"))
        await pilot.pause()
        await pilot.pause()

        source = str(app.screen.query_one("#ts-review-stream-source", Static).content)

        assert "Stream Source: REVIEWER" in source
