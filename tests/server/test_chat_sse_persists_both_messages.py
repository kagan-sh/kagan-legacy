"""Regression test for the Greptile P1 data-loss in SSE chat turns.

Prior to the fix, ``_sse_stream`` called the legacy ``save_chat_session``
shim *after* ``engine.push_user``. The shim's ``upsert_with_history`` deleted
every ``ChatMessage`` row for the session and re-inserted only the snapshot
that ``get_chat_session`` had loaded *before* the user row was persisted.
Net effect: every SSE turn ended with the user row missing from the DB.

This test drives a full ``_sse_stream`` against a real ``KaganCore`` plus a
``ScriptedFactory`` stand-in for ``SpawnPerTurnACPFactory``, then asserts that
both the user and the assistant rows survived the round trip.
"""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

from kagan.cli.chat.sessions import get_chat_session
from kagan.core import KaganCore
from kagan.server import _chat_routes
from tests.helpers.chat_engine import ScriptedFactory

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.smoke]


async def _drain_sse(stream: Any) -> list[str]:
    chunks: list[str] = []
    async for chunk in stream:
        chunks.append(chunk)
    return chunks


async def test_sse_turn_persists_both_user_and_assistant_rows(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A full SSE turn must persist BOTH the user row and the assistant row.

    Greptile P1: prior to the fix the second call (``save_chat_session``)
    wiped the user row that ``push_user`` had just persisted.
    """
    db_path = tmp_path / "kagan.db"
    core = KaganCore(db_path=db_path)
    try:
        await core.reset()

        # Replace the engine's ACP factory with a scripted one so we don't
        # try to spawn a real orchestrator.
        scripted = ScriptedFactory(chunks=["assistant reply"])
        # The route builds a *new* SpawnPerTurnACPFactory per request and
        # passes it into ``stream_assistant`` as ``acp_factory``. Patch the
        # constructor to return our scripted factory regardless of args.
        monkeypatch.setattr(
            _chat_routes,
            "SpawnPerTurnACPFactory",
            lambda **_kwargs: scripted,
        )

        session = await core.chat_sessions.create(source="web", label="t")
        session_dict = await get_chat_session(core, session.id)
        assert session_dict is not None

        ctx = SimpleNamespace(client=core)
        stream = _chat_routes._sse_stream(  # noqa: SLF001
            ctx,
            session.id,
            session_dict,
            text="hello there",
            backend="claude-code",
            attachments=None,
        )
        frames = await _drain_sse(stream)

        # Sanity: the producer emitted CHAT_USER_MESSAGE and CHAT_DONE frames.
        joined = "".join(frames)
        assert "CHAT_USER_MESSAGE" in joined
        assert "CHAT_DONE" in joined

        # The actual regression assertion: both rows survived in the DB.
        history = await core.chat_sessions.history(session.id)
        roles = [m.role for m in history]
        assert "user" in roles, (
            f"User row missing — Greptile P1 regression has returned. roles={roles}"
        )
        assert "assistant" in roles
        user_rows = [m for m in history if m.role == "user"]
        assistant_rows = [m for m in history if m.role == "assistant"]
        assert len(user_rows) == 1
        assert user_rows[0].content == "hello there"
        assert len(assistant_rows) == 1
        assert assistant_rows[0].content == "assistant reply"
    finally:
        core.close()
