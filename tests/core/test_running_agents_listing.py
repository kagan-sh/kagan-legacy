"""Behavioral tests: list_running_agents and resolve_active_session via client.

Tests use KaganCore.list_running_agents() and KaganCore.resolve_active_session()
public methods. DB sessions are seeded directly via _db_async to set up known
states without needing real agent processes.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.models import Session, Task

pytestmark = [pytest.mark.core]


async def _seed_session(
    client: KaganCore,
    task_id: str,
    *,
    status: SessionStatus = SessionStatus.RUNNING,
    role: str | None = "worker",
    backend: str = "fake",
) -> str:
    """Insert a Session row directly and return its ID."""
    session = Session(
        task_id=task_id,
        agent_backend=backend,
        status=status,
        agent_role=role,
    )

    def _write(s) -> Session:
        s.add(session)
        s.flush()
        s.refresh(session)
        s.expunge(session)
        return session

    result = await _db_async(client.engine, _write, commit=True)
    return result.id


async def _seed_task(client: KaganCore, title: str, project_id: str) -> str:
    """Insert a Task row directly and return its ID."""
    task = Task(
        project_id=project_id,
        title=title,
        status=TaskStatus.IN_PROGRESS,
    )

    def _write(s) -> Task:
        s.add(task)
        s.flush()
        s.refresh(task)
        s.expunge(task)
        return task

    result = await _db_async(client.engine, _write, commit=True)
    return result.id


@pytest.fixture
async def client(tmp_path: Path) -> KaganCore:
    async with KaganCore(db_path=tmp_path / "test.db") as c:
        yield c


@pytest.fixture
async def client_with_project(client: KaganCore) -> tuple[KaganCore, str]:
    project = await client.projects.create("Test Project")
    await client.projects.set_active(project.id)
    return client, project.id


async def test_list_running_agents_empty_when_no_sessions(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """Returns an empty list when no sessions exist."""
    client, _ = client_with_project
    rows = await client.list_running_agents()
    assert rows == []


async def test_list_running_agents_returns_active_sessions(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """Active sessions (RUNNING/PENDING) are included in the result."""
    client, project_id = client_with_project
    task_id = await _seed_task(client, "Feature X", project_id)
    await _seed_session(client, task_id, status=SessionStatus.RUNNING, role="worker")

    rows = await client.list_running_agents()
    assert len(rows) == 1
    row = rows[0]
    assert row.task_id == task_id
    assert row.task_title == "Feature X"
    assert row.session_status == "RUNNING"
    assert row.agent_role == "worker"


async def test_list_running_agents_excludes_completed_sessions(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """Completed sessions are NOT returned."""
    client, project_id = client_with_project
    task_id = await _seed_task(client, "Done Task", project_id)
    await _seed_session(client, task_id, status=SessionStatus.COMPLETED, role="worker")

    rows = await client.list_running_agents()
    assert rows == []


async def test_list_running_agents_project_filter(
    client: KaganCore,
) -> None:
    """project_id filter restricts results to tasks in that project."""
    proj_a = await client.projects.create("Project A")
    proj_b = await client.projects.create("Project B")

    task_a = await _seed_task(client, "Task in A", proj_a.id)
    task_b = await _seed_task(client, "Task in B", proj_b.id)

    await _seed_session(client, task_a, status=SessionStatus.RUNNING, role="worker")
    await _seed_session(client, task_b, status=SessionStatus.RUNNING, role="reviewer")

    rows_a = await client.list_running_agents(project_id=proj_a.id)
    rows_b = await client.list_running_agents(project_id=proj_b.id)

    assert len(rows_a) == 1
    assert rows_a[0].task_id == task_a

    assert len(rows_b) == 1
    assert rows_b[0].task_id == task_b


async def test_list_running_agents_shape_fields(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """Returned rows have all required fields."""
    client, project_id = client_with_project
    task_id = await _seed_task(client, "Shape Test", project_id)
    await _seed_session(client, task_id, status=SessionStatus.PENDING, role="reviewer")

    rows = await client.list_running_agents()
    assert len(rows) == 1
    row = rows[0]
    # Check all required fields are present
    assert row.task_id
    assert row.task_title == "Shape Test"
    assert row.task_status == "IN_PROGRESS"
    assert row.session_id
    assert row.agent_backend == "fake"
    assert row.session_status == "PENDING"
    assert row.agent_role == "reviewer"
    assert row.started_at is not None


async def test_resolve_active_session_returns_none_for_no_sessions(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """resolve_active_session returns None when task has no sessions."""
    client, project_id = client_with_project
    task_id = await _seed_task(client, "Empty Task", project_id)

    result = await client.resolve_active_session(task_id)
    assert result is None


async def test_resolve_active_session_returns_running_worker(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """resolve_active_session returns the active worker session."""
    client, project_id = client_with_project
    task_id = await _seed_task(client, "Active Task", project_id)
    session_id = await _seed_session(client, task_id, status=SessionStatus.RUNNING, role="worker")

    result = await client.resolve_active_session(task_id)
    assert result is not None
    assert result.id == session_id
