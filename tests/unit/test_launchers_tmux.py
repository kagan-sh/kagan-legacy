import asyncio

import pytest

from kagan.core import _agent, _launchers

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


async def _launch_with_blocked_injection(
    *,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
    agent_cmd: str,
    agent_backend: str,
) -> tuple[dict[str, object], float]:
    captured: dict[str, object] = {}
    started = asyncio.Event()
    release = asyncio.Event()
    finished = asyncio.Event()

    async def _fake_run_detached(*_cmd: str, **_kwargs: object) -> None:
        return None

    async def _fake_inject(**kwargs: object) -> None:
        captured.update(kwargs)
        started.set()
        await release.wait()
        finished.set()

    monkeypatch.setattr(_launchers, "_run_detached", _fake_run_detached)
    monkeypatch.setattr(_launchers, "_inject_tmux_startup_prompt", _fake_inject)

    loop = asyncio.get_running_loop()
    start = loop.time()
    await _launchers.launch_tmux(
        worktree_path=tmp_path,
        session_id="session:abc123",
        agent_cmd=agent_cmd,
        agent_backend=agent_backend,
        startup_prompt="Implement feature X",
    )
    elapsed = loop.time() - start

    await asyncio.wait_for(started.wait(), timeout=0.2)
    assert not finished.is_set()

    release.set()
    await asyncio.wait_for(finished.wait(), timeout=0.2)

    return captured, elapsed


async def test_launch_tmux_does_not_wait_for_codex_prompt_injection(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, elapsed = await _launch_with_blocked_injection(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        agent_cmd="codex",
        agent_backend="codex",
    )

    assert elapsed < 0.2
    assert captured["max_attempts"] == 60
    assert captured["wait_commands"] == ("codex",)
    assert "use_literal_send_keys" not in captured
    assert "ready_text" not in captured


async def test_launch_tmux_keeps_opencode_prompt_injection_behavior(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, elapsed = await _launch_with_blocked_injection(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        agent_cmd="opencode",
        agent_backend="opencode",
    )

    assert elapsed < 0.2
    assert captured["max_attempts"] == 60
    assert captured["wait_commands"] == ("node", "opencode")
    assert captured["use_literal_send_keys"] is True
    assert captured["ready_text"] == "Ask anything..."
    settle_seconds = captured.get("settle_seconds")
    assert isinstance(settle_seconds, (int, float))
    assert settle_seconds > 0


async def test_launch_tmux_uses_literal_prompt_injection_for_kimi(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured, elapsed = await _launch_with_blocked_injection(
        monkeypatch=monkeypatch,
        tmp_path=tmp_path,
        agent_cmd="kimi",
        agent_backend="kimi-cli",
    )

    assert elapsed < 0.2
    assert captured["max_attempts"] == 60
    assert captured["wait_commands"] == ("kimi",)
    assert captured["use_literal_send_keys"] is True
    assert "ready_text" not in captured
    settle_seconds = captured.get("settle_seconds")
    assert isinstance(settle_seconds, (int, float))
    assert settle_seconds > 0


@pytest.mark.smoke
@pytest.mark.parametrize("agent_backend", sorted(_agent.AGENT_BACKENDS))
async def test_tmux_startup_prompt_smoke_all_supported_backends(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
    agent_backend: str,
) -> None:
    session_name = "kagan-session-smoke"
    prompt_path = tmp_path / "start_prompt.md"
    prompt_path.write_text("First line\nSecond line\n", encoding="utf-8")

    executable_value = _agent.AGENT_BACKENDS[agent_backend].get("executable")
    assert isinstance(executable_value, str)
    executable = executable_value
    wait_commands = _launchers._prompt_injection_wait_commands(
        agent_cmd=executable,
        agent_backend=agent_backend,
    )
    options = _launchers._tmux_prompt_injection_options(agent_backend=agent_backend)
    use_literal = bool(options["use_literal_send_keys"])
    ready_text_raw = options["ready_text"]
    ready_text = ready_text_raw if isinstance(ready_text_raw, str) else None
    current_command = wait_commands[0] if wait_commands else executable

    seen_calls: list[tuple[str, ...]] = []

    async def _fake_run_tmux_command(*args: str, capture_stdout: bool = False) -> tuple[int, str]:
        del capture_stdout
        seen_calls.append(args)
        cmd = args[0]
        if cmd == "has-session":
            return 0, ""
        if cmd == "display-message":
            return 0, f"{current_command}\n"
        if cmd == "capture-pane":
            return 0, f"{ready_text}\n" if ready_text else ""
        if cmd in {"send-keys", "load-buffer", "paste-buffer", "delete-buffer"}:
            return 0, ""
        return 0, ""

    monkeypatch.setattr(_launchers, "_run_tmux_command", _fake_run_tmux_command)

    injected = await _launchers._send_tmux_startup_prompt(
        session_name,
        prompt_path,
        wait_for_commands=wait_commands,
        max_attempts=2,
        use_literal_send_keys=use_literal,
        ready_text=ready_text,
    )

    assert injected is True
    if use_literal:
        assert any(call and call[0] == "send-keys" and "-l" in call for call in seen_calls)
    else:
        assert any(call and call[0] == "load-buffer" for call in seen_calls)
        assert any(call and call[0] == "paste-buffer" for call in seen_calls)
