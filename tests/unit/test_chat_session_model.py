"""Unit tests for the implicit session model (Change 2).

``hydrate_persistent_session`` should:
- Always create a fresh session when called with no flags.
- Resume a specific session when ``explicit_session_id`` is supplied.
"""

from __future__ import annotations

import pytest

from tests.helpers.fake_repl_chat_client import FakeReplChatClient

pytestmark = [pytest.mark.unit]


class _FakeRow:
    def __init__(
        self,
        session_id: str,
        backend: str = "claude-code",
        updated_at: str = "2024-01-01T00:00:00",
    ) -> None:
        self.id = session_id
        self.label = "REPL session"
        self.source = "repl"
        self.agent_backend = backend
        self.project_id = "proj-1"
        self.session_type = "orchestrator"
        self.updated_at = updated_at


def _make_controller(client: FakeReplChatClient) -> object:
    from kagan.cli.chat.controller import ChatController

    return ChatController(client, agent_backend="claude-code")


async def test_new_invocation_creates_fresh_session() -> None:
    """No flags → always create a new session, never show a picker."""
    client = FakeReplChatClient(new_session_id="brand-new")
    ctrl = _make_controller(client)

    await ctrl.hydrate_persistent_session()

    assert len(client.chat_sessions.create_calls) == 1
    assert ctrl._chat_session_id == "brand-new"


async def test_new_invocation_creates_fresh_session_even_when_sessions_exist() -> None:
    """Even if old sessions exist, no picker should appear on plain invocation."""
    client = FakeReplChatClient(new_session_id="fresh")
    old_row = _FakeRow("old-session")
    client.chat_sessions.set_list_with_history([(old_row, [])])
    ctrl = _make_controller(client)

    await ctrl.hydrate_persistent_session()

    assert len(client.chat_sessions.create_calls) == 1
    assert ctrl._chat_session_id == "fresh"


async def test_session_flag_picks_by_id() -> None:
    """``explicit_session_id`` selects that specific session."""
    specific = _FakeRow("specific-session")

    client = FakeReplChatClient()
    client.chat_sessions.set_get_with_history((specific, []))
    ctrl = _make_controller(client)

    await ctrl.hydrate_persistent_session(explicit_session_id="specific-session")

    assert len(client.chat_sessions.create_calls) == 0
    assert ctrl._chat_session_id == "specific-session"


async def test_unknown_explicit_session_id_creates_new_session() -> None:
    """Missing session id falls through to ``create`` like a fresh invocation."""
    client = FakeReplChatClient(new_session_id="fallback-new")
    client.chat_sessions.set_get_with_history(None)
    ctrl = _make_controller(client)

    await ctrl.hydrate_persistent_session(explicit_session_id="nope")

    assert len(client.chat_sessions.create_calls) == 1
    assert ctrl._chat_session_id == "fallback-new"
