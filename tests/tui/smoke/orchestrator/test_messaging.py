from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock, patch

import pytest
from textual.containers import Horizontal
from textual.widgets import Input, Static

from kagan.core.domain.enums import StreamPhase, TaskStatus, TaskType
from kagan.tui.ui.screens.kanban import KanbanScreen
from kagan.tui.ui.screens.task_output import TaskOutputScreen
from kagan.tui.ui.widgets.card import TaskCard
from kagan.tui.ui.widgets.chat_overlay import ChatOverlay
from kagan.tui.ui.widgets.status_bar import StatusBar
from kagan.tui.ui.widgets.streaming_output import StreamingOutput
from tests.helpers.wait import wait_for_screen, wait_until

from .conftest import (
    UI_TIMEOUT_BOOT,
    UI_TIMEOUT_LONG,
    UI_TIMEOUT_SHORT,
    _has_thinking_indicator,
    _open_task_output_via_enter,
    _wait_for_kanban_overlay,
)

pytestmark = pytest.mark.usefixtures("global_mock_tmux")


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
            timeout=UI_TIMEOUT_LONG,
            description="overlay to enter content mode",
        )
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)
        assert "Split this feature into tasks" in output.get_text_content()


@pytest.mark.asyncio
async def test_orchestrator_overlay_keeps_assistant_turns_in_separate_response_blocks(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Acknowledged.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        output = overlay.query_one("#chat-overlay-output", StreamingOutput)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)

        chat_input.focus()
        chat_input.value = "First turn"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: len(list(output.query(".agent-response"))) >= 1,
            timeout=UI_TIMEOUT_LONG,
            description="first assistant response block",
        )
        await wait_until(
            lambda: status_bar.status == "ready",
            timeout=UI_TIMEOUT_LONG,
            description="overlay status to return ready after first assistant turn",
        )
        await wait_until(
            lambda: not chat_input.disabled,
            timeout=UI_TIMEOUT_LONG,
            description="chat input to re-enable after first assistant turn",
        )

        chat_input.focus()
        chat_input.value = "Second turn"
        await pilot.pause()
        await pilot.press("enter")
        await wait_until(
            lambda: "Second turn" in output.get_text_content(),
            timeout=UI_TIMEOUT_LONG,
            description="second user turn to be appended to transcript",
        )
        await wait_until(
            lambda: len(list(output.query(".agent-response"))) >= 2,
            timeout=UI_TIMEOUT_LONG,
            description="second assistant response block rendered separately",
        )
        assert len(list(output.query(".agent-response"))) >= 2


@pytest.mark.asyncio
async def test_orchestrator_overlay_activity_status_reflects_thinking_state(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Acknowledged.")

    async with app.run_test(size=(120, 40)) as pilot:
        _kanban, overlay = await _wait_for_kanban_overlay(pilot)
        chat_input = overlay.query_one("#chat-overlay-input", Input)
        status_bar = overlay.query_one("#chat-overlay-status", StatusBar)

        await wait_until(
            lambda: status_bar.status == "ready",
            timeout=UI_TIMEOUT_LONG,
            description="orchestrator status to settle to ready before thinking assertions",
        )

        left_status = status_bar.query_one(".status-left", Static)
        assert "Ready" in str(left_status.render())

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
                description="orchestrator status to enter thinking mode for spinner label",
            )
            assert "Thinking" in str(left_status.render())
        finally:
            prompt_gate.set()
            await wait_until(
                lambda: status_bar.status in {"ready", "error"},
                timeout=UI_TIMEOUT_LONG,
                description="orchestrator status to settle after thinking assertions",
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
                timeout=UI_TIMEOUT_LONG,
                description="orchestrator status to enter initializing during reconnect",
            )
            assert chat_input.disabled is True
            assert status_bar.status == "initializing"
            connect_gate.set()
            await send_task
            assert chat_input.disabled is False
            await wait_until(
                lambda: status_bar.status == "ready",
                timeout=UI_TIMEOUT_LONG,
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
                timeout=UI_TIMEOUT_LONG,
                description="orchestrator status to enter thinking while awaiting response",
            )
            assert chat_input.disabled is True
            prompt_gate.set()
            await send_task
            assert chat_input.disabled is False
            await wait_until(
                lambda: app.focused is chat_input,
                timeout=UI_TIMEOUT_LONG,
                description="chat input to regain focus after orchestrator response completes",
            )
            await wait_until(
                lambda: status_bar.status == "ready",
                timeout=UI_TIMEOUT_LONG,
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
            timeout=UI_TIMEOUT_LONG,
            description="orchestrator status to enter thinking before timeout",
        )
        assert chat_input.disabled is True

        await send_task

        await wait_until(
            lambda: status_bar.status == "error",
            timeout=UI_TIMEOUT_LONG,
            description="orchestrator status to switch to error after timeout",
        )
        await wait_until(
            lambda: not _has_thinking_indicator(output),
            timeout=UI_TIMEOUT_LONG,
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
            timeout=UI_TIMEOUT_LONG,
            description="overlay status to return ready after empty completion",
        )
        await wait_until(
            lambda: not _has_thinking_indicator(output),
            timeout=UI_TIMEOUT_LONG,
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
            timeout=UI_TIMEOUT_LONG,
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
            timeout=UI_TIMEOUT_LONG,
            description="overlay status to move to error when send_prompt fails",
        )
        await wait_until(
            lambda: not _has_thinking_indicator(output),
            timeout=UI_TIMEOUT_LONG,
            description="thinking indicator to clear when send_prompt fails",
        )
        assert output.phase == StreamPhase.IDLE


