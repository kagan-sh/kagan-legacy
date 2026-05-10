"""Kanban board smoke tests — unique-edge cases only.

Card-state assertions are covered by Flow L (tests/e2e_tui/test_l_task_lifecycle_tui.py).
Arrow/Tab navigation redundancy covered by hjkl test below.
Ctrl+. overlay covered by tests/tui/test_orchestrator_overlay.py.
"""

import asyncio
from typing import TYPE_CHECKING, cast

import pytest
from tests.helpers.driver import KaganDriver

from kagan.core import TaskStatus

if TYPE_CHECKING:
    from kagan.tui.screens.kanban import KanbanScreen

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Kanban Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    await driver.create_task("Backlog A")
    await driver.create_task("Backlog B")
    yield driver
    await driver.teardown()


@pytest.fixture
async def empty_board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Empty Board Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    yield driver
    await driver.teardown()


# ── Unique: interactive while bootstrap runs ──────────────────────────────────


async def test_kanban_mount_remains_interactive_while_bootstrap_runs(
    board: KaganDriver, monkeypatch: pytest.MonkeyPatch
) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.screens.kanban import KanbanScreen
    from kagan.tui.widgets.search_bar import SearchBar

    started = asyncio.Event()
    release = asyncio.Event()
    original_bootstrap = KanbanScreen._bootstrap_initial_state

    async def delayed_bootstrap(self: KanbanScreen) -> None:
        started.set()
        await release.wait()
        await original_bootstrap(self)

    monkeypatch.setattr(KanbanScreen, "_bootstrap_initial_state", delayed_bootstrap)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await asyncio.wait_for(started.wait(), timeout=1.0)

        await pilot.press("/")
        await pilot.pause()
        assert app.screen.query_one(SearchBar).has_class("active")

        release.set()
        await pilot.pause()


# ── Unique: p peek toggle ─────────────────────────────────────────────────────


async def test_p_opens_peek_overlay(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        peek = app.screen.query_one("#peek-overlay")
        assert not peek.has_class("visible")
        assert not peek.display
        await pilot.press("p")
        await pilot.pause()
        assert peek.has_class("visible")
        assert peek.display
        assert peek.region.x > 0


# ── Unique: search history loop ───────────────────────────────────────────────


async def test_search_history_loops_with_up_and_down(board: KaganDriver) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        project = (await app.core.projects.list())[-1]
        await app.activate_project(project)
        app.switch_screen("kanban-screen")
        await pilot.pause()

        await pilot.press("/")
        await pilot.pause()
        search_input = app.screen.query_one("#search-input", Input)
        search_input.value = "first query"
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press("/")
        await pilot.pause()
        search_input = app.screen.query_one("#search-input", Input)
        search_input.value = "second query"
        await pilot.press("escape")
        await pilot.pause()

        await pilot.press("/")
        await pilot.pause()
        await pilot.press("up")
        await pilot.pause()
        assert search_input.value == "second query"

        await pilot.press("up")
        await pilot.pause()
        assert search_input.value == "first query"

        await pilot.press("up")
        await pilot.pause()
        assert search_input.value == "second query"

        await pilot.press("down")
        await pilot.pause()
        assert search_input.value == "first query"


# ── Unique: hjkl navigation ───────────────────────────────────────────────────


async def test_hjkl_navigation_moves_selection_across_cards(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    in_progress_a = await board.create_task("In Progress A")
    await board.move_task(in_progress_a.id, TaskStatus.IN_PROGRESS)
    in_progress_b = await board.create_task("In Progress B")
    await board.move_task(in_progress_b.id, TaskStatus.IN_PROGRESS)
    review = await board.create_task("Review A")
    await board.move_task(review.id, TaskStatus.IN_PROGRESS)
    await board.move_task(review.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()

        screen = cast("KanbanScreen", app.screen)
        assert screen._selected_task_id == in_progress_a.id

        await pilot.press("j")
        await pilot.pause()
        assert screen._selected_task_id == in_progress_b.id

        await pilot.press("k")
        await pilot.pause()
        assert screen._selected_task_id == in_progress_a.id

        await pilot.press("l")
        await pilot.pause()
        assert screen._selected_task_id == review.id

        await pilot.press("h")
        await pilot.pause()
        assert screen._selected_task_id == in_progress_a.id


# ── Unique: F1 help modal ─────────────────────────────────────────────────────


async def test_f1_opens_help_modal_on_kanban(empty_board: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.screens.help import HelpModal

    app = KaganApp(db_path=empty_board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()

        assert isinstance(app.screen, HelpModal)
