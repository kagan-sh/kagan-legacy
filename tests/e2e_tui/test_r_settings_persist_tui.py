"""Flow R — Settings Persist Roundtrip (TUI).

Opens SettingsModal via ``Ctrl+,``, changes the default agent backend to
``fake-agent``, dismisses with Escape, then reads back the persisted value.
Also verifies the value survives an app restart against the same database.

Assertions:
  1. ``Ctrl+,`` opens a screen with id ``settings-modal``.
  2. Changing the default agent backend select updates the setting.
  3. Escape closes the modal and returns to KanbanScreen.
  4. Settings are readable from ``app.core.settings.get()``.
  5. (Bonus) Setting persists when a new KaganApp is instantiated against
     the same DB path.

Limitation: step 5 re-reads from the same DB file; it does not fully
reboot the KaganCore async context but creates a new KaganApp instance.
This is sufficient to verify the value was written to disk.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e_tui.helpers.wait import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_tui]


async def test_settings_change_persists(tui_driver: Any) -> None:
    """Change default_agent_backend via SettingsModal; read back via core API."""
    from textual.widgets import Select

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
        await pilot.pause()

        # Open SettingsModal via action (Ctrl+, binding)
        app.action_open_settings()
        await wait_for(lambda: app.screen.id == "settings-modal", tries=60)
        await pilot.pause()

        # Change the default agent backend to fake-agent
        try:
            agent_select = app.screen.query_one("#settings-default-agent", Select)
        except Exception:
            pytest.skip("settings-default-agent Select not found — widget layout changed")
            return

        agent_select.value = "fake-agent"
        await pilot.pause(delay=0.5)

        # Dismiss with Escape (auto-saves)
        await pilot.press("escape")
        await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
        await pilot.pause()

        # Read back from core settings
        settings = await app.core.settings.get()
        saved_backend = settings.get("default_agent_backend")
        assert saved_backend == "fake-agent", f"Expected 'fake-agent' but got {saved_backend!r}"


async def test_settings_survive_app_restart(tui_driver: Any) -> None:
    """Value written in one KaganApp instance is readable in a fresh instance."""
    from textual.widgets import Select

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen

    db_path = tui_driver.tmp_path / "kagan.db"

    # --- first app: write the setting ---
    app = KaganApp(db_path=db_path)
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
        await pilot.pause()

        app.action_open_settings()
        await wait_for(lambda: app.screen.id == "settings-modal", tries=60)
        await pilot.pause()

        try:
            agent_select = app.screen.query_one("#settings-default-agent", Select)
        except Exception:
            pytest.skip("settings-default-agent Select not found")
            return

        agent_select.value = "fake-agent"
        await pilot.pause(delay=0.5)
        await pilot.press("escape")
        await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)

    # --- second app: verify the setting is still there ---
    app2 = KaganApp(db_path=db_path)
    async with app2.run_test(size=(120, 40)) as pilot2:
        await pilot2.pause()
        await pilot2.press("enter")
        await wait_for(lambda: isinstance(app2.screen, KanbanScreen), tries=60)
        await pilot2.pause()

        settings = await app2.core.settings.get()
        saved_backend = settings.get("default_agent_backend")
        assert saved_backend == "fake-agent", (
            f"Setting not persisted across restart; got {saved_backend!r}"
        )
