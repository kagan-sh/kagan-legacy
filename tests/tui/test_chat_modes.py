import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


async def test_ctrl_period_opens_chat_overlay_docked(board_with_task: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+period")
        await pilot.pause()
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel")
        title = app.screen.query_one("#chat-title", Static)
        assert panel.has_class("visible")
        assert not panel.has_class("fullscreen")
        assert "Orchestrator" in str(title.content)


async def test_f4_opens_chat_overlay_docked(board_with_task: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("f4")
        await pilot.pause()
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel")
        title = app.screen.query_one("#chat-title", Static)
        assert panel.has_class("visible")
        assert not panel.has_class("fullscreen")
        assert "Orchestrator" in str(title.content)


async def test_ctrl_p_opens_command_palette(board_with_task: KaganDriver) -> None:
    from textual.command import CommandPalette

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+shift+p")
        await pilot.pause()

        assert isinstance(app.screen, CommandPalette)


async def test_ctrl_p_opens_chat_fullscreen(board_with_task: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
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


async def test_fullscreen_toggle_preserves_session(board_with_task: KaganDriver) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board_with_task.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel")
        title = app.screen.query_one("#chat-title", Static)
        assert panel.has_class("visible")
        assert not panel.has_class("fullscreen")
        mode_before = str(title.content)

        await pilot.press("ctrl+shift+t")
        await pilot.pause()

        assert panel.has_class("visible")
        assert panel.has_class("fullscreen")
        assert str(title.content) == mode_before
