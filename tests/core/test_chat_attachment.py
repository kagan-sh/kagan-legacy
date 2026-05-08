"""Behavioral tests for chat session attach/detach and agent lifecycle events.

Tests use KaganCore public methods: client.attach_chat() and
client.chat_sessions.*. Agent lifecycle notifications are persisted on the
task event stream, not as synthetic chat messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlmodel import select

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.chat._attach import (
    attach_chat_to_session,
    record_agent_lifecycle_event,
)
from kagan.core.enums import SessionStatus
from kagan.core.models import ChatSession, Session, SessionEvent

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

pytestmark = [pytest.mark.core]


async def _seed_session(engine, task_id: str, *, role: str = "worker") -> str:
    session = Session(
        task_id=task_id,
        agent_backend="fake",
        status=SessionStatus.RUNNING,
        agent_role=role,
    )

    def _w(s) -> Session:
        s.add(session)
        s.flush()
        s.refresh(session)
        s.expunge(session)
        return session

    result = await _db_async(engine, _w, commit=True)
    return result.id


@pytest.fixture
async def client(tmp_path: Path) -> AsyncGenerator[KaganCore]:
    async with KaganCore(db_path=tmp_path / "attach_test.db") as c:
        project = await c.projects.create("Attach Project")
        await c.projects.set_active(project.id)
        yield c


async def _get_chat_row(engine, chat_session_id: str) -> ChatSession | None:
    return await _db_async(engine, lambda s: s.get(ChatSession, chat_session_id))


async def test_attach_chat_to_session_sets_attached_fields(client: KaganCore) -> None:
    """Attaching stores the session id; role remains on the Session row."""
    chat = await client.chat_sessions.create(source="web", label="Orchestrator")
    task = await client.tasks.create("Task A")
    session_id = await _seed_session(client.engine, task.id)

    await client.attach_chat(chat.id, session_id, agent_role="worker")

    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id == session_id
    attached_role = await _db_async(
        client.engine,
        lambda s: s.get(Session, row.attached_session_id).agent_role,
    )
    assert attached_role == "worker"


async def test_detach_chat_clears_fields(client: KaganCore) -> None:
    """Detaching (session_id=None) clears the attach target."""
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


async def test_reattach_to_different_session(client: KaganCore) -> None:
    """Attaching to a second session derives role from the second Session."""
    chat = await client.chat_sessions.create(source="tui", label="Orchestrator")
    task = await client.tasks.create("Task C")
    s1 = await _seed_session(client.engine, task.id, role="worker")
    s2 = await _seed_session(client.engine, task.id, role="reviewer")

    await client.attach_chat(chat.id, s1, agent_role="worker")
    await client.attach_chat(chat.id, s2, agent_role="reviewer")

    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id == s2
    attached_role = await _db_async(
        client.engine,
        lambda db: db.get(Session, row.attached_session_id).agent_role,
    )
    assert attached_role == "reviewer"


async def test_record_agent_lifecycle_event_appends_task_event(client: KaganCore) -> None:
    """record_agent_lifecycle_event adds an event without mutating chat history."""
    chat = await client.chat_sessions.create(source="web", label="Notified Session")
    task = await client.tasks.create("Task D")
    session_id = await _seed_session(client.engine, task.id)

    await record_agent_lifecycle_event(
        client.engine,
        task_id=task.id,
        kind="agent_finished",
        session_id=session_id,
        summary="Worker session completed successfully.",
    )

    messages = await client.chat_sessions.history(chat.id)
    assert messages == []
    events = await _db_async(
        client.engine,
        lambda s: s.exec(select(SessionEvent).where(SessionEvent.session_id == session_id)).all(),
    )
    assert len(events) == 1
    assert events[0].event_type == "agent_lifecycle"
    assert events[0].payload["kind"] == "agent_finished"
    assert events[0].payload["session_id"] == session_id
    assert "successfully" in events[0].payload["summary"]


async def test_record_agent_lifecycle_event_for_unknown_task_is_no_op(client: KaganCore) -> None:
    """record_agent_lifecycle_event with an unknown task_id silently no-ops."""
    task = await client.tasks.create("Task E")
    session_id = await _seed_session(client.engine, task.id)

    # Should not raise
    await record_agent_lifecycle_event(
        client.engine,
        task_id="nonexistent-task-id",
        kind="agent_started",
        session_id=session_id,
        summary="Should not appear",
    )


async def test_record_agent_lifecycle_event_is_not_duplicated_by_chat_count(
    client: KaganCore,
) -> None:
    """Lifecycle events are per agent session, not per open chat session."""
    chat1 = await client.chat_sessions.create(source="web", label="Chat 1")
    chat2 = await client.chat_sessions.create(source="web", label="Chat 2")
    task = await client.tasks.create("Task F")
    session_id = await _seed_session(client.engine, task.id)

    await record_agent_lifecycle_event(
        client.engine,
        task_id=task.id,
        kind="agent_started",
        session_id=session_id,
        summary="Agent kicked off.",
    )

    msgs1 = await client.chat_sessions.history(chat1.id)
    msgs2 = await client.chat_sessions.history(chat2.id)

    assert msgs1 == []
    assert msgs2 == []
    events = await _db_async(
        client.engine,
        lambda s: s.exec(select(SessionEvent).where(SessionEvent.session_id == session_id)).all(),
    )
    assert len(events) == 1
    assert events[0].payload["kind"] == "agent_started"


async def test_attach_chat_noop_for_unknown_chat_session(client: KaganCore) -> None:
    """attach_chat_to_session with unknown chat_session_id is a silent no-op."""
    # Should not raise
    await attach_chat_to_session(
        client.engine,
        "no-such-chat",
        "some-session-id",
        agent_role="worker",
    )
