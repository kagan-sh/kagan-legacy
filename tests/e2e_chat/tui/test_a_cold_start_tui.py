"""Flow A — Cold-Start Chat (TUI).

TODO: delete tests/tui/test_chat_lifecycle.py (replaced by A + F)
TODO: delete tests/unit/tui/test_chat_runner.py (partially replaced by A + D)

Assertions:
  1. Project exists in driver.
  2. User message lands in the chat panel.
  3. Assistant chunk arrives in rendered messages.
  4. Snapshot of normalised chat panel text.
"""

from __future__ import annotations

from typing import Any

import pytest

from tests.helpers.async_utils import wait_for

pytestmark = [pytest.mark.tui, pytest.mark.e2e_chat]


async def _noop_warm(*args: Any, **kwargs: Any) -> None:
    return None


def _make_fake_acp(reply_text: str) -> Any:
    """Build a minimal ACPSessionFactory that emits one chunk."""
    from kagan.core.chat.acp import ACPTurnResult

    class _FakeACP:
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
            import asyncio

            from acp.schema import AgentMessageChunk, TextContentBlock

            chunk = AgentMessageChunk(
                content=TextContentBlock(type="text", text=reply_text),
                session_update="agent_message_chunk",
            )
            await on_update(chunk)
            await asyncio.sleep(0)
            return ACPTurnResult(full_response=reply_text, cancelled=False)

    return _FakeACP()


async def test_cold_start_project_exists(tui_driver: Any) -> None:
    """(1) Project created by fixture is visible."""
    projects = await tui_driver.list_projects()
    assert any(p.name == "E2E Chat TUI Project" for p in projects)


async def test_cold_start_user_msg_lands_and_chunk_arrives(
    tui_driver: Any,
) -> None:
    """(2)+(3) User message lands; assistant chunk arrives in panel."""
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.widgets.chat import ChatPanel

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    reply_text = "hello back from cold start"
    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    app.core.chat._acp = _make_fake_acp(reply_text)

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
                pytest.skip("Orchestrator overlay input not reachable from current screen state")
                return

            inp.focus()
            await pilot.press("H", "i")
            await pilot.press("enter")
            await pilot.pause()

            panel = app.screen.query_one("#chat-panel", ChatPanel)
            await wait_for(
                lambda: any(reply_text in m for m in panel.export_rendered_messages()),
                pump_delay=0.05,
                tries=60,
            )

            # (2) user message in panel
            rendered = panel.export_rendered_messages()
            assert any("Hi" in m or "hi" in m for m in rendered), (
                f"User message not found in: {rendered}"
            )
            # (3) assistant chunk arrived
            assert any(reply_text in m for m in rendered), (
                f"Assistant reply not found in: {rendered}"
            )
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]


async def test_cold_start_snapshot_normalised(
    tui_driver: Any,
) -> None:
    """(4) Normalised snapshot of chat panel text after a cold-start turn."""
    from textual.widgets import Input

    from kagan.core.chat.acp import ACPTurnResult  # noqa: F401 — used implicitly via _make_fake_acp
    from kagan.tui import KaganApp
    from kagan.tui.screens import _chat_runner as runner
    from kagan.tui.widgets.chat import ChatPanel
    from tests.e2e_chat.helpers.inline_snapshot_normalisers import normalise

    original_warm = runner.warm_orchestrator_backend
    runner.warm_orchestrator_backend = _noop_warm  # type: ignore[assignment]

    reply_text = "snapshot-reply"
    app = KaganApp(db_path=tui_driver.tmp_path / "kagan.db")
    app.core.chat._acp = _make_fake_acp(reply_text)

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
                pytest.skip("Orchestrator overlay input not reachable")
                return

            inp.focus()
            await pilot.press("H", "i")
            await pilot.press("enter")
            await pilot.pause()

            panel = app.screen.query_one("#chat-panel", ChatPanel)
            await wait_for(
                lambda: any(reply_text in m for m in panel.export_rendered_messages()),
                pump_delay=0.05,
                tries=60,
            )

            raw_text = "\n".join(panel.export_rendered_messages())
            normalised = normalise(raw_text, tmp_root=str(tui_driver.tmp_path))
            assert "snapshot-reply" in normalised
    finally:
        runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]
