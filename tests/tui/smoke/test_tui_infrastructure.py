"""Consolidated TUI infrastructure smoke tests.

Covers:
- User-facing message helpers (instance lock, permission timer, task close).
- StreamingOutput post_thought / post_response race safety.
- TUI client disconnect does not disrupt other IPC clients.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

import pytest
from textual.app import App, ComposeResult

from kagan.core.ipc.client import IPCClient
from kagan.core.ipc.contracts import CoreRequest, CoreResponse
from kagan.core.ipc.discovery import CoreEndpoint
from kagan.core.ipc.server import IPCServer
from kagan.core.ipc.transports import UnixSocketTransport
from kagan.tui.ui.user_messages import (
    instance_lock_copy,
    permission_timer_line,
    task_deleted_close_message,
    task_moved_close_message,
)
from kagan.tui.ui.widgets.streaming_output import StreamingOutput

# ---------------------------------------------------------------------------
# User message tests
# ---------------------------------------------------------------------------


def test_instance_lock_copy_covers_startup_and_switch_hints() -> None:
    startup = instance_lock_copy(is_startup=True)
    switch = instance_lock_copy(is_startup=False)

    assert startup.button_label == "Quit"
    assert "start Kagan again" in startup.note
    assert switch.button_label == "OK"
    assert "continue in your current repository" in switch.note


def test_permission_timer_line_formats_countdown() -> None:
    assert permission_timer_line(125) == "Waiting for decision... (2:05)"
    assert permission_timer_line(-3) == "Waiting for decision... (0:00)"


def test_task_close_messages_are_explicit() -> None:
    assert task_deleted_close_message("review") == (
        "Task was deleted by another action. Closing review."
    )
    assert task_moved_close_message("done") == "Task moved to DONE. Closing task output."


# ---------------------------------------------------------------------------
# StreamingOutput race-safety tests
# ---------------------------------------------------------------------------


class StreamingOutputApp(App[None]):
    """Minimal app to host a StreamingOutput widget for testing."""

    def compose(self) -> ComposeResult:
        yield StreamingOutput(id="output")


@pytest.mark.asyncio
async def test_post_thought_returns_valid_widget() -> None:
    """post_thought creates and returns a usable StreamingMarkdown widget."""
    app = StreamingOutputApp()
    async with app.run_test(size=(80, 24)):
        output = app.query_one(StreamingOutput)
        widget = await output.post_thought("thinking fragment")
        assert widget is not None
        assert widget.content == "thinking fragment"


@pytest.mark.asyncio
async def test_post_thought_appends_to_existing_thought() -> None:
    """Repeated post_thought calls append to the same thought widget."""
    app = StreamingOutputApp()
    async with app.run_test(size=(80, 24)):
        output = app.query_one(StreamingOutput)
        first = await output.post_thought("part 1")
        second = await output.post_thought(" part 2")
        assert first is second
        assert second.content == "part 1 part 2"


@pytest.mark.asyncio
async def test_post_thought_survives_interleaved_post_response() -> None:
    """post_thought does not crash when post_response nullifies _agent_thought.

    This is the core regression scenario: a response message arrives between
    a thought's mount and its first append_content call.
    """
    app = StreamingOutputApp()
    async with app.run_test(size=(80, 24)):
        output = app.query_one(StreamingOutput)

        # Establish a thought widget.
        thought_widget = await output.post_thought("initial thought")
        assert thought_widget.content == "initial thought"

        # post_response nullifies _agent_thought internally.
        await output.post_response("response text")
        assert output._agent_thought is None

        # Next post_thought must succeed even though _agent_thought is None.
        new_thought = await output.post_thought("new thought after response")
        assert new_thought is not None
        assert new_thought.content == "new thought after response"
        assert new_thought is not thought_widget


@pytest.mark.asyncio
async def test_post_response_survives_interleaved_post_tool_call() -> None:
    """post_response does not crash when post_tool_call nullifies _agent_response.

    Same defensive-reference pattern applied to _agent_response.
    """

    app = StreamingOutputApp()
    async with app.run_test(size=(80, 24)):
        output = app.query_one(StreamingOutput)

        # Establish a response widget.
        response_widget = await output.post_response("initial response")
        assert response_widget.content == "initial response"

        # post_tool_call nullifies _agent_response internally.
        await output.post_tool_call("tc-1", "Read file")
        assert output._agent_response is None

        # Next post_response must succeed even though _agent_response is None.
        new_response = await output.post_response("response after tool call")
        assert new_response is not None
        assert new_response.content == "response after tool call"
        assert new_response is not response_widget


@pytest.mark.asyncio
async def test_rapid_thought_messages_no_crash() -> None:
    """Rapid successive Thinking messages do not cause NoneType errors."""
    app = StreamingOutputApp()
    async with app.run_test(size=(80, 24)):
        output = app.query_one(StreamingOutput)
        for i in range(20):
            widget = await output.post_thought(f"thought-{i} ")
            assert widget is not None


@pytest.mark.asyncio
async def test_rapid_interleaved_thought_response_no_crash() -> None:
    """Rapid alternation between thought and response messages is safe."""
    app = StreamingOutputApp()
    async with app.run_test(size=(80, 24)):
        output = app.query_one(StreamingOutput)
        for i in range(10):
            thought = await output.post_thought(f"thought-{i}")
            assert thought is not None
            response = await output.post_response(f"response-{i}")
            assert response is not None


@pytest.mark.asyncio
async def test_post_thought_after_clear() -> None:
    """post_thought works correctly after output is cleared."""
    app = StreamingOutputApp()
    async with app.run_test(size=(80, 24)):
        output = app.query_one(StreamingOutput)
        await output.post_thought("before clear")
        await output.clear()
        assert output._agent_thought is None

        widget = await output.post_thought("after clear")
        assert widget is not None
        assert widget.content == "after clear"


@pytest.mark.asyncio
async def test_post_thought_after_reset_turn() -> None:
    """post_thought works correctly after reset_turn nullifies _agent_thought."""
    app = StreamingOutputApp()
    async with app.run_test(size=(80, 24)):
        output = app.query_one(StreamingOutput)
        await output.post_thought("before reset")
        output.reset_turn()
        assert output._agent_thought is None

        widget = await output.post_thought("after reset")
        assert widget is not None
        assert widget.content == "after reset"


# ---------------------------------------------------------------------------
# IPC client-disconnect tests
# ---------------------------------------------------------------------------

TEST_CLIENT_VERSION = "test-version"

_state: dict[str, str] = {}


async def _stateful_handler(req: CoreRequest) -> CoreResponse:
    """Handler that persists key-value state across clients."""
    if req.method == "set":
        key = req.params.get("key", "")
        value = req.params.get("value", "")
        _state[key] = value
        return CoreResponse.success(req.request_id, result={"set": True})

    if req.method == "get":
        key = req.params.get("key", "")
        return CoreResponse.success(
            req.request_id,
            result={"value": _state.get(key)},
        )

    return CoreResponse.failure(req.request_id, code="UNKNOWN_METHOD", message="unknown")


@pytest.fixture
def short_tmp():  # type: ignore[override]
    """Create a short temp directory for Unix socket paths (macOS 104-byte limit)."""
    d = tempfile.mkdtemp(prefix="k-", dir="/tmp")
    yield Path(d)
    shutil.rmtree(d, ignore_errors=True)


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Unix sockets unavailable on Windows",
)
async def test_server_survives_client_disconnect(short_tmp) -> None:
    """When a TUI-style client disconnects, the server keeps running and serves others."""
    _state.clear()
    sock = str(short_tmp / "t.sock")
    transport = UnixSocketTransport(path=sock)
    server = IPCServer(handler=_stateful_handler, transport=transport)
    await server.start()

    ep = CoreEndpoint(transport="socket", address=sock, token=server.token)

    # Client A ("TUI") writes some state then disconnects
    client_a = IPCClient(ep, transport=UnixSocketTransport(path=sock))
    await client_a.connect()
    resp = await client_a.request(
        session_id="tui",
        session_origin="tui",
        client_version=TEST_CLIENT_VERSION,
        capability="state",
        method="set",
        params={"key": "progress", "value": "50%"},
    )
    assert resp.ok
    await client_a.close()
    assert not client_a.is_connected

    # Server should still be running
    assert server.is_running

    # Client B ("MCP") connects and can see the state written by Client A
    client_b = IPCClient(ep, transport=UnixSocketTransport(path=sock))
    await client_b.connect()
    resp = await client_b.request(
        session_id="mcp",
        session_origin="tui",
        client_version=TEST_CLIENT_VERSION,
        capability="state",
        method="get",
        params={"key": "progress"},
    )
    assert resp.ok
    assert resp.result is not None
    assert resp.result["value"] == "50%"

    await client_b.close()
    await server.stop()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Unix sockets unavailable on Windows",
)
async def test_state_mutations_visible_across_clients(short_tmp) -> None:
    """State changes from one client are visible to another client."""
    _state.clear()
    sock = str(short_tmp / "t.sock")
    transport = UnixSocketTransport(path=sock)
    server = IPCServer(handler=_stateful_handler, transport=transport)
    await server.start()

    ep = CoreEndpoint(transport="socket", address=sock, token=server.token)
    client_a = IPCClient(ep, transport=UnixSocketTransport(path=sock))
    client_b = IPCClient(ep, transport=UnixSocketTransport(path=sock))
    await client_a.connect()
    await client_b.connect()

    try:
        # Client A sets a value
        await client_a.request(
            session_id="tui",
            session_origin="tui",
            client_version=TEST_CLIENT_VERSION,
            capability="state",
            method="set",
            params={"key": "status", "value": "in_progress"},
        )

        # Client B reads the value
        resp = await client_b.request(
            session_id="mcp",
            session_origin="tui",
            client_version=TEST_CLIENT_VERSION,
            capability="state",
            method="get",
            params={"key": "status"},
        )
        assert resp.ok
        assert resp.result is not None
        assert resp.result["value"] == "in_progress"

        # Client B updates the value
        await client_b.request(
            session_id="mcp",
            session_origin="tui",
            client_version=TEST_CLIENT_VERSION,
            capability="state",
            method="set",
            params={"key": "status", "value": "review"},
        )

        # Client A sees the updated value
        resp = await client_a.request(
            session_id="tui",
            session_origin="tui",
            client_version=TEST_CLIENT_VERSION,
            capability="state",
            method="get",
            params={"key": "status"},
        )
        assert resp.ok
        assert resp.result is not None
        assert resp.result["value"] == "review"
    finally:
        await client_a.close()
        await client_b.close()
        await server.stop()


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="Unix sockets unavailable on Windows",
)
async def test_reconnect_after_disconnect(short_tmp) -> None:
    """A client can reconnect after disconnecting and resume communication."""
    _state.clear()
    sock = str(short_tmp / "t.sock")
    transport = UnixSocketTransport(path=sock)
    server = IPCServer(handler=_stateful_handler, transport=transport)
    await server.start()

    ep = CoreEndpoint(transport="socket", address=sock, token=server.token)
    client = IPCClient(ep, transport=UnixSocketTransport(path=sock))

    try:
        # First session: set state
        await client.connect()
        await client.request(
            session_id="tui",
            session_origin="tui",
            client_version=TEST_CLIENT_VERSION,
            capability="state",
            method="set",
            params={"key": "round", "value": "1"},
        )
        await client.close()

        # Reconnect
        client = IPCClient(ep, transport=UnixSocketTransport(path=sock))
        await client.connect()
        resp = await client.request(
            session_id="tui",
            session_origin="tui",
            client_version=TEST_CLIENT_VERSION,
            capability="state",
            method="get",
            params={"key": "round"},
        )
        assert resp.ok
        assert resp.result is not None
        assert resp.result["value"] == "1"
    finally:
        await client.close()
        await server.stop()
