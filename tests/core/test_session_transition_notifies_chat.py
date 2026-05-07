"""Behavioral tests: session lifecycle transitions inject agent notifications into chat.

Verifies that transition_session() fires notify_project_chat_sessions() so the
orchestrator chat model sees agent lifecycle events on the next turn.

Test strategy:
- Seed project + chat session + task + agent session directly via _db_async.
- Call transition_session() via the public client-level funnel.
- Assert that a system ChatMessage with the expected kind lands in the chat.
- Negative case: project-mismatch chat sessions receive no notification.
"""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import pytest

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus
from kagan.core.models import Session
from kagan.core.transitions import transition_session

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.core]


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


async def _seed_session(
    engine,
    task_id: str,
    *,
    status: SessionStatus = SessionStatus.PENDING,
    role: str | None = "worker",
) -> str:
    """Insert a Session row and return its ID."""
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
async def client(tmp_path: Path) -> KaganCore:  # type: ignore[misc]
    async with KaganCore(db_path=tmp_path / "notify_test.db") as c:
        project = await c.projects.create("Notify Project")
        await c.projects.set_active(project.id)
        yield c


async def _chat_messages(client: KaganCore, chat_id: str) -> list[dict]:
    """Return all chat messages for chat_id as plain dicts (content parsed as JSON if valid)."""
    messages = await client.chat_sessions.history(chat_id)
    result = []
    for msg in messages:
        try:
            content = json.loads(msg.content)
        except (ValueError, TypeError):
            content = msg.content
        result.append({"role": msg.role, "content": content})
    return result


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_pending_to_running_injects_agent_started(client: KaganCore) -> None:
    """PENDING → RUNNING fires agent_started into project chat sessions."""
    project_id = client.active_project_id
    assert project_id is not None

    chat = await client.chat_sessions.create(
        source="web", label="Orchestrator", project_id=project_id
    )
    task = await client.tasks.create("Worker task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.PENDING)

    await transition_session(client, session_id, SessionStatus.RUNNING)

    msgs = await _chat_messages(client, chat.id)
    system_msgs = [m for m in msgs if m["role"] == "system"]
    assert len(system_msgs) == 1

    payload = system_msgs[0]["content"]
    assert payload["type"] == "agent_notification"
    assert payload["kind"] == "agent_started"
    assert payload["session_id"] == session_id
    assert "Worker task" in payload["summary"]


async def test_running_to_completed_injects_agent_finished(client: KaganCore) -> None:
    """RUNNING → COMPLETED fires agent_finished into project chat sessions."""
    project_id = client.active_project_id
    assert project_id is not None

    chat = await client.chat_sessions.create(
        source="tui", label="Orchestrator", project_id=project_id
    )
    task = await client.tasks.create("Completion task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await transition_session(client, session_id, SessionStatus.COMPLETED)

    msgs = await _chat_messages(client, chat.id)
    system_msgs = [m for m in msgs if m["role"] == "system"]
    assert len(system_msgs) == 1

    payload = system_msgs[0]["content"]
    assert payload["type"] == "agent_notification"
    assert payload["kind"] == "agent_finished"
    assert payload["session_id"] == session_id
    assert "Completion task" in payload["summary"]


async def test_running_to_failed_injects_agent_stopped(client: KaganCore) -> None:
    """RUNNING → FAILED fires agent_stopped into project chat sessions."""
    project_id = client.active_project_id
    assert project_id is not None

    chat = await client.chat_sessions.create(
        source="web", label="Orchestrator", project_id=project_id
    )
    task = await client.tasks.create("Failing task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await transition_session(client, session_id, SessionStatus.FAILED)

    msgs = await _chat_messages(client, chat.id)
    system_msgs = [m for m in msgs if m["role"] == "system"]
    assert len(system_msgs) == 1

    payload = system_msgs[0]["content"]
    assert payload["type"] == "agent_notification"
    assert payload["kind"] == "agent_stopped"
    assert payload["session_id"] == session_id
    assert "Failing task" in payload["summary"]


async def test_running_to_cancelled_injects_agent_stopped(client: KaganCore) -> None:
    """RUNNING → CANCELLED fires agent_stopped (not agent_finished)."""
    project_id = client.active_project_id
    assert project_id is not None

    chat = await client.chat_sessions.create(
        source="web", label="Orchestrator", project_id=project_id
    )
    task = await client.tasks.create("Cancelled task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await transition_session(client, session_id, SessionStatus.CANCELLED)

    msgs = await _chat_messages(client, chat.id)
    system_msgs = [m for m in msgs if m["role"] == "system"]
    assert len(system_msgs) == 1

    payload = system_msgs[0]["content"]
    assert payload["kind"] == "agent_stopped"
    assert payload["session_id"] == session_id


async def test_project_mismatch_chat_receives_no_notification(client: KaganCore) -> None:
    """Chat sessions in a different project are not notified."""
    project_a = client.active_project_id
    assert project_a is not None

    project_b = await client.projects.create("Other Project")

    # Chat session belonging to project_b
    chat_other = await client.chat_sessions.create(
        source="web", label="Other Orchestrator", project_id=project_b.id
    )

    task = await client.tasks.create("Task in A")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.PENDING)

    await transition_session(client, session_id, SessionStatus.RUNNING)

    msgs = await _chat_messages(client, chat_other.id)
    # chat_other is in project_b; task is in project_a — no notification expected
    system_msgs = [m for m in msgs if m["role"] == "system"]
    assert system_msgs == []


async def test_notification_does_not_block_transition(client: KaganCore) -> None:
    """Transition succeeds and returns updated session even if no chat sessions exist."""
    task = await client.tasks.create("Solo task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.PENDING)

    # No chat sessions created — notify_project_chat_sessions is a no-op silently
    updated = await transition_session(client, session_id, SessionStatus.RUNNING)
    assert updated.status == SessionStatus.RUNNING
    assert updated.id == session_id
