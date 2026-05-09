"""Verify that task_screen no longer mounts an in-screen ChatPanel.

The OrchestratorOverlay (commit d5ff69c) replaces the former embedded chat
panel.  These tests confirm the layout is clean and the overlay auto-attach
path is the only chat surface on the task screen.
"""

from __future__ import annotations

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("No Embedded Chat Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    yield driver
    await driver.teardown()


async def _navigate_to_task_screen(pilot, board: KaganDriver) -> None:
    """Boot the app, open inspector, push task screen, dismiss any auto overlay."""
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    await pilot.pause()
    await pilot.pause()
    await pilot.press("enter")  # open inspector
    await pilot.pause()
    await pilot.press("enter")  # open task screen
    await pilot.pause()
    await pilot.pause()
    # BACKLOG tasks auto-push OrchestratorOverlay; dismiss to reach TaskScreen
    if isinstance(pilot.app.screen, OrchestratorOverlay):
        await pilot.press("escape")
        await pilot.pause()


async def test_task_screen_has_no_chat_panel_widget(board: KaganDriver) -> None:
    """TaskScreen must not mount a ChatPanel — only the overlay hint is present."""
    from textual.css.query import NoMatches

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    await board.create_task("No chat panel task")
    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _navigate_to_task_screen(pilot, board)

        assert app.screen.id == "task-screen"
        # Must raise NoMatches — ChatPanel is no longer composed into TaskScreen
        with pytest.raises(NoMatches):
            app.screen.query_one(ChatPanel)


async def test_task_screen_shows_overlay_hint_static(board: KaganDriver) -> None:
    """The #ts-chat-hint Static is present and visible in place of the chat panel."""
    from textual.widgets import Static

    from kagan.tui import KaganApp

    await board.create_task("Chat hint task")
    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _navigate_to_task_screen(pilot, board)

        assert app.screen.id == "task-screen"
        hint = app.screen.query_one("#ts-chat-hint", Static)
        assert hint.display
        assert str(hint.content) == "Ctrl+Space · orchestrator · Ctrl+. sessions"


async def test_task_action_bar_does_not_advertise_embedded_chat_shortcuts(
    board: KaganDriver,
) -> None:
    """TaskScreen footer keeps pointing back, never stale embedded chat controls."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.task_action_bar import TaskActionBar

    await board.create_task("No stale chat shortcuts task")
    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await _navigate_to_task_screen(pilot, board)

        assert app.screen.id == "task-screen"
        action_bar = app.screen.query_one("#ts-actions", TaskActionBar)

        # Guard against the old embedded chat branch re-labelling Esc as close.
        action_bar.chat_visible = True
        action_bar.chat_fullscreen = True
        await pilot.pause()

        hint_text = str(app.screen.query_one("#ts-action-hint", Static).content).lower()
        assert "back" in hint_text
        for removed_hint in ("split", "fullscreen", "sessions", "close"):
            assert removed_hint not in hint_text


async def test_backlog_task_auto_pushes_orchestrator_overlay(board: KaganDriver) -> None:
    """Opening a BACKLOG task auto-pushes OrchestratorOverlay instead of an in-screen panel."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    await board.create_task("Auto overlay task")
    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("enter")  # open inspector
        await pilot.pause()
        await pilot.press("enter")  # open task screen
        await pilot.pause()
        await pilot.pause()

        # The overlay should have been pushed — not an in-screen panel
        assert isinstance(app.screen, OrchestratorOverlay)
        overlay = app.screen
        # Orchestrator mode (no session attached) by default for a task with no sessions
        assert overlay._selected_session_id is None


async def test_escape_from_auto_overlay_reaches_task_screen(board: KaganDriver) -> None:
    """Pressing Esc on the auto-pushed overlay returns to task-screen (not kanban)."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    await board.create_task("Overlay return task")
    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

        if isinstance(app.screen, OrchestratorOverlay):
            await pilot.press("escape")
            await pilot.pause()
            assert app.screen.id == "task-screen"
