"""Feature tests: Session and Backend — TUI integration."""

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Session Project")
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    await driver.add_repo(repo_path)
    await driver.create_task("Attached task", launcher="tmux")
    yield driver
    await driver.teardown()


async def test_ctrl_r_opens_repo_picker_modal(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause()
        assert app.screen.id == "repo-picker-modal"


async def test_repo_picker_lists_project_repositories(board: KaganDriver) -> None:
    from textual.widgets import OptionList

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+r")
        await pilot.pause()
        repo_list = app.screen.query_one("#repo-picker-list", OptionList)
        assert repo_list.option_count >= 1


def test_tmux_session_name_uses_session_id() -> None:
    from kagan.tui.screens.kanban import KanbanScreen

    assert KanbanScreen._tmux_session_name("session:abc123") == "kagan-session-abc123"
