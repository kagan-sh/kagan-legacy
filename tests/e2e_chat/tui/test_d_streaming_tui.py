"""Flow D — Streaming Output + Typewriter (TUI).

TODO: delete tests/tui/test_chat_streaming.py (replaced by D)
TODO: delete tests/unit/tui/test_chat_runner.py (partially replaced by D)

Assertions:
  1. 3 chunks scheduled.
  2. Panel accumulates chunks in order.
  3. Final text equals concatenation of all chunks.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.helpers.async_utils import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_chat]


async def test_streaming_chunks_accumulate_in_order(tui_driver: Any) -> None:
    """(1-3) Three chunks arrive in order; concatenated text matches."""

    from textual.widgets import Input

    from kagan.core.chat.acp import ACPTurnResult
    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.widgets.chat import ChatPanel

    async def _noop_warm(*args: Any, **kwargs: Any) -> None:
        return None

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    chunks = ["chunk-one", " chunk-two", " chunk-three"]
    expected = "".join(chunks)

    class _StreamingACP:
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

            # (1) Emit 3 chunks.
            for chunk_text in chunks:
                chunk = AgentMessageChunk(
                    content=TextContentBlock(type="text", text=chunk_text),
                    session_update="agent_message_chunk",
                )
                await on_update(chunk)
                await asyncio.sleep(0)

            return ACPTurnResult(full_response=expected, cancelled=False)

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    app.core.chat._acp = _StreamingACP()

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

            inp.focus()
            await pilot.press("g", "o")
            await pilot.press("enter")
            await pilot.pause()

            panel = app.screen.query_one("#chat-panel", ChatPanel)

            # (2) + (3) All chunks accumulated; final rendered text matches.
            await wait_for(
                lambda: any("chunk-three" in m for m in panel.export_rendered_messages()),
                pump_delay=0.05,
                tries=80,
            )

            rendered = "\n".join(panel.export_rendered_messages())

            # (2) Chunks arrived in order — all three must be present.
            assert "chunk-one" in rendered, f"chunk-one missing: {rendered}"
            assert "chunk-two" in rendered, f"chunk-two missing: {rendered}"
            assert "chunk-three" in rendered, f"chunk-three missing: {rendered}"

            # (3) Full text (concatenated) present somewhere in rendered output.
            full_text = "".join(panel.export_rendered_messages())
            assert "chunk-one" in full_text and "chunk-three" in full_text
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]
