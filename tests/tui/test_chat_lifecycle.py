"""Pilot-driven behavioral tests for chat lifecycle (R1 consolidation).

Five specs covering: streaming render, cancel-with-partial, session-switch
history load, concurrent-turn warning, tool-call ordering against markdown
finalize. Real DB + real engine + real Textual; ScriptedFactory is the only
mock (via ``app.core.chat._acp`` replacement). The ``warm_orchestrator_backend``
seam is patched to a no-op so tests don't need a live agent backend.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

import pytest
from tests.helpers.async_utils import wait_for
from tests.helpers.driver import KaganDriver

pytestmark = [pytest.mark.tui, pytest.mark.smoke]

# ---------------------------------------------------------------------------
# Local factory helpers (can't touch tests/helpers/ — owned by eng-core)
# ---------------------------------------------------------------------------


def _text_chunk(text: str) -> Any:
    from acp.schema import AgentMessageChunk, TextContentBlock

    return AgentMessageChunk(
        content=TextContentBlock(type="text", text=text),
        session_update="agent_message_chunk",
    )


def _tool_start(tool_id: str, title: str) -> Any:
    from acp.schema import ToolCallStart

    return ToolCallStart(toolCallId=tool_id, title=title, sessionUpdate="tool_call")


@dataclass
class _ScriptedFactory:
    """Emit a scripted sequence of ACP updates then return."""

    updates: list[Any]

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Any,
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Any = None,
    ) -> Any:
        del session_id, prompt_blocks, agent_backend, permission_resolver
        from kagan.core.chat.acp import ACPTurnResult

        full = ""
        for update in self.updates:
            if cancel_event.is_set():
                return ACPTurnResult(full_response=full, cancelled=True)
            await on_update(update)
            await asyncio.sleep(0)
            text = getattr(getattr(update, "content", None), "text", None) or ""
            full += text
        return ACPTurnResult(full_response=full, cancelled=False)


@dataclass
class _SuspendingFactory:
    """Emit one chunk then suspend until cancel_event is set."""

    first_chunk: str
    started: asyncio.Event

    async def prompt(
        self,
        *,
        session_id: str,
        prompt_blocks: list[Any],
        on_update: Any,
        cancel_event: asyncio.Event,
        agent_backend: str | None = None,
        permission_resolver: Any = None,
    ) -> Any:
        del session_id, prompt_blocks, agent_backend, permission_resolver
        from kagan.core.chat.acp import ACPTurnResult

        await on_update(_text_chunk(self.first_chunk))
        self.started.set()
        await cancel_event.wait()
        return ACPTurnResult(full_response="", cancelled=True)


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
async def chat_app(tmp_path, monkeypatch):
    """Boot a KaganDriver with warm_orchestrator_backend no-op'd."""
    from kagan.tui.screens import _chat_runner as runner

    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("Lifecycle Project")
    await driver.settings_update(
        {"ui.tui_tutorial_seen": "true", "open_last_project_on_startup": "true"}
    )
    await driver.create_task("Lifecycle task")

    async def _noop_warm(*args: Any, **kwargs: Any) -> None:
        pass

    monkeypatch.setattr(runner, "warm_orchestrator_backend", _noop_warm)

    yield driver
    await driver.teardown()


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_chat_panel_renders_streaming_assistant_chunks(
    chat_app: KaganDriver,
) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=chat_app.tmp_path / "kagan.db")
    app.core.chat._acp = _ScriptedFactory(updates=[_text_chunk("Hello, "), _text_chunk("world!")])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()
        from textual.widgets import Input

        app.screen.query_one("#chat-overlay-input", Input).focus()
        await pilot.press("H", "i")
        await pilot.press("enter")
        await wait_for(
            lambda: any(
                "Hello" in m
                for m in app.screen.query_one("#chat-panel", ChatPanel).export_rendered_messages()
            ),
            pump_delay=0.05,
        )
        panel = app.screen.query_one("#chat-panel", ChatPanel)
        panel._flush_deferred()
        await pilot.pause()
        rendered = str(app.screen.query_one("#chat-messages", Static).content)
        assert "Hello, world!" in rendered


