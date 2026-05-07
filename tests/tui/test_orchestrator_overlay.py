"""Behavioral tests for OrchestratorOverlay.

Per testing.md: behavioral specs via KaganDriver + Textual Pilot.
Targeted waits only — no wait_for_workers().
"""

from __future__ import annotations

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


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


async def test_o_key_opens_overlay_from_kanban(board: KaganDriver) -> None:
    """Pressing o on the kanban screen opens the OrchestratorOverlay."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        # We should be on the kanban screen
        assert app.screen.id == "kanban-screen"
        await pilot.press("o")
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
        await pilot.press("o")
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
        await pilot.press("o")
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
        await pilot.press("o")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        panel = app.screen.query_one("#orch-chat", ChatPanel)
        assert panel.is_attached


async def test_attach_updates_breadcrumb(board: KaganDriver) -> None:
    """Calling attach() with a role updates the breadcrumb text."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)

        # Simulate attach with a fake session id (no actual DB session needed
        # for the breadcrumb test — the overlay accepts any string)
        await overlay.attach("fake-session-id", "worker")
        await pilot.pause()

        breadcrumb = overlay.query_one("#orch-breadcrumb", Static)
        assert "Worker" in str(breadcrumb.content)


async def test_esc_while_attached_detaches_first_then_closes(board: KaganDriver) -> None:
    """First Esc detaches to orchestrator; second Esc closes the overlay."""
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("o")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)

        # Attach to a fake session
        await overlay.attach("fake-session-id", "worker")
        await pilot.pause()

        # First Esc — should detach back to orchestrator
        await pilot.press("escape")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
        breadcrumb = overlay.query_one("#orch-breadcrumb", Static)
        assert "Orchestrator" in str(breadcrumb.content)
        assert overlay._attached_session_id is None

        # Second Esc — should close overlay
        await pilot.press("escape")
        await pilot.pause()
        assert app.screen.id == "kanban-screen"


async def test_ctrl_space_also_opens_overlay(board: KaganDriver) -> None:
    """Ctrl+Space is an alternative binding for opening the overlay."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+space")
        await pilot.pause()
        assert isinstance(app.screen, OrchestratorOverlay)