@pytest.mark.asyncio
async def test_orchestrator_overlay_auto_session_streams_live_execution_logs(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
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
                    timeout=UI_TIMEOUT_SHORT,
                    description="overlay to close before AUTO Enter streaming test",
                )

            output_screen = await _open_task_output_via_enter(pilot, kanban, auto_task.id)
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            embedded_overlay.set_target_scope(auto_task.id)
            embedded_overlay.show_for_task(auto_task, fullscreen=False)
            await wait_until(
                lambda: embedded_overlay._active_target().task_id == auto_task.id,
                timeout=UI_TIMEOUT_SHORT,
                description="Task Output overlay to attach to AUTO task target",
            )
            output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)
            await wait_until(
                lambda: "AUTO live chunk" in output.get_text_content(),
                timeout=UI_TIMEOUT_SHORT,
                description="AUTO overlay session to render streamed execution log chunk",
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_auto_session_polling_renders_new_chunks_without_switch(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    from types import SimpleNamespace

    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        board_overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO delayed stream chunk",
            "Ensure overlay polling renders new chunks without switching sessions",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-live-delayed-001",
            is_running=True,
        )
        delayed_entry = SimpleNamespace(
            id="entry-live-delayed-001",
            logs='{"messages":[{"type":"response","content":"AUTO delayed chunk"}]}',
        )
        poll_count = {"value": 0}

        def _entries_side_effect(*_args, **_kwargs):
            poll_count["value"] += 1
            if poll_count["value"] < 2:
                return []
            return [delayed_entry]

        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "get_execution_log_entries",
                AsyncMock(side_effect=_entries_side_effect),
            ) as get_entries_mock,
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
                    timeout=UI_TIMEOUT_SHORT,
                    description="overlay to close before delayed AUTO stream test",
                )

            output_screen = await _open_task_output_via_enter(pilot, kanban, auto_task.id)
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            await wait_until(
                lambda: embedded_overlay.has_class("visible"),
                timeout=UI_TIMEOUT_SHORT,
                description="Task Output overlay to become visible for delayed stream polling",
            )

            output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)
            await wait_until(
                lambda: "AUTO delayed chunk" in output.get_text_content(),
                timeout=UI_TIMEOUT_LONG,
                description="AUTO overlay polling to render delayed stream chunk",
            )
            assert get_entries_mock.await_count >= 2


