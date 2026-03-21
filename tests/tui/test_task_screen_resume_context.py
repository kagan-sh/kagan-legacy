import pytest
from tests.helpers.driver import KaganDriver
from textual.containers import Vertical
from textual.widgets import Static

from kagan.core import TaskStatus
from kagan.tui import KaganApp
from kagan.tui.screens.task_screen import TaskScreen

pytestmark = [pytest.mark.tui]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Resume Context Task")
    await driver.create_task("Resume context ready")
    yield driver
    await driver.teardown()


async def test_resume_context_displays_notes_for_in_progress_tasks(board: KaganDriver) -> None:
    task = (await board.list_tasks())[0]
    await board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await board.annotate(task.id, "First scratchpad note")
    await board.annotate(task.id, "Second note with context")

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        section = app.screen.query_one("#ts-resume-context-section", Vertical)
        resume = app.screen.query_one("#ts-resume-context", Static)

        assert section.display
        content = str(resume.content)
        assert "First scratchpad note" in content
        assert "Second note with context" in content


async def test_resume_context_hidden_for_backlog_tasks(board: KaganDriver) -> None:
    task = (await board.list_tasks())[0]

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        section = app.screen.query_one("#ts-resume-context-section", Vertical)

        assert not section.display
