from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, patch

import pytest
from textual.widgets import Input, OptionList, Static

from kagan.core.domain.enums import StreamPhase, TaskStatus, TaskType
from kagan.tui.ui.screens.kanban import KanbanScreen
from kagan.tui.ui.screens.task_output import TaskOutputScreen
from kagan.tui.ui.widgets.card import TaskCard
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay
from kagan.tui.ui.widgets.header import KaganHeader
from kagan.tui.ui.widgets.keybinding_hint import KanbanHintBar
from kagan.tui.ui.widgets.plan_approval import PlanApprovalWidget
from kagan.tui.ui.widgets.slash_complete import SlashComplete
from kagan.tui.ui.widgets.status_bar import StatusBar
from kagan.tui.ui.widgets.streaming_output import StreamingOutput, ThinkingIndicator
from tests.helpers.mock_responses import make_plan_submit_tool_call
from tests.helpers.wait import wait_for_screen, wait_for_widget, wait_until

if TYPE_CHECKING:
    from textual.pilot import Pilot

pytestmark = pytest.mark.usefixtures("global_mock_tmux")


async def _wait_for_kanban_overlay(
    pilot: Pilot, *, open_if_hidden: bool = True
) -> tuple[KanbanScreen, ChatOverlay]:
    kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=15.0))
    overlay = kanban.query_one("#chat-overlay", ChatOverlay)
    if open_if_hidden and not overlay.has_class("visible"):
        await pilot.press("ctrl+p")
    await wait_until(
        lambda: overlay.has_class("visible"),
        timeout=10.0,
        description="orchestrator overlay to become visible",
    )
    return kanban, overlay


def _has_slash_complete(overlay: ChatOverlay) -> bool:
    return bool(list(overlay.query(SlashComplete)))


def _has_thinking_indicator(output: StreamingOutput) -> bool:
    return bool(list(output.query(ThinkingIndicator)))


def _thinking_indicator_text(output: StreamingOutput) -> str:
    indicators = list(output.query(ThinkingIndicator))
    if not indicators:
        return ""
    return str(indicators[0].render())


@pytest.mark.asyncio
async def test_kanban_starts_on_board_when_tasks_exist(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=15.0))
        overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        assert not overlay.has_class("visible")
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert bool(hint_bar.display)


@pytest.mark.asyncio
async def test_orchestrator_overlay_defaults_to_fullscreen_intro_on_empty_board(
    e2e_app_without_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_without_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot, open_if_hidden=False)
        assert overlay.has_class("fullscreen")
        header = kanban.query_one(KaganHeader)
        assert overlay.region.y >= header.region.height
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert not bool(hint_bar.display)
        assert not overlay.has_class("has-content")
        heading = overlay.query_one("#chat-overlay-empty-heading", Static)
        assert str(overlay._INTRO_HEADING) in str(heading.render())


@pytest.mark.asyncio
async def test_orchestrator_overlay_mode_toggles_switch_and_close(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        assert overlay.has_class("fullscreen")
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert not bool(hint_bar.display)

        # Docked toggle: fullscreen -> docked
        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=5.0,
            description="overlay to switch from fullscreen to docked mode",
        )
        await wait_until(
            lambda: overlay.region.height > 0,
            timeout=5.0,
            description="docked overlay to complete layout",
        )
        assert not bool(hint_bar.display)
        assert overlay.region.y + overlay.region.height >= pilot.app.size.height - 1

        # Docked toggle again: docked -> board
        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to switch from docked to board mode",
        )
        assert bool(hint_bar.display)

        # Fullscreen toggle: board -> fullscreen
        kanban.action_open_chat_fullscreen()
        await wait_until(
            lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
            timeout=5.0,
            description="overlay to open fullscreen from board mode",
        )
        assert not bool(hint_bar.display)

        # Cross transition: fullscreen -> docked via docked toggle
        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=5.0,
            description="overlay to switch from fullscreen to docked via docked toggle",
        )

        # Cross transition: docked -> fullscreen via fullscreen toggle
        kanban.action_open_chat_fullscreen()
        await wait_until(
            lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
            timeout=5.0,
            description="overlay to switch from docked to fullscreen via fullscreen toggle",
        )

        # Fullscreen toggle again: fullscreen -> board
        kanban.action_open_chat_fullscreen()
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close fullscreen to board mode",
        )
        assert bool(hint_bar.display)


