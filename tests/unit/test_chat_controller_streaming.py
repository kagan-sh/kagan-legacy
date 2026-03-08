import pytest
from acp.schema import AgentMessageChunk, TextContentBlock, ToolCallStart

import kagan.chat.controller as chat_controller

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


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

    monkeypatch.setattr(chat_controller, "_console", fake_console)
    monkeypatch.setattr(chat_controller.time, "monotonic", _tick)

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

    monkeypatch.setattr(chat_controller, "_console", fake_console)
    monkeypatch.setattr(chat_controller.time, "monotonic", _tick)

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
    assert "dim cyan" in printed[2]
