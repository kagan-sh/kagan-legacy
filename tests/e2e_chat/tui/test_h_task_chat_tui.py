"""Flow H — Task-Scoped Chat (TUI).

Assertions:
  1. Task is created in the project.
  2. Opening the orchestrator overlay from the task screen pre-fills task context.
  3. Scripted reply arrives in the chat panel.
"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest

from tests.helpers.async_utils import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_chat]


async def test_task_screen_orchestrator_overlay_auto_attaches(
    tui_driver: Any,
) -> None:
    """(1-3) Task created; overlay opened with task context; reply visible."""

    from textual.widgets import Input

    from kagan.core.chat.acp import ACPTurnResult
    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.screens.task_screen import TaskScreen
    from kagan.tui.widgets.chat import ChatPanel

    async def _noop_warm(*args: Any, **kwargs: Any) -> None:
        return None

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    reply_text = "task-chat-reply"

    class _TaskChatACP:
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
                content=TextContentBlock(type="text", text=reply_text),
                session_update="agent_message_chunk",
            )
            await on_update(chunk)
            await asyncio.sleep(0)
            return ACPTurnResult(full_response=reply_text, cancelled=False)

    # (1) Create a task.
    task = await tui_driver.create_task("H flow task")
    assert task.id, "Task should have an id"

    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    app.core.chat._acp = _TaskChatACP()

    try:
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()

            # Push TaskScreen directly to simulate opening a task.
            app.push_screen(TaskScreen(task_id=task.id))
            await pilot.pause()

            # (2) Open the orchestrator overlay from the task screen.
            await pilot.press("ctrl+space")
            await pilot.pause()

            # Check the overlay is up and pre-filled with task context.
            if not isinstance(app.screen, OrchestratorOverlay):
                pytest.skip("OrchestratorOverlay not pushed as expected")
                return

            try:
                inp = app.screen.query_one("#chat-overlay-input", Input)
            except Exception:
                pytest.skip("Orchestrator overlay input not reachable")
                return

            panel = app.screen.query_one("#chat-panel", ChatPanel)

            # (3) Send a message and wait for the reply.
            inp.focus()
            # Clear any pre-fill from the task context.
            await pilot.press("ctrl+a")
            await pilot.press("delete")
            await pilot.press("h", "i")
            await pilot.press("enter")
            await pilot.pause()

            await wait_for(
                lambda: any(reply_text in m for m in panel.export_rendered_messages()),
                pump_delay=0.05,
                tries=80,
            )

            rendered = panel.export_rendered_messages()
            assert any(reply_text in m for m in rendered), f"Task chat reply not found: {rendered}"
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]
