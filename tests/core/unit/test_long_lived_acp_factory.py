"""Unit tests for ``kagan.core.chat._factories.LongLivedACPFactory``.

Mocks ``acp.spawn_agent_process`` and the ACP-capable-backend lookup so these
tests don't actually spawn an orchestrator subprocess. The factory's contract:
ONE subprocess across many turns; ``restart()`` tears down + respawns; the
permission resolver round-trips through the long-lived ``_CaptureACPClient``.
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from kagan.cli.chat import acp as cli_chat_acp
from kagan.core import BackendCapability
from kagan.core._agent import BackendSpec
from kagan.core.chat import LongLivedACPFactory

if TYPE_CHECKING:
    pass

pytestmark = [pytest.mark.core]


# ---------------------------------------------------------------------------
# Mock ACP plumbing
# ---------------------------------------------------------------------------


class _FakeSession:
    session_id = "session-fake"


class _FakeProcess:
    returncode = None
    stderr = None


class _FakeConn:
    """Captures the bound capture client so tests can drive it directly."""

    def __init__(self) -> None:
        self.capture: Any = None
        self.prompt_calls: list[Any] = []
        self.closed = False
        self.prompt_behavior: Any = None  # callable(self, prompt_blocks) -> Awaitable

    async def initialize(self, **_kwargs: Any) -> None:
        return None

    async def new_session(self, **_kwargs: Any) -> _FakeSession:
        return _FakeSession()

    async def prompt(self, *, session_id: str, prompt: list[Any]) -> None:
        del session_id
        self.prompt_calls.append(prompt)
        if self.prompt_behavior is not None:
            await self.prompt_behavior(self, prompt)


class _SpawnRecorder:
    """Tracks how many times spawn_agent_process is invoked."""

    def __init__(self) -> None:
        self.count = 0
        self.conns: list[_FakeConn] = []
        self.last_capture: Any = None

    def spawn(self, capture: Any, _exe: str, *_args: Any, **_kwargs: Any) -> Any:
        self.count += 1
        self.last_capture = capture
        conn = _FakeConn()
        conn.capture = capture
        self.conns.append(conn)

        recorder = self

        class _Ctx:
            async def __aenter__(self_ctx) -> tuple[_FakeConn, _FakeProcess]:
                del self_ctx
                return conn, _FakeProcess()

            async def __aexit__(self_ctx, exc_type: Any, exc: Any, tb: Any) -> bool:
                del self_ctx, exc_type, exc, tb
                conn.closed = True
                return False

        return _Ctx()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def patched_factory(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> tuple[LongLivedACPFactory, _SpawnRecorder]:
    spec = BackendSpec(
        name="typed-backend",
        executable="typed-backend",
        acp_command=("typed-backend", "acp"),
        capabilities=frozenset({BackendCapability.ACP_STREAMING}),
    )
    monkeypatch.setattr(cli_chat_acp, "get_backend_spec", lambda _name: spec)
    monkeypatch.setattr(cli_chat_acp.shutil, "which", lambda _exe: "/usr/bin/typed-backend")

    # The factory imports get_backend_spec lazily from `kagan.core`; patch at
    # the source module so the deferred import resolves to our fake.
    import kagan.core as core_pkg
    import kagan.core._agent as core_agent_mod

    monkeypatch.setattr(core_pkg, "get_backend_spec", lambda _name: spec)
    monkeypatch.setattr(core_agent_mod, "get_backend_spec", lambda _name: spec)

    recorder = _SpawnRecorder()
    monkeypatch.setattr(cli_chat_acp.acp, "spawn_agent_process", recorder.spawn)

    # Stub orchestrator system-prompt resolution so _build_prompt_blocks is fast.
    import kagan.core.chat._factories as factories_mod

    async def _fake_settings_get() -> dict[str, Any]:
        return {}

    client = SimpleNamespace(
        active_project_id=None,
        settings=SimpleNamespace(get=_fake_settings_get),
    )

    monkeypatch.setattr(
        factories_mod,
        "resolve_orchestrator_prompt",
        lambda _settings, _cwd: "SYSTEM",
        raising=False,
    )
    # The factory imports it lazily inside _build_prompt_blocks. Patch the
    # source module that the lazy import resolves to.
    import kagan.core as core_pkg

    monkeypatch.setattr(core_pkg, "resolve_orchestrator_prompt", lambda _s, _c: "SYSTEM")

    factory = LongLivedACPFactory(
        client=client,
        agent_backend="typed-backend",
        cwd=tmp_path,
    )
    return factory, recorder


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_long_lived_factory_shares_subprocess_across_turns(
    patched_factory: tuple[LongLivedACPFactory, _SpawnRecorder],
) -> None:
    factory, recorder = patched_factory

    async with factory:
        from acp.schema import TextContentBlock

        for _ in range(2):
            cancel = asyncio.Event()
            updates: list[Any] = []

            async def _on_update(u: Any) -> None:
                updates.append(u)

            result = await factory.prompt(
                session_id="ignored",
                prompt_blocks=[TextContentBlock(type="text", text="hi")],
                on_update=_on_update,
                cancel_event=cancel,
            )
            assert result.cancelled is False

    assert recorder.count == 1, "spawn_agent_process must be called once across turns"
    assert len(recorder.conns[0].prompt_calls) == 2


async def test_long_lived_factory_restart_respawns(
    patched_factory: tuple[LongLivedACPFactory, _SpawnRecorder],
) -> None:
    factory, recorder = patched_factory

    async with factory:
        from acp.schema import TextContentBlock

        cancel = asyncio.Event()

        async def _noop(_u: Any) -> None:
            return None

        await factory.prompt(
            session_id="x",
            prompt_blocks=[TextContentBlock(type="text", text="t1")],
            on_update=_noop,
            cancel_event=cancel,
        )
        assert recorder.count == 1
        first_conn = recorder.conns[0]

        await factory.restart()
        assert recorder.count == 2
        assert first_conn.closed is True

        await factory.prompt(
            session_id="x",
            prompt_blocks=[TextContentBlock(type="text", text="t2")],
            on_update=_noop,
            cancel_event=asyncio.Event(),
        )
        assert recorder.count == 2  # still two spawns total
        assert len(recorder.conns[1].prompt_calls) == 1


async def test_long_lived_factory_cancel_mid_turn(
    patched_factory: tuple[LongLivedACPFactory, _SpawnRecorder],
) -> None:
    factory, recorder = patched_factory

    started = asyncio.Event()

    async def _suspend_until_cancelled(conn: _FakeConn, _prompt: Any) -> None:
        del conn
        started.set()
        # Suspend forever — the factory's cancel_task will cancel us.
        await asyncio.Event().wait()

    async with factory:
        recorder.conns[0].prompt_behavior = _suspend_until_cancelled

        from acp.schema import TextContentBlock

        cancel = asyncio.Event()

        async def _on_update(_u: Any) -> None:
            return None

        async def _cancel_soon() -> None:
            await started.wait()
            cancel.set()

        cancel_driver = asyncio.create_task(_cancel_soon())
        try:
            result = await factory.prompt(
                session_id="x",
                prompt_blocks=[TextContentBlock(type="text", text="long")],
                on_update=_on_update,
                cancel_event=cancel,
            )
        finally:
            cancel_driver.cancel()

        assert result.cancelled is True


async def test_long_lived_factory_permission_resolver_round_trip(
    patched_factory: tuple[LongLivedACPFactory, _SpawnRecorder],
) -> None:
    """Drives request_permission on the long-lived capture client and asserts
    the resolver decision becomes an ACP AllowedOutcome."""
    factory, recorder = patched_factory

    from acp.schema import (
        AllowedOutcome,
        PermissionOption,
        TextContentBlock,
    )

    resolved: dict[str, Any] = {}

    async def _resolver(payload: Any) -> Any:
        from kagan.core.chat.acp import PermissionDecision

        resolved["payload"] = payload
        return PermissionDecision(outcome="allow_once")

    async def _request_permission_during_prompt(conn: _FakeConn, _prompt: Any) -> None:
        # Mid-turn the agent issues a request_permission JSON-RPC call.
        options = [
            PermissionOption(option_id="allow-1", name="Allow once", kind="allow_once"),
            PermissionOption(option_id="deny-1", name="Deny", kind="reject_once"),
        ]
        tool_call = SimpleNamespace(tool_call_id="tc-1", title="bash", kind="execute")
        response = await conn.capture.request_permission(
            options=options, session_id="s", tool_call=tool_call
        )
        resolved["response"] = response

    async with factory:
        recorder.conns[0].prompt_behavior = _request_permission_during_prompt

        cancel = asyncio.Event()

        async def _noop(_u: Any) -> None:
            return None

        await factory.prompt(
            session_id="x",
            prompt_blocks=[TextContentBlock(type="text", text="needs-permission")],
            on_update=_noop,
            cancel_event=cancel,
            permission_resolver=_resolver,
        )

    response = resolved["response"]
    assert isinstance(response.outcome, AllowedOutcome)
    assert response.outcome.option_id == "allow-1"
    payload = resolved["payload"]
    assert payload.tool_call.get("title") == "bash"
    assert any(opt.get("kind") == "allow_once" for opt in payload.options)
