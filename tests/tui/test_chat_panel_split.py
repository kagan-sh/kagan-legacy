"""Unit tests for the R1 phase 4b ChatPanel split.

Verifies the three new widget classes (ChatTranscript, ChatInput,
ChatSessionMenu) are mounted in their expected DOM positions, that delegated
helpers route through them, and that user-visible behaviors that previously
went through ChatPanel still produce the same observable effects.
"""

from __future__ import annotations

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Split Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})
    await driver.create_task("Split task")
    yield driver
    await driver.teardown()


async def test_chat_transcript_handles_assistant_chunk(board: KaganDriver) -> None:
    """append_assistant_fragment() must reach the streaming output owned by
    the ChatTranscript subtree.
    """
    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.chat_transcript import ChatTranscript

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+period")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        transcript = app.screen.query_one("#chat-overlay-content", ChatTranscript)
        assert isinstance(transcript, ChatTranscript)

        panel.append_assistant_fragment("Hello world")
        await pilot.pause()

        rendered = panel.export_rendered_messages()
        assert any("Hello world" in line for line in rendered)


async def test_chat_input_query_helpers_route_through_subclass(
    board: KaganDriver,
) -> None:
    """ChatInput exposes the input widget; ChatPanel's _input_widget must
    return the same Input instance via the new subclass.
    """
    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.chat_input import ChatInput

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+period")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        chat_input = app.screen.query_one("#chat-overlay-command-line", ChatInput)
        assert isinstance(chat_input, ChatInput)

        # Both helpers must agree.
        assert chat_input.input_widget() is panel._input_widget()

        # Driving value through ChatInput must be visible to ChatPanel.
        chat_input.value = "/help"
        assert panel._input_widget().value == "/help"


async def test_chat_session_menu_owns_selector_and_label(board: KaganDriver) -> None:
    """ChatSessionMenu owns the session selector and current-label widget;
    ChatPanel's _session_selector must route through it.
    """
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.chat_session_menu import ChatSessionMenu

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+period")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        menu = app.screen.query_one("#chat-overlay-session-switcher", ChatSessionMenu)
        assert isinstance(menu, ChatSessionMenu)

        assert menu.session_selector() is panel._session_selector()
        label_widget = menu.current_label_widget()
        assert isinstance(label_widget, Static)

        # Setting the label through the menu must reflect what the panel sees.
        menu.set_current_label("Custom Session")
        assert "Custom Session" in str(label_widget.content)
