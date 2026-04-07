import pytest
from acp.schema import AgentMessageChunk, TextContentBlock, ToolCallStart

import kagan.cli.chat._chat_acp as chat_acp_module
import kagan.cli.chat.controller as chat_controller

pytestmark = [pytest.mark.unit]


class _FakeConsoleFile:
    def __init__(self) -> None:
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1


class _FakeConsole:
    def __init__(self) -> None:
        self.file = _FakeConsoleFile()
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def print(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _message_chunk(text: str) -> AgentMessageChunk:
    return AgentMessageChunk(
        content=TextContentBlock(type="text", text=text),
        session_update="agent_message_chunk",
    )


async def test_orchestrator_client_batches_chunk_flushes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = _FakeConsole()
    ticks = iter([1.00, 1.01, 1.02, 1.03])

    def _tick() -> float:
        return next(ticks, 1.03)

    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module.time, "monotonic", _tick)

    client = chat_controller._OrchestratorACPClient()
    client.start_turn()

    await client.session_update("session-1", _message_chunk("a"))
    await client.session_update("session-1", _message_chunk("b"))
    await client.session_update("session-1", _message_chunk("c"))

    response = client.finish_turn()
    printed = [str(args[0]) for args, _kwargs in fake_console.calls]

    assert response == "abc"
    assert printed == ["a", "bc"]
    assert fake_console.file.flush_count == 2


async def test_orchestrator_client_flushes_buffer_before_tool_lines(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = _FakeConsole()
    ticks = iter([2.00, 2.01, 2.02])

    def _tick() -> float:
        return next(ticks, 2.02)

    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module.time, "monotonic", _tick)

    client = chat_controller._OrchestratorACPClient()
    client.start_turn()

    await client.session_update("session-1", _message_chunk("a"))
    await client.session_update("session-1", _message_chunk("b"))
    await client.session_update(
        "session-1",
        ToolCallStart(title="Read file", tool_call_id="tool-1", session_update="tool_call"),
    )

    printed = [str(args[0]) for args, _kwargs in fake_console.calls]
    assert printed[0] == "a"
    assert printed[1] == "b"
    assert "● Read file" in printed[2]


async def test_deferred_flush_fires_after_cadence_interval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Buffered text is flushed by the scheduled timer callback when no more chunks arrive."""
    fake_console = _FakeConsole()
    ticks = iter([1.00, 1.01])

    def _tick() -> float:
        return next(ticks, 1.01)

    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module.time, "monotonic", _tick)

    client = chat_controller._OrchestratorACPClient()
    client.start_turn()

    await client.session_update("session-1", _message_chunk("a"))  # t=1.00 → flush
    await client.session_update("session-1", _message_chunk("b"))  # t=1.01 → buffer + schedule

    # Only "a" has been flushed so far
    assert len(fake_console.calls) == 1
    assert client._output_flusher._flush_handle is not None

    # Simulate the timer firing
    client._output_flusher._do_deferred_flush()

    printed = [str(args[0]) for args, _kwargs in fake_console.calls]
    assert printed == ["a", "b"]
    assert fake_console.file.flush_count == 2
    assert client._output_flusher._flush_handle is None


async def test_flush_timer_cancelled_on_start_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Starting a new turn cancels any pending flush timer."""
    fake_console = _FakeConsole()
    ticks = iter([1.00, 1.01])

    def _tick() -> float:
        return next(ticks, 1.01)

    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module.time, "monotonic", _tick)

    client = chat_controller._OrchestratorACPClient()
    client.start_turn()

    await client.session_update("session-1", _message_chunk("a"))  # flush
    await client.session_update("session-1", _message_chunk("b"))  # buffer + schedule

    assert client._output_flusher._flush_handle is not None

    # Starting a new turn cancels the timer and clears buffers
    client.start_turn()
    assert client._output_flusher._flush_handle is None
    assert client._output_flusher._pending_chunks == []
