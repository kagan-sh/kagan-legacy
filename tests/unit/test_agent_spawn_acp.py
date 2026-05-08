import asyncio

import pytest

from kagan.core._agent import (
    AgentError,
    BackendCapability,
    BackendSpec,
    _ByteCountingStreamReader,
    build_agent_environment,
    spawn_agent_via_acp,
)

pytestmark = [pytest.mark.unit]


class _FakeProcess:
    def __init__(self) -> None:
        self.pid = 4242
        self.stdin = object()
        self.stdout = object()
        self.stderr = object()


async def _spawn_and_capture_command(
    *,
    backend_name: str,
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    prompt: str,
) -> list[str]:
    captured: dict[str, list[str]] = {}

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        del kwargs
        captured["cmd"] = [str(part) for part in cmd]
        return _FakeProcess()

    async def _fake_run_acp_session(*, process, client, worktree_path, prompt, mcp_manifest):
        del process, client, worktree_path, prompt
        assert mcp_manifest
        return None

    monkeypatch.setattr(
        "kagan.core._agent.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )
    monkeypatch.setattr("kagan.core._acp.run_acp_session", _fake_run_acp_session)
    # resolve_spawn_command calls shutil.which; return the bare name unchanged so
    # assertions on the captured command remain stable across environments.
    monkeypatch.setattr("kagan.core._subprocess.shutil.which", lambda exe: exe)

    _, reader_task = await spawn_agent_via_acp(
        backend_name,
        tmp_path,
        prompt,
        session_id="session-1",
        task_id="task-1",
        db_path=str(tmp_path / "kagan.db"),
        on_session_update=lambda *_: None,
    )
    await reader_task
    assert not (tmp_path / ".mcp.json").exists()
    return captured["cmd"]


@pytest.mark.parametrize(
    ("backend_name", "expected_command"),
    [
        ("kimi-cli", ["kimi", "acp"]),
        ("codex", ["npx", "-y", "@zed-industries/codex-acp"]),
        ("claude-code", ["npx", "claude-code-acp"]),
    ],
)
async def test_spawn_agent_acp_uses_acp_command_without_prompt_flags(
    backend_name: str,
    expected_command: list[str],
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cmd = await _spawn_and_capture_command(
        backend_name=backend_name,
        tmp_path=tmp_path,
        monkeypatch=monkeypatch,
        prompt="hello-from-test-prompt",
    )
    assert cmd == expected_command
    assert "-p" not in cmd
    assert "--prompt" not in cmd
    assert "hello-from-test-prompt" not in cmd


async def test_spawn_agent_acp_rejects_non_acp_backends(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = BackendSpec(
        name="test-non-acp",
        executable="example",
        acp_command=("example", "acp"),
        capabilities=frozenset(),
    )
    monkeypatch.setattr("kagan.core._agent.get_backend_spec", lambda _name: spec)

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        del cmd, kwargs
        raise AssertionError("create_subprocess_exec should not be called")

    monkeypatch.setattr(
        "kagan.core._agent.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    with pytest.raises(AgentError, match="does not support ACP execution"):
        await spawn_agent_via_acp(
            "test-non-acp",
            tmp_path,
            "ignored",
            session_id="session-1",
            task_id="task-1",
            db_path=str(tmp_path / "kagan.db"),
            on_session_update=lambda *_: None,
        )


async def test_spawn_agent_acp_uses_typed_capability_over_legacy_supports_flag(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    spec = BackendSpec(
        name="typed-acp",
        executable="typed-acp",
        acp_command=("typed-acp", "acp"),
        capabilities=frozenset({BackendCapability.ACP_STREAMING}),
    )
    monkeypatch.setattr("kagan.core._agent.get_backend_spec", lambda _name: spec)
    # resolve_spawn_command uses shutil.which from _subprocess, not _agent.
    monkeypatch.setattr("kagan.core._subprocess.shutil.which", lambda exe: exe)

    captured: dict[str, list[str]] = {}

    class _FakeProc:
        pid = 4242
        stdin = object()
        stdout = object()
        stderr = object()

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        del kwargs
        captured["cmd"] = [str(part) for part in cmd]
        return _FakeProc()

    async def _fake_run_acp_session(*, process, client, worktree_path, prompt, mcp_manifest):
        del process, client, worktree_path, prompt, mcp_manifest
        return None

    monkeypatch.setattr(
        "kagan.core._agent.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )
    monkeypatch.setattr("kagan.core._acp.run_acp_session", _fake_run_acp_session)

    pid, reader_task = await spawn_agent_via_acp(
        "typed-acp",
        tmp_path,
        "hello",
        session_id="session-1",
        task_id="task-1",
        db_path=str(tmp_path / "kagan.db"),
        on_session_update=lambda *_: None,
    )
    await reader_task

    assert pid == 4242
    assert captured["cmd"] == ["typed-acp", "acp"]


async def test_build_agent_environment_strips_macos_malloc_stack_logging_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("kagan.core._agent.sys.platform", "darwin")
    env = build_agent_environment(
        session_id="session-1",
        task_id=None,
        backend_env_vars={},
        base_env={
            "MallocStackLogging": "1",
            "MallocStackLoggingNoCompact": "1",
            "HOME": "/tmp/home",
        },
    )

    assert "MallocStackLogging" not in env
    assert "MallocStackLoggingNoCompact" not in env
    assert env["KAGAN_SESSION_ID"] == "session-1"
    assert env["KAGAN_MCP_CMD"] == "kagan mcp"


async def test_build_agent_environment_strips_malloc_stack_logging(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Non-essential env vars like MallocStackLogging are excluded by the allowlist."""
    env = build_agent_environment(
        session_id="session-1",
        task_id=None,
        backend_env_vars={},
        base_env={
            "MallocStackLogging": "1",
            "MallocStackLoggingNoCompact": "1",
        },
    )

    assert "MallocStackLogging" not in env
    assert "MallocStackLoggingNoCompact" not in env


async def test_byte_counting_reader_skips_blank_lines() -> None:
    reader = asyncio.StreamReader()
    reader.feed_data(b'\n  \n\r\n{"ok":true}\n')
    reader.feed_eof()

    proc = type("P", (), {"pid": 1, "terminate": lambda self: None})()
    wrapper = _ByteCountingStreamReader(reader, proc)

    assert await wrapper.readline() == b'{"ok":true}\n'
    assert await wrapper.readline() == b""
