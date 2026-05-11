from typing import cast

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

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        screen_status = str(app.screen.query_one("#ts-status", Static).content)
        review_status = str(app.screen.query_one("#ts-detail-status", Static).content)
        source = str(app.screen.query_one("#ts-detail-stream-source", Static).content)

        assert "No workspace diff available" not in screen_status
        assert "No workspace diff available" not in review_status
        assert "IN_PROGRESS" in review_status
        assert "Stream: WORKER" in source


async def test_review_stream_source_prefers_reviewer_for_review_tasks(board: KaganDriver) -> None:
    from textual.widgets import Static, TabbedContent

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await board.list_tasks())[0]
    await board.move_task(task.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        for _ in range(10):
            await pilot.pause()
            tabs = app.screen.query_one("#ts-tabs", TabbedContent)
            if tabs.active == "review":
                break

        source = str(app.screen.query_one("#ts-detail-stream-source", Static).content)

        assert tabs.active == "review"
        assert "Stream: AI REVIEWER" in source


async def test_overview_hints_surface_review_actions_for_review_tasks(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await board.list_tasks())[0]
    await board.move_task(task.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        hint_text = str(app.screen.query_one("#ts-action-hint", Static).content).lower()

        assert "1-3" in hint_text
        assert "approve" in hint_text
        assert "reject" in hint_text


async def test_review_task_manual_overview_tab_stays_on_overview(board: KaganDriver) -> None:
    from textual.containers import VerticalScroll
    from textual.widgets import TabbedContent

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen

    task = await board.create_task(
        "Review task with criteria",
        acceptance_criteria=["The overview tab remains usable."],
    )
    await board.move_task(task.id, TaskStatus.IN_PROGRESS)
    await board.move_task(task.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        for _ in range(10):
            await pilot.pause()
            tabs = app.screen.query_one("#ts-tabs", TabbedContent)
            if tabs.active == "review":
                break

        screen = cast("TaskScreen", app.screen)
        screen.action_tab_overview()
        await pilot.pause()
        await screen._refresh_runtime_state()
        await pilot.pause()

        tabs = app.screen.query_one("#ts-tabs", TabbedContent)
        focused = app.screen.focused

        assert tabs.active == "overview"
        assert isinstance(focused, VerticalScroll)
        assert focused.id == "ts-overview-scroll"


async def test_reject_modal_enter_submits_feedback_and_moves_task_to_in_progress(
    board: KaganDriver,
) -> None:
    from textual.widgets import TextArea

    from kagan.tui import KaganApp
    from kagan.tui.screens.rejection_input import RejectionInputModal
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await board.list_tasks())[0]
    await board.move_task(task.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()

        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        cast("TaskScreen", app.screen).action_reject()
        await pilot.pause()
        await pilot.pause()

        assert isinstance(app.screen, RejectionInputModal)

        feedback = app.screen.query_one("#feedback-input", TextArea)
        feedback.text = "Please address review comments"
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

    latest = await board.get_task(task.id)
    assert latest.status is TaskStatus.IN_PROGRESS
