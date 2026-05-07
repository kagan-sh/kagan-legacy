"""Tests for multi-turn message queueing in ChatPanel.

While the agent is streaming a response the input stays enabled.  Messages
submitted during that window are held in a pending queue and drained
automatically once the turn completes.  Escape clears the queue.
"""

from __future__ import annotations

import asyncio

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path) -> KaganDriver:
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Queue Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})
    await driver.create_task("Queue task")
    yield driver  # type: ignore[misc]
    await driver.teardown()


async def test_input_remains_enabled_during_streaming(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Chat input widget stays enabled (not disabled) while the agent streams."""
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen

    reply_started = asyncio.Event()
    release_reply = asyncio.Event()

    async def fake_send_chat_message(*, core, panel, text, history):
        del core, text
        panel.set_runtime_status("thinking")
        reply_started.set()
        await release_reply.wait()
        panel.append_assistant_fragment("Done")
        panel.set_runtime_status("ready")
        return [*history, ("assistant", "Done")]

    monkeypatch.setattr(kanban_screen, "send_chat_message", fake_send_chat_message)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        await pilot.press("H", "i")
        await pilot.press("enter")

        await asyncio.wait_for(reply_started.wait(), timeout=2)
        # Input must remain enabled during streaming
        assert not input_widget.disabled

        release_reply.set()
        await pilot.pause()
        await pilot.pause()
        assert not input_widget.disabled


async def test_second_message_queued_and_drained(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A second message submitted while streaming is queued then sent after
    the first turn completes."""
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen
    from kagan.tui.widgets.chat import ChatPanel

    received: list[str] = []
    reply_started = asyncio.Event()
    release_reply = asyncio.Event()

    async def fake_send_chat_message(*, core, panel, text, history):
        del core
        received.append(text)
        panel.set_runtime_status("thinking")
        if len(received) == 1:
            reply_started.set()
            await release_reply.wait()
        panel.append_assistant_fragment(f"Echo: {text}")
        panel.set_runtime_status("ready")
        return [*history, ("user", text), ("assistant", f"Echo: {text}")]

    monkeypatch.setattr(kanban_screen, "send_chat_message", fake_send_chat_message)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "first message"
        await pilot.press("enter")

        await asyncio.wait_for(reply_started.wait(), timeout=2)

        # Submit second message while first is streaming
        input_widget.value = "second message"
        await pilot.press("enter")
        await pilot.pause()

        # Queue should hold the second message
        panel = app.screen.query_one(ChatPanel)
        assert panel.pending_queue_size() == 1

        # Release the first reply
        release_reply.set()
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        # Both messages should have been processed
        assert "first message" in received
        assert "second message" in received


async def test_escape_clears_pending_queue(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pressing Escape during streaming cancels the turn and clears the queue."""
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen
    from kagan.tui.widgets.chat import ChatPanel

    reply_started = asyncio.Event()
    release_reply = asyncio.Event()

    async def fake_send_chat_message(*, core, panel, text, history):
        del core, text
        panel.set_runtime_status("thinking")
        reply_started.set()
        await release_reply.wait()
        panel.append_assistant_fragment("Done")
        panel.set_runtime_status("ready")
        return [*history, ("assistant", "Done")]

    monkeypatch.setattr(kanban_screen, "send_chat_message", fake_send_chat_message)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "first"
        await pilot.press("enter")

        await asyncio.wait_for(reply_started.wait(), timeout=2)

        # Queue two more messages
        panel = app.screen.query_one(ChatPanel)
        input_widget.value = "second"
        await pilot.press("enter")
        await pilot.pause()
        input_widget.value = "third"
        await pilot.press("enter")
        await pilot.pause()

        assert panel.pending_queue_size() == 2

        # Escape (action_dismiss) should clear queue and interrupt
        panel.action_dismiss()
        await pilot.pause()

        assert panel.pending_queue_size() == 0

        release_reply.set()
        await pilot.pause()


async def test_queued_badge_shows_count(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The queue badge shows the number of queued messages and hides when empty."""
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen
    from kagan.tui.widgets.chat import ChatPanel

    reply_started = asyncio.Event()
    release_reply = asyncio.Event()

    async def fake_send_chat_message(*, core, panel, text, history):
        del core, text
        panel.set_runtime_status("thinking")
        reply_started.set()
        await release_reply.wait()
        panel.append_assistant_fragment("Done")
        panel.set_runtime_status("ready")
        return [*history, ("assistant", "Done")]

    monkeypatch.setattr(kanban_screen, "send_chat_message", fake_send_chat_message)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "trigger"
        await pilot.press("enter")

        await asyncio.wait_for(reply_started.wait(), timeout=2)

        # Queue two messages
        input_widget.value = "msg1"
        await pilot.press("enter")
        await pilot.pause()
        input_widget.value = "msg2"
        await pilot.press("enter")
        await pilot.pause()

        panel = app.screen.query_one(ChatPanel)
        assert panel.pending_queue_size() == 2

        badge = app.screen.query_one("#chat-overlay-queue-badge", Static)
        assert badge.display
        assert "2" in str(badge.content)

        # Release — queue drains
        release_reply.set()
        await pilot.pause()
        await pilot.pause()
        await pilot.pause()

        # After draining all messages, badge should hide
        assert panel.pending_queue_size() == 0
        await pilot.pause()
        assert not badge.display
