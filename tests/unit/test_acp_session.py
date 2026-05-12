import asyncio
import json
from contextlib import asynccontextmanager
from typing import Any, cast

import pytest
from acp.schema import AgentMessageChunk, AgentThoughtChunk, TextContentBlock

from kagan.core._acp import map_acp_update_to_event, run_acp_session
from kagan.core._acp_spawn import spawn_filtered_agent_process
from kagan.core._acp_streams import JsonRpcObjectStreamReader
from kagan.core._agent import _ByteCountingStreamReader

pytestmark = [pytest.mark.unit]


class _FakeSession:
    session_id = "session-1"


class _FakeConnection:
    def __init__(self) -> None:
        self.prompt_called = False
        self.closed = False

    async def initialize(self, *, protocol_version):
        del protocol_version
        return None

    async def new_session(self, *, cwd, mcp_servers):
        del cwd, mcp_servers
        return _FakeSession()

    async def prompt(self, *, session_id, prompt):
        del session_id, prompt
        self.prompt_called = True
        return None

    async def close(self):
        self.closed = True
        return None


class _CancelOnCloseConnection(_FakeConnection):
    async def close(self):
        raise asyncio.CancelledError


class _FakeProcess:
    def __init__(self) -> None:
        self.pid = 12345
        self.stdin = object()
        self.stdout = object()
        self.stderr: Any = None
        self.returncode: int | None = None
        self.terminated = False
        self.wait_calls = 0
        self.killed = False

    def terminate(self) -> None:
        self.terminated = True
        self.returncode = 0

    def kill(self) -> None:
        self.killed = True
        self.returncode = -9

    async def wait(self) -> int:
        self.wait_calls += 1
        return 0 if self.returncode is None else self.returncode


class _SlowInitializeConnection(_FakeConnection):
    async def initialize(self, *, protocol_version):
        del protocol_version
        await asyncio.Event().wait()


class _FakeStderr:
    def __init__(self, text: str) -> None:
        self._payload = text.encode("utf-8")

    async def read(self, _n: int = -1) -> bytes:
        return self._payload


