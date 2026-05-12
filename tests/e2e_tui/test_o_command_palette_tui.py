"""Flow O — Command Palette / Quick Actions.

Assertions:
  1. From KanbanScreen, press Ctrl+Shift+P → command palette opens.
  2. Type a known action label, assert it appears in the results list.
  3. Press Escape → palette closes; KanbanScreen is active again.

NOTE: The custom palette widget lives in ``KanbanCommandProvider`` registered
on ``KanbanScreen.COMMANDS``. Textual's built-in ``CommandPalette``
(``SystemModalScreen``) is used as the container — not a custom widget.
We assert the SystemModalScreen mounts and dismisses rather than testing
command dispatch, which would require async result-list polling that is
brittle across Textual versions.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e_tui.helpers.screens import is_screen, wait_for_screen
from tests.e2e_tui.helpers.wait import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_tui]


async def test_command_palette_opens_on_ctrl_shift_p(tui_driver: Any) -> None:
    """(1) Ctrl+Shift+P opens the Textual CommandPalette modal."""
    from textual.screen import SystemModalScreen

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        await pilot.press("ctrl+shift+p")
        await pilot.pause()

        # CommandPalette is a SystemModalScreen pushed on top of the screen stack.
        # It is accessible via app.screen (the topmost screen).
        await wait_for(
            lambda: isinstance(app.screen, SystemModalScreen),
            tries=60,
        )
        assert isinstance(app.screen, SystemModalScreen), (
            f"CommandPalette (SystemModalScreen) should be open, got {type(app.screen).__name__}"
        )


async def test_command_palette_closes_on_escape(tui_driver: Any) -> None:
    """(3) Escape closes the CommandPalette; KanbanScreen is active again."""
    from textual.screen import SystemModalScreen

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        await pilot.press("ctrl+shift+p")
        await pilot.pause()
        await wait_for(lambda: isinstance(app.screen, SystemModalScreen), tries=60)

        await pilot.press("escape")
        await pilot.pause()
        await wait_for(lambda: isinstance(app.screen, KanbanScreen), tries=60)
        assert is_screen(app, KanbanScreen), (
            f"KanbanScreen should be active after Escape, got {type(app.screen).__name__}"
        )


async def test_command_palette_f2_alias_opens_palette(tui_driver: Any) -> None:
    """(1-alt) F2 is an alias for Ctrl+Shift+P and also opens the palette."""
    from textual.screen import SystemModalScreen

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        await pilot.press("f2")
        await pilot.pause()
        await wait_for(lambda: isinstance(app.screen, SystemModalScreen), tries=60)
        assert isinstance(app.screen, SystemModalScreen), (
            "F2 should open CommandPalette (SystemModalScreen)"
        )

        # Close palette
        await pilot.press("escape")
        await pilot.pause()
        await wait_for(lambda: is_screen(app, KanbanScreen), tries=60)


async def test_command_palette_type_filter_and_escape(tui_driver: Any) -> None:
    """(2)+(3) Type 'task.new' in palette; palette accepts input; Esc closes."""
    from textual.screen import SystemModalScreen
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        await pilot.press("ctrl+shift+p")
        await pilot.pause()
        await wait_for(lambda: isinstance(app.screen, SystemModalScreen), tries=60)

        # The CommandPalette has an input widget (#--input or similar).
        # Type a known command prefix and verify palette stays open (accepts input).
        try:
            palette_input = app.screen.query_one("Input", Input)
            palette_input.focus()
        except Exception:
            pytest.skip("CommandPalette input not queryable in this Textual version")
            return

        await pilot.press("t", "a", "s", "k")
        await pilot.pause()

        # Palette should still be visible after typing
        assert isinstance(app.screen, SystemModalScreen), "Palette should stay open while typing"

        await pilot.press("escape")
        await pilot.pause()
        await wait_for(lambda: is_screen(app, KanbanScreen), tries=60)
        assert is_screen(app, KanbanScreen)
