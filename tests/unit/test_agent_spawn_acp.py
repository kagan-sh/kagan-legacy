import pytest

from kagan.core._agent import (
    AGENT_BACKENDS,
    AgentError,
    build_agent_environment,
    spawn_agent_via_acp,
)

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


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
    AGENT_BACKENDS["test-non-acp"] = {
        "executable": "example",
        "prompt_flag": "-p",
        "workdir_flag": None,
        "env_vars": {},
        "supports_acp": False,
    }

    async def _fake_create_subprocess_exec(*cmd, **kwargs):
        del cmd, kwargs
        raise AssertionError("create_subprocess_exec should not be called")

    monkeypatch.setattr(
        "kagan.core._agent.asyncio.create_subprocess_exec",
        _fake_create_subprocess_exec,
    )

    try:
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
    finally:
        AGENT_BACKENDS.pop("test-non-acp", None)


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