@pytest.mark.asyncio
async def test_orchestrator_overlay_hides_intro_after_first_message(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Acknowledged.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "Split this feature into tasks"
        await pilot.pause()
        await pilot.press("enter")

        await wait_until(
            lambda: overlay.has_class("has-content"),
            timeout=10.0,
            description="overlay to enter content mode",
        )
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)
        assert "Split this feature into tasks" in output.get_text_content()


@pytest.mark.asyncio
async def test_orchestrator_overlay_escape_closes_while_thinking(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_thinking("Thinking about the request...")
    mock_agent_factory.set_default_response("Acknowledged.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)

        chat_input.focus()
        chat_input.value = "Plan task changes"
        await pilot.pause()
        await pilot.press("enter")

        await wait_until(
            lambda: status_bar.status == "thinking",
            timeout=5.0,
            description="orchestrator status to enter thinking mode",
        )

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close with escape during thinking",
        )
        assert bool(hint_bar.display)

        await pilot.press("ctrl+p")
        await wait_until(
            lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
            timeout=5.0,
            description="overlay to reopen after thinking-mode escape",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_ctrl_c_single_clear_double_interrupts_stream(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_thinking("Thinking about the request...")
    mock_agent_factory.set_default_response("Acknowledged.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)

        chat_input.focus()
        chat_input.value = "Plan task changes"
        await pilot.pause()
        await pilot.press("enter")

        await wait_until(
            lambda: status_bar.status == "thinking",
            timeout=5.0,
            description="orchestrator status to enter thinking mode before Ctrl+C interrupt",
        )

        chat_input.focus()
        chat_input.value = "temporary draft"
        await pilot.pause()

        cancel_mock = AsyncMock()
        with (
            patch.object(overlay, "_cancel_active_prompt", cancel_mock),
            patch.object(overlay, "_is_double_ctrl_c_press", side_effect=[False, True]),
            patch.object(overlay, "_is_interruptible_stream_active", return_value=True),
        ):
            await pilot.press("ctrl+c")
            await wait_until(
                lambda: chat_input.value == "",
                timeout=5.0,
                description="single Ctrl+C to clear chat input",
            )

            await pilot.press("ctrl+c")
            await wait_until(
                lambda: cancel_mock.await_count >= 1,
                timeout=5.0,
                description="double Ctrl+C to interrupt active orchestrator stream",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_double_ctrl_c_ignored_when_not_streaming(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)

        await wait_until(
            lambda: status_bar.status == "ready",
            timeout=5.0,
            description="orchestrator status to be ready before Ctrl+C idle check",
        )

        cancel_mock = AsyncMock()
        with patch.object(overlay, "_cancel_active_prompt", cancel_mock):
            chat_input.focus()
            chat_input.value = "temporary draft"
            await pilot.pause()

            await pilot.press("ctrl+c")
            await wait_until(
                lambda: chat_input.value == "",
                timeout=5.0,
                description="single Ctrl+C to clear chat input while idle",
            )

            await pilot.press("ctrl+c")
            await pilot.pause()

        assert cancel_mock.await_count == 0


@pytest.mark.asyncio
async def test_board_quit_is_ctrl_q_not_q(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close before quit keybinding checks",
        )

        with patch.object(app, "exit") as exit_mock:
            await pilot.press("q")
            await pilot.pause()
            assert exit_mock.call_count == 0

            await pilot.press("ctrl+q")
            await wait_until(
                lambda: exit_mock.call_count >= 1,
                timeout=5.0,
                description="Ctrl+Q to dispatch app quit",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_shows_initializing_state_while_establishing_connection(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)

        connect_gate = asyncio.Event()

        class _ManualReadyAgent:
            async def send_prompt(self, _prompt: str) -> str | None:
                return "end_turn"

            def get_response_text(self) -> str:
                return ""

            def set_message_target(self, _target: object) -> None:
                return None

            async def stop(self) -> None:
                return None

        async def _delayed_ensure_agent() -> None:
            await connect_gate.wait()
            overlay._agent = _ManualReadyAgent()

        original_ensure_agent = overlay._ensure_agent
        overlay._agent = None
        overlay._ensure_agent = _delayed_ensure_agent

        try:
            send_task = asyncio.create_task(
                overlay._send_orchestrator_message("Reconnect orchestrator")
            )
            await wait_until(
                lambda: status_bar.status == "initializing",
                timeout=10.0,
                description="orchestrator status to enter initializing during reconnect",
            )
            assert chat_input.disabled is True
            await wait_until(
                lambda: "Initializing" in _thinking_indicator_text(output),
                timeout=10.0,
                description="chat output indicator to show initializing label",
            )
            connect_gate.set()
            await send_task
            assert chat_input.disabled is False
            await wait_until(
                lambda: status_bar.status == "ready",
                timeout=10.0,
                description="orchestrator status to transition back to ready after reconnect",
            )
        finally:
            overlay._ensure_agent = original_ensure_agent


@pytest.mark.asyncio
async def test_orchestrator_overlay_disables_input_while_waiting_for_response(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)

        prompt_gate = asyncio.Event()

        class _DelayedResponseAgent:
            async def send_prompt(self, _prompt: str) -> str | None:
                await prompt_gate.wait()
                return "end_turn"

            def get_response_text(self) -> str:
                return ""

            def set_message_target(self, _target: object) -> None:
                return None

            async def stop(self) -> None:
                return None

        overlay._agent = _DelayedResponseAgent()
        send_task = asyncio.create_task(overlay._send_orchestrator_message("Delayed response"))
        try:
            await wait_until(
                lambda: status_bar.status == "thinking",
                timeout=10.0,
                description="orchestrator status to enter thinking while awaiting response",
            )
            assert chat_input.disabled is True
            prompt_gate.set()
            await send_task
            assert chat_input.disabled is False
            await wait_until(
                lambda: app.focused is chat_input,
                timeout=10.0,
                description="chat input to regain focus after orchestrator response completes",
            )
            await wait_until(
                lambda: status_bar.status == "ready",
                timeout=10.0,
                description="orchestrator status to return ready after delayed response",
            )
        finally:
            prompt_gate.set()
            if not send_task.done():
                await send_task


@pytest.mark.asyncio
async def test_orchestrator_overlay_timeout_exits_thinking_and_unlocks_input(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)

        class _NeverReturnsAgent:
            async def send_prompt(self, _prompt: str) -> str | None:
                await asyncio.Future()
                return None

            def get_response_text(self) -> str:
                return ""

            async def cancel(self) -> bool:
                return True

            def set_message_target(self, _target: object) -> None:
                return None

            async def stop(self) -> None:
                return None

        overlay._agent = _NeverReturnsAgent()
        overlay._ORCHESTRATOR_PROMPT_TIMEOUT_SECONDS = 0.05

        send_task = asyncio.create_task(overlay._send_orchestrator_message("Timeout request"))
        await wait_until(
            lambda: status_bar.status == "thinking",
            timeout=10.0,
            description="orchestrator status to enter thinking before timeout",
        )
        assert chat_input.disabled is True

        await send_task

        await wait_until(
            lambda: status_bar.status == "error",
            timeout=10.0,
            description="orchestrator status to switch to error after timeout",
        )
        await wait_until(
            lambda: not _has_thinking_indicator(output),
            timeout=10.0,
            description="thinking indicator to clear after timeout",
        )
        assert chat_input.disabled is False


@pytest.mark.asyncio
async def test_orchestrator_overlay_clears_indicator_when_prompt_has_no_stream_output(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("")
    mock_agent_factory.set_default_thinking("")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)

        chat_input.focus()
        chat_input.value = "Respond with no visible output"
        await pilot.pause()
        await pilot.press("enter")

        await wait_until(
            lambda: status_bar.status == "ready",
            timeout=10.0,
            description="overlay status to return ready after empty completion",
        )
        await wait_until(
            lambda: not _has_thinking_indicator(output),
            timeout=10.0,
            description="thinking indicator to clear after empty completion",
        )
        assert output.phase == StreamPhase.IDLE


@pytest.mark.asyncio
async def test_orchestrator_overlay_clears_indicator_when_send_prompt_raises(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        await wait_until(
            lambda: mock_agent_factory.get_last_agent() is not None,
            timeout=10.0,
            description="overlay mock agent to initialize",
        )
        agent = mock_agent_factory.get_last_agent()
        assert agent is not None
        agent.send_prompt = AsyncMock(side_effect=RuntimeError("send failed in test"))

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)

        chat_input.focus()
        chat_input.value = "Trigger failure path"
        await pilot.pause()
        await pilot.press("enter")

        await wait_until(
            lambda: status_bar.status == "error",
            timeout=10.0,
            description="overlay status to move to error when send_prompt fails",
        )
        await wait_until(
            lambda: not _has_thinking_indicator(output),
            timeout=10.0,
            description="thinking indicator to clear when send_prompt fails",
        )
        assert output.phase == StreamPhase.IDLE


@pytest.mark.asyncio
async def test_orchestrator_overlay_shows_slash_popup_and_escape_dismisses_only_popup(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert not bool(hint_bar.display)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "/"

        await wait_until(
            lambda: _has_slash_complete(overlay),
            timeout=5.0,
            description="slash complete popup to appear",
        )

        await pilot.press("escape")
        await wait_until(
            lambda: not _has_slash_complete(overlay),
            timeout=5.0,
            description="slash complete popup to close on escape",
        )
        assert overlay.has_class("visible")
        assert chat_input.value == ""
        assert not bool(hint_bar.display)


@pytest.mark.asyncio
async def test_orchestrator_overlay_slash_popup_enter_runs_highlighted_command(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert not bool(hint_bar.display)

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "/"

        await wait_until(
            lambda: _has_slash_complete(overlay),
            timeout=5.0,
            description="slash complete popup to appear for enter selection",
        )

        slash_complete = overlay.query_one(SlashComplete)
        option_list = slash_complete.query_one("#slash-options", OptionList)
        help_index = next(
            (
                index
                for index, option in enumerate(option_list.options)
                if getattr(option, "id", None) == "help"
            ),
            None,
        )
        assert help_index is not None
        option_list.highlighted = help_index

        await pilot.press("enter")
        await wait_until(
            lambda: not _has_slash_complete(overlay),
            timeout=5.0,
            description="slash complete popup to close on enter selection",
        )

        output = overlay.query_one("#chat-overlay-output", StreamingOutput)
        await wait_until(
            lambda: "Available Commands" in output.get_text_content(),
            timeout=10.0,
            description="slash popup enter selection to execute /help",
        )
        assert overlay.has_class("visible")
        assert not bool(hint_bar.display)


@pytest.mark.asyncio
async def test_orchestrator_overlay_slash_popup_overlays_footer_and_supports_paging(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "/"

        await wait_until(
            lambda: _has_slash_complete(overlay),
            timeout=5.0,
            description="slash complete popup to appear for overlay/footer assertions",
        )

        slash_complete = overlay.query_one(SlashComplete)
        option_list = slash_complete.query_one("#slash-options", OptionList)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)
        chat_input = overlay.query_one("#chat-overlay-input", Input)

        await wait_until(
            lambda: option_list.region.height > 0 and slash_complete.region.height > 0,
            timeout=5.0,
            description="slash popup layout to settle",
        )

        # Popup should sit over footer/status area instead of pushing layout.
        assert slash_complete.region.y <= status_bar.region.y
        assert status_bar.region.y < slash_complete.region.y + slash_complete.region.height
        # Popup must not overlap the chat input row.
        assert slash_complete.region.y + slash_complete.region.height <= chat_input.region.y

        # Default popup height reserves six visible rows.
        assert option_list.region.height == 6
        assert option_list.highlighted == 0

        await pilot.press("end")
        assert option_list.highlighted is not None
        await pilot.press("pageup")
        assert option_list.highlighted is not None
        await pilot.press("pagedown")
        assert option_list.highlighted is not None
        await pilot.press("home")
        assert option_list.highlighted == 0


@pytest.mark.asyncio
async def test_orchestrator_overlay_help_slash_command_posts_command_reference(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "/help"
        await pilot.pause()
        await pilot.press("enter")

        output = overlay.query_one("#chat-overlay-output", StreamingOutput)
        await wait_until(
            lambda: (
                "Available Commands" in output.get_text_content()
                and "/clear" in output.get_text_content()
                and "/mode" in output.get_text_content()
            ),
            timeout=10.0,
            description="/help output to render available command list",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_tab_switches_to_auto_target_when_available(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "Auto task for chat target switch",
            "Created by test",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        await pilot.pause()
        await pilot.press("tab")

        await wait_until(
            lambda: "AUTO #" in chat_input.placeholder,
            timeout=10.0,
            description="chat target to switch to AUTO task on tab",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_renders_plan_approval_from_tool_calls(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Here's a plan.")
    mock_agent_factory.set_default_tool_calls(
        make_plan_submit_tool_call(
            tool_call_id="tc-orchestrator-plan-001",
            tasks=[
                {
                    "title": "Create orchestrator smoke coverage",
                    "type": "AUTO",
                    "description": "Add tests for docked/fullscreen overlay behavior.",
                    "acceptance_criteria": [
                        "Overlay opens fullscreen on board entry",
                        "Ctrl+P/Ctrl+O toggle orchestrator modes",
                    ],
                    "priority": "high",
                }
            ],
        )
    )

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)
        await wait_until(
            lambda: status_bar.status == "ready",
            timeout=10.0,
            description="orchestrator status to become ready",
        )
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        chat_input.value = "Plan this work"
        await pilot.pause()
        await pilot.press("enter")

        await wait_for_widget(pilot, "PlanApprovalWidget", timeout=20.0)
        overlay.query_one(PlanApprovalWidget)


@pytest.mark.asyncio
async def test_orchestrator_overlay_escape_closes_and_board_keys_work_again(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        hint_bar = kanban.query_one("#kanban-hint-bar", KanbanHintBar)
        assert not bool(hint_bar.display)

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        chat_input.focus()
        await pilot.pause()
        await pilot.press("escape")

        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close on escape",
        )
        await wait_until(
            lambda: bool(hint_bar.display),
            timeout=5.0,
            description="hint bar to become visible after overlay closes",
        )

        await pilot.press("ctrl+p")
        await wait_until(
            lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
            timeout=5.0,
            description="board Ctrl+P binding to reopen fullscreen overlay",
        )
        await wait_until(
            lambda: not bool(hint_bar.display),
            timeout=5.0,
            description="hint bar to hide when fullscreen overlay is visible",
        )

        await pilot.press("ctrl+o")
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=5.0,
            description="Ctrl+O to switch fullscreen overlay to docked mode",
        )
        assert not bool(hint_bar.display)

        await pilot.press("ctrl+o")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="board Ctrl+O binding to close docked overlay",
        )
        await wait_until(
            lambda: bool(hint_bar.display),
            timeout=5.0,
            description="hint bar to become visible after docked overlay closes",
        )

        await pilot.press("ctrl+o")
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=5.0,
            description="board Ctrl+O binding to reopen docked overlay",
        )
        assert not bool(hint_bar.display)

        await pilot.press("ctrl+p")
        await wait_until(
            lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
            timeout=5.0,
            description="Ctrl+P to switch docked overlay to fullscreen mode",
        )
        assert not bool(hint_bar.display)

        await pilot.press("ctrl+p")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="board Ctrl+P binding to close fullscreen overlay",
        )
        await wait_until(
            lambda: bool(hint_bar.display),
            timeout=5.0,
            description="hint bar to become visible after fullscreen overlay closes",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_routes_review_task_to_session_flow(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        review_task = await kanban.ctx.api.create_task(
            "Review target from Enter",
            "Ensure Enter routes REVIEW tasks through session flow",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.REVIEW.value)
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close before Enter opens focused review context",
        )

        review_card = kanban.query_one(f"#card-{review_task.id}", TaskCard)
        review_card.focus()
        await pilot.pause()
        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            await pilot.press("enter")
            await wait_until(
                lambda: open_session_mock.await_count >= 1,
                timeout=10.0,
                description="Enter to route REVIEW task through session flow",
            )
            called_task = open_session_mock.await_args.args[0]
            assert called_task.id == review_task.id
            assert not overlay.has_class("visible")


@pytest.mark.asyncio
async def test_review_shortcut_routes_to_review_stream_not_overlay(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        review_task = await kanban.ctx.api.create_task(
            "Review shortcut target",
            "Ensure r routes REVIEW task to review stream",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.REVIEW.value)
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close before pressing review shortcut",
        )

        review_card = kanban.query_one(f"#card-{review_task.id}", TaskCard)
        review_card.focus()
        await pilot.pause()
        with patch.object(kanban._review, "action_open_review", autospec=True) as open_review_mock:
            await pilot.press("r")
            await wait_until(
                lambda: open_review_mock.await_count >= 1,
                timeout=10.0,
                description="'r' to route REVIEW task to review stream",
            )
            assert not overlay.has_class("visible")


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_routes_pair_task_to_session_flow(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        pair_task = await kanban.ctx.api.create_task(
            "PAIR backlog enter target",
            "Ensure Enter routes PAIR tasks through session flow",
            project_id=project_id,
            task_type=TaskType.PAIR,
        )
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close before opening pair backlog context",
        )

        pair_card = kanban.query_one(f"#card-{pair_task.id}", TaskCard)
        pair_card.focus()
        await pilot.pause()
        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            await pilot.press("enter")
            await wait_until(
                lambda: open_session_mock.await_count >= 1,
                timeout=10.0,
                description="Enter to route PAIR task through session flow",
            )
            called_task = open_session_mock.await_args.args[0]
            assert called_task.id == pair_task.id
            assert not overlay.has_class("visible")


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_uses_last_focused_pair_task_when_focus_clears(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        pair_task = await kanban.ctx.api.create_task(
            "PAIR enter fallback target",
            "Ensure Enter still opens the last focused PAIR task when focus clears",
            project_id=project_id,
            task_type=TaskType.PAIR,
        )
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close before validating Enter fallback behavior",
        )

        pair_card = kanban.query_one(f"#card-{pair_task.id}", TaskCard)
        pair_card.focus()
        await wait_until(
            lambda: kanban.last_focused_task_id == pair_task.id,
            timeout=5.0,
            description="PAIR card focus to update remembered task id",
        )

        kanban.app.set_focus(None)
        await pilot.pause()

        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            await pilot.press("enter")
            await wait_until(
                lambda: open_session_mock.await_count >= 1,
                timeout=10.0,
                description="Enter to use remembered PAIR task when focus is temporarily cleared",
            )
            called_task = open_session_mock.await_args.args[0]
            assert called_task.id == pair_task.id


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_ignores_repeated_open_session_while_loading(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        pair_task = await kanban.ctx.api.create_task(
            "PAIR enter loading guard",
            "Ensure repeated Enter does not queue concurrent open-session workers",
            project_id=project_id,
            task_type=TaskType.PAIR,
        )
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close before validating repeated Enter guard",
        )

        pair_card = kanban.query_one(f"#card-{pair_task.id}", TaskCard)
        pair_card.focus()
        await pilot.pause()

        open_started = asyncio.Event()
        allow_complete = asyncio.Event()

        async def _block_open_session(task: object) -> None:
            del task
            open_started.set()
            await allow_complete.wait()

        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            open_session_mock.side_effect = _block_open_session

            await pilot.press("enter")
            await wait_until(
                lambda: open_started.is_set(),
                timeout=10.0,
                description="first Enter to start open-session flow",
            )

            await pilot.press("enter")
            await pilot.pause()
            assert open_session_mock.await_count == 1

            allow_complete.set()
            await wait_until(
                lambda: all(
                    worker.group != "open-session" or worker.is_finished
                    for worker in kanban.workers
                ),
                timeout=10.0,
                description="open-session worker to finish cleanly after guarded Enter",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_routes_backlog_auto_task_to_session_flow(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO backlog enter starts task",
            "Ensure Enter routes backlog AUTO tasks through session flow",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban._board.refresh_board()

        await pilot.press("escape")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=5.0,
            description="overlay to close before pressing Enter on AUTO backlog task",
        )

        auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
        auto_card.focus()
        await pilot.pause()

        with patch.object(kanban._session, "open_session_flow", autospec=True) as open_session_mock:
            await pilot.press("enter")
            await wait_until(
                lambda: open_session_mock.await_count >= 1,
                timeout=10.0,
                description="Enter to route AUTO backlog task through session flow",
            )
            called_task = open_session_mock.await_args.args[0]
            assert called_task.id == auto_task.id
            assert not overlay.has_class("visible")


@pytest.mark.asyncio
async def test_orchestrator_overlay_backlog_auto_confirmed_start_passes_start_requested_flag(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=15.0))
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO backlog confirm start",
            "Ensure confirmed backlog start carries start_requested state to output opening",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban._board.refresh_board()

        auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
        auto_card.focus()
        await pilot.pause()

        with (
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban._session,
                "confirm_start_auto_task",
                AsyncMock(return_value=True),
            ),
            patch.object(
                kanban._session,
                "start_agent_flow",
                AsyncMock(return_value=True),
            ) as start_agent_mock,
            patch.object(
                kanban._session,
                "_open_auto_output_after_start",
                AsyncMock(),
            ) as open_after_start_mock,
        ):
            await pilot.press("enter")
            await wait_until(
                lambda: open_after_start_mock.await_count >= 1,
                timeout=10.0,
                description="backlog AUTO Enter to open output after confirmed start",
            )
            called_task = start_agent_mock.await_args.args[0]
            assert called_task.id == auto_task.id
            called_after_task = open_after_start_mock.await_args.args[0]
            assert called_after_task.id == auto_task.id
            assert open_after_start_mock.await_args.kwargs["start_requested"] is True


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_opens_auto_chat_session(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=15.0))
        board_overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO enter opens chat session",
            "Ensure Enter opens orchestrator chat in AUTO session",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        if board_overlay.has_class("visible"):
            await pilot.press("escape")
            await wait_until(
                lambda: not board_overlay.has_class("visible"),
                timeout=5.0,
                description="overlay to close before Enter opens AUTO chat session",
            )

        auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
        auto_card.focus()
        await pilot.pause()
        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-open-001",
            is_running=True,
        )
        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "get_execution_log_entries",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
        ):
            await pilot.press("enter")
            output_screen = cast(
                "TaskOutputScreen",
                await wait_for_screen(pilot, TaskOutputScreen, timeout=10.0),
            )
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            await wait_until(
                lambda: embedded_overlay.has_class("visible")
                and not embedded_overlay.has_class("fullscreen"),
                timeout=10.0,
                description="AUTO Enter to open session overlay in Task Output screen",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_enter_opens_task_output_when_auto_idle(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=15.0))
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO enter opens idle task output",
            "Ensure Enter opens split task output even before a live run starts",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
        auto_card.focus()
        await pilot.pause()
        readiness = SimpleNamespace(
            can_open_output=False,
            execution_id=None,
            is_running=False,
            message="No active AUTO run.",
        )
        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
        ):
            await pilot.press("enter")
            output_screen = cast(
                "TaskOutputScreen",
                await wait_for_screen(pilot, TaskOutputScreen, timeout=10.0),
            )
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            await wait_until(
                lambda: embedded_overlay.has_class("visible")
                and not embedded_overlay.has_class("fullscreen"),
                timeout=10.0,
                description="AUTO Enter to open split task output even when idle",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_task_output_ctrl_p_cycles_split_fullscreen_and_board(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=15.0))
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO output Ctrl+P cycle",
            "Ensure Ctrl+P cycles split view, fullscreen session, then board",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
        auto_card.focus()
        await pilot.pause()
        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-cycle-001",
            is_running=True,
        )
        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "get_execution_log_entries",
                AsyncMock(return_value=[]),
            ),
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
        ):
            await pilot.press("enter")
            output_screen = cast(
                "TaskOutputScreen",
                await wait_for_screen(pilot, TaskOutputScreen, timeout=10.0),
            )
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)

            assert not output_screen.has_class("task-output-terminal-fullscreen")
            assert not embedded_overlay.has_class("fullscreen")

            await pilot.press("ctrl+p")
            await wait_until(
                lambda: output_screen.has_class("task-output-terminal-fullscreen")
                and embedded_overlay.has_class("fullscreen"),
                timeout=10.0,
                description="Ctrl+P to switch split task output to fullscreen terminal",
            )

            await pilot.press("ctrl+p")
            await wait_until(
                lambda: not output_screen.has_class("task-output-terminal-fullscreen")
                and not embedded_overlay.has_class("fullscreen"),
                timeout=10.0,
                description="Ctrl+P to return fullscreen terminal back to split task output",
            )

            await pilot.press("ctrl+p")
            await wait_for_screen(pilot, KanbanScreen, timeout=10.0)


