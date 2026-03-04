import asyncio
from typing import Any

import pytest

import kagan.chat.acp as chat_acp

pytestmark = [pytest.mark.unit, pytest.mark.asyncio]


@pytest.fixture(autouse=True)
def _reset_warmup_state() -> None:
    chat_acp._WARMUP_STATE.warmed_backends.clear()
    chat_acp._WARMUP_STATE.locks.clear()


async def test_warm_orchestrator_backend_runs_once_per_backend_when_called_concurrently(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _fake_run_orchestrator_turn(
        client: Any,
        *,
        prompt: str,
        agent_backend: str,
        mcp_session_id: str | None = None,
        on_update: Any = None,
        send_prompt: bool = True,
    ) -> str:
        del client, mcp_session_id, on_update, prompt
        calls.append(f"{agent_backend}:{send_prompt}")
        await asyncio.sleep(0)
        return ""

    monkeypatch.setattr(chat_acp, "run_orchestrator_turn", _fake_run_orchestrator_turn)

    await asyncio.gather(
        chat_acp.warm_orchestrator_backend(object(), agent_backend="claude-code"),
        chat_acp.warm_orchestrator_backend(object(), agent_backend="claude-code"),
        chat_acp.warm_orchestrator_backend(object(), agent_backend="claude-code"),
    )

    assert calls == ["claude-code:False"]


async def test_warm_orchestrator_backend_tracks_cache_per_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[str] = []

    async def _fake_run_orchestrator_turn(
        client: Any,
        *,
        prompt: str,
        agent_backend: str,
        mcp_session_id: str | None = None,
        on_update: Any = None,
        send_prompt: bool = True,
    ) -> str:
        del client, mcp_session_id, on_update, prompt
        calls.append(f"{agent_backend}:{send_prompt}")
        return ""

    monkeypatch.setattr(chat_acp, "run_orchestrator_turn", _fake_run_orchestrator_turn)

    await chat_acp.warm_orchestrator_backend(object(), agent_backend="claude-code")
    await chat_acp.warm_orchestrator_backend(object(), agent_backend="codex")
    await chat_acp.warm_orchestrator_backend(object(), agent_backend="claude-code")

    assert calls == ["claude-code:False", "codex:False"]
