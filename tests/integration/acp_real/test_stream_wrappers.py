"""Real-stdio integration tests for ACP stream wrappers.

These tests drive the production ``spawn_filtered_agent_process`` and
``ClientSideConnection`` constructors against a hermetic echo agent
(``tests/helpers/echo_agent.py``). No agent binary on PATH is required —
the agent is a plain Python script invoked via ``sys.executable``.

What this layer catches that the unit suite cannot:

- ``ClientSideConnection.__init__`` enforces
  ``isinstance(output_stream, asyncio.StreamReader)``. Our wrappers must
  inherit from it; a regression here surfaced in 0.19.0b34 because the
  always-on suite stubbed the SDK out entirely.
- The full handshake → new_session → prompt → notification → teardown
  sequence over real stdio.
- ``_ByteCountingStreamReader`` / ``JsonRpcObjectStreamReader`` read-method
  delegation — anything the SDK actually calls is exercised.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any

import pytest
from acp import (
    PROTOCOL_VERSION,
    InitializeResponse,
    NewSessionResponse,
    text_block,
)
from acp.client.connection import ClientSideConnection
from acp.schema import (
    ClientCapabilities,
    Implementation,
    SessionNotification,
)

from kagan.core._acp_spawn import spawn_filtered_agent_process
from kagan.core._acp_streams import JsonRpcObjectStreamReader
from kagan.core._agent import _ByteCountingStreamReader
from tests.helpers.acp_loopback import AcpLoopback

pytestmark = [pytest.mark.integration]


_ECHO_AGENT_SCRIPT = Path(__file__).resolve().parents[2] / "helpers" / "echo_agent.py"


class _RecordingClient:
    """Minimal Client implementation that records session updates."""

    def __init__(self) -> None:
        self.notifications: list[SessionNotification] = []

    def on_connect(self, conn: Any) -> None:
        del conn

    async def request_permission(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError

    async def write_text_file(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError

    async def read_text_file(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError

    async def session_update(
        self, session_id: str, update: Any, **kwargs: Any
    ) -> None:
        self.notifications.append(
            SessionNotification(
                session_id=session_id, update=update, field_meta=kwargs or None
            )
        )

    async def create_terminal(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError

    async def terminal_output(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError

    async def release_terminal(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError

    async def wait_for_terminal_exit(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError

    async def kill_terminal(self, *_args: Any, **_kwargs: Any) -> Any:
        raise NotImplementedError

    async def ext_method(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        del params
        from acp import RequestError

        raise RequestError.method_not_found(method)

    async def ext_notification(
        self, method: str, params: dict[str, Any]
    ) -> None:
        del method, params


async def test_client_side_connection_accepts_kagan_stream_wrappers() -> None:
    """Regression: ``ClientSideConnection`` rejects readers that aren't
    ``asyncio.StreamReader`` subclasses. Both wrappers must clear that gate."""
    async with AcpLoopback() as link:

        class _FakeProcess:
            returncode: int | None = None

        json_wrapped = JsonRpcObjectStreamReader(
            link.client_reader, backend_name="echo"
        )
        bytes_wrapped = _ByteCountingStreamReader(link.client_reader, _FakeProcess())  # type: ignore[arg-type]

        for wrapper in (json_wrapped, bytes_wrapped):
            assert isinstance(wrapper, asyncio.StreamReader), type(wrapper)
            # Base attributes must be initialised — ``exception()`` reads
            # ``self._exception`` and would AttributeError if super().__init__
            # had been skipped.
            assert wrapper.exception() is None
            ClientSideConnection(_RecordingClient(), link.client_writer, wrapper)


async def test_spawn_filtered_agent_process_completes_full_handshake(
    tmp_path: Path,
) -> None:
    """End-to-end: spawn the echo agent through Kagan's
    ``spawn_filtered_agent_process``, run initialize → new_session → prompt,
    receive a notification, exit cleanly. This is the path that broke in
    0.19.0b34 with no test catching it."""
    assert _ECHO_AGENT_SCRIPT.exists(), _ECHO_AGENT_SCRIPT

    client = _RecordingClient()
    async with spawn_filtered_agent_process(
        client,
        sys.executable,
        str(_ECHO_AGENT_SCRIPT),
        backend_name="echo",
    ) as (conn, process):
        init = await asyncio.wait_for(
            conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(terminal=False),
                client_info=Implementation(
                    name="kagan-test", title="Kagan Test", version="0.0.0"
                ),
            ),
            timeout=5.0,
        )
        assert isinstance(init, InitializeResponse)

        session = await asyncio.wait_for(
            conn.new_session(mcp_servers=[], cwd=str(tmp_path)),
            timeout=5.0,
        )
        assert isinstance(session, NewSessionResponse)

        await asyncio.wait_for(
            conn.prompt(
                session_id=session.session_id,
                prompt=[text_block("hello echo")],
            ),
            timeout=5.0,
        )

        for _ in range(50):
            if client.notifications:
                break
            await asyncio.sleep(0.02)
        assert client.notifications, "echo agent did not send a session update"

    assert process.returncode is not None
