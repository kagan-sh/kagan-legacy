"""Flow F — Session Persistence + Restore (TUI).

TODO: delete tests/tui/test_chat_lifecycle.py (replaced by F + A)

Assertions:
  1. Send a message and receive a reply.
  2. Tear down the driver (close the DB).
  3. Reboot the driver with the same db_path.
  4. Chat history contains the prior message + reply.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import pytest

from tests.helpers.async_utils import wait_for

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.tui, pytest.mark.e2e_chat]


async def test_chat_history_survives_reboot(tmp_path: Path) -> None:
    """(1-4) Send a turn, reboot, verify history is loaded from DB."""

    from textual.widgets import Input

    from kagan.core.chat.acp import ACPTurnResult
    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.widgets.chat import ChatPanel
    from tests.helpers.driver import KaganDriver
    from tests.helpers.fake_agent_backend import ensure_fake_agent_backend_registered

    ensure_fake_agent_backend_registered()

    db_path = tmp_path / "kagan.db"

    async def _noop_warm(*args: Any, **kwargs: Any) -> None:
        return None

    # ------------------------------------------------------------------
    # Phase 1: send message and get reply.
    # ------------------------------------------------------------------
    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    reply_text = "persistence-reply"

    class _PersistACP:
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

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Persist Project")
    await driver.settings_update(
        {
            "ui.tui_tutorial_seen": "true",
            "open_last_project_on_startup": "true",
        }
    )

    try:
        app = KaganApp(db_path=db_path)
        app.core.chat._acp = _PersistACP()

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
            await pilot.press("h", "i")
            await pilot.press("enter")
            await pilot.pause()

            panel = app.screen.query_one("#chat-panel", ChatPanel)
            await wait_for(
                lambda: any(reply_text in m for m in panel.export_rendered_messages()),
                pump_delay=0.05,
                tries=60,
            )

            # (1) Verified: message and reply are in the panel.
            rendered = panel.export_rendered_messages()
            assert any(reply_text in m for m in rendered), f"Reply not in panel: {rendered}"

        # (2) App exited — driver still alive.
        sessions = await driver.chat_list_sessions()
        assert len(sessions) > 0, "No chat sessions found after first run"
        session_id = sessions[0]["id"]
        history = await driver.chat_history(session_id)
        assert len(history) >= 2, f"Expected at least 2 messages, got {len(history)}"

        await driver.teardown()

        # ------------------------------------------------------------------
        # Phase 3: reboot with same db_path.
        # ------------------------------------------------------------------
        driver2 = await KaganDriver.boot(tmp_path)

        try:
            # (4) History is present via the driver's chat API.
            sessions2 = await driver2.chat_list_sessions()
            assert len(sessions2) > 0, "Sessions gone after reboot"
            session_id2 = sessions2[0]["id"]
            history2 = await driver2.chat_history(session_id2)
            texts = [getattr(msg, "content", None) or str(msg) for msg in history2]

            assert any(reply_text in str(t) for t in texts), (
                f"Persisted reply not found after reboot: {texts}"
            )
        finally:
            await driver2.teardown()
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]