@pytest.mark.asyncio
async def test_orchestrator_overlay_auto_session_streams_live_execution_logs(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=15.0))
        board_overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO live stream in overlay",
            "Ensure AUTO session streams execution logs",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-live-001",
            is_running=True,
        )
        log_entry = SimpleNamespace(
            id="entry-live-001",
            logs='{"messages":[{"type":"response","content":"AUTO live chunk"}]}',
        )

        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "get_execution_log_entries",
                AsyncMock(return_value=[log_entry]),
            ),
            patch.object(
                kanban.ctx.api,
                "reconcile_running_tasks",
                AsyncMock(return_value=[]),
            ),
        ):
            if board_overlay.has_class("visible"):
                await pilot.press("escape")
                await wait_until(
                    lambda: not board_overlay.has_class("visible"),
                    timeout=5.0,
                    description="overlay to close before AUTO Enter streaming test",
                )

            auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
            auto_card.focus()
            await pilot.pause()
            await pilot.press("enter")

            output_screen = cast(
                "TaskOutputScreen",
                await wait_for_screen(pilot, TaskOutputScreen, timeout=10.0),
            )
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)
            await wait_until(
                lambda: "AUTO live chunk" in output.get_text_content(),
                timeout=10.0,
                description="AUTO overlay session to render streamed execution log chunk",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_docked_allows_start_agent_shortcut_on_backlog_auto(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO backlog start agent via key",
            "Ensure 'a' works with docked overlay and focused card",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban._board.refresh_board()

        await pilot.press("ctrl+o")
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=5.0,
            description="switch overlay from fullscreen to docked mode",
        )

        auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
        auto_card.focus()
        await pilot.pause()

        with patch.object(kanban._session, "start_agent_flow", autospec=True) as start_agent_mock:
            await pilot.press("a")
            await wait_until(
                lambda: start_agent_mock.await_count >= 1,
                timeout=10.0,
                description="'a' to dispatch start_agent for focused AUTO backlog card",
            )
            called_task = start_agent_mock.await_args.args[0]
            assert called_task.id == auto_task.id


@pytest.mark.asyncio
async def test_orchestrator_overlay_slash_session_commands(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO target for slash attach",
            "Validate /browse and /attach",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        chat_input = overlay.query_one("#chat-overlay-input", Input)
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)

        chat_input.focus()
        chat_input.value = "/browse"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: auto_task.id in output.get_text_content(),
            timeout=10.0,
            description="/browse to list AUTO task chat target",
        )

        chat_input.focus()
        chat_input.value = f"/attach {auto_task.id}"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: "AUTO #" in chat_input.placeholder,
            timeout=10.0,
            description="/attach to switch active target to AUTO task",
        )

        chat_input.focus()
        chat_input.value = "/new session"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: not overlay.has_class("has-content"),
            timeout=10.0,
            description="/new session to clear overlay transcript",
        )

        chat_input.focus()
        chat_input.value = "/clear all sessions"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: chat_input.placeholder.startswith("Describe your task"),
            timeout=10.0,
            description="/clear all sessions to reset active chat target",
        )


