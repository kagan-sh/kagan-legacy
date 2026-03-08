import asyncio

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Chat Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})
    await driver.create_task("Chat task")
    await driver.create_task("Chat task 2")
    yield driver
    await driver.teardown()


async def test_ctrl_o_cycles_chat_panel_vertical_horizontal_off(board: KaganDriver) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test(size=(100, 20)) as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        chat_panel = app.screen.query_one("#chat-panel")
        assert chat_panel.has_class("visible")
        assert app.screen.has_class("chat-overlay-vertical")
        assert str(chat_panel.styles.layer) == "default"
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert chat_panel.has_class("visible")
        assert app.screen.has_class("chat-overlay-horizontal")
        assert str(chat_panel.styles.layer) == "default"
        board_widget = app.screen.query_one("#board-container")
        assert board_widget.region.height > 0
        assert board_widget.region.height >= (chat_panel.region.height - 1)
        await pilot.press("ctrl+t")
        await pilot.pause()
        assert not chat_panel.has_class("visible")


async def test_horizontal_to_vertical_transition_restores_valid_board_height(
    board: KaganDriver,
) -> None:
    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        await pilot.press("ctrl+t")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        chat_panel = app.screen.query_one("#chat-panel")
        board_widget = app.screen.query_one("#board-container")
        horizontal_board_height = board_widget.region.height
        assert app.screen.has_class("chat-overlay-horizontal")
        assert horizontal_board_height > 0

        await pilot.press("ctrl+shift+t")
        await pilot.pause()
        assert chat_panel.has_class("fullscreen")

        await pilot.press("ctrl+t")
        await pilot.pause()
        assert chat_panel.has_class("visible")
        assert not chat_panel.has_class("fullscreen")
        assert app.screen.has_class("chat-overlay-vertical")

        assert board_widget.region.height > 0
        assert board_widget.region.height > horizontal_board_height


async def test_chat_overlay_keeps_empty_board_review_hint_visible(tmp_path) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Empty Chat Overlay Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()

        hint = app.screen.query_one("#review-queue-hint", Static)
        assert hint.has_class("visible")
        assert hint.display

        await pilot.press("ctrl+t")
        await pilot.pause()

        assert app.screen.has_class("chat-overlay-visible")
        assert hint.display
        hint_text = str(hint.render())
        assert "No tasks yet." in hint_text
        assert "type in chat" in hint_text

        await pilot.press("ctrl+t")
        await pilot.pause()

        assert not app.screen.has_class("chat-overlay-visible")
        assert not app.screen.has_class("chat-overlay-horizontal")
        assert hint.display

    await driver.teardown()


async def test_send_message_updates_chat_output(board: KaganDriver) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        app.screen.query_one("#chat-overlay-input", Input).focus()
        await pilot.press("H", "i")
        await pilot.press("enter")
        await pilot.pause()
        message_output = app.screen.query_one("#chat-messages", Static)
        assert "Hi" in str(message_output.content)


async def test_chat_input_history_loops_with_up_and_down(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen

    async def fake_send_chat_message(*, core, panel, text, history):
        del core
        panel.append_assistant_fragment(f"Echo: {text}")
        panel.set_runtime_status("ready")
        return [*history, ("user", text), ("assistant", f"Echo: {text}")]

    monkeypatch.setattr(kanban_screen, "send_chat_message", fake_send_chat_message)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        for prompt in ("first", "second", "third"):
            input_widget.value = prompt
            await pilot.press("enter")
            await pilot.pause()

        assert input_widget.value == ""

        await pilot.press("up")
        await pilot.pause()
        assert input_widget.value == "third"

        await pilot.press("up")
        await pilot.pause()
        assert input_widget.value == "second"

        await pilot.press("up")
        await pilot.pause()
        assert input_widget.value == "first"

        await pilot.press("up")
        await pilot.pause()
        assert input_widget.value == "third"

        await pilot.press("down")
        await pilot.pause()
        assert input_widget.value == "first"


async def test_ctrl_c_clears_chat_input_and_hint_is_visible(board: KaganDriver) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        status_hint = app.screen.query_one("#chat-overlay-status-right", Static)
        assert "Ctrl+C clear" in str(status_hint.content)

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "clear me"
        await pilot.press("ctrl+c")
        await pilot.pause()

        assert input_widget.value == ""


async def test_kanban_boot_starts_orchestrator_warmup(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Warmup Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})

    warmed_backends: list[str] = []

    async def fake_warm_orchestrator_backend(core, *, agent_backend: str) -> None:
        del core
        warmed_backends.append(agent_backend)

    monkeypatch.setattr(kanban_screen, "warm_orchestrator_backend", fake_warm_orchestrator_backend)

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.pause()

    assert warmed_backends
    await driver.teardown()


