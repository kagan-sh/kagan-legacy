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
    await driver.create_task("Backlog A")
    await driver.create_task("Backlog B")
    yield driver
    await driver.teardown()


@pytest.fixture
async def empty_board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Empty Board Project")
    yield driver
    await driver.teardown()


async def test_ctrl_o_opens_chat_on_kanban(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()
        chat_panel = app.screen.query_one("#chat-panel")
        assert chat_panel.has_class("visible")
        assert app.screen.has_class("chat-overlay-vertical")


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
        await pilot.pause()
        await pilot.press("enter")
        await asyncio.wait_for(started.wait(), timeout=1.0)

        await pilot.press("/")
        await pilot.pause()
        assert app.screen.query_one(SearchBar).has_class("active")

        release.set()
        await pilot.pause()


async def test_space_opens_peek_overlay(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        peek = app.screen.query_one("#peek-overlay")
        assert not peek.has_class("visible")
        assert not peek.display
        await pilot.press("space")
        await pilot.pause()
        assert peek.has_class("visible")
        assert peek.display
        assert peek.region.x > 0


async def test_slash_opens_search_with_presets_and_legacy_affordances(
    board: KaganDriver,
) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.search_bar import SearchBar, SearchPresets

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        project = (await app.core.projects.list())[-1]
        await app.activate_project(project)
        app.switch_screen("kanban-screen")
        await pilot.pause()
        await pilot.press("/")
        await pilot.pause()
        search_bar = app.screen.query_one(SearchBar)
        search_input = search_bar.query_one("#search-input", Input)
        presets = search_bar.query_one(SearchPresets)
        clear = search_bar.query_one(".search-clear", Static)
        meta = search_bar.query_one("#search-meta", Static)
        preset_labels = [
            str(getattr(pill, "content", "")) for pill in presets.query(".preset-pill")
        ]
        assert search_bar.has_class("active")
        assert search_input.display
        assert search_bar.has_class("has-presets")
        assert presets.has_class("visible")
        assert str(clear.render()) == "Esc hide"
        assert str(meta.render()) == "2/2 tasks"
        assert any("Recent" in label for label in preset_labels)
        assert any("Priority" in label for label in preset_labels)


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


async def test_search_query_replaces_header_with_input(board: KaganDriver) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.widgets.header import KaganHeader

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        project = (await app.core.projects.list())[-1]
        await app.activate_project(project)
        app.switch_screen("kanban-screen")
        await pilot.pause()

        await pilot.press("/")
        await pilot.pause()

        screen = cast("KanbanScreen", app.screen)
        header = screen.query_one(KaganHeader)
        search_input = screen.query_one("#search-input", Input)

        assert not screen.has_class("search-replace-header")
        assert header.display

        search_input.value = "backlog"
        await pilot.pause()

        assert screen.has_class("search-replace-header")
        assert not header.display

        search_input.value = ""
        await pilot.pause()

        assert not screen.has_class("search-replace-header")
        assert header.display


async def test_ctrl_o_on_selected_auto_task_opens_docked_task_overlay(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+o")
        await pilot.pause()

        panel = app.screen.query_one(ChatPanel)
        assert panel.has_class("visible")
        assert panel.has_class("docked")
        assert not panel.has_class("fullscreen")
        assert app.screen.has_class("chat-overlay-vertical")

        heading = panel.query_one("#chat-overlay-empty-heading", Static)
        assert str(heading.content) == "What are you working on?"


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
        await pilot.press("enter")
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


async def test_arrow_navigation_moves_selection_across_cards(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    in_progress_a = await board.create_task("In Progress Arrow A")
    await board.move_task(in_progress_a.id, TaskStatus.IN_PROGRESS)
    in_progress_b = await board.create_task("In Progress Arrow B")
    await board.move_task(in_progress_b.id, TaskStatus.IN_PROGRESS)
    review = await board.create_task("Review Arrow")
    await board.move_task(review.id, TaskStatus.IN_PROGRESS)
    await board.move_task(review.id, TaskStatus.REVIEW)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        screen = cast("KanbanScreen", app.screen)
        assert screen._selected_task_id == in_progress_a.id

        await pilot.press("down")
        await pilot.pause()
        assert screen._selected_task_id == in_progress_b.id

        await pilot.press("up")
        await pilot.pause()
        assert screen._selected_task_id == in_progress_a.id

        await pilot.press("right")
        await pilot.pause()
        assert screen._selected_task_id == review.id

        await pilot.press("left")
        await pilot.pause()
        assert screen._selected_task_id == in_progress_a.id


async def test_tab_navigation_moves_within_column_and_shift_tab_reverses(
    board: KaganDriver,
) -> None:
    from kagan.tui import KaganApp

    in_progress_a = await board.create_task("In Progress Tab A")
    await board.move_task(in_progress_a.id, TaskStatus.IN_PROGRESS)
    in_progress_b = await board.create_task("In Progress Tab B")
    await board.move_task(in_progress_b.id, TaskStatus.IN_PROGRESS)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        screen = cast("KanbanScreen", app.screen)
        assert screen._selected_task_id == in_progress_a.id

        await pilot.press("tab")
        await pilot.pause()
        assert screen._selected_task_id == in_progress_b.id

        await pilot.press("shift+tab")
        await pilot.pause()
        assert screen._selected_task_id == in_progress_a.id


async def test_empty_board_shows_onboarding_hint_with_help_fallback(
    empty_board: KaganDriver,
) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=empty_board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        hint = app.screen.query_one("#review-queue-hint", Static)
        hint_text = str(hint.render())
        assert hint.has_class("visible")
        assert "No tasks yet." in hint_text
        assert "? / F1" in hint_text


async def test_f1_opens_help_modal_on_kanban(empty_board: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.screens.help import HelpModal

    app = KaganApp(db_path=empty_board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("f1")
        await pilot.pause()

        assert isinstance(app.screen, HelpModal)
