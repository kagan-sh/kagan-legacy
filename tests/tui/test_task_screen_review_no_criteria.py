"""Tests for the no-criteria review gate in TaskScreen.

Covers:
- No-criteria approve shows ReviewNoCriteriaModal (not a dead-end notification)
- Approve manually path triggers manual approval with strong confirmation
- Reject path from no-criteria modal routes to rejection flow
- Enter on review tab is deterministic (acts, does not tab-switch)
- Footer hints show manual gate affordances for no-criteria review
"""

from typing import TYPE_CHECKING, cast

import pytest
from tests.helpers.driver import KaganDriver

from kagan.core import TaskStatus

if TYPE_CHECKING:
    from kagan.tui.screens.review_no_criteria import ReviewNoCriteriaModal

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def review_board(tmp_path):
    """Board with a single task in REVIEW status (no acceptance criteria)."""
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Review No Criteria Project")
    task = await driver.create_task("Task without criteria")
    await driver.move_task(task.id, TaskStatus.IN_PROGRESS)
    await driver.move_task(task.id, TaskStatus.REVIEW)
    yield driver
    await driver.teardown()


async def test_approve_no_criteria_shows_modal(review_board: KaganDriver) -> None:
    """Pressing approve on a task with no criteria opens the choice modal."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.review_no_criteria import ReviewNoCriteriaModal
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await review_board.list_tasks())[0]

    app = KaganApp(db_path=review_board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        await pilot.press("a")
        await pilot.pause()
        await pilot.pause()

        # The top screen should be the ReviewNoCriteriaModal
        assert isinstance(app.screen, ReviewNoCriteriaModal)


async def test_approve_manually_from_no_criteria_modal(review_board: KaganDriver) -> None:
    """Choosing 'approve manually' in no-criteria modal shows strong confirmation."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.confirm import ConfirmModal
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await review_board.list_tasks())[0]

    app = KaganApp(db_path=review_board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        await pilot.press("a")
        await pilot.pause()
        await pilot.pause()

        # Choose "approve manually" (Enter key in the no-criteria modal)
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Should now show the strong confirmation modal
        assert isinstance(app.screen, ConfirmModal)
        confirm_text = str(app.screen.query_one(".confirm-message", Static).content)
        assert "exceptional" in confirm_text.lower() or "no criteria" in confirm_text.lower()


async def test_reject_from_no_criteria_modal(review_board: KaganDriver) -> None:
    """Choosing 'reject' in no-criteria modal opens the rejection input."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.rejection_input import RejectionInputModal
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await review_board.list_tasks())[0]

    app = KaganApp(db_path=review_board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        await pilot.press("a")
        await pilot.pause()
        await pilot.pause()

        cast("ReviewNoCriteriaModal", app.screen).action_reject()
        await pilot.pause()
        await pilot.pause()

        # Should now show the rejection input modal
        assert isinstance(app.screen, RejectionInputModal)


async def test_enter_on_detail_tab_does_not_switch_tab(review_board: KaganDriver) -> None:
    from textual.widgets import TabbedContent

    from kagan.tui import KaganApp
    from kagan.tui.screens.review_no_criteria import ReviewNoCriteriaModal
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await review_board.list_tasks())[0]

    app = KaganApp(db_path=review_board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(TaskScreen(task_id=task.id))
        # Wait for async on_mount to complete and select initial tab
        for _ in range(10):
            await pilot.pause()
            ts = next((s for s in reversed(app.screen_stack) if isinstance(s, TaskScreen)), None)
            if ts is not None and ts._task_model is not None:
                break

        # Press Enter (primary_action) — should trigger approve flow, not switch tab
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        screen_stack = app.screen_stack
        task_screen = next((s for s in reversed(screen_stack) if isinstance(s, TaskScreen)), None)
        if task_screen is not None:
            tabs = task_screen.query_one("#ts-tabs", TabbedContent)
            assert tabs.active == "review"

        # Top of stack should be the no-criteria modal
        assert isinstance(app.screen, ReviewNoCriteriaModal)


async def test_review_no_criteria_hints_show_manual_gate(review_board: KaganDriver) -> None:
    """Footer hints on review tab with no criteria show approve manually, edit, reject, rebase."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen

    task = (await review_board.list_tasks())[0]

    app = KaganApp(db_path=review_board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await pilot.pause()

        hint_text = str(app.screen.query_one("#ts-action-hint", Static).content).lower()

        assert "no acceptance criteria" in hint_text
        assert "approve manually" in hint_text
        assert "add criteria" in hint_text
        assert "reject" in hint_text
        assert "rebase" in hint_text
