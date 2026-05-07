"""Behavioral tests for CLI chat session attach/detach via public client API.

Tests verify:
- Calling attach_chat persists the attach state across "REPL restart" (second client).
- Detaching returns the chat session to orchestrator mode.
- list_running_agents returns expected sessions for the project.

These tests use KaganCore (real DB, no mocks) per testing.md conventions.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.models import ChatSession, Session, Task

if TYPE_CHECKING:
    from pathlib import Path

pytestmark = [pytest.mark.core]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_task(engine, project_id: str, title: str = "Worker task") -> str:
    task = Task(project_id=project_id, title=title, status=TaskStatus.IN_PROGRESS)

    def _write(s) -> Task:
        s.add(task)
        s.flush()
        s.refresh(task)
        s.expunge(task)
        return task

    result = await _db_async(engine, _write, commit=True)
    return result.id


async def _seed_session(
    engine,
    task_id: str,
    *,
    role: str = "worker",
    status: SessionStatus = SessionStatus.RUNNING,
) -> str:
    session = Session(task_id=task_id, agent_backend="fake", status=status, agent_role=role)

    def _write(s) -> Session:
        s.add(session)
        s.flush()
        s.refresh(session)
        s.expunge(session)
        return session

    result = await _db_async(engine, _write, commit=True)
    return result.id


async def _get_chat_row(engine, chat_id: str) -> ChatSession | None:
    return await _db_async(engine, lambda s: s.get(ChatSession, chat_id))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def client(tmp_path: Path) -> KaganCore:
    async with KaganCore(db_path=tmp_path / "attach_cli.db") as c:
        project = await c.projects.create("Attach CLI Project")
        await c.projects.set_active(project.id)
        yield c


@pytest.fixture
async def db_path(tmp_path: Path) -> Path:
    return tmp_path / "attach_persist.db"


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_attach_chat_persists_across_repl_restart(
    db_path: Path,
) -> None:
    """Attach state (attached_session_id) survives closing and re-opening the client."""
    async with KaganCore(db_path=db_path) as c1:
        project = await c1.projects.create("Persist Project")
        await c1.projects.set_active(project.id)

        chat = await c1.chat_sessions.create(source="repl", label="Orchestrator")
        task_id = await _seed_task(c1.engine, project.id)
        session_id = await _seed_session(c1.engine, task_id, role="worker")

        # Attach
        await c1.attach_chat(chat.id, session_id, agent_role="worker")
        row = await _get_chat_row(c1.engine, chat.id)
        assert row is not None
        assert row.attached_session_id == session_id

    # Second client, same DB — simulates REPL restart
    async with KaganCore(db_path=db_path) as c2:
        row2 = await _get_chat_row(c2.engine, chat.id)
        assert row2 is not None
        assert row2.attached_session_id == session_id
        assert row2.attached_role == "worker"


async def test_detach_returns_to_orchestrator_mode(client: KaganCore) -> None:
    """Detaching clears attached_session_id and attached_role."""
    chat = await client.chat_sessions.create(source="repl", label="Orchestrator")
    project_id = client.active_project_id
    assert project_id is not None

    task_id = await _seed_task(client.engine, project_id)
    session_id = await _seed_session(client.engine, task_id, role="worker")

    # Attach then detach
    await client.attach_chat(chat.id, session_id, agent_role="worker")
    await client.attach_chat(chat.id, None)

    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id is None
    assert row.attached_role is None


async def test_list_running_agents_returns_sessions_for_project(client: KaganCore) -> None:
    """list_running_agents returns only sessions for the active project."""
    project_id = client.active_project_id
    assert project_id is not None

    task_id = await _seed_task(client.engine, project_id, title="CLI attach task")
    session_id = await _seed_session(
        client.engine, task_id, role="worker", status=SessionStatus.RUNNING
    )

    rows = await client.list_running_agents(project_id=project_id)
    assert len(rows) == 1
    assert rows[0].session_id == session_id
    assert rows[0].agent_role == "worker"
    assert rows[0].task_title == "CLI attach task"


async def test_resolve_active_session_returns_running_worker(client: KaganCore) -> None:
    """resolve_active_session returns the active worker session for a task."""
    project_id = client.active_project_id
    assert project_id is not None

    task_id = await _seed_task(client.engine, project_id)
    session_id = await _seed_session(
        client.engine, task_id, role="worker", status=SessionStatus.RUNNING
    )

    result = await client.resolve_active_session(task_id)
    assert result is not None
    assert result.id == session_id


async def test_attach_chat_switches_session_id_on_reattach(client: KaganCore) -> None:
    """Re-attaching to a second session overwrites the first attach target."""
    chat = await client.chat_sessions.create(source="repl", label="Orchestrator")
    project_id = client.active_project_id
    assert project_id is not None

    task_id = await _seed_task(client.engine, project_id)
    s1 = await _seed_session(client.engine, task_id, role="worker")
    s2 = await _seed_session(client.engine, task_id, role="reviewer")

    await client.attach_chat(chat.id, s1, agent_role="worker")
    await client.attach_chat(chat.id, s2, agent_role="reviewer")

    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id == s2
    assert row.attached_role == "reviewer"
