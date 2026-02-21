from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from textual.widgets import Input

from kagan.core.domain.enums import TaskType
from kagan.tui.ui.widgets.keybinding_hint import KanbanHintBar
from kagan.tui.ui.widgets.status_bar import StatusBar
from tests.helpers.wait import wait_until

from .conftest import (
    UI_TIMEOUT_LONG,
    UI_TIMEOUT_SHORT,
    _wait_for_kanban_overlay,
)

pytestmark = pytest.mark.usefixtures("global_mock_tmux")


@pytest.mark.asyncio
async def test_orchestrator_overlay_escape_interrupts_while_thinking_and_keeps_overlay_open(
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

        try:
            chat_input.focus()
            chat_input.value = "Plan task changes"
            await pilot.pause()
            await pilot.press("enter")

            await wait_until(
                lambda: status_bar.status == "thinking",
                timeout=UI_TIMEOUT_LONG,
                description="orchestrator status to enter thinking mode",
            )

            cancel_mock = AsyncMock()
            with patch.object(overlay, "_cancel_active_prompt", cancel_mock):
                await pilot.press("escape")
                await wait_until(
                    lambda: cancel_mock.await_count >= 1,
                    timeout=UI_TIMEOUT_SHORT,
                    description="Escape to interrupt active orchestrator stream",
                )
            assert overlay.has_class("visible")
            assert not bool(hint_bar.display)
        finally:
            prompt_gate.set()
            await wait_until(
                lambda: status_bar.status in {"ready", "error"},
                timeout=UI_TIMEOUT_LONG,
                description="orchestrator status to settle after escape interrupt test",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_ctrl_c_clears_input_without_interrupting_stream(
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

        try:
            chat_input.focus()
            chat_input.value = "Plan task changes"
            await pilot.pause()
            await pilot.press("enter")

            await wait_until(
                lambda: status_bar.status == "thinking",
                timeout=UI_TIMEOUT_LONG,
                description="orchestrator status to enter thinking mode before Ctrl+C clear check",
            )

            chat_input.focus()
            chat_input.value = "temporary draft"
            await pilot.pause()

            cancel_mock = AsyncMock()
            with patch.object(overlay, "_cancel_active_prompt", cancel_mock):
                await pilot.press("ctrl+c")
                await wait_until(
                    lambda: chat_input.value == "",
                    timeout=UI_TIMEOUT_SHORT,
                    description="single Ctrl+C to clear chat input",
                )

                await pilot.press("ctrl+c")
                await pilot.pause()
            assert cancel_mock.await_count == 0
            assert overlay.has_class("visible")
        finally:
            prompt_gate.set()
            await wait_until(
                lambda: status_bar.status in {"ready", "error"},
                timeout=UI_TIMEOUT_LONG,
                description="orchestrator status to settle after Ctrl+C clear test",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_ctrl_c_repeat_ignored_when_not_streaming(
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
            timeout=UI_TIMEOUT_SHORT,
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
                timeout=UI_TIMEOUT_SHORT,
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
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close before quit keybinding checks",
        )

        with patch.object(app, "exit") as exit_mock:
            await pilot.press("q")
            await pilot.pause()
            assert exit_mock.call_count == 0

            await pilot.press("ctrl+q")
            await wait_until(
                lambda: exit_mock.call_count >= 1,
                timeout=UI_TIMEOUT_SHORT,
                description="Ctrl+Q to dispatch app quit",
            )


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
            timeout=UI_TIMEOUT_SHORT,
            description="overlay to close on escape",
        )
        await wait_until(
            lambda: bool(hint_bar.display),
            timeout=UI_TIMEOUT_SHORT,
            description="hint bar to become visible after overlay closes",
        )

        await pilot.press("ctrl+p")
        await wait_until(
            lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="board Ctrl+P binding to reopen fullscreen overlay",
        )
        await wait_until(
            lambda: not bool(hint_bar.display),
            timeout=UI_TIMEOUT_SHORT,
            description="hint bar to hide when fullscreen overlay is visible",
        )

        await pilot.press("ctrl+o")
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="Ctrl+O to switch fullscreen overlay to docked mode",
        )
        assert not bool(hint_bar.display)

        await pilot.press("ctrl+o")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="board Ctrl+O binding to close docked overlay",
        )
        await wait_until(
            lambda: bool(hint_bar.display),
            timeout=UI_TIMEOUT_SHORT,
            description="hint bar to become visible after docked overlay closes",
        )

        await pilot.press("ctrl+o")
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="board Ctrl+O binding to reopen docked overlay",
        )
        assert not bool(hint_bar.display)

        await pilot.press("ctrl+p")
        await wait_until(
            lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="Ctrl+P to switch docked overlay to fullscreen mode",
        )
        assert not bool(hint_bar.display)

        await pilot.press("ctrl+p")
        await wait_until(
            lambda: not overlay.has_class("visible"),
            timeout=UI_TIMEOUT_SHORT,
            description="board Ctrl+P binding to close fullscreen overlay",
        )
        await wait_until(
            lambda: bool(hint_bar.display),
            timeout=UI_TIMEOUT_SHORT,
            description="hint bar to become visible after fullscreen overlay closes",
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

        if not overlay.has_class("fullscreen"):
            kanban.action_open_chat_fullscreen()
            await wait_until(
                lambda: overlay.has_class("visible") and overlay.has_class("fullscreen"),
                timeout=UI_TIMEOUT_SHORT,
                description="normalize overlay to fullscreen before docked toggle",
            )

        kanban.action_toggle_chat_overlay()
        await wait_until(
            lambda: overlay.has_class("visible") and not overlay.has_class("fullscreen"),
            timeout=UI_TIMEOUT_SHORT,
            description="switch overlay from fullscreen to docked mode",
        )

        from kagan.tui.ui.widgets.card import TaskCard

        auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
        auto_card.focus()
        await pilot.pause()

        with patch.object(kanban._session, "start_agent_flow", autospec=True) as start_agent_mock:
            await pilot.press("a")
            await wait_until(
                lambda: start_agent_mock.await_count >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="'a' to dispatch start_agent for focused AUTO backlog card",
            )
            called_task = start_agent_mock.await_args.args[0]
            assert called_task.id == auto_task.id
