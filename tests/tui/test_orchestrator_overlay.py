"""Behavioral tests for OrchestratorOverlay.

Per testing.md: behavioral specs via KaganDriver + Textual Pilot.
Targeted waits only — no wait_for_workers().
"""

from __future__ import annotations

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


async def _pause_until(pilot, predicate, *, attempts: int = 20) -> None:
    for _ in range(attempts):
        if predicate():
            return
        await pilot.pause()
    assert predicate()


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Overlay Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    await driver.create_task("Alpha task")
    yield driver
    await driver.teardown()


async def test_ctrl_space_opens_overlay_from_kanban(board: KaganDriver) -> None:
    """Ctrl+Space on the kanban screen opens the OrchestratorOverlay."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        # We should be on the kanban screen
        assert app.screen.id == "kanban-screen"
        await pilot.press("ctrl+space")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)


async def test_esc_closes_overlay_when_in_orchestrator_mode(board: KaganDriver) -> None:
    """Esc while in orchestrator mode closes the overlay."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+space")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"


async def test_overlay_breadcrumb_shows_orchestrator_by_default(board: KaganDriver) -> None:
    """The breadcrumb line reads 'Orchestrator' when not attached to a session."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+space")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        breadcrumb = app.screen.query_one("#orch-breadcrumb", Static)
        assert "Orchestrator" in str(breadcrumb.content)


async def test_overlay_contains_chat_panel(board: KaganDriver) -> None:
    """The overlay renders a ChatPanel so messages can be sent."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+space")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        panel = app.screen.query_one("#chat-panel", ChatPanel)
        assert panel.is_mounted


async def test_ctrl_space_toggles_overlay(board: KaganDriver) -> None:
    """Ctrl+Space opens the overlay from kanban and closes it when pressed again."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+space")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        await pilot.press("ctrl+space")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"


# Removed: test_attached_session_replays_recent_events,
# test_attached_session_streams_live_events_for_selected_session,
# test_attached_session_without_task_id_exits_quietly.
# These tested the old attach()/detach() behaviour which was removed
# in the Unified Sessions Refactor (OrchestratorOverlay now uses
# _select_session via SessionList and has no attach method).
