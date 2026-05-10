"""Unit tests for ``kagan.tui.screens._chat_runner``.

Phase 4c migration tests — verify that the shared helper extracted from
``kanban_chat.py`` (now deleted) plus ``kanban.py`` correctly drives a chat
turn through ``ChatEngine`` and translates engine events onto a
``ChatPanel``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

import pytest
from textual.app import App, ComposeResult

from kagan.core.events import (
    AssistantChunk,
    AssistantMessagePersisted,
    Event,
    ToolCall,
    ToolCallUpdate,
    TurnEnd,
    TurnStart,
)
from kagan.core.permission import PermissionRequest

# Legacy alias for readability in type annotations below.
ChatEvent = Event | PermissionRequest
from kagan.tui.screens._chat_runner import (
    apply_chat_event_to_panel,
    apply_task_chat_event,
    present_agent_event,
    send_chat_message,
    tool_call_id,
    tool_call_title,
)
from kagan.tui.widgets.chat import ChatPanel

pytestmark = [pytest.mark.tui, pytest.mark.unit]


class _ChatPanelHostApp(App[None]):
    def compose(self) -> ComposeResult:
        yield ChatPanel(classes="chat-overlay")


# ---------------------------------------------------------------------------
# apply_chat_event_to_panel
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_apply_chat_event_to_panel_streams_assistant_text() -> None:
    app = _ChatPanelHostApp()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)
        # Drive a small synthetic turn through the translator.
        events: list[Event] = [
            TurnStart(turn_id="t-1", session_id="s-1", agent_id=""),
            AssistantChunk(turn_id="t-1", session_id="s-1", message_id="m-1", delta="Hello "),
            AssistantChunk(turn_id="t-1", session_id="s-1", message_id="m-1", delta="world"),
            TurnEnd(turn_id="t-1", reason="done"),
        ]
        for event in events:
            apply_chat_event_to_panel(panel, event)
        await pilot.pause()
        rendered = "\n".join(panel.export_rendered_messages())
        assert "Hello" in rendered
        assert "world" in rendered


@pytest.mark.asyncio
async def test_apply_chat_event_to_panel_handles_tool_calls() -> None:
    app = _ChatPanelHostApp()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)
        apply_chat_event_to_panel(
            panel,
            ToolCall(
                turn_id="t-1",
                session_id="s-1",
                tool_call_id="call_1",
                name="grep",
                title="grep",
                kind=None,
                args="pattern=foo",
            ),
        )
        apply_chat_event_to_panel(
            panel,
            ToolCallUpdate(tool_call_id="call_1", content="match.py:3", progress="completed"),
        )
        await pilot.pause()
        # Translator must not crash and must leave the runtime status at a
        # known value (either still "thinking" mid-stream or driven by a
        # later event — we only check that the calls returned cleanly).
        assert panel._runtime_status in {"thinking", "ready", "error"}


# ---------------------------------------------------------------------------
# send_chat_message — engine-driven turn
# ---------------------------------------------------------------------------


class _StubChatEngine:
    """Minimal ChatEngine surface needed by ``send_chat_message``."""

    def __init__(self, events: list[Event]) -> None:
        self._events = events
        self.push_user_calls: list[tuple[str, str]] = []
        self.stream_calls: list[tuple[str, list[Any], str | None]] = []

    async def push_user(self, session_id: str, content: str) -> Any:
        self.push_user_calls.append((session_id, content))
        return type("Msg", (), {"id": 1, "content": content})()

    def stream_assistant(
        self,
        session_id: str,
        *,
        prompt_blocks: list[Any],
        agent_backend: str | None = None,
    ) -> AsyncIterator[Event]:
        self.stream_calls.append((session_id, prompt_blocks, agent_backend))

        async def _gen() -> AsyncIterator[Event]:
            for event in self._events:
                yield event

        return _gen()


class _StubSettings:
    async def get(self) -> dict[str, Any]:
        return {"chat.default_agent_backend": "claude-code"}


class _StubOrchestratorSessions:
    def __init__(self, session_id: str) -> None:
        self._id = session_id

    def current_session_id(self) -> str:
        return self._id


class _StubCore:
    def __init__(self, events: list[Event]) -> None:
        self.chat = _StubChatEngine(events)
        self.settings = _StubSettings()


class _ChatPanelHostAppWithCore(App[None]):
    def __init__(self, core: _StubCore, sessions: _StubOrchestratorSessions) -> None:
        super().__init__()
        self.core = core  # type: ignore[assignment]
        self.orchestrator_sessions = sessions  # type: ignore[assignment]

    def compose(self) -> ComposeResult:
        yield ChatPanel(classes="chat-overlay")


@pytest.mark.asyncio
async def test_send_chat_message_drives_engine_turn() -> None:
    """Happy path: send_chat_message pushes user, streams events, returns history."""
    events: list[Event] = [
        TurnStart(turn_id="t-1", session_id="sess-123", agent_id=""),
        AssistantChunk(turn_id="t-1", session_id="sess-123", message_id="m-1", delta="hi "),
        AssistantChunk(turn_id="t-1", session_id="sess-123", message_id="m-1", delta="there"),
        AssistantMessagePersisted(message_id=42, content="hi there", terminated=False),
        TurnEnd(turn_id="t-1", reason="done"),
    ]
    core = _StubCore(events)
    sessions = _StubOrchestratorSessions(session_id="sess-123")
    app = _ChatPanelHostAppWithCore(core, sessions)

    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)

        # warm_orchestrator_backend wraps a subprocess call we don't want to
        # spawn — patch it to a no-op for the duration of the test.
        from kagan.tui.screens import _chat_runner

        original_warm = _chat_runner.warm_orchestrator_backend

        async def _noop(*args: Any, **kwargs: Any) -> None:
            return None

        _chat_runner.warm_orchestrator_backend = _noop  # type: ignore[assignment]
        try:
            history = await send_chat_message(
                core=core,  # type: ignore[arg-type]
                panel=panel,
                text="hello",
                history=[],
            )
        finally:
            _chat_runner.warm_orchestrator_backend = original_warm  # type: ignore[assignment]

        assert core.chat.push_user_calls == [("sess-123", "hello")]
        assert len(core.chat.stream_calls) == 1
        assert history == [("user", "hello"), ("assistant", "hi there")]


@pytest.mark.asyncio
async def test_send_chat_message_surfaces_missing_session() -> None:
    """If no orchestrator session is loaded, surface a system message and bail."""

    class _NoSession:
        def current_session_id(self) -> None:
            return None

    core = _StubCore([])
    app = _ChatPanelHostAppWithCore(core, _NoSession())  # type: ignore[arg-type]
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)

        from kagan.tui.screens import _chat_runner

        async def _noop(*args: Any, **kwargs: Any) -> None:
            return None

        _chat_runner.warm_orchestrator_backend = _noop  # type: ignore[assignment]

        history = await send_chat_message(
            core=core,  # type: ignore[arg-type]
            panel=panel,
            text="hello",
            history=[],
        )
        # Original history returned untouched.
        assert history == []
        # No engine call.
        assert core.chat.push_user_calls == []


# ---------------------------------------------------------------------------
# Helpers lifted from the deleted kanban_chat.py
# ---------------------------------------------------------------------------


def test_tool_call_id_and_title_helpers() -> None:
    payload = {"id": "call_42", "name": "Grep"}
    assert tool_call_id(payload) == "call_42"
    # title falls back to ``name`` when not in the nested ACP block.
    assert tool_call_title(payload) == "Grep"

    nested = {"acp": {"toolCallId": "abc", "title": "Custom"}}
    assert tool_call_id(nested) == "abc"
    assert tool_call_title(nested) == "Custom"

    # call_ / toolu_ prefixes collapse to the generic "tool call" label
    # when used as the title (raw id passed through without a name).
    only_id = {"id": "call_xyz"}
    assert tool_call_title(only_id) == "tool call"


def test_present_agent_event_centralizes_task_event_labels() -> None:
    running = present_agent_event("output_chunk", {"text": "plan", "kind": "thought"})
    assert running.text == "plan"
    assert running.chunk_kind == "thought"
    assert running.runtime_status == "thinking"
    assert running.stream_action == "Reasoning through approach"
    assert running.confidence == "assumption"

    tool = present_agent_event("tool_call_update", {"id": "call_1", "name": "grep"})
    assert tool.tool_id == "call_1"
    assert tool.tool_title == "grep"
    assert tool.tool_status == "updated"
    assert tool.stream_action == "Running tool: grep"

    failed = present_agent_event("agent_failed", {"message": "boom"})
    assert failed.note == "boom"
    assert failed.runtime_status == "error"
    assert failed.stream_action == "Agent failed"


@pytest.mark.asyncio
async def test_apply_task_chat_event_renders_output_chunk() -> None:
    """Sanity-check the task-event translator works with kind strings."""
    app = _ChatPanelHostApp()
    async with app.run_test(size=(120, 30)) as pilot:
        await pilot.pause()
        panel = app.screen.query_one(ChatPanel)
        apply_task_chat_event(
            panel,
            "output_chunk",
            {"text": "task agent output", "kind": "assistant"},
        )
        await pilot.pause()
        rendered = "\n".join(panel.export_rendered_messages())
        assert "task agent output" in rendered