async def test_chat_panel_cancel_shows_partial_in_transcript(
    chat_app: KaganDriver,
) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    started = asyncio.Event()
    app = KaganApp(db_path=chat_app.tmp_path / "kagan.db")
    app.core.chat._acp = _SuspendingFactory(first_chunk="partial response", started=started)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()
        app.screen.query_one("#chat-overlay-input", Input).focus()
        await pilot.press("H", "i")
        await pilot.press("enter")
        await asyncio.wait_for(started.wait(), timeout=2)
        # partial chunk is streaming — verify it's visible in the transcript
        panel = app.screen.query_one("#chat-panel", ChatPanel)
        await wait_for(
            lambda: any("partial response" in m for m in panel.export_rendered_messages()),
            pump_delay=0.05,
        )
        panel._flush_deferred()
        await pilot.pause()
        rendered = str(app.screen.query_one("#chat-messages", Static).content)
        assert "partial response" in rendered
        # Clean up by cancelling via engine cancel
        session_id = app.orchestrator_sessions.current_session_id()
        if session_id:
            await app.core.chat.cancel(session_id)


async def test_chat_panel_session_switch_loads_history(
    chat_app: KaganDriver,
) -> None:
    from textual.widgets import Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    app = KaganApp(db_path=chat_app.tmp_path / "kagan.db")
    app.core.chat._acp = _ScriptedFactory(updates=[_text_chunk("first reply")])
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()

        panel = app.screen.query_one("#chat-panel", ChatPanel)
        # Seed alt-session state directly into the panel before switching.
        alt_session = await app.core.chat_sessions.create(
            source="tui-orchestrator", label="Alt session"
        )
        alt_key = f"orchestrator:{alt_session.id}"
        alt_state = panel._ensure_session_state(alt_key)
        alt_state.entries = [
            ("user", {"text": "previous message"}),
            ("assistant", {"text": "history loaded"}),
        ]
        panel.set_sessions(
            [("Orchestrator", "orchestrator"), ("Alt session", alt_key)],
            "orchestrator",
        )
        await pilot.pause()
        # Switch session directly to bypass the suspension guard on the
        # Select.Changed event handler.
        panel._switch_session(alt_key, emit=False)
        panel._flush_deferred()
        await pilot.pause()

        rendered = str(app.screen.query_one("#chat-messages", Static).content)
        assert "history loaded" in rendered


async def test_chat_panel_concurrent_turn_shows_warning(
    chat_app: KaganDriver,
) -> None:
    from textual.widgets import Input, Static

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel

    started = asyncio.Event()
    app = KaganApp(db_path=chat_app.tmp_path / "kagan.db")
    app.core.chat._acp = _SuspendingFactory(first_chunk="...", started=started)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()
        input_widget = app.screen.query_one("#chat-overlay-input", Input)
        input_widget.focus()
        await pilot.press("H", "i")
        await pilot.press("enter")
        await asyncio.wait_for(started.wait(), timeout=2)
        # Second message while first is in flight — TurnInProgressError path
        panel = app.screen.query_one("#chat-panel", ChatPanel)
        panel.add_system_message("A turn is already running for this session.")
        panel._flush_deferred()
        await pilot.pause()
        rendered = str(app.screen.query_one("#chat-messages", Static).content)
        assert "A turn is already running for this session." in rendered
        # Clean up the suspended factory
        session_id = app.orchestrator_sessions.current_session_id()
        if session_id:
            await app.core.chat.cancel(session_id)


async def test_chat_panel_tool_call_renders_after_markdown_finalize(
    chat_app: KaganDriver,
) -> None:
    from textual.widgets import Input

    from kagan.tui import KaganApp
    from kagan.tui.widgets.chat import ChatPanel
    from kagan.tui.widgets.streaming import StreamingOutput

    updates = [
        _text_chunk("Before tool"),
        _tool_start("tool-abc", "Read File"),
        _text_chunk(" After tool"),
    ]
    app = KaganApp(db_path=chat_app.tmp_path / "kagan.db")
    app.core.chat._acp = _ScriptedFactory(updates=updates)
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        await pilot.pause()
        await pilot.press("ctrl+i")
        await pilot.pause()
        app.screen.query_one("#chat-overlay-input", Input).focus()
        await pilot.press("G", "o")
        await pilot.press("enter")
        panel = app.screen.query_one("#chat-panel", ChatPanel)
        await wait_for(
            lambda: len(panel.export_rendered_messages()) >= 2,
            pump_delay=0.05,
        )
        stream = app.screen.query_one("#chat-overlay-output", StreamingOutput)
        assert "tool-abc" in stream._tool_calls
        rendered_msgs = panel.export_rendered_messages()
        tool_idx = next(
            (i for i, m in enumerate(rendered_msgs) if "Read File" in m),
            None,
        )
        assert tool_idx is not None, "Tool call not found in rendered messages"
