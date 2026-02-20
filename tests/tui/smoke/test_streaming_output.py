from __future__ import annotations

import pytest
from textual.app import App, ComposeResult
from textual.containers import Vertical

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
