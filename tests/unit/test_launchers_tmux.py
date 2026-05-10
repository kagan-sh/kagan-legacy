"""Tests for tmux launcher — v0.5.0-style prompt-as-CLI-arg approach."""

import asyncio
import sys

import pytest

from kagan.core import _agent, _launchers

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(sys.platform == "win32", reason="tmux is unavailable on Windows"),
]


@pytest.mark.asyncio
async def test_launch_tmux_creates_session_and_sends_command(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """launch_tmux creates an empty tmux session then send-keys the launch command."""
    calls: list[tuple[str, ...]] = []

    async def _fake_run_detached(*cmd: str, **_kw: object) -> None:
        calls.append(cmd)

    async def _fake_send_keys(session_name: str, text: str) -> None:
        calls.append(("send-keys", session_name, text))

    monkeypatch.setattr(_launchers, "_run_detached", _fake_run_detached)
    monkeypatch.setattr(_launchers, "_tmux_send_keys", _fake_send_keys)

    await _launchers.launch_tmux(
        worktree_path=tmp_path,
        session_id="session:abc123",
        agent_cmd="claude",
        agent_backend="claude-code",
        startup_prompt="Implement feature X",
    )

    # First call: tmux new-session
    assert calls[0][0] == "tmux"
    assert "new-session" in calls[0]
    assert "-d" in calls[0]
    session_name = "kagan-session-abc123"
    assert session_name in calls[0]

    # Second call: send-keys with launch command containing prompt
    assert calls[1][0] == "send-keys"
    assert calls[1][1] == session_name
    launch_cmd = calls[1][2]
    assert "claude" in launch_cmd
    assert "Implement feature X" in launch_cmd


@pytest.mark.asyncio
async def test_launch_tmux_falls_back_to_agent_cmd_without_backend(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Without agent_backend, launch_tmux falls back to bare agent_cmd."""
    calls: list[tuple[str, ...]] = []

    async def _fake_run_detached(*cmd: str, **_kw: object) -> None:
        calls.append(cmd)

    async def _fake_send_keys(session_name: str, text: str) -> None:
        calls.append(("send-keys", session_name, text))

    monkeypatch.setattr(_launchers, "_run_detached", _fake_run_detached)
    monkeypatch.setattr(_launchers, "_tmux_send_keys", _fake_send_keys)

    await _launchers.launch_tmux(
        worktree_path=tmp_path,
        session_id="sess1",
        agent_cmd="my-agent",
        agent_backend=None,
        startup_prompt="Hello",
    )

    launch_cmd = calls[1][2]
    assert launch_cmd == "my-agent"


@pytest.mark.asyncio
async def test_launch_tmux_writes_mcp_json_and_prompt(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def _noop_run(*_cmd: str, **_kw: object) -> None:
        return None

    async def _noop_send(_name: str, _text: str) -> None:
        return None

    monkeypatch.setattr(_launchers, "_run_detached", _noop_run)
    monkeypatch.setattr(_launchers, "_tmux_send_keys", _noop_send)

    await _launchers.launch_tmux(
        worktree_path=tmp_path,
        session_id="s1",
        agent_cmd="claude",
        agent_backend="claude-code",
        db_path="/tmp/test.db",
        startup_prompt="Test prompt content",
    )

    mcp_json = tmp_path / ".mcp.json"
    assert mcp_json.exists()

    prompt_file = tmp_path / ".kagan" / "start_prompt.md"
    assert prompt_file.exists()
    assert "Test prompt content" in prompt_file.read_text()


@pytest.mark.asyncio
async def test_launch_tmux_does_not_block(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """launch_tmux should return quickly — no blocking injection loop."""

    async def _noop_run(*_cmd: str, **_kw: object) -> None:
        return None

    async def _noop_send(_name: str, _text: str) -> None:
        return None

    monkeypatch.setattr(_launchers, "_run_detached", _noop_run)
    monkeypatch.setattr(_launchers, "_tmux_send_keys", _noop_send)

    loop = asyncio.get_running_loop()
    start = loop.time()
    await _launchers.launch_tmux(
        worktree_path=tmp_path,
        session_id="s1",
        agent_cmd="claude",
        agent_backend="claude-code",
        startup_prompt="Test",
    )
    elapsed = loop.time() - start
    assert elapsed < 1.0


def test_build_launch_command_uses_prompt_flag() -> None:
    """_build_launch_command uses the registry's prompt_flag."""
    cmd = _launchers._build_launch_command("claude-code", "Hello world")
    assert cmd is not None
    assert cmd.startswith("claude -p ")


@pytest.mark.parametrize("agent_backend", sorted(_agent.list_backends()))
def test_build_launch_command_smoke_all_backends(agent_backend: str) -> None:
    """All registered backends produce a non-None command."""
    cmd = _launchers._build_launch_command(agent_backend, "test prompt")
    assert cmd is not None
    executable = _agent.get_backend_spec(agent_backend).executable
    assert executable in cmd


def test_tmux_session_name_uses_session_id() -> None:
    """KanbanScreen._tmux_session_name strips the 'session:' prefix."""
    from kagan.tui.screens.kanban import KanbanScreen

    assert KanbanScreen._tmux_session_name("session:abc123") == "kagan-session-abc123"
