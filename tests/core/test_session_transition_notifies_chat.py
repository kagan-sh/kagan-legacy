"""Behavioral tests: session lifecycle transitions persist explicit events.

Lifecycle updates must not be stored as synthetic chat messages. The transition
funnel records one task event per agent session boundary so chat transcripts
remain user/assistant conversation history.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from sqlmodel import select

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, SessionEvent
from kagan.core.transitions import transition_session

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator
    from pathlib import Path

pytestmark = [pytest.mark.core]


async def _seed_session(
    engine,
    task_id: str,
    *,
    status: SessionStatus = SessionStatus.PENDING,
    role: str | None = "worker",
) -> str:
    session = Session(
        task_id=task_id,
        agent_backend="fake",
        status=status,
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
    async with KaganCore(db_path=tmp_path / "notify_test.db") as c:
        project = await c.projects.create("Notify Project")
        await c.projects.set_active(project.id)
        yield c


async def _lifecycle_events(client: KaganCore, session_id: str) -> list[SessionEvent]:
    return await _db_async(
        client.engine,
        lambda s: list(
            s.exec(
                select(SessionEvent)
                .where(SessionEvent.session_id == session_id)
                .where(SessionEvent.event_type == "agent_lifecycle")
            ).all()
        ),
    )


async def test_pending_to_running_records_agent_started_event(client: KaganCore) -> None:
    """PENDING to RUNNING records agent_started without mutating chat history."""
    project_id = client.active_project_id
    assert project_id is not None
    chat = await client.chat_sessions.create(
        source="web", label="Orchestrator", project_id=project_id
    )
    task = await client.tasks.create("Worker task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.PENDING)

    await transition_session(client, session_id, SessionStatus.RUNNING)

    assert await client.chat_sessions.history(chat.id) == []
    events = await _lifecycle_events(client, session_id)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["kind"] == "agent_started"
    assert payload["session_id"] == session_id
    assert "Worker task" in payload["summary"]


async def test_running_to_completed_records_agent_finished_event(client: KaganCore) -> None:
    """RUNNING to COMPLETED records agent_finished."""
    project_id = client.active_project_id
    assert project_id is not None
    chat = await client.chat_sessions.create(
        source="tui", label="Orchestrator", project_id=project_id
    )
    task = await client.tasks.create("Completion task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await transition_session(client, session_id, SessionStatus.COMPLETED)

    assert await client.chat_sessions.history(chat.id) == []
    events = await _lifecycle_events(client, session_id)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["kind"] == "agent_finished"
    assert payload["session_id"] == session_id
    assert "Completion task" in payload["summary"]


@pytest.mark.parametrize("target", [SessionStatus.FAILED, SessionStatus.CANCELLED])
async def test_running_to_stopped_records_agent_stopped_event(
    client: KaganCore, target: SessionStatus
) -> None:
    """RUNNING to FAILED/CANCELLED records agent_stopped."""
    task = await client.tasks.create(f"{target.value} task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await transition_session(client, session_id, target)

    events = await _lifecycle_events(client, session_id)
    assert len(events) == 1
    payload = events[0].payload
    assert payload["kind"] == "agent_stopped"
    assert payload["session_id"] == session_id
    assert target.value.lower() in payload["summary"]


async def test_orchestrator_and_chat_sessions_are_not_lifecycle_storage(
    client: KaganCore,
) -> None:
    """Lifecycle event storage is independent of chat sessions."""
    project_id = client.active_project_id
    assert project_id is not None

    task = await client.tasks.create("Task X")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    chat_a = await client.chat_sessions.create(
        source="web", label="Orchestrator", project_id=project_id
    )

    await transition_session(client, session_id, SessionStatus.COMPLETED)

    assert await client.chat_sessions.history(chat_a.id) == []
    events = await _lifecycle_events(client, session_id)
    assert len(events) == 1
    assert events[0].payload["kind"] == "agent_finished"


async def test_notification_does_not_block_transition(client: KaganCore) -> None:
    """Transition succeeds and returns updated session even if event recording is a no-op."""
    task = await client.tasks.create("Solo task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.PENDING)

    updated = await transition_session(client, session_id, SessionStatus.RUNNING)

    assert updated.status == SessionStatus.RUNNING
    assert updated.id == session_id
