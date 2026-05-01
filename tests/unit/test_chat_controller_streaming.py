import io

import pytest
from acp.schema import AgentMessageChunk, PermissionOption, TextContentBlock, ToolCallStart
from rich.console import Console

import kagan.cli.chat._chat_acp as chat_acp_module
import kagan.cli.chat.controller as chat_controller

pytestmark = [pytest.mark.unit]


class _FakeConsoleFile:
    def __init__(self) -> None:
        self.flush_count = 0

    def flush(self) -> None:
        self.flush_count += 1


class _FakeConsole:
    """Minimal stand-in used by the permission-flow tests, which don't drive
    the streaming Markdown region."""

    def __init__(self) -> None:
        self.file = _FakeConsoleFile()
        self.calls: list[tuple[tuple[object, ...], dict[str, object]]] = []

    def print(self, *args: object, **kwargs: object) -> None:
        self.calls.append((args, kwargs))


def _real_console() -> tuple[Console, io.StringIO]:
    """Real Rich Console that writes to an in-memory buffer.

    Required because Rich's Live and Markdown renderers call methods on the
    Console (set_live, height, is_terminal, …) that a hand-rolled fake can't
    fully implement without becoming a maintenance burden.
    """
    buf = io.StringIO()
    console = Console(file=buf, force_terminal=False, color_system=None, width=80)
    return console, buf


def _message_chunk(text: str) -> AgentMessageChunk:
    return AgentMessageChunk(
        content=TextContentBlock(type="text", text=text),
        session_update="agent_message_chunk",
    )


async def test_streamed_chunks_are_collected_and_returned_by_finish_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    console, _ = _real_console()
    monkeypatch.setattr(chat_acp_module, "_console", console)

    client = chat_controller._OrchestratorACPClient()
    client.start_turn()

    await client.session_update("session-1", _message_chunk("a"))
    await client.session_update("session-1", _message_chunk("b"))
    await client.session_update("session-1", _message_chunk("c"))

    response = client.finish_turn()
    assert response == "abc"


async def test_markdown_region_renders_reply_to_console_at_finish_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pipe characters in the reply must reach the console as a rendered table,
    not as raw '|' characters in scrollback."""
    console, buf = _real_console()
    monkeypatch.setattr(chat_acp_module, "_console", console)

    client = chat_controller._OrchestratorACPClient()
    client.start_turn()

    await client.session_update(
        "session-1",
        _message_chunk("| col |\n| --- |\n| val |\n"),
    )
    client.finish_turn()

    output = buf.getvalue()
    # Markdown renders a table header into a Unicode box-drawing border —
    # absence of that border means the reply was printed as raw pipes.
    assert "━" in output or "─" in output
    # The cell value is preserved.
    assert "val" in output


async def test_markdown_region_finalizes_before_tool_call_start(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A tool start arriving mid-stream must commit the assistant text to
    scrollback first so the transcript reads top-to-bottom."""
    console, buf = _real_console()
    monkeypatch.setattr(chat_acp_module, "_console", console)

    client = chat_controller._OrchestratorACPClient()
    client.start_turn()

    await client.session_update("session-1", _message_chunk("Looking up files."))
    await client.session_update(
        "session-1",
        ToolCallStart(title="Read file", tool_call_id="tool-1", session_update="tool_call"),
    )
    client.finish_turn()

    output = buf.getvalue()
    text_pos = output.find("Looking up files")
    tool_pos = output.find("Read file")
    assert text_pos != -1
    assert tool_pos != -1
    assert text_pos < tool_pos


async def test_start_turn_discards_in_flight_markdown_region(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Starting a new turn must clear any partial preview from the previous
    turn so it doesn't bleed into the next reply."""
    console, _ = _real_console()
    monkeypatch.setattr(chat_acp_module, "_console", console)

    client = chat_controller._OrchestratorACPClient()
    client.start_turn()
    await client.session_update("session-1", _message_chunk("partial"))

    assert client._md_region.is_active

    client.start_turn()  # should reset
    assert not client._md_region.is_active
    assert client._response_chunks.is_empty


async def test_permission_request_denies_in_noninteractive_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = _FakeConsole()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module, "_stdio_is_interactive", lambda: False)

    client = chat_controller._OrchestratorACPClient()
    response = await client.request_permission(
        [
            PermissionOption(kind="allow_once", name="Allow once", option_id="allow-1"),
            PermissionOption(kind="allow_always", name="Allow always", option_id="allow-all"),
        ],
        session_id="session-1",
        tool_call=ToolCallStart(
            title="Edit file",
            tool_call_id="tool-1",
            session_update="tool_call",
        ),
    )

    assert response.outcome.outcome == "cancelled"


async def test_permission_request_selects_interactive_allow_option(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = _FakeConsole()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module, "_stdio_is_interactive", lambda: True)
    # Mock the async panel to return index 1 = allow_always without launching a real terminal.
    async def _fake_panel(*_a, **_kw):  # noqa: RUF006
        return (1, "")
    monkeypatch.setattr(chat_acp_module, "_run_approval_panel_async", _fake_panel)
    # Ensure no residual session approval bleeds into this test.
    chat_acp_module._session_approvals.revoke("run command")

    client = chat_controller._OrchestratorACPClient()
    response = await client.request_permission(
        [
            PermissionOption(kind="allow_once", name="Allow once", option_id="allow-1"),
            PermissionOption(kind="allow_always", name="Allow always", option_id="allow-all"),
            PermissionOption(kind="reject_once", name="Deny", option_id="deny-1"),
        ],
        session_id="session-1",
        tool_call=ToolCallStart(
            title="Run command",
            tool_call_id="tool-1",
            session_update="tool_call",
        ),
    )

    assert response.outcome.outcome == "selected"
    assert response.outcome.option_id == "allow-all"


async def test_permission_request_can_select_deny_option_from_acp_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_console = _FakeConsole()
    monkeypatch.setattr(chat_acp_module, "_console", fake_console)
    monkeypatch.setattr(chat_acp_module, "_stdio_is_interactive", lambda: True)
    # Mock the async panel to return index 2 = reject_once.
    async def _fake_panel(*_a, **_kw):  # noqa: RUF006
        return (2, "")
    monkeypatch.setattr(chat_acp_module, "_run_approval_panel_async", _fake_panel)
    # Clear any session-level grant that may bleed from allow_always tests.
    chat_acp_module._session_approvals.revoke("run command")

    client = chat_controller._OrchestratorACPClient()
    response = await client.request_permission(
        [
            PermissionOption(kind="allow_once", name="Allow once", option_id="allow-1"),
            PermissionOption(kind="reject_once", name="Deny", option_id="deny-1"),
        ],
        session_id="session-1",
        tool_call=ToolCallStart(
            title="Run command",
            tool_call_id="tool-1",
            session_update="tool_call",
        ),
    )

    assert response.outcome.outcome == "cancelled"
