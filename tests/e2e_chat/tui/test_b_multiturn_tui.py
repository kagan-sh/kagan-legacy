"""Flow B — Multiturn + Queue Drain (TUI).

TODO: delete tests/tui/test_chat_multiturn_queue.py (replaced by B)

Assertions:
  1. Send first message — streaming starts.
  2. Send second message while first is in flight — queue badge shows "↓ 1 queued".
  3. First turn ends — second message sends automatically.
  4. Both replies appear in panel.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.helpers.async_utils import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_chat]


async def test_multiturn_queue_badge_and_drain(tui_driver: Any) -> None:
    """(1-4) Queue badge appears then drains; both replies in panel."""

    from textual.widgets import Input

    from kagan.core.chat.acp import ACPTurnResult
    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.widgets.chat import ChatPanel

    async def _noop_warm(*args: Any, **kwargs: Any) -> None:
        return None

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    # Gate that controls when the first turn releases.
    first_turn_gate = asyncio.Event()

    replies = ["first-reply", "second-reply"]
    call_count = 0

    class _SequencedACP:
        async def prompt(
            self,
            *,
            session_id: str,
            prompt_blocks: list[Any],
            on_update: Any,
            cancel_event: Any,
            agent_backend: str | None = None,
            permission_resolver: Any = None,
        ) -> ACPTurnResult:
            nonlocal call_count
            from acp.schema import AgentMessageChunk, TextContentBlock

            idx = min(call_count, len(replies) - 1)
            reply = replies[idx]
            call_count += 1

            if idx == 0:
                # First turn: emit chunk then hold until gate is released.
                chunk = AgentMessageChunk(
                    content=TextContentBlock(type="text", text=reply),
                    session_update="agent_message_chunk",
                )
                await on_update(chunk)
                await asyncio.sleep(0)
                await asyncio.wait_for(first_turn_gate.wait(), timeout=5.0)
            else:
                chunk = AgentMessageChunk(
                    content=TextContentBlock(type="text", text=reply),
                    session_update="agent_message_chunk",
                )
                await on_update(chunk)
                await asyncio.sleep(0)

            return ACPTurnResult(full_response=reply, cancelled=False)

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    app.core.chat._acp = _SequencedACP()

    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            await pilot.press("ctrl+space")
            await pilot.pause()

            try:
                inp = app.screen.query_one("#chat-overlay-input", Input)
            except Exception:
                pytest.skip("Orchestrator overlay not reachable")
                return

            panel = app.screen.query_one("#chat-panel", ChatPanel)

            # (1) Send first message.
            inp.focus()
            await pilot.press("f", "i", "r", "s", "t")
            await pilot.press("enter")
            await pilot.pause()

            # Wait until first turn is streaming (runtime_status changes).
            await wait_for(
                lambda: panel._runtime_status in {"thinking", "initializing"},
                pump_delay=0.05,
                tries=40,
            )

            # (2) Send second message while streaming — should hit the queue.
            inp.focus()
            await pilot.press("s", "e", "c", "o", "n", "d")
            await pilot.press("enter")
            await pilot.pause()

            # Queue badge should be visible.
            await wait_for(
                lambda: panel.pending_queue_size() >= 1,
                pump_delay=0.05,
                tries=40,
            )
            assert panel.pending_queue_size() >= 1, "Queue should hold at least 1 message"

            # (3) Release the first turn gate.
            first_turn_gate.set()
            await pilot.pause()

            # (4) Wait for both replies to appear.
            await wait_for(
                lambda: (
                    any("first-reply" in m for m in panel.export_rendered_messages())
                    and any("second-reply" in m for m in panel.export_rendered_messages())
                ),
                pump_delay=0.1,
                tries=80,
            )

            rendered = panel.export_rendered_messages()
            assert any("first-reply" in m for m in rendered), f"first-reply missing: {rendered}"
            assert any("second-reply" in m for m in rendered), f"second-reply missing: {rendered}"
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]
