"""Integration tests for LongLivedACPFactory restart / retry behaviour.

Drives the real echo agent (``tests/helpers/echo_agent.py``) via
``spawn_filtered_agent_process`` to exercise the prompt loop with an actual
ACP subprocess.  Accessing ``factory._proc`` directly is intentional per the
patterns in ``test_stream_wrappers.py``.

No agent binary on PATH is required — the echo agent is invoked via
``sys.executable``.
"""

from __future__ import annotations

import asyncio
import sys
from contextlib import AsyncExitStack
from pathlib import Path

import pytest
from acp import PROTOCOL_VERSION, text_block
from acp.schema import ClientCapabilities, Implementation

from kagan.core._acp_spawn import spawn_filtered_agent_process
from kagan.core.chat._factories import LongLivedACPFactory

pytestmark = [pytest.mark.integration]

_ECHO_AGENT_SCRIPT = Path(__file__).resolve().parents[2] / "helpers" / "echo_agent.py"


# ---------------------------------------------------------------------------
# Minimal stubs
# ---------------------------------------------------------------------------


class _FakeSettings:
    async def get(self) -> dict[str, str]:
        return {}


class _FakeClient:
    active_project_id: str | None = None
    settings = _FakeSettings()


async def _boot_factory_via_echo_agent(
    tmp_path: Path,
) -> tuple[LongLivedACPFactory, AsyncExitStack]:
    """Spawn the echo agent and wire its conn/proc into a LongLivedACPFactory.

    We bypass ``__aenter__`` because ``_spawn_and_handshake`` requires a real
    ``kagan mcp`` CLI on PATH.  Instead we perform the handshake manually (the
    same sequence as ``test_stream_wrappers.py``) and assign the resulting
    conn/proc/capture into the factory's private fields.
    """
    from kagan.cli.chat.acp import _CaptureACPClient

    assert _ECHO_AGENT_SCRIPT.exists(), _ECHO_AGENT_SCRIPT

    factory = LongLivedACPFactory(
        client=_FakeClient(),
        agent_backend="claude-code",
        cwd=str(tmp_path),
    )

    capture = _CaptureACPClient(on_update=None, permission_resolver=None)
    stack = AsyncExitStack()

    conn, proc = await stack.enter_async_context(
        spawn_filtered_agent_process(
            capture,
            sys.executable,
            str(_ECHO_AGENT_SCRIPT),
            backend_name="echo",
        )
    )

    await asyncio.wait_for(
        conn.initialize(
            protocol_version=PROTOCOL_VERSION,
            client_capabilities=ClientCapabilities(terminal=False),
            client_info=Implementation(name="kagan-test", title="Kagan Test", version="0.0.0"),
        ),
        timeout=10.0,
    )

    session = await asyncio.wait_for(
        conn.new_session(mcp_servers=[], cwd=str(tmp_path)),
        timeout=10.0,
    )

    # Wire the live conn/proc into the factory.
    factory._entered = True
    factory._stack = stack
    factory._conn = conn
    factory._proc = proc
    factory._capture = capture
    factory._acp_session_id = session.session_id
    factory._resolved_cwd = tmp_path

    return factory, stack


async def _simple_prompt(factory: LongLivedACPFactory, text: str) -> str:
    """Send one prompt block through the factory and return the response text."""
    cancel_event = asyncio.Event()
    result = await factory.prompt(
        session_id="unused",
        prompt_blocks=[text_block(text)],
        on_update=lambda _: None,
        cancel_event=cancel_event,
    )
    return result.full_response


async def test_long_lived_factory_restarts_after_dead_process_before_prompt(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Kill the subprocess between turns; the next prompt() auto-restarts
    and returns a successful response from the fresh echo agent session."""
    factory, _stack = await _boot_factory_via_echo_agent(tmp_path)
    try:
        # First turn — should succeed on the live echo agent.
        first_response = await _simple_prompt(factory, "hello")
        assert first_response  # echo agent echoes back the prompt text

        # Terminate the subprocess.
        factory._proc.kill()
        await factory._proc.wait()
        assert factory._proc.returncode is not None

        # Stub restart() so it re-wires the factory without needing a real
        # kagan binary — we re-spawn the echo agent in its place.
        async def _fake_restart() -> None:
            fresh_factory, _fresh_stack = await _boot_factory_via_echo_agent(tmp_path)
            # Steal all internal state from the fresh factory.
            factory._entered = fresh_factory._entered
            factory._stack = fresh_factory._stack
            factory._conn = fresh_factory._conn
            factory._proc = fresh_factory._proc
            factory._capture = fresh_factory._capture
            factory._acp_session_id = fresh_factory._acp_session_id

        monkeypatch.setattr(factory, "restart", _fake_restart)

        # Second turn — factory should detect the dead process, restart, and succeed.
        second_response = await _simple_prompt(factory, "world")
        assert second_response  # echo agent echoes back the prompt text
    finally:
        # Tear down whatever stack is current on the factory.
        await factory.__aexit__(None, None, None)
