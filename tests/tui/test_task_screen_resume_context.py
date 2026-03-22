import pytest
from tests.helpers.driver import KaganDriver
from textual.containers import Vertical
from textual.widgets import Static

from kagan.core import TaskStatus
from kagan.tui import KaganApp
from kagan.tui.screens.task_screen import TaskScreen

pytestmark = [pytest.mark.tui]


async def test_resume_context_displays_notes_for_in_progress_tasks(
    board_with_task: KaganDriver,
) -> None:
    task = (await board_with_task.list_tasks())[0]
    await board_with_task.move_task(task.id, TaskStatus.IN_PROGRESS)
    await board_with_task.annotate(task.id, "First scratchpad note")
    await board_with_task.annotate(task.id, "Second note with context")

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
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


async def test_resume_context_hidden_for_backlog_tasks(board_with_task: KaganDriver) -> None:
    task = (await board_with_task.list_tasks())[0]

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        section = app.screen.query_one("#ts-resume-context-section", Vertical)

        assert not section.display
