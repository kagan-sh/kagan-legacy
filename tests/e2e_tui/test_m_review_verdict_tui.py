"""Flow M — Review Verdict (approve / reject + feedback).

Assertions:
  1. Task set up in REVIEW via driver.
  2. Push TaskScreen; press 1/2/3 — each tab activates.
  3. Press a (approve) → verdict recorded; core.reviews.is_approved returns True.
  4. Press x (reject) → RejectionInputModal opens; type feedback; submit.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e_tui.helpers.screens import wait_for_screen
from tests.e2e_tui.helpers.wait import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_tui]


async def test_task_screen_tabs_activate_on_1_2_3(tui_driver: Any) -> None:
    """(2) Pressing 1, 2, 3 switches tabs in TaskScreen."""
    from textual.widgets import TabbedContent

    from kagan.core.enums import TaskStatus
    from kagan.tui import KaganApp
    from kagan.tui.screens.task_screen import TaskScreen

    task = await tui_driver.create_task("Tab Test Task")
    await tui_driver.move_task(task.id, TaskStatus.IN_PROGRESS)
    await tui_driver.move_task(task.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await wait_for_screen(app, TaskScreen)
        await pilot.pause()

        tabs = app.screen.query_one("#ts-tabs", TabbedContent)

        # (1) Overview tab
        await pilot.press("1")
        await pilot.pause()
        await wait_for(lambda: tabs.active == "overview", tries=60)
        assert tabs.active == "overview"

        # (2) Changes tab
        await pilot.press("2")
        await pilot.pause()
        await wait_for(lambda: tabs.active == "changes", tries=60)
        assert tabs.active == "changes"

        # (3) Review tab
        await pilot.press("3")
        await pilot.pause()
        await wait_for(lambda: tabs.active == "review", tries=60)
        assert tabs.active == "review"


async def test_approve_records_verdict(tui_driver: Any) -> None:
    """(3) Press a → approval verdict recorded."""
    from kagan.core.enums import TaskStatus
    from kagan.tui import KaganApp
    from kagan.tui.screens.confirm import ConfirmModal
    from kagan.tui.screens.task_screen import TaskScreen

    task = await tui_driver.create_task(
        "Approve Test Task",
        acceptance_criteria=["criterion one"],
    )
    await tui_driver.move_task(task.id, TaskStatus.IN_PROGRESS)
    await tui_driver.move_task(task.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await wait_for_screen(app, TaskScreen)
        await pilot.pause()

        await pilot.press("a")
        await pilot.pause()

        # ConfirmModal may be pushed for tasks with criteria
        if isinstance(app.screen, ConfirmModal):
            await pilot.press("enter")
            await pilot.pause()

        async def _approved() -> bool:
            import asyncio

            return await asyncio.to_thread(app.core.reviews.is_approved, task.id)

        await wait_for(_approved, tries=60, pump_delay=0.1)
        assert await _approved(), "Task should be approved after pressing 'a'"


async def test_reject_opens_rejection_input_modal(tui_driver: Any) -> None:
    """(4) Press x → RejectionInputModal opens; feedback submitted; task moved back."""
    from kagan.core.enums import TaskStatus
    from kagan.tui import KaganApp
    from kagan.tui.screens.rejection_input import RejectionInputModal
    from kagan.tui.screens.task_screen import TaskScreen

    task = await tui_driver.create_task("Reject Test Task")
    await tui_driver.move_task(task.id, TaskStatus.IN_PROGRESS)
    await tui_driver.move_task(task.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        app.push_screen(TaskScreen(task_id=task.id))
        await pilot.pause()
        await wait_for_screen(app, TaskScreen)
        await pilot.pause()

        await pilot.press("x")
        await pilot.pause()

        await wait_for(lambda: isinstance(app.screen, RejectionInputModal), tries=60)
        assert isinstance(app.screen, RejectionInputModal), "RejectionInputModal should open on 'x'"

        # Type feedback and submit
        from textual.widgets import TextArea

        feedback_area = app.screen.query_one(TextArea)
        feedback_area.focus()
        await pilot.press("N", "e", "e", "d", "s", " ", "w", "o", "r", "k")
        await pilot.press("ctrl+s")
        await pilot.pause()

        # Modal dismisses; task screen pops back; task moved to IN_PROGRESS
        async def _in_progress() -> bool:
            t = await tui_driver.get_task(task.id)
            return t.status == TaskStatus.IN_PROGRESS

        await wait_for(_in_progress, tries=60, pump_delay=0.1)
        t = await tui_driver.get_task(task.id)
        assert t.status == TaskStatus.IN_PROGRESS, (
            f"Task should be IN_PROGRESS after rejection, got {t.status}"
        )
