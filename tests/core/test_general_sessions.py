"""Tests for general session support in the core chat system.

General sessions are raw backend chats with no Kagan orchestrator prompt,
no MCP tools, and a visible disclaimer.
"""

from __future__ import annotations

import asyncio
from typing import Any

import acp
import pytest

from kagan.cli.chat import acp as cli_chat_acp
from kagan.core import ChatSessionCreateRequest, KaganCore
from kagan.core.chat import make_spawn_per_turn_acp_factory

pytestmark = [pytest.mark.core, pytest.mark.smoke]


async def _noop_update(_update: Any) -> None:
    return None


# ---------------------------------------------------------------------------
# Model / aggregate tests
# ---------------------------------------------------------------------------


async def test_existing_chat_sessions_migrate_to_orchestrator_type(tmp_path: Any) -> None:
    """A session created without specifying type defaults to 'orchestrator'."""
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        row = await core.chat_sessions.create(source="test", label="Default Type")
        assert row.session_type == "orchestrator"

        fetched = await core.chat_sessions.get(row.id)
        assert fetched is not None
        assert fetched.session_type == "orchestrator"
    finally:
        core.close()


async def test_general_session_records_visible_disclaimer(tmp_path: Any) -> None:
    """create_general appends a disclaimer system message to chat history."""
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        row = await core.chat_sessions.create_general(backend="fake", label="General Test")
        assert row.session_type == "general"

        history = await core.chat_sessions.history(row.id)
        assert len(history) == 1
        assert history[0].role == "system"
        assert "General session" in history[0].content
        assert "without Kagan project tools" in history[0].content
    finally:
        core.close()


# ---------------------------------------------------------------------------
# Request model
# ---------------------------------------------------------------------------


def test_chat_session_create_request_accepts_session_type() -> None:
    """ChatSessionCreateRequest accepts an optional session_type field."""
    req = ChatSessionCreateRequest(session_type="general")
    assert req.session_type == "general"

    req_default = ChatSessionCreateRequest()
    assert req_default.session_type is None


# ---------------------------------------------------------------------------
# Factory tests
# ---------------------------------------------------------------------------


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
async def test_general_session_does_not_attach_kagan_tools(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Any,
) -> None:
    """Raw long-lived factory skips MCP manifest creation and passes blocks verbatim."""
    from kagan.core.chat._factories import LongLivedACPFactory

    # Verify the dataclass accepts raw=True
    factory = LongLivedACPFactory(
        client=object(),
        agent_backend="codex",
        cwd=tmp_path,
        raw=True,
    )
    assert factory.raw is True

    # Verify _build_prompt_blocks passes through without system prompt injection.
    # _build_prompt_blocks reads self.client.settings.get() and self._resolved_cwd;
    # mock them so the method can run without a real KaganCore.
    class _FakeClient:
        async def settings_get(self) -> dict[str, str]:
            return {}

    factory.client = _FakeClient()
    factory._resolved_cwd = tmp_path  # type: ignore[attr-defined]

    blocks = [acp.text_block("user question")]
    built = await factory._build_prompt_blocks(blocks)

    # Should be exactly the input blocks (no system prompt prepended)
    assert len(built) == 1
    assert built[0].text == "user question"