async def test_board_orchestrator_message_does_not_fall_back_to_task_chat(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen
    from kagan.tui.widgets.chat import ChatPanel

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Empty Chat Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})

    async def fake_send_chat_message(*, core, panel, text, history):
        del core
        panel.append_assistant_fragment(f"Echo: {text}")
        return [*history, ("user", text), ("assistant", f"Echo: {text}")]

    monkeypatch.setattr(kanban_screen, "send_chat_message", fake_send_chat_message)

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        app.screen.query_one("#chat-overlay-input", Input).focus()
        await pilot.press("H", "i")
        await pilot.press("enter")
        await pilot.pause()

        # Flush the deferred hidden-buffer update (debounced at 500ms)
        panel = app.screen.query_one("#chat-panel", ChatPanel)
        panel._flush_deferred()
        await pilot.pause()

        message_output = app.screen.query_one("#chat-messages", Static)
        rendered = str(message_output.content)
        assert "Echo: Hi" in rendered
        assert "No selected task" not in rendered
        assert "Select a task first" not in rendered

    await driver.teardown()


async def test_chat_input_is_disabled_while_orchestrator_reply_is_running(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Chat Lock Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})

    reply_started = asyncio.Event()
    release_reply = asyncio.Event()

    async def fake_send_chat_message(*, core, panel, text, history):
        del core, text
        panel.set_runtime_status("thinking")
        reply_started.set()
        await release_reply.wait()
        panel.append_assistant_fragment("Echo")
        panel.set_runtime_status("ready")
        return [*history, ("assistant", "Echo")]

    monkeypatch.setattr(kanban_screen, "send_chat_message", fake_send_chat_message)

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        await pilot.press("H", "i")
        await pilot.press("enter")

        await asyncio.wait_for(reply_started.wait(), timeout=1)
        assert input_widget.disabled

        release_reply.set()
        await pilot.pause()
        await pilot.pause()
        assert not input_widget.disabled

    await driver.teardown()


