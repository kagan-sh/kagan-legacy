"""Behavioral tests: attached-session replay markers for user turns.

Test strategy:
- Seed a task + agent Session directly via _db_async.
- Call client.record_session_user_message_for_replay() via the public API.
- Assert the event was persisted in the task event stream as replay-only
  (output_chunk / kind=user / replay_only=True).
- Negative case: calling on a COMPLETED session raises KaganError.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus
from kagan.core.errors import KaganError
from kagan.core.models import Session

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
    status: SessionStatus = SessionStatus.RUNNING,
) -> str:
    """Insert a Session row and return its ID."""
    session = Session(
        task_id=task_id,
        agent_backend="fake",
        status=status,
        agent_role="worker",
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
    async with KaganCore(db_path=tmp_path / "send_test.db") as c:
        project = await c.projects.create("Send Test Project")
        await c.projects.set_active(project.id)
        yield c


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_record_replay_message_for_running_session_emits_replay_only_output_chunk(
    client: KaganCore,
) -> None:
    """Recording a message for a RUNNING session persists a replay-only output chunk."""
    task = await client.tasks.create("Running task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await client.record_session_user_message_for_replay(session_id, "hello agent")

    events = await client.tasks.events.list_recent(task.id, limit=20, session_id=session_id)
    user_chunks = [
        e for e in events if e.event_type == "output_chunk" and e.payload.get("kind") == "user"
    ]
    assert len(user_chunks) == 1
    assert user_chunks[0].payload["text"] == "hello agent"
    assert user_chunks[0].payload["replay_only"] is True
    assert user_chunks[0].session_id == session_id


async def test_record_replay_message_for_pending_session_emits_output_chunk(
    client: KaganCore,
) -> None:
    """Recording a replay message for a PENDING session also succeeds."""
    task = await client.tasks.create("Pending task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.PENDING)

    await client.record_session_user_message_for_replay(session_id, "start working on X")

    events = await client.tasks.events.list_recent(task.id, limit=20, session_id=session_id)
    user_chunks = [
        e for e in events if e.event_type == "output_chunk" and e.payload.get("kind") == "user"
    ]
    assert len(user_chunks) == 1
    assert user_chunks[0].payload["text"] == "start working on X"
    assert user_chunks[0].payload["replay_only"] is True


async def test_send_message_to_session_keeps_compatibility_as_replay_only(
    client: KaganCore,
) -> None:
    """The legacy send API is explicit replay annotation, not live agent input."""
    task = await client.tasks.create("Compatibility task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await client.send_message_to_session(session_id, "legacy call")

    events = await client.tasks.events.list_recent(task.id, limit=20, session_id=session_id)
    user_chunks = [
        e for e in events if e.event_type == "output_chunk" and e.payload.get("kind") == "user"
    ]
    assert len(user_chunks) == 1
    assert user_chunks[0].payload == {
        "text": "legacy call",
        "kind": "user",
        "replay_only": True,
        "acp": {
            "sessionUpdate": "user_message_chunk",
            "content": {"type": "text", "text": "legacy call"},
        },
    }


async def test_send_to_completed_session_raises(client: KaganCore) -> None:
    """Sending to a COMPLETED session raises KaganError with status in message."""
    task = await client.tasks.create("Completed task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.COMPLETED)

    with pytest.raises(KaganError, match="session does not accept input"):
        await client.record_session_user_message_for_replay(session_id, "too late")


async def test_send_to_failed_session_raises(client: KaganCore) -> None:
    """Sending to a FAILED session raises KaganError."""
    task = await client.tasks.create("Failed task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.FAILED)

    with pytest.raises(KaganError, match="session does not accept input"):
        await client.record_session_user_message_for_replay(session_id, "no luck")


async def test_send_to_nonexistent_session_raises(client: KaganCore) -> None:
    """Sending to an unknown session ID raises KaganError with 'not found'."""
    with pytest.raises(KaganError, match="session not found"):
        await client.record_session_user_message_for_replay("nonexistent0000", "ghost")
