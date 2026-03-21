import pytest
from tests.helpers.driver import KaganDriver
from textual.containers import VerticalScroll
from textual.widgets import Input, Select, TextArea

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Authoring Project")
    await driver.create_task("Existing task")
    yield driver
    await driver.teardown()


async def test_n_opens_task_creation_form(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        assert app.screen.id == "task-editor-modal"


async def test_save_in_task_form_creates_new_backlog_task(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("A", "u", "t", "h", "o", "r", "e", "d")
        await pilot.press("ctrl+s")
        await pilot.pause()
    results = await board.search_tasks("Authored")
    assert len(results) == 1


async def test_task_form_stays_scrollable_when_advanced_options_expand(
    board: KaganDriver,
) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test(size=(90, 20)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

        form = app.screen.query_one(".task-form", VerticalScroll)
        initial_max_scroll = form.max_scroll_y

        await pilot.press("ctrl+period")
        await pilot.pause()

        expanded_max_scroll = form.max_scroll_y
        assert expanded_max_scroll > initial_max_scroll
        assert expanded_max_scroll > 0


async def test_task_form_scroll_action_moves_view_when_advanced_expanded(
    board: KaganDriver,
) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test(size=(90, 20)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        await pilot.press("ctrl+period")
        await pilot.pause()

        form = app.screen.query_one(".task-form", VerticalScroll)
        assert form.max_scroll_y > 0

        app.screen.action_scroll_down()
        await pilot.pause()
        assert form.scroll_y > 0


async def test_toggling_advanced_brings_acceptance_criteria_into_view(
    board: KaganDriver,
) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test(size=(90, 20)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()

        form = app.screen.query_one(".task-form", VerticalScroll)
        initial_scroll = form.scroll_y

        await pilot.press("ctrl+period")
        await pilot.pause()

        criteria = app.screen.query_one("#task-acceptance-criteria", TextArea)

        assert criteria.has_focus
        assert form.scroll_y > initial_scroll


async def test_task_form_saves_attached_launcher_override(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("n")
        await pilot.pause()
        title_input = app.screen.query_one("#task-title", Input)
        title_input.value = "Launcher"
        await pilot.press("ctrl+period")
        await pilot.pause()
        launcher_select = app.screen.query_one("#task-launcher", Select)
        launcher_select.value = "vscode"
        await pilot.press("ctrl+s")
        await pilot.pause()

    results = await board.search_tasks("Launcher")
    assert len(results) == 1
    saved = await board.get_task(results[0].id)
    assert saved.launcher == "vscode"