@pytest.mark.asyncio
async def test_orchestrator_overlay_auto_session_streams_appended_logs_for_same_entry(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        board_overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO appended stream entry",
            "Ensure appended logs on same entry id are rendered incrementally",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-live-append-001",
            is_running=True,
        )
        first_chunk = '{"messages":[{"type":"response","content":"AUTO chunk one"}]}'
        appended_chunk = (
            f'{first_chunk}\n{{"messages":[{{"type":"response","content":"AUTO chunk two"}}]}}'
        )
        stream_poll = {"count": 0}

        def _entries_side_effect(*_args, **_kwargs):
            stream_poll["count"] += 1
            logs = first_chunk if stream_poll["count"] <= 1 else appended_chunk
            return [SimpleNamespace(id="entry-live-append-001", logs=logs)]

        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "get_execution_log_entries",
                AsyncMock(side_effect=_entries_side_effect),
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
                    timeout=UI_TIMEOUT_SHORT,
                    description="overlay to close before AUTO appended stream test",
                )

            auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
            auto_card.focus()
            await pilot.pause()
            await pilot.press("o")

            output_screen = cast(
                "TaskOutputScreen",
                await wait_for_screen(pilot, TaskOutputScreen, timeout=UI_TIMEOUT_LONG),
            )
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)
            await embedded_overlay._refresh_auto_stream_for_task(auto_task.id)
            await embedded_overlay._refresh_auto_stream_for_task(auto_task.id)
            await wait_until(
                lambda: "AUTO chunk one" in output.get_text_content()
                and "AUTO chunk two" in output.get_text_content(),
                timeout=UI_TIMEOUT_LONG,
                description=(
                    "AUTO overlay session to render appended chunks for same execution log entry"
                ),
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_auto_session_shows_wait_note_before_first_log_chunk(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        board_overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO wait note before first stream chunk",
            "Ensure users see a waiting note while execution has no log chunks yet",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-wait-001",
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
            if board_overlay.has_class("visible"):
                await pilot.press("escape")
                await wait_until(
                    lambda: not board_overlay.has_class("visible"),
                    timeout=UI_TIMEOUT_SHORT,
                    description="overlay to close before AUTO wait-note stream test",
                )

            auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
            auto_card.focus()
            await pilot.pause()
            await pilot.press("o")

            output_screen = cast(
                "TaskOutputScreen",
                await wait_for_screen(pilot, TaskOutputScreen, timeout=UI_TIMEOUT_LONG),
            )
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)
            await wait_until(
                lambda: "waiting for first output chunk" in output.get_text_content().lower(),
                timeout=UI_TIMEOUT_LONG,
                description=(
                    "AUTO overlay session to show waiting note "
                    "when execution has no persisted chunks yet"
                ),
            )


@pytest.mark.asyncio
async def test_orchestrator_overlay_auto_session_wait_then_first_chunk_keeps_live_follow(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    from types import SimpleNamespace

    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        board_overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO wait then first chunk follow",
            "Ensure first arriving chunk auto-renders and keeps live follow without keypresses",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-wait-then-first-chunk-001",
            is_running=True,
        )
        first_chunk_entry = SimpleNamespace(
            id="entry-wait-then-first-chunk-001",
            logs='{"messages":[{"type":"response","content":"AUTO first chunk after wait"}]}',
        )
        poll_count = {"value": 0}

        def _entries_side_effect(*_args, **_kwargs):
            poll_count["value"] += 1
            if poll_count["value"] < 2:
                return []
            return [first_chunk_entry]

        with (
            patch.object(
                kanban.ctx.api,
                "prepare_auto_output",
                AsyncMock(return_value=readiness),
            ),
            patch.object(
                kanban.ctx.api,
                "get_execution_log_entries",
                AsyncMock(side_effect=_entries_side_effect),
            ) as get_entries_mock,
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
                    timeout=UI_TIMEOUT_SHORT,
                    description="overlay to close before AUTO wait-then-first-chunk follow test",
                )

            auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
            auto_card.focus()
            await pilot.pause()
            await pilot.press("o")

            output_screen = cast(
                "TaskOutputScreen",
                await wait_for_screen(pilot, TaskOutputScreen, timeout=UI_TIMEOUT_LONG),
            )
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)
            jump_row = output.query_one("#stream-live-jump-row", Horizontal)

            await wait_until(
                lambda: "waiting for first output chunk" in output.get_text_content().lower(),
                timeout=UI_TIMEOUT_LONG,
                description="AUTO stream to show wait note before first chunk",
            )
            await wait_until(
                lambda: "AUTO first chunk after wait" in output.get_text_content(),
                timeout=UI_TIMEOUT_LONG,
                description="AUTO stream to render first arriving chunk without session switch",
            )
            assert get_entries_mock.await_count >= 2
            assert output._follow_live_stream is True
            assert output._unread_events == 0
            assert not bool(jump_row.display)


