"""Tests: AgentLifecycle broadcast hook is called on session transitions.

Verifies that `_notify_chat_on_session_transition` fires the
`_lifecycle_broadcast_fn` hook on KaganCore with correct kind literals
when a session enters RUNNING, COMPLETED, FAILED, or CANCELLED.

The DB recording of `agent_lifecycle` SessionEvent rows is covered by
`tests/core/test_session_transition_notifies_chat.py`.  These tests focus
on the broadcast side-channel introduced in Item 4.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from pathlib import Path

import pytest

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus
from kagan.core.events import AgentLifecycle
from kagan.core.models import Session
from kagan.core.transitions import transition_session

pytestmark = [pytest.mark.core]


async def _seed_session(
    engine, task_id: str, *, status: SessionStatus = SessionStatus.PENDING
) -> str:
    session = Session(task_id=task_id, agent_backend="fake", status=status)

    def _w(s) -> Session:
        s.add(session)
        s.flush()
        s.refresh(session)
        s.expunge(session)
        return session

    result = await _db_async(engine, _w, commit=True)
    return result.id


@pytest.fixture
async def client(tmp_path: Path) -> AsyncGenerator[KaganCore, None]:
    async with KaganCore(db_path=tmp_path / "lc_broadcast.db") as c:
        project = await c.projects.create("Broadcast Project")
        await c.projects.set_active(project.id)
        yield c


async def test_running_transition_calls_broadcast_with_started(client: KaganCore) -> None:
    """PENDING → RUNNING triggers broadcast with kind='started'."""
    captured: list[tuple[str, AgentLifecycle]] = []

    async def _hook(project_id: str, event: AgentLifecycle) -> None:
        captured.append((project_id, event))

    client._lifecycle_broadcast_fn = _hook  # type: ignore[assignment]

    task = await client.tasks.create("Broadcast task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.PENDING)

    await transition_session(client, session_id, SessionStatus.RUNNING)

    assert len(captured) == 1
    project_id, lc_event = captured[0]
    assert lc_event.kind == "started"
    assert lc_event.task_id == task.id
    assert lc_event.session_id == session_id


async def test_completed_transition_calls_broadcast_with_finished(client: KaganCore) -> None:
    """RUNNING → COMPLETED triggers broadcast with kind='finished'."""
    captured: list[tuple[str, AgentLifecycle]] = []

    async def _hook(project_id: str, event: AgentLifecycle) -> None:
        captured.append((project_id, event))

    client._lifecycle_broadcast_fn = _hook  # type: ignore[assignment]

    task = await client.tasks.create("Completion broadcast task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await transition_session(client, session_id, SessionStatus.COMPLETED)

    assert len(captured) == 1
    _, lc_event = captured[0]
    assert lc_event.kind == "finished"
    assert lc_event.task_id == task.id


async def test_failed_transition_calls_broadcast_with_failed(client: KaganCore) -> None:
    """RUNNING → FAILED triggers broadcast with kind='failed'."""
    captured: list[tuple[str, AgentLifecycle]] = []

    async def _hook(project_id: str, event: AgentLifecycle) -> None:
        captured.append((project_id, event))

    client._lifecycle_broadcast_fn = _hook  # type: ignore[assignment]

    task = await client.tasks.create("Failed broadcast task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await transition_session(client, session_id, SessionStatus.FAILED)

    assert len(captured) == 1
    _, lc_event = captured[0]
    assert lc_event.kind == "failed"


async def test_cancelled_transition_calls_broadcast_with_stopped(client: KaganCore) -> None:
    """RUNNING → CANCELLED triggers broadcast with kind='stopped'."""
    captured: list[tuple[str, AgentLifecycle]] = []

    async def _hook(project_id: str, event: AgentLifecycle) -> None:
        captured.append((project_id, event))

    client._lifecycle_broadcast_fn = _hook  # type: ignore[assignment]

    task = await client.tasks.create("Cancelled broadcast task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.RUNNING)

    await transition_session(client, session_id, SessionStatus.CANCELLED)

    assert len(captured) == 1
    _, lc_event = captured[0]
    assert lc_event.kind == "stopped"


async def test_no_broadcast_when_hook_not_set(client: KaganCore) -> None:
    """Transition succeeds without error when _lifecycle_broadcast_fn is None."""
    assert client._lifecycle_broadcast_fn is None

    task = await client.tasks.create("No hook task")
    session_id = await _seed_session(client.engine, task.id, status=SessionStatus.PENDING)

    # Should not raise.
    updated = await transition_session(client, session_id, SessionStatus.RUNNING)
    assert updated.status == SessionStatus.RUNNING