@pytest.mark.asyncio
async def test_orchestrator_overlay_uses_task_scoped_persona(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban, overlay = await _wait_for_kanban_overlay(pilot)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        worker_task = await kanban.ctx.api.create_task(
            "Worker persona target",
            "Use worker persona for in-progress task",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(worker_task.id, TaskStatus.IN_PROGRESS.value)

        review_task = await kanban.ctx.api.create_task(
            "Reviewer persona target",
            "Use reviewer persona for review task",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban.ctx.api.move_task(review_task.id, TaskStatus.REVIEW.value)
        await kanban._board.refresh_board()

        captured_personas: list[str | None] = []

        def _fake_prompt_builder(
            _user_input: str,
            conversation_history: list[tuple[str, str]] | None = None,
            *,
            session_snapshot: str | None = None,
            persona: str | None = None,
        ) -> str:
            del conversation_history, session_snapshot
            captured_personas.append(persona)
            return "persona-check-prompt"

        async def _send_orchestrator_message_for_task(task_id: str, expected_target: str) -> None:
            await pilot.press("escape")
            await wait_until(
                lambda: not overlay.has_class("visible"),
                timeout=5.0,
                description="overlay to close before focusing next task context",
            )
            task_card = kanban.query_one(f"#card-{task_id}", TaskCard)
            task_card.focus()
            await pilot.pause()
            overlay.show_for_task(task_card.task_model, fullscreen=False)
            await wait_until(
                lambda: overlay.has_class("visible"),
                timeout=5.0,
                description="overlay to reopen for selected task context",
            )

            chat_input = overlay.query_one("#chat-overlay-input", Input)
            await wait_until(
                lambda: expected_target in chat_input.placeholder,
                timeout=10.0,
                description="task-specific target placeholder",
            )
            chat_input.focus()
            chat_input.value = "/attach orchestrator"
            await pilot.pause()
            await pilot.press("enter")
            await wait_until(
                lambda: chat_input.placeholder.startswith("Describe your task"),
                timeout=10.0,
                description="/attach orchestrator to switch back to orchestrator chat",
            )
            chat_input.focus()
            chat_input.value = "persona check"
            await pilot.pause()
            await pilot.press("enter")

        with patch(
            "kagan.tui.ui.widgets.chat_overlay.build_orchestrator_prompt",
            side_effect=_fake_prompt_builder,
        ):
            await _send_orchestrator_message_for_task(worker_task.id, "AUTO #")
            await wait_until(
                lambda: len(captured_personas) >= 1,
                timeout=10.0,
                description="worker-context orchestrator prompt capture",
            )
            assert captured_personas[-1] == app.config.general.worker_persona

            await _send_orchestrator_message_for_task(review_task.id, "REVIEW #")
            await wait_until(
                lambda: len(captured_personas) >= 2,
                timeout=10.0,
                description="review-context orchestrator prompt capture",
            )
            assert captured_personas[-1] == app.config.general.pr_reviewer_persona