@pytest.mark.asyncio
async def test_orchestrator_overlay_auto_session_renders_plain_text_execution_logs(
    e2e_app_with_tasks,
    mock_agent_factory,
) -> None:
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    app = e2e_app_with_tasks
    app._agent_factory = mock_agent_factory
    mock_agent_factory.set_default_response("Ready.")

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast(
            "KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=UI_TIMEOUT_BOOT)
        )
        board_overlay = kanban.query_one("#chat-overlay", ChatOverlay)
        project_id = app.ctx.active_project_id
        assert project_id is not None

        auto_task = await kanban.ctx.api.create_task(
            "AUTO plain text stream",
            "Ensure plain text execution logs are visible in AUTO session output",
            project_id=project_id,
            task_type=TaskType.AUTO,
        )
        await kanban.ctx.api.move_task(auto_task.id, TaskStatus.IN_PROGRESS.value)
        await kanban._board.refresh_board()

        readiness = SimpleNamespace(
            can_open_output=True,
            execution_id="exec-live-plain-001",
            is_running=True,
        )
        plain_text_line = "AUTO plain text log line"
        log_entry = SimpleNamespace(id="entry-live-plain-001", logs=plain_text_line)

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
                    timeout=UI_TIMEOUT_SHORT,
                    description="overlay to close before AUTO plain text stream test",
                )

            auto_card = kanban.query_one(f"#card-{auto_task.id}", TaskCard)
            auto_card.focus()
            await pilot.pause()
            await pilot.press("o")

            output_screen = cast(
                "TaskOutputScreen",
                await wait_for_screen(pilot, TaskOutputScreen, timeout=UI_TIMEOUT_LONG),
            )
            embedded_overlay = output_screen.query_one("#task-output-chat-overlay", ChatOverlay)
            output = embedded_overlay.query_one("#chat-overlay-output", StreamingOutput)
            await wait_until(
                lambda: plain_text_line in output.get_text_content(),
                timeout=UI_TIMEOUT_LONG,
                description="AUTO overlay session to render plain text execution log entry",
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

        async def _send_orchestrator_message_for_task(task_id: str) -> None:
            await pilot.press("escape")
            await wait_until(
                lambda: not overlay.has_class("visible"),
                timeout=UI_TIMEOUT_SHORT,
                description="overlay to close before focusing next task context",
            )
            task_card = kanban.query_one(f"#card-{task_id}", TaskCard)
            task_card.focus()
            await pilot.pause()
            overlay.show_for_task(task_card.task_model, fullscreen=False)
            await wait_until(
                lambda: overlay.has_class("visible"),
                timeout=UI_TIMEOUT_SHORT,
                description="overlay to reopen for selected task context",
            )

            chat_input = overlay.query_one("#chat-overlay-input", Input)
            await wait_until(
                lambda: chat_input.placeholder.startswith("Describe your task"),
                timeout=UI_TIMEOUT_LONG,
                description="orchestrator placeholder for task-scoped context",
            )
            chat_input.focus()
            chat_input.value = "persona check"
            await pilot.pause()
            await pilot.press("enter")

        with patch(
            "kagan.tui.ui.widgets.chat_overlay.build_orchestrator_prompt",
            side_effect=_fake_prompt_builder,
        ):
            await _send_orchestrator_message_for_task(worker_task.id)
            await wait_until(
                lambda: len(captured_personas) >= 1,
                timeout=UI_TIMEOUT_LONG,
                description="worker-context orchestrator prompt capture",
            )
            assert captured_personas[-1] == app.config.general.worker_persona

            await _send_orchestrator_message_for_task(review_task.id)
            await wait_until(
                lambda: len(captured_personas) >= 2,
                timeout=UI_TIMEOUT_LONG,
                description="review-context orchestrator prompt capture",
            )
            assert captured_personas[-1] == app.config.general.pr_reviewer_persona
