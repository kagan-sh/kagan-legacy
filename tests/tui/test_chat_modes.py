"""Behavioral tests for orchestrator chat turn error handling.

Per testing.md: behavioral specs via KaganDriver + Textual Pilot.
Targeted waits only — no wait_for_workers().
"""

from __future__ import annotations

import pytest
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]


@pytest.fixture
async def board(tmp_path):
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Chat Modes Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    await driver.create_task("Sample task")
    yield driver
    await driver.teardown()


# ---------------------------------------------------------------------------
# Bug B — no-response path does not corrupt history
# ---------------------------------------------------------------------------


async def test_orchestrator_returns_no_response_does_not_corrupt_history(
    board: KaganDriver,
    monkeypatch,
) -> None:
    """When the engine yields no content, history is unchanged and error message appears."""
    import asyncio

    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+space")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)

        panel = overlay.query_one("#chat-panel", ChatPanel)
        history_before = list(overlay._orchestrator_history)

        # send_chat_message with empty stream → returns unchanged history + adds system message
        async def _no_response_send(*, core, panel, text, history):
            panel.set_runtime_status("error")
            panel.add_system_message("Orchestrator returned no response.")
            return list(history)

        async def _noop_persist(*args, **kwargs):
            pass

        monkeypatch.setattr(
            "kagan.tui.screens.orchestrator_overlay.send_chat_message",
            _no_response_send,
        )
        monkeypatch.setattr(
            overlay.kagan_app.orchestrator_sessions,
            "persist_active",
            _noop_persist,
        )
        task = asyncio.create_task(overlay._send_orchestrator_message("test prompt"))
        for _ in range(10):
            await pilot.pause()
            if task.done():
                break
        if not task.done():
            task.cancel()

        history_after = list(overlay._orchestrator_history)
        assert history_after == history_before, (
            "History must not be mutated when the orchestrator returns no response"
        )

        # There should be a system message about no response
        from textual.widgets import Static

        static_texts = " ".join(str(w.content) for w in panel.query(Static))
        assert "no response" in static_texts.lower()


async def test_orchestrator_agent_error_surfaces_as_message_and_keeps_history(
    board: KaganDriver,
    monkeypatch,
) -> None:
    """An AgentError from send_chat_message shows an error message; history unchanged."""
    import asyncio

    from kagan.core.errors import AgentError, KaganError
    from kagan.tui import KaganApp
    from kagan.tui.screens.orchestrator_overlay import OrchestratorOverlay
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=board.tmp_path / "kagan.db")
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.pause()
        await pilot.press("ctrl+space")
        await pilot.pause()
        overlay = app.screen
        assert isinstance(overlay, OrchestratorOverlay)

        panel = overlay.query_one("#chat-panel", ChatPanel)
        history_before = list(overlay._orchestrator_history)

        # Simulate the AgentError→KaganError path from send_chat_message
        async def _raising_send(*, core, panel, text, history):
            panel.set_runtime_status("error")
            panel.add_system_message("Orchestrator error: handshake failed")
            raise KaganError("handshake failed") from AgentError("handshake failed")

        monkeypatch.setattr(
            "kagan.tui.screens.orchestrator_overlay.send_chat_message",
            _raising_send,
        )
        task = asyncio.create_task(overlay._send_orchestrator_message("test prompt"))
        for _ in range(10):
            await pilot.pause()
            if task.done():
                break
        if not task.done():
            task.cancel()

        history_after = list(overlay._orchestrator_history)
        assert history_after == history_before, "History must not be mutated on AgentError"

        from textual.widgets import Static

        static_texts = " ".join(str(w.content) for w in panel.query(Static))
        assert "error" in static_texts.lower()
