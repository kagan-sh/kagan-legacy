"""Single high-signal TUI smoke: Kanban → workspace screen (orchestrator workspace).

Uses ``KaganDriver`` + Textual Pilot only — no AsyncMock of domain services.
Mirrors the workspace entry path documented in ``docs/internal/features/tui.md``.
"""

from __future__ import annotations

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Workspace Smoke Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    await driver.create_task("Smoke task")
    yield driver
    await driver.teardown()


async def test_kanban_w_key_opens_workspace_screen(board: KaganDriver) -> None:
    """From Kanban, ``w`` switches to the workspace (orchestrator) screen."""
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        assert app.screen.id == "kanban-screen"

        await pilot.press("w")
        await pilot.pause()

        assert app.screen.id == "workspace-screen"
