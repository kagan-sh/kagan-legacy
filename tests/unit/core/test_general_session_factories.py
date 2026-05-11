"""Unit tests: general-session ACP factory wiring (monkeypatch allowed)."""

from __future__ import annotations

import asyncio
from typing import Any

import acp
import pytest

from kagan.cli.chat import acp as cli_chat_acp
from kagan.core.chat import make_spawn_per_turn_acp_factory

pytestmark = [pytest.mark.core, pytest.mark.unit]


async def _noop_update(_update: Any) -> None:
    return None


@pytest.mark.asyncio
async def test_general_session_uses_raw_backend_without_kagan_prompt(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Raw spawn-per-turn factory forwards prompt blocks verbatim (lightweight=True)."""
    captured: dict[str, Any] = {}

    async def fake_run_orchestrator_turn(
        passed_client: object,
        *,
        prompt: str,
        agent_backend: str,
        on_update: Any,
        attachments: list[dict[str, str]] | None,
        cwd: Any,
        lightweight: bool = False,
        permission_resolver: Any,
    ) -> str:
        captured.update(
            {
                "prompt": prompt,
                "agent_backend": agent_backend,
                "lightweight": lightweight,
            }
        )
        return "raw reply"

    monkeypatch.setattr(cli_chat_acp, "run_orchestrator_turn", fake_run_orchestrator_turn)

    factory = make_spawn_per_turn_acp_factory(
        client=object(),
        default_agent_backend="codex",
        raw=True,
    )
    result = await factory.prompt(
        session_id="session-1",
        prompt_blocks=[acp.text_block("hello")],
        on_update=_noop_update,
        cancel_event=asyncio.Event(),
    )

    assert result.full_response == "raw reply"
    assert result.cancelled is False
    assert captured["lightweight"] is True
    assert captured["prompt"] == "hello"


@pytest.mark.asyncio
async def test_general_session_does_not_attach_kagan_tools(tmp_path: Any) -> None:
    """Raw long-lived factory skips MCP manifest creation and passes blocks verbatim."""
    from kagan.core.chat._factories import LongLivedACPFactory

    factory = LongLivedACPFactory(
        client=object(),
        agent_backend="codex",
        cwd=tmp_path,
        raw=True,
    )
    assert factory.raw is True

    class _FakeClient:
        async def settings_get(self) -> dict[str, str]:
            return {}

    factory.client = _FakeClient()
    factory._resolved_cwd = tmp_path  # type: ignore[attr-defined]

    blocks = [acp.text_block("user question")]
    built = await factory._build_prompt_blocks(blocks)

    assert len(built) == 1
    assert built[0].text == "user question"
