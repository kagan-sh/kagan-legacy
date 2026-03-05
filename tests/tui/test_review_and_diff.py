import pytest
from tests.helpers.driver import KaganDriver

from kagan.core import TaskStatus

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Review Project")
    task = await driver.create_task("Ready for review")
    await driver.move_task(task.id, TaskStatus.IN_PROGRESS)
    await driver.move_task(task.id, TaskStatus.REVIEW)
    yield driver
    await driver.teardown()


async def test_review_key_opens_task_screen_review_tab(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("r")
        await pilot.pause()
        assert app.screen.id == "task-screen"
