"""Typed backend contract coverage for chat ACP helpers."""

from types import SimpleNamespace

import pytest

from kagan.cli.chat import acp as chat_acp
from kagan.core import BackendCapability, BackendSpec

pytestmark = [pytest.mark.unit]


def test_resolve_acp_command_uses_typed_backend_spec(monkeypatch: pytest.MonkeyPatch) -> None:
    spec = BackendSpec(
        name="typed-backend",
        executable="typed-backend",
        acp_command=("typed-backend", "acp"),
        supports_acp=False,
        capabilities=frozenset({BackendCapability.ACP_STREAMING}),
    )
    monkeypatch.setattr(chat_acp, "get_backend_spec", lambda _name: spec)
    monkeypatch.setattr(chat_acp.shutil, "which", lambda _exe: "/usr/bin/typed-backend")

    assert chat_acp._resolve_acp_command_for_backend("typed-backend") == (
        "typed-backend",
        ["acp"],
    )


def test_resolve_acp_command_rejects_backends_without_typed_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = BackendSpec(
        name="typed-backend",
        executable="typed-backend",
        acp_command=("typed-backend", "acp"),
        supports_acp=True,
        capabilities=frozenset(),
    )
    monkeypatch.setattr(chat_acp, "get_backend_spec", lambda _name: spec)

    with pytest.raises(RuntimeError, match="does not support ACP"):
        chat_acp._resolve_acp_command_for_backend("typed-backend")


@pytest.mark.asyncio
async def test_run_orchestrator_turn_uses_backend_spec_env_vars(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    spec = BackendSpec(
        name="typed-backend",
        executable="typed-backend",
        acp_command=("typed-backend", "acp"),
        env_vars={"TYPED_BACKEND_FLAG": "enabled"},
        supports_acp=False,
        capabilities=frozenset({BackendCapability.ACP_STREAMING}),
    )
    monkeypatch.setattr(chat_acp, "get_backend_spec", lambda _name: spec)
    monkeypatch.setattr(chat_acp.shutil, "which", lambda _exe: "/usr/bin/typed-backend")

    captured: dict[str, object] = {}

    class _FakeSession:
        session_id = "session-1"

    class _FakeConn:
        async def initialize(self, **_kwargs):
            return None

        async def new_session(self, **_kwargs):
            return _FakeSession()

        async def prompt(self, **_kwargs):
            return None

    class _FakeProcess:
        returncode = None
        stderr = None

    class _FakeSpawnContext:
        async def __aenter__(self):
            return _FakeConn(), _FakeProcess()

        async def __aexit__(self, exc_type, exc, tb):
            del exc_type, exc, tb
            return False

    def _fake_spawn_agent_process(_client, exe, *exe_args, **kwargs):
        captured["exe"] = exe
        captured["exe_args"] = list(exe_args)
        captured["env"] = dict(kwargs["env"])
        captured["cwd"] = kwargs["cwd"]
        return _FakeSpawnContext()

    monkeypatch.setattr(chat_acp.acp, "spawn_agent_process", _fake_spawn_agent_process)

    client = SimpleNamespace(
        active_project_id=None,
        settings=SimpleNamespace(get=lambda: {}),  # unused because send_prompt=False
    )

    result = await chat_acp.run_orchestrator_turn(
        client,
        prompt="",
        agent_backend="typed-backend",
        send_prompt=False,
        lightweight=True,
        cwd=tmp_path,
    )

    assert result == ""
    # resolve_spawn_command resolves the executable via shutil.which; on POSIX the
    # resolved path is passed directly, so accept any value ending in "typed-backend".
    assert str(captured["exe"]).endswith("typed-backend")
    assert captured["exe_args"] == ["acp"]
    assert captured["cwd"] == str(tmp_path)
    env = captured["env"]
    assert isinstance(env, dict)
    assert env["TYPED_BACKEND_FLAG"] == "enabled"
    assert env["KAGAN_SESSION_ID"]
    assert env["KAGAN_MCP_CMD"] == "kagan mcp"
