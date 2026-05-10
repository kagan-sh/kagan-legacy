"""Flow K — Cold-Start Onboarding.

Assertions:
  1. Boot with no project → OnboardingFlow (project-picker) is visible.
  2. After project activation, KanbanScreen mounts.
  3. Tutorial overlay shown on first boot (tui_tutorial_seen=false).
  4. Press Esc → tutorial dismisses; setting persists as true.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e_tui.helpers.screens import is_screen, wait_for_screen
from tests.e2e_tui.helpers.wait import wait_for
from tests.helpers.driver import KaganDriver
from tests.helpers.fake_agent_backend import ensure_fake_agent_backend_registered

pytestmark = [pytest.mark.tui, pytest.mark.e2e_tui]


@pytest.fixture
async def fresh_driver(tmp_path: Any) -> Any:
    """Driver with NO project and tutorial NOT seen — raw cold-start state."""
    ensure_fake_agent_backend_registered()
    driver = await KaganDriver.boot(tmp_path)
    # Override boot default: tutorial_seen=false, no auto-open
    await driver.settings_update(
        {
            "ui.tui_tutorial_seen": "false",
            "open_last_project_on_startup": "false",
        }
    )
    yield driver
    await driver.teardown()


async def test_cold_start_no_project_shows_onboarding(fresh_driver: Any) -> None:
    """(1) App with no project routes to OnboardingFlow (project-picker)."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.setup import OnboardingFlow

    app = KaganApp(db_path=fresh_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        assert is_screen(app, OnboardingFlow), (
            f"Expected OnboardingFlow, got {type(app.screen).__name__}"
        )


async def test_cold_start_project_activates_kanban(tmp_path: Any) -> None:
    """(2) After a project is created and open_last_project_on_startup set, KanbanScreen mounts."""
    ensure_fake_agent_backend_registered()
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("K Flow Project")
    await driver.settings_update(
        {
            "ui.tui_tutorial_seen": "true",
            "open_last_project_on_startup": "true",
        }
    )

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await wait_for_screen(app, KanbanScreen)
            assert is_screen(app, KanbanScreen)
    finally:
        await driver.teardown()


async def test_tutorial_overlay_shown_on_first_boot(fresh_driver: Any) -> None:
    """(3) Tutorial overlay is displayed when tui_tutorial_seen=false."""
    await fresh_driver.create_project("K Tutorial Project")
    await fresh_driver.settings_update(
        {
            "ui.tui_tutorial_seen": "false",
            "open_last_project_on_startup": "true",
        }
    )

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.screens.tutorial import TutorialOverlay

    app = KaganApp(db_path=fresh_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        overlay = app.screen.query_one("#kanban-tutorial-overlay", TutorialOverlay)
        await wait_for(lambda: bool(overlay.display), tries=80, pump_delay=0.05)
        assert overlay.display, "Tutorial overlay should be visible on first boot"


async def test_tutorial_dismisses_on_esc_and_setting_persists(fresh_driver: Any) -> None:
    """(4) Esc dismisses tutorial; setting is persisted as true."""
    await fresh_driver.create_project("K Esc Project")
    await fresh_driver.settings_update(
        {
            "ui.tui_tutorial_seen": "false",
            "open_last_project_on_startup": "true",
        }
    )

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.screens.tutorial import TutorialOverlay

    app = KaganApp(db_path=fresh_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        overlay = app.screen.query_one("#kanban-tutorial-overlay", TutorialOverlay)
        await wait_for(lambda: bool(overlay.display), tries=80, pump_delay=0.05)

        overlay.focus()
        await pilot.press("escape")
        await pilot.pause()

        await wait_for(lambda: not bool(overlay.display), tries=80, pump_delay=0.05)
        assert not overlay.display, "Tutorial should be hidden after Esc"

        settings = await app.core.settings.get()
        assert settings.get("ui.tui_tutorial_seen") == "true", (
            "tui_tutorial_seen should be persisted as 'true'"
        )
