"""Behavioral tests for chat session attach/detach and agent notification injection.

Tests use KaganCore public methods: client.attach_chat() and
client.chat_sessions.*. The inject_agent_notification helper is exercised via
the public core.chat API.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.chat._attach import (
    attach_chat_to_session,
    inject_agent_notification,
    notify_project_chat_sessions,
)
from kagan.core.enums import SessionStatus
from kagan.core.models import ChatSession, Session

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.core]


async def _seed_session(engine, task_id: str) -> str:
    session = Session(task_id=task_id, agent_backend="fake", status=SessionStatus.RUNNING)

    def _w(s) -> Session:
        s.add(session)
        s.flush()
        s.refresh(session)
        s.expunge(session)
        return session

    result = await _db_async(engine, _w, commit=True)
    return result.id


@pytest.fixture
async def client(tmp_path: Path) -> KaganCore:
    async with KaganCore(db_path=tmp_path / "attach_test.db") as c:
        project = await c.projects.create("Attach Project")
        await c.projects.set_active(project.id)
        yield c


async def _get_chat_row(engine, chat_session_id: str) -> ChatSession | None:
    return await _db_async(engine, lambda s: s.get(ChatSession, chat_session_id))


async def test_attach_chat_to_session_sets_attached_fields(client: KaganCore) -> None:
    """Attaching a chat session stores the session_id and role."""
    chat = await client.chat_sessions.create(source="web", label="Orchestrator")
    task = await client.tasks.create("Task A")
    session_id = await _seed_session(client.engine, task.id)

    await client.attach_chat(chat.id, session_id, agent_role="worker")

    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id == session_id
    assert row.attached_role == "worker"


async def test_detach_chat_clears_fields(client: KaganCore) -> None:
    """Detaching (session_id=None) clears attached_session_id and role."""
    chat = await client.chat_sessions.create(source="web", label="Orchestrator")
    task = await client.tasks.create("Task B")
    session_id = await _seed_session(client.engine, task.id)

    await client.attach_chat(chat.id, session_id, agent_role="reviewer")
    # Confirm attached
    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id == session_id

    # Detach
    await client.attach_chat(chat.id, None)

    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id is None
    assert row.attached_role is None


async def test_reattach_to_different_session(client: KaganCore) -> None:
    """Attaching to a second session overwrites the first."""
    chat = await client.chat_sessions.create(source="tui", label="Orchestrator")
    task = await client.tasks.create("Task C")
    s1 = await _seed_session(client.engine, task.id)
    s2 = await _seed_session(client.engine, task.id)

    await client.attach_chat(chat.id, s1, agent_role="worker")
    await client.attach_chat(chat.id, s2, agent_role="reviewer")

    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id == s2
    assert row.attached_role == "reviewer"


async def test_inject_agent_notification_appends_system_message(client: KaganCore) -> None:
    """inject_agent_notification adds a system role message to the chat transcript."""
    chat = await client.chat_sessions.create(source="web", label="Notified Session")
    task = await client.tasks.create("Task D")
    session_id = await _seed_session(client.engine, task.id)

    await inject_agent_notification(
        client.engine,
        chat.id,
        kind="agent_finished",
        session_id=session_id,
        summary="Worker session completed successfully.",
    )

    messages = await client.chat_sessions.history(chat.id)
    assert len(messages) == 1
    msg = messages[0]
    assert msg.role == "system"
    payload = json.loads(msg.content)
    assert payload["type"] == "agent_notification"
    assert payload["kind"] == "agent_finished"
    assert payload["session_id"] == session_id
    assert "successfully" in payload["summary"]


async def test_inject_notification_nonexistent_chat_is_no_op(client: KaganCore) -> None:
    """inject_agent_notification with an unknown chat_session_id silently no-ops."""
    task = await client.tasks.create("Task E")
    session_id = await _seed_session(client.engine, task.id)

    # Should not raise
    await inject_agent_notification(
        client.engine,
        "nonexistent-chat-id",
        kind="agent_started",
        session_id=session_id,
        summary="Should not appear",
    )


async def test_notify_project_chat_sessions_notifies_all_matching(client: KaganCore) -> None:
    """notify_project_chat_sessions injects into all project chat sessions."""
    project_id = client.active_project_id
    assert project_id is not None

    chat1 = await client.chat_sessions.create(source="web", label="Chat 1", project_id=project_id)
    chat2 = await client.chat_sessions.create(source="web", label="Chat 2", project_id=project_id)
    task = await client.tasks.create("Task F")
    session_id = await _seed_session(client.engine, task.id)

    await notify_project_chat_sessions(
        client.engine,
        project_id=project_id,
        kind="agent_started",
        session_id=session_id,
        summary="Agent kicked off.",
    )

    msgs1 = await client.chat_sessions.history(chat1.id)
    msgs2 = await client.chat_sessions.history(chat2.id)

    assert len(msgs1) == 1
    assert len(msgs2) == 1
    assert json.loads(msgs1[0].content)["kind"] == "agent_started"
    assert json.loads(msgs2[0].content)["kind"] == "agent_started"


async def test_attach_chat_noop_for_unknown_chat_session(client: KaganCore) -> None:
    """attach_chat_to_session with unknown chat_session_id is a silent no-op."""
    # Should not raise
    await attach_chat_to_session(
        client.engine,
        "no-such-chat",
        "some-session-id",
        agent_role="worker",
    )
