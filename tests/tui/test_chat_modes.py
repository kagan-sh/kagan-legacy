import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Chat Modes Project")
    await driver.create_task("Chat task")
    yield driver
    await driver.teardown()


async def test_ctrl_o_opens_chat_overlay_docked(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel")
        title = app.screen.query_one("#chat-title", Static)
        assert panel.has_class("visible")
        assert not panel.has_class("fullscreen")
        assert "Orchestrator" in str(title.content)


async def test_ctrl_p_opens_command_palette(board: KaganDriver) -> None:
    from textual.command import CommandPalette

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+p")
        await pilot.pause()

        assert isinstance(app.screen, CommandPalette)


async def test_ctrl_p_opens_chat_fullscreen(board: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+shift+t")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel")
        title = app.screen.query_one("#chat-title", Static)
        assert panel.has_class("visible")
        assert panel.has_class("fullscreen")
        assert "Orchestrator" in str(title.content)


async def test_fullscreen_toggle_preserves_session(board: KaganDriver) -> None:
    """Switching from docked overlay to fullscreen must not clear the stream."""
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        # Open docked overlay (orchestrator mode)
        await pilot.press("ctrl+t")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel")
        title = app.screen.query_one("#chat-title", Static)
        assert panel.has_class("visible")
        assert not panel.has_class("fullscreen")
        mode_before = str(title.content)

        # Switch to fullscreen — session/mode must be preserved
        await pilot.press("ctrl+shift+t")
        await pilot.pause()

        assert panel.has_class("visible")
        assert panel.has_class("fullscreen")
        assert str(title.content) == mode_before