async def test_run_acp_session_terminates_process_after_prompt(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp_manifest = json.dumps(
        {
            "mcpServers": {
                "kagan": {
                    "command": "kagan",
                    "args": ["mcp"],
                    "env": {},
                }
            }
        }
    )

    fake_conn = _FakeConnection()
    monkeypatch.setattr("kagan.core._acp.acp.connect_to_agent", lambda *_: fake_conn)

    process = _FakeProcess()
    await run_acp_session(
        process=cast("Any", process),
        client=cast("Any", object()),
        worktree_path=tmp_path,
        prompt="one-shot prompt",
        mcp_manifest=mcp_manifest,
    )

    assert fake_conn.prompt_called is True
    assert process.terminated is True
    assert process.wait_calls >= 1
    assert fake_conn.closed is True


async def test_spawn_filtered_agent_process_terminates_process_on_context_exit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kagan.core._acp_spawn as acp_spawn

    process = _FakeProcess()
    fake_conn = _FakeConnection()

    @asynccontextmanager
    async def fake_spawn_stdio_transport(*_args: Any, **_kwargs: Any):
        yield object(), object(), process

    monkeypatch.setattr(acp_spawn, "spawn_stdio_transport", fake_spawn_stdio_transport)
    monkeypatch.setattr(acp_spawn, "ClientSideConnection", lambda *_args, **_kwargs: fake_conn)

    async with spawn_filtered_agent_process(lambda agent: agent, "agent", backend_name="codex"):
        pass

    assert process.terminated is True
    assert process.wait_calls == 1
    assert fake_conn.closed is True


async def test_spawn_filtered_agent_process_terminates_process_when_close_is_cancelled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import kagan.core._acp_spawn as acp_spawn

    process = _FakeProcess()
    fake_conn = _CancelOnCloseConnection()

    @asynccontextmanager
    async def fake_spawn_stdio_transport(*_args: Any, **_kwargs: Any):
        yield object(), object(), process

    monkeypatch.setattr(acp_spawn, "spawn_stdio_transport", fake_spawn_stdio_transport)
    monkeypatch.setattr(acp_spawn, "ClientSideConnection", lambda *_args, **_kwargs: fake_conn)

    with pytest.raises(asyncio.CancelledError):
        async with spawn_filtered_agent_process(lambda agent: agent, "agent", backend_name="codex"):
            pass

    assert process.terminated is True
    assert process.wait_calls == 1


async def test_run_acp_session_surfaces_early_process_exit_on_initialize_timeout(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    mcp_manifest = json.dumps(
        {"mcpServers": {"kagan": {"command": "kagan", "args": ["mcp"], "env": {}}}}
    )

    fake_conn = _SlowInitializeConnection()
    monkeypatch.setattr("kagan.core._acp.acp.connect_to_agent", lambda *_: fake_conn)
    monkeypatch.setenv("KAGAN_ACP_STARTUP_TIMEOUT_SECONDS", "0.01")

    process = _FakeProcess()
    process.returncode = 1
    process.stderr = _FakeStderr("EACCES: permission denied")

    with pytest.raises(RuntimeError, match="exited before ACP initialize"):
        await run_acp_session(
            process=cast("Any", process),
            client=cast("Any", object()),
            worktree_path=tmp_path,
            prompt="one-shot prompt",
            mcp_manifest=mcp_manifest,
        )


async def test_map_acp_update_to_event_uses_lightweight_chunk_payload_without_model_dump(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def _raise_model_dump(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        del self, args, kwargs
        raise AssertionError("model_dump should not run for message/thought chunks")

    monkeypatch.setattr(AgentMessageChunk, "model_dump", _raise_model_dump)
    monkeypatch.setattr(AgentThoughtChunk, "model_dump", _raise_model_dump)

    message_update = AgentMessageChunk(
        content=TextContentBlock(type="text", text="hello"),
        session_update="agent_message_chunk",
    )
    thought_update = AgentThoughtChunk(
        content=TextContentBlock(type="text", text="plan"),
        session_update="agent_thought_chunk",
    )

    message_result = map_acp_update_to_event(message_update)
    thought_result = map_acp_update_to_event(thought_update)

    assert message_result == (
        "output_chunk",
        {
            "text": "hello",
            "acp": {
                "sessionUpdate": "agent_message_chunk",
                "content": {"type": "text", "text": "hello"},
            },
        },
    )
    assert thought_result == (
        "output_chunk",
        {
            "text": "plan",
            "thought": True,
            "acp": {
                "sessionUpdate": "agent_thought_chunk",
                "content": {"type": "text", "text": "plan"},
            },
        },
    )


async def test_acp_stream_wrappers_satisfy_client_side_connection_isinstance_gate() -> None:
    """Regression: ``ClientSideConnection.__init__`` enforces
    ``isinstance(output_stream, asyncio.StreamReader)``. Both wrappers we hand
    the SDK must therefore be subclasses of ``asyncio.StreamReader`` — losing
    that inheritance silently produced ``ClientSideConnection requires asyncio
    StreamWriter/StreamReader`` at runtime in 0.19.0b34.
    """
    from acp.client.connection import ClientSideConnection

    loop = asyncio.get_running_loop()
    reader = asyncio.StreamReader()
    transport = cast("Any", _NullTransport())
    writer = asyncio.StreamWriter(transport, asyncio.StreamReaderProtocol(reader), reader, loop)

    class _FakeProcess:
        returncode: int | None = None

    wrappers: list[asyncio.StreamReader] = [
        JsonRpcObjectStreamReader(reader, backend_name="claude-code"),
        cast(
            "asyncio.StreamReader", _ByteCountingStreamReader(reader, cast("Any", _FakeProcess()))
        ),
    ]

    for wrapper in wrappers:
        assert isinstance(wrapper, asyncio.StreamReader), type(wrapper)
        # Base StreamReader attributes (e.g. ``_exception``) must be initialised
        # — otherwise ``exception()`` raises ``AttributeError`` on any error
        # path the SDK might exercise via the inherited interface.
        assert wrapper.exception() is None
        # Construct the real SDK connection. The isinstance gate fires before
        # any router setup, so success here means the gate accepts the wrapper.
        ClientSideConnection(lambda _agent: cast("Any", object()), writer, wrapper)


async def test_acp_stream_wrappers_delegate_exception_to_underlying_reader() -> None:
    """The asyncio transport calls ``set_exception`` on the *wrapped* reader
    when the process dies. ``wrapper.exception()`` must reflect that, not
    return ``None`` (its own un-touched ``_exception`` attribute)."""
    underlying = asyncio.StreamReader()

    class _FakeProcess:
        returncode: int | None = None

    wrappers: list[asyncio.StreamReader] = [
        JsonRpcObjectStreamReader(underlying, backend_name="claude-code"),
        cast(
            "asyncio.StreamReader",
            _ByteCountingStreamReader(underlying, cast("Any", _FakeProcess())),
        ),
    ]

    for wrapper in wrappers:
        assert wrapper.exception() is None

    boom = ConnectionResetError("transport died")
    underlying.set_exception(boom)

    for wrapper in wrappers:
        assert wrapper.exception() is boom, (
            f"{type(wrapper).__name__}.exception() must delegate to the wrapped reader"
        )

    # ``set_exception`` on the wrapper must also propagate to the underlying
    # reader so the SDK's own paths see it.
    fresh_underlying = asyncio.StreamReader()
    fresh_wrapper = JsonRpcObjectStreamReader(fresh_underlying, backend_name="claude-code")
    other_boom = OSError("eof")
    fresh_wrapper.set_exception(other_boom)
    assert fresh_underlying.exception() is other_boom


class _NullTransport(asyncio.Transport):
    def is_closing(self) -> bool:
        return True

    def close(self) -> None:
        return None
