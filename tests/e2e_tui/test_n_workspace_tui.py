"""Flow N — Workspace Switcher.

Assertions:
  1. From KanbanScreen, press w → WorkspaceScreen.
  2. Press n → new orchestrator session created (count increases).
  3. Press / → search input focused; type filter.
  4. Press Escape once (clears filter) then again (returns to sidebar/kanban).
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.e2e_tui.helpers.screens import is_screen, wait_for_screen
from tests.e2e_tui.helpers.wait import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_tui]


async def test_w_opens_workspace_from_kanban(tui_driver: Any) -> None:
    """(1) Press w on KanbanScreen → WorkspaceScreen."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.screens.workspace import WorkspaceScreen

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        await pilot.press("w")
        await pilot.pause()
        await wait_for_screen(app, WorkspaceScreen)
        assert is_screen(app, WorkspaceScreen), (
            f"Expected WorkspaceScreen after 'w', got {type(app.screen).__name__}"
        )


async def test_workspace_new_session_increases_count(tui_driver: Any) -> None:
    """(2) Press n → new orchestrator session appears in sidebar."""
    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.screens.workspace import WorkspaceScreen

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        await pilot.press("w")
        await pilot.pause()
        await wait_for_screen(app, WorkspaceScreen)

        count_before = len(app.orchestrator_sessions.list_items())

        await pilot.press("n")
        await pilot.pause()
        await wait_for(
            lambda: len(app.orchestrator_sessions.list_items()) > count_before,
            tries=60,
        )
        assert len(app.orchestrator_sessions.list_items()) > count_before, (
            "Session count should increase after pressing 'n'"
        )


async def test_workspace_search_focuses_input(tui_driver: Any) -> None:
    """(3) Press / on WorkspaceScreen → search input focused; typing filters list."""
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.screens.workspace import WorkspaceScreen

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        await pilot.press("w")
        await pilot.pause()
        await wait_for_screen(app, WorkspaceScreen)

        await pilot.press("/")
        await pilot.pause()

        search = app.screen.query_one("#workspace-search", Input)
        await wait_for(lambda: app.screen.focused is search, tries=60)
        assert app.screen.focused is search, "Search input should be focused after '/'"

        await pilot.press("x", "x", "x")
        await pilot.pause()
        assert "xxx" in search.value, f"Filter text not in search input: {search.value!r}"


async def test_workspace_esc_clears_filter_then_returns_to_sidebar(tui_driver: Any) -> None:
    """(4) Esc clears filter; second Esc returns focus to sidebar (not kanban)."""
    from textual.widgets import Input, OptionList

    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.screens.workspace import WorkspaceScreen

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause()
        await wait_for_screen(app, KanbanScreen)

        await pilot.press("w")
        await pilot.pause()
        await wait_for_screen(app, WorkspaceScreen)

        # Focus search and type something
        await pilot.press("/")
        await pilot.pause()
        search = app.screen.query_one("#workspace-search", Input)
        await wait_for(lambda: app.screen.focused is search, tries=60)

        await pilot.press("f", "i", "l", "t", "e", "r")
        await pilot.pause()
        assert search.value, "Filter text should be entered"

        # First Esc → clears filter
        await pilot.press("escape")
        await pilot.pause()
        await wait_for(lambda: search.value == "", tries=60)
        assert search.value == "", "First Esc should clear the search filter"

        # Second Esc → focus returns to sidebar list
        await pilot.press("escape")
        await pilot.pause()
        session_list = app.screen.query_one("#workspace-session-list", OptionList)
        await wait_for(lambda: app.screen.focused is session_list, tries=60)
        assert app.screen.focused is session_list, "Second Esc should return focus to session list"
