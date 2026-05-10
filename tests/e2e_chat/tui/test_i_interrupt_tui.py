"""Flow I — Interrupt / Stop Turn (TUI).

Assertions:
  1. ``slow`` scenario scheduled (holds until cancel_event).
  2. ChatPanel.action_dismiss() clears the pending queue during streaming.
  3. ``_pending_queue`` cleared after interrupt.
  4. Chat input re-enabled after engine cancel.

Implementation note: in the OrchestratorOverlay, ``escape`` is bound with
``priority=True`` to ``action_handle_esc`` which closes the overlay — it does
NOT delegate to ChatPanel.action_dismiss. To test the interrupt path, we call
``panel.action_dismiss()`` directly, which is the same code path the CHAT_BINDINGS
escape binding would invoke if the panel were embedded in the workspace screen.
"""

from __future__ import annotations

import asyncio
import contextlib
from typing import Any

import pytest

from tests.helpers.async_utils import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_chat]


async def test_interrupt_clears_queue_and_re_enables_input(
    tui_driver: Any,
) -> None:
    """(1-4) Slow turn interrupted; queue cleared; input re-enabled."""

    from textual.widgets import Input

    from kagan.core.chat.acp import ACPTurnResult
    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.widgets.chat import ChatPanel

    async def _noop_warm(*args: Any, **kwargs: Any) -> None:
        return None

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    # (1) Slow scenario: emit one chunk, then hold until cancel_event.
    first_chunk_arrived = asyncio.Event()

    class _SlowACP:
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
            from acp.schema import AgentMessageChunk, TextContentBlock

            chunk = AgentMessageChunk(
                content=TextContentBlock(type="text", text="thinking..."),
                session_update="agent_message_chunk",
            )
            await on_update(chunk)
            first_chunk_arrived.set()

            # Hold until cancelled.
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(cancel_event.wait(), timeout=10.0)
            return ACPTurnResult(full_response="thinking...", cancelled=True)

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    app.core.chat._acp = _SlowACP()

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

            # Send first message to start streaming.
            inp.focus()
            await pilot.press("h", "i")
            await pilot.press("enter")
            await pilot.pause()

            # Wait until streaming starts (first chunk visible).
            await asyncio.wait_for(first_chunk_arrived.wait(), timeout=5.0)
            await pilot.pause()

            assert panel._runtime_status in {"thinking", "initializing"}, (
                f"Expected streaming status, got: {panel._runtime_status}"
            )

            # While streaming, seed a queued message by typing and pressing enter.
            inp.focus()
            await pilot.press("q", "u", "e", "u", "e", "d")
            await pilot.press("enter")
            await pilot.pause()

            # Verify queue has something.
            await wait_for(
                lambda: panel.pending_queue_size() >= 1,
                pump_delay=0.05,
                tries=20,
            )
            assert panel.pending_queue_size() >= 1, "Expected queued message"

            # (2) Trigger interrupt via panel.action_dismiss() directly.
            # Note: in the OrchestratorOverlay, pressing escape closes the
            # overlay (priority=True binding). The panel's action_dismiss is
            # the correct seam for testing queue-clear + interrupt behavior.
            panel.action_dismiss()
            await pilot.pause()

            # (3) Queue cleared.
            await wait_for(
                lambda: panel.pending_queue_size() == 0,
                pump_delay=0.05,
                tries=40,
            )
            assert panel.pending_queue_size() == 0, (
                f"Pending queue not cleared: {panel._pending_queue}"
            )

            # Cancel the engine turn to release the slow ACP.
            session_id = app.orchestrator_sessions.current_session_id()
            if session_id:
                await app.core.chat.cancel(session_id)
            await pilot.pause()

            # (4) Input should be re-enabled (not in busy state).
            await wait_for(
                lambda: panel._runtime_status not in {"thinking", "initializing"},
                pump_delay=0.1,
                tries=60,
            )
            assert panel._runtime_status not in {"thinking", "initializing"}, (
                f"Panel still busy after interrupt: {panel._runtime_status}"
            )
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]
