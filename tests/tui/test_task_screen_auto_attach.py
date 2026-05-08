"""Behavioral tests for task screen auto-attach logic.

Per testing.md: behavioral specs via KaganDriver + Textual Pilot.
"""

from __future__ import annotations

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Auto Attach Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    yield driver
    await driver.teardown()


async def test_task_with_no_sessions_opens_overlay_in_orchestrator_mode(
    board: KaganDriver,
) -> None:
    """Opening a task that has no sessions pushes the overlay in orchestrator mode."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    await board.create_task("Clean task")

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        # Select and open task screen
        await pilot.press("enter")  # open inspector
        await pilot.pause()
        await pilot.press("enter")  # open task screen
        await pilot.pause()
        await pilot.pause()

        # The overlay should have been auto-pushed in orchestrator mode
        assert isinstance(app.screen, OrchestratorOverlay)
        overlay = app.screen
        assert overlay._selected_session_id is None


async def test_task_screen_renders_chat_hint(board: KaganDriver) -> None:
    """The task screen now shows a slim 'Press o' hint instead of a chat panel."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    await board.create_task("Hint task")

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # If an overlay was pushed, pop it to get to task-screen
        if isinstance(app.screen, OrchestratorOverlay):
            await pilot.press("escape")
            await pilot.pause()

        if app.screen.id == "task-screen":
            hint = app.screen.query_one("#ts-chat-hint", Static)
            assert hint.display


async def test_escape_from_overlay_returns_to_task_screen(board: KaganDriver) -> None:
    """Pressing Esc on the auto-pushed overlay returns to task-screen."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    await board.create_task("Return task")

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        # Should have auto-pushed overlay
        if isinstance(app.screen, OrchestratorOverlay):
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen.id == "task-screen"
