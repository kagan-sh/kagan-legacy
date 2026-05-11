"""Tests for general session support in the core chat system.

General sessions are raw backend chats with no Kagan orchestrator prompt,
no MCP tools, and a visible disclaimer.
"""

from __future__ import annotations

from typing import Any

import pytest

from kagan.core import ChatSessionCreateRequest, KaganCore

pytestmark = [pytest.mark.core, pytest.mark.smoke]


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