async def test_slash_clear_resets_chat_output(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen

    async def fake_send_chat_message(*, core, panel, text, history):
        del core
        panel.append_assistant_fragment(f"Echo: {text}")
        panel.set_runtime_status("ready")
        return [*history, ("user", text), ("assistant", f"Echo: {text}")]

    monkeypatch.setattr(kanban_screen, "send_chat_message", fake_send_chat_message)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        app.screen.query_one("#chat-overlay-input", Input).focus()
        await pilot.press("H", "i")
        await pilot.press("enter")
        await pilot.pause()
        app.screen.query_one("#chat-overlay-input", Input).value = "/clear"
        await pilot.press("enter")
        await pilot.pause()
        message_output = app.screen.query_one("#chat-messages", Static)
        assert "No messages" in str(message_output.content)


async def test_ctrl_k_opens_session_picker_modal(board: KaganDriver) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens.session_picker import SessionPickerModal

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        app.screen.query_one("#chat-overlay-input", Input).focus()
        await pilot.press("ctrl+k")
        await pilot.pause()
        assert isinstance(app.screen, SessionPickerModal)


async def test_slash_sessions_opens_session_picker_modal(board: KaganDriver) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens.session_picker import SessionPickerModal

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "/sessions"
        await pilot.press("enter")
        await pilot.pause()
        assert isinstance(app.screen, SessionPickerModal)


async def test_session_picker_groups_task_sessions_by_ticket_and_role(board: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        panel.set_sessions(
            [
                ("Orchestrator", "orchestrator"),
                ("Ticket Alpha · Worker", "task-worker"),
                ("Ticket Alpha · Reviewer", "task-reviewer"),
            ],
            "task-worker",
        )
        modal = panel.create_session_picker_modal()

        labels = [group.label for group in modal._all_groups]
        assert "Task Targets" not in labels
        assert "Ticket Alpha" in labels

        ticket_group = next(group for group in modal._all_groups if group.label == "Ticket Alpha")
        option_labels = [option.label for option in ticket_group.options]
        assert "Ticket Alpha · Worker" in option_labels
        assert "Ticket Alpha · Reviewer" in option_labels


async def test_slash_flow_adds_guided_messages(board: KaganDriver) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "/flow Build onboarding"
        await pilot.press("enter")
        await pilot.pause()

        message_output = app.screen.query_one("#chat-messages", Static)
        rendered = str(message_output.content)
        assert "Plan -> Execute -> Orchestrate" in rendered
        assert "Goal: Build onboarding" in rendered


async def test_slash_sessions_delete_shows_explicit_repl_only_message(board: KaganDriver) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "/sessions delete abc123"
        await pilot.press("enter")
        await pilot.pause()

        message_output = app.screen.query_one("#chat-messages", Static)
        assert "Session deletion is currently available in REPL only" in str(message_output.content)


async def test_slash_exit_closes_chat_panel_and_updates_layout(board: KaganDriver) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        chat_panel = app.screen.query_one("#chat-panel")
        assert chat_panel.has_class("visible")
        assert app.screen.has_class("chat-overlay-visible")

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        input_widget.value = "/exit"
        await pilot.press("enter")
        await pilot.pause()

        assert not chat_panel.has_class("visible")
        assert not app.screen.has_class("chat-overlay-visible")


async def test_chat_stays_visible_and_content_persists_on_card_navigation(
    board: KaganDriver,
) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        app.screen.query_one("#chat-overlay-input", Input).focus()
        await pilot.press("P", "i", "n", "n", "e", "d")
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("j")
        await pilot.pause()
        chat_panel = app.screen.query_one("#chat-panel")
        message_output = app.screen.query_one("#chat-messages", Static)
        assert chat_panel.has_class("visible")
        assert "Pinned" in str(message_output.content)


async def test_tab_from_chat_input_does_not_open_session_picker_modal(board: KaganDriver) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens.session_picker import SessionPickerModal

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        assert app.screen.focused is input_widget

        await pilot.press("tab")
        await pilot.pause()

        assert not isinstance(app.screen, SessionPickerModal)
        assert app.screen.focused is input_widget


async def test_tab_from_fullscreen_chat_input_does_not_open_session_picker_modal(
    board: KaganDriver,
) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens.session_picker import SessionPickerModal

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+shift+t")
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        assert app.screen.focused is input_widget

        await pilot.press("tab")
        await pilot.pause()

        assert not isinstance(app.screen, SessionPickerModal)
        assert app.screen.focused is input_widget


async def test_ctrl_o_focuses_input_when_no_tasks(tmp_path) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Empty Overlay Focus Project")
    await driver.settings_update({"ui.tui_tutorial_seen": "true"})

    app = KaganApp(db_path=driver.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        assert app.screen.focused is input_widget

    await driver.teardown()


async def test_tool_call_upsert_reuses_existing_widget_without_duplicate_ids(
    board: KaganDriver,
) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.streaming import StreamingOutput

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        panel.upsert_tool_call("tool-1", "Search", status="running")
        await pilot.pause()
        panel.upsert_tool_call("tool-1", "Search", status="failed")
        await pilot.pause()

        stream = app.screen.query_one("#chat-overlay-output", StreamingOutput)
        assert len(stream._tool_calls) == 1
        assert stream._tool_calls["tool-1"].status == "failed"


async def test_tool_call_details_render_literal_brackets_without_markup_crash(
    board: KaganDriver,
) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.streaming import StreamingOutput

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        panel.upsert_tool_call(
            "tool-1",
            "Search",
            status="completed",
            args='{"query": "[literal-brackets]"}',
            result='src/file.py:10: yield Select(["a"], value="a")',
        )
        await pilot.pause()

        stream = app.screen.query_one("#chat-overlay-output", StreamingOutput)
        body = stream._tool_calls["tool-1"].query_one("#tool-call-body", Static)
        rendered = str(body.content)
        assert "[literal-brackets]" in rendered
        assert 'yield Select(["a"]' in rendered


async def test_tool_call_header_renders_command_like_text_without_markup_crash(
    board: KaganDriver,
) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.streaming import StreamingOutput

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        panel.upsert_tool_call(
            "tool-2",
            "Run git",
            status="completed",
            args=('{"command": ["/bin/zsh", "-lc", "git -c user.name=\\"Kagan Agent\\" status"]}'),
        )
        await pilot.pause()

        stream = app.screen.query_one("#chat-overlay-output", StreamingOutput)
        header = stream._tool_calls["tool-2"].query_one("#tool-call-header", Static)
        rendered = str(header.content)
        assert "Run git" in rendered
        assert "command:" in rendered
        assert "Kagan Agent" in rendered


async def test_expanded_tool_call_details_stay_scroll_bounded(board: KaganDriver) -> None:
    from textual.containers import ScrollableContainer

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.streaming import StreamingOutput

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()
        await pilot.press("ctrl+shift+t")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        long_output = "\n".join(f"line {index} " + ("x" * 420) for index in range(80))
        panel.upsert_tool_call(
            "tool-3",
            "Large output",
            status="completed",
            result=long_output,
        )
        await pilot.pause()

        stream = app.screen.query_one("#chat-overlay-output", StreamingOutput)
        stream_body = stream.query_one("#streaming-body", ScrollableContainer)
        tool_widget = stream._tool_calls["tool-3"]
        tool_widget.action_toggle_expand()
        await pilot.pause()

        details = tool_widget.query_one("#tool-content", ScrollableContainer)
        assert details.display
        assert details.region.y >= stream_body.region.y
        assert details.region.height <= stream_body.region.height
        assert (
            details.region.y + details.region.height
            <= stream_body.region.y + stream_body.region.height
        )
        assert details.region.height < panel.region.height
        assert details.virtual_size.height > details.region.height
        assert details.virtual_size.width <= details.region.width


async def test_runtime_status_update_is_safe_when_status_bar_missing(board: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        status_bar = app.screen.query_one("#chat-overlay-status")
        status_bar.remove()
        await pilot.pause()

        panel.set_runtime_status("ready")


async def test_stream_updates_are_safe_when_stream_output_missing(board: KaganDriver) -> None:
    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        output = app.screen.query_one("#chat-overlay-output")
        output.remove()
        await pilot.pause()

        panel.set_stream_action("Waiting for prompt", confidence="certain")
        panel.append_assistant_fragment("partial")
        panel.upsert_tool_call("tool-1", "Search", status="running")
        panel.update_tool_call("tool-1", "completed", result="ok")


async def test_orchestrator_sessions_persist_across_tui_restart_and_can_switch_back(
    board: KaganDriver,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from textual.widgets import Input, Select, Static

    from kagan.tui import KaganApp
    from kagan.tui.screens import kanban as kanban_screen
    from kagan.tui.widgets.chat import ChatPanel

    async def fake_send_chat_message(*, core, panel, text, history):
        del core
        panel.append_assistant_fragment(f"Echo: {text}")
        panel.set_runtime_status("ready")
        return [*history, ("user", text), ("assistant", f"Echo: {text}")]

    monkeypatch.setattr(kanban_screen, "send_chat_message", fake_send_chat_message)

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        selector = app.screen.query_one("#chat-overlay-session-select", Select)
        first_key = str(selector.value)

        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        await pilot.press("A", "l", "p", "h", "a")
        await pilot.press("enter")
        await pilot.pause()

        input_widget.value = "/new"
        await pilot.press("enter")
        await pilot.pause()

        second_key = str(selector.value)
        assert second_key != first_key

        await pilot.press("B", "e", "t", "a")
        await pilot.press("enter")
        await pilot.pause()

    app2 = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app2.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+t")
        await pilot.pause()

        selector = app2.screen.query_one("#chat-overlay-session-select", Select)
        assert str(selector.value) == second_key

        selector.value = first_key
        await pilot.pause()

        panel = app2.screen.query_one("#chat-panel", ChatPanel)
        panel._flush_deferred()
        await pilot.pause()

        message_output = app2.screen.query_one("#chat-messages", Static)
        assert "Echo: Alpha" in str(message_output.content)
