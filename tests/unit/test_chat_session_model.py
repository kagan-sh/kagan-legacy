"""Unit tests for the implicit session model (Change 2).

``hydrate_persistent_session`` should:
- Always create a fresh session when called with no flags.
- Resume a specific session when ``explicit_session_id`` is supplied.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from kagan.cli.chat._session_picker import ChatSessionView

pytestmark = [pytest.mark.unit]


def _make_session_view(
    session_id: str,
    label: str = "REPL session",
    updated_at: str = "2024-01-01T00:00:00",
    agent_backend: str = "claude-code",
) -> ChatSessionView:
    return ChatSessionView(
        id=session_id,
        label=label,
        source="repl",
        agent_backend=agent_backend,
        project_id="proj-1",
        orchestrator_history=[],
        messages_rendered=[],
        updated_at=updated_at,
    )


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
        self.updated_at = updated_at


def _fake_row_to_view(row: Any, msgs: list[Any]) -> ChatSessionView:
    from kagan.cli.chat._session_picker import chat_session_to_view

    return chat_session_to_view(row, msgs)


def _make_client(
    new_session_id: str = "new-session",
) -> Any:
    """Build a minimal fake client with chat_sessions stub."""
    client = MagicMock()
    client.active_project_id = "proj-1"

    # chat_sessions.create returns a row-like object
    created_row = _FakeRow(new_session_id)
    client.chat_sessions.create = AsyncMock(return_value=created_row)
    client.chat_sessions.set_last_session_id = AsyncMock()
    client.chat_sessions.list_with_history = AsyncMock(return_value=[])
    client.chat_sessions.get_with_history = AsyncMock(return_value=None)

    return client


def _make_controller(client: Any) -> Any:
    from kagan.cli.chat.controller import ChatController

    return ChatController(client, agent_backend="claude-code")


async def test_new_invocation_creates_fresh_session() -> None:
    """No flags → always create a new session, never show a picker."""
    client = _make_client(new_session_id="brand-new")
    ctrl = _make_controller(client)

    await ctrl.hydrate_persistent_session()

    # create() must have been called
    client.chat_sessions.create.assert_awaited_once()
    assert ctrl._chat_session_id == "brand-new"


async def test_new_invocation_creates_fresh_session_even_when_sessions_exist() -> None:
    """Even if old sessions exist, no picker should appear on plain invocation."""
    client = _make_client(new_session_id="fresh")
    old_row = _FakeRow("old-session")
    client.chat_sessions.list_with_history = AsyncMock(return_value=[(old_row, [])])
    ctrl = _make_controller(client)

    await ctrl.hydrate_persistent_session()

    client.chat_sessions.create.assert_awaited_once()
    assert ctrl._chat_session_id == "fresh"


async def test_session_flag_picks_by_id() -> None:
    """``explicit_session_id`` selects that specific session."""
    specific = _FakeRow("specific-session")

    client = _make_client()
    client.chat_sessions.get_with_history = AsyncMock(return_value=(specific, []))
    ctrl = _make_controller(client)

    await ctrl.hydrate_persistent_session(explicit_session_id="specific-session")

    client.chat_sessions.create.assert_not_awaited()
    assert ctrl._chat_session_id == "specific-session"
