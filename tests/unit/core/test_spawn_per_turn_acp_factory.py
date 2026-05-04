"""Unit tests for the spawn-per-turn ACP factory helper."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

import acp
import pytest

from kagan.cli.chat import acp as cli_chat_acp
from kagan.core.chat import make_spawn_per_turn_acp_factory

if TYPE_CHECKING:
    from pathlib import Path


async def _noop_update(_update: Any) -> None:
    return None


@pytest.mark.asyncio
async def test_spawn_per_turn_factory_forwards_prompt_contract(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client = object()
    attachments = [{"name": "note.txt", "data": "hello"}]
    captured: dict[str, Any] = {}

    async def fake_run_orchestrator_turn(
        passed_client: object,
        *,
        prompt: str,
        agent_backend: str,
        on_update: Any,
        attachments: list[dict[str, str]] | None,
        cwd: Path | None,
        permission_resolver: Any,
    ) -> str:
        captured.update(
            {
                "client": passed_client,
                "prompt": prompt,
                "agent_backend": agent_backend,
                "on_update": on_update,
                "attachments": attachments,
                "cwd": cwd,
                "permission_resolver": permission_resolver,
            }
        )
        return "assistant reply"

    monkeypatch.setattr(cli_chat_acp, "run_orchestrator_turn", fake_run_orchestrator_turn)

    factory = make_spawn_per_turn_acp_factory(
        client=client,
        default_agent_backend="codex",
        cwd=tmp_path,
        attachments=attachments,
    )
    result = await factory.prompt(
        session_id="ignored-for-spawn",
        prompt_blocks=[acp.text_block("first"), acp.text_block("second")],
        on_update=_noop_update,
        cancel_event=asyncio.Event(),
        agent_backend="claude-code",
        permission_resolver=None,
    )

    assert result.full_response == "assistant reply"
    assert result.cancelled is False
    assert captured == {
        "client": client,
        "prompt": "first\n\nsecond",
        "agent_backend": "claude-code",
        "on_update": _noop_update,
        "attachments": attachments,
        "cwd": tmp_path,
        "permission_resolver": None,
    }


@pytest.mark.asyncio
async def test_spawn_per_turn_factory_requires_backend() -> None:
    factory = make_spawn_per_turn_acp_factory(client=object())

    with pytest.raises(ValueError, match="agent_backend is required"):
        await factory.prompt(
            session_id="session-1",
            prompt_blocks=[acp.text_block("hello")],
            on_update=_noop_update,
            cancel_event=asyncio.Event(),
        )


@pytest.mark.asyncio
async def test_spawn_per_turn_factory_cancels_underlying_turn(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def fake_run_orchestrator_turn(*_args: Any, **_kwargs: Any) -> str:
        started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return "unreachable"

    monkeypatch.setattr(cli_chat_acp, "run_orchestrator_turn", fake_run_orchestrator_turn)

    cancel_event = asyncio.Event()
    factory = make_spawn_per_turn_acp_factory(client=object(), default_agent_backend="codex")
    turn_task = asyncio.create_task(
        factory.prompt(
            session_id="session-1",
            prompt_blocks=[acp.text_block("hello")],
            on_update=_noop_update,
            cancel_event=cancel_event,
        )
    )

    await started.wait()
    cancel_event.set()
    result = await turn_task

    assert result.cancelled is True
    assert result.full_response == ""
    assert cancelled.is_set()
