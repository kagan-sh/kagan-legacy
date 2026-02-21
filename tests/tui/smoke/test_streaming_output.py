from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from kagan.core.domain.enums import StreamPhase
from kagan.core.wire.events import AgentCompleted, AgentFailed
from kagan.tui.ui.widgets.streaming_output import StreamingOutput, ThinkingIndicator
from tests.helpers.wait import wait_until


class _StreamingOutputHarness(App[None]):
    def compose(self) -> ComposeResult:
        with Vertical():
            yield StreamingOutput(id="output")


def _has_thinking_indicator(output: StreamingOutput) -> bool:
    return bool(list(output.query(ThinkingIndicator)))


@pytest.mark.asyncio
async def test_streaming_output_clears_indicator_on_agent_completed_event() -> None:
    app = _StreamingOutputHarness()

    async with app.run_test(size=(100, 20)):
        output = app.query_one("#output", StreamingOutput)
        await output.post_thinking_indicator()
        assert _has_thinking_indicator(output)
        assert output.phase == StreamPhase.THINKING

        handled = await output.dispatch_wire_event(AgentCompleted(task_id="task-1", outcome="done"))
        assert handled

        await wait_until(
            lambda: not _has_thinking_indicator(output),
            timeout=5.0,
            description="thinking indicator to clear on AgentCompleted",
        )
        assert output.phase == StreamPhase.IDLE


@pytest.mark.asyncio
async def test_streaming_output_clears_indicator_on_agent_failed_event() -> None:
    app = _StreamingOutputHarness()

    async with app.run_test(size=(100, 20)):
        output = app.query_one("#output", StreamingOutput)
        await output.post_thinking_indicator()
        assert _has_thinking_indicator(output)
        assert output.phase == StreamPhase.THINKING

        handled = await output.dispatch_wire_event(AgentFailed(task_id="task-2", error="boom"))
        assert handled

        await wait_until(
            lambda: not _has_thinking_indicator(output),
            timeout=5.0,
            description="thinking indicator to clear on AgentFailed",
        )
        assert output.phase == StreamPhase.IDLE


@pytest.mark.asyncio
async def test_streaming_output_updates_status_on_completion() -> None:
    app = _StreamingOutputHarness()

    async with app.run_test(size=(100, 20)):
        output = app.query_one("#output", StreamingOutput)
        await output.post_user_input("Ship this change")

        action = output.query_one("#stream-current-action", Static)
        assert "Queued user request" in str(action.render())

        handled = await output.dispatch_wire_event(AgentCompleted(task_id="task-1", outcome="done"))
        assert handled

        summary_cards = list(output.query(".stream-summary-card"))
        assert not summary_cards
        assert "Run completed" in str(action.render())


@pytest.mark.asyncio
async def test_streaming_output_shows_jump_to_live_when_scrolled_up() -> None:
    app = _StreamingOutputHarness()

    async with app.run_test(size=(70, 12)):
        output = app.query_one("#output", StreamingOutput)
        for index in range(64):
            await output.post_note(f"Line {index}", classes="info")

        await wait_until(
            lambda: output.max_scroll_y > 0,
            timeout=5.0,
            description="output to have scrollable history",
        )
        output.scroll_to(y=0, animate=False, immediate=True, release_anchor=True)
        await wait_until(
            lambda: output.scroll_y <= 1,
            timeout=5.0,
            description="output to reach top of scrollback",
        )
        output._follow_live_stream = False
        output._sync_live_jump()

        await output.post_note("Latest update", classes="info")

        jump_row = output.query_one("#stream-live-jump-row", Horizontal)
        jump_button = output.query_one("#stream-jump-live-btn", Button)
        assert bool(jump_row.display)
        assert "Jump to latest" in str(jump_button.label)

        output.action_jump_to_live()
        await wait_until(
            lambda: not bool(jump_row.display),
            timeout=5.0,
            description="jump-to-live indicator to hide after jumping",
        )


@pytest.mark.asyncio
async def test_streaming_output_keeps_following_after_jump_to_live() -> None:
    app = _StreamingOutputHarness()

    async with app.run_test(size=(70, 12)):
        output = app.query_one("#output", StreamingOutput)
        for index in range(64):
            await output.post_note(f"Bootstrap {index}", classes="info")

        await wait_until(
            lambda: output.max_scroll_y > 0,
            timeout=5.0,
            description="output to have scrollable history",
        )
        output.scroll_to(y=0, animate=False, immediate=True, release_anchor=True)
        await wait_until(
            lambda: output.scroll_y <= 1,
            timeout=5.0,
            description="output to scroll away from live edge",
        )
        output._follow_live_stream = False
        output._sync_live_jump()
        await output.post_note("Unread marker", classes="info")

        jump_row = output.query_one("#stream-live-jump-row", Horizontal)
        assert bool(jump_row.display)

        output.action_jump_to_live()
        await wait_until(
            lambda: not bool(jump_row.display),
            timeout=5.0,
            description="jump row to hide after returning to live edge",
        )

        current_scroll_y = output.scroll_y
        for index in range(6):
            await output.post_note(f"Live follow {index}", classes="info")
        await wait_until(
            lambda: output.scroll_y >= current_scroll_y,
            timeout=5.0,
            description="output to continue auto-following after jump-to-live",
        )
        assert not bool(jump_row.display)
