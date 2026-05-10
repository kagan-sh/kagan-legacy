"""Tests for unified session read model (SessionItem)."""

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core._session_items import SessionCapabilities
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.models import ChatSession, Session, Task

pytestmark = [pytest.mark.core]


async def _seed_chat_session(
    client: KaganCore,
    *,
    label: str = "Test Chat",
    project_id: str | None = None,
    source: str = "test",
    session_type: str = "orchestrator",
) -> str:
    chat = ChatSession(
        label=label,
        source=source,
        project_id=project_id,
        session_type=session_type,
    )

    def _write(s) -> ChatSession:
        s.add(chat)
        s.flush()
        s.refresh(chat)
        s.expunge(chat)
        return chat

    result = await _db_async(client.engine, _write, commit=True)
    return result.id


async def _seed_task(client: KaganCore, title: str, project_id: str) -> str:
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


async def _seed_session(
    client: KaganCore,
    task_id: str,
    *,
    status: SessionStatus = SessionStatus.RUNNING,
    role: str | None = "worker",
    backend: str = "fake",
    ended_at: str | None = None,
) -> str:
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


@pytest.fixture
async def client(tmp_path: Path) -> KaganCore:
    async with KaganCore(db_path=tmp_path / "test.db") as c:
        yield c


@pytest.fixture
async def client_with_project(client: KaganCore) -> tuple[KaganCore, str]:
    project = await client.projects.create("Test Project")
    await client.projects.set_active(project.id)
    return client, project.id


async def test_session_items_include_orchestrator_task_and_general_sessions(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """Both chat sessions and task sessions appear in the unified list."""
    client, project_id = client_with_project
    chat_id = await _seed_chat_session(client, label="Orchestrator", project_id=project_id)
    task_id = await _seed_task(client, "Task Session", project_id)
    session_id = await _seed_session(client, task_id, status=SessionStatus.RUNNING, role="worker")

    items = await client.list_session_items()

    ids = {i.id for i in items}
    assert f"orch:{chat_id}" in ids
    assert f"task:{session_id}" in ids


async def test_session_items_sort_active_before_terminal_and_newest_first(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """Active sessions come before idle, which come before terminal; newest first within group."""
    client, project_id = client_with_project

    # Create a chat session (idle group)
    await _seed_chat_session(client, label="Chat", project_id=project_id)

    # Create task sessions in chronological order
    task_running = await _seed_task(client, "Running Task", project_id)
    task_completed = await _seed_task(client, "Completed Task", project_id)
    task_pending = await _seed_task(client, "Pending Task", project_id)

    await _seed_session(client, task_running, status=SessionStatus.RUNNING, role="worker")
    await _seed_session(client, task_completed, status=SessionStatus.COMPLETED, role="worker")
    await _seed_session(client, task_pending, status=SessionStatus.PENDING, role="worker")

    items = await client.list_session_items()

    types = [i.type for i in items]
    statuses = [i.status for i in items]

    # pending was created last -> should be first in active group
    # running was created first -> should be second in active group
    # chat (idle) -> third
    # completed (terminal) -> fourth
    assert statuses[0] == "pending"
    assert statuses[1] == "running"
    assert types[2] == "orchestrator"
    assert statuses[3] == "completed"


async def test_session_items_have_stable_kind_scoped_ids(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """IDs are prefixed with kind to ensure stability."""
    client, project_id = client_with_project
    chat_id = await _seed_chat_session(client, label="Chat", project_id=project_id)
    task_id = await _seed_task(client, "Task", project_id)
    session_id = await _seed_session(client, task_id, status=SessionStatus.RUNNING, role="worker")

    items = await client.list_session_items()

    chat_item = next(i for i in items if i.type == "orchestrator")
    task_item = next(i for i in items if i.type == "task")

    assert chat_item.id == f"orch:{chat_id}"
    assert task_item.id == f"task:{session_id}"


async def test_session_items_preserve_general_session_type_after_refresh(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """General chat sessions remain gen-scoped raw sessions in the unified list."""
    client, project_id = client_with_project
    general_id = await _seed_chat_session(
        client,
        label="General Chat",
        project_id=project_id,
        source="general",
        session_type="general",
    )

    items = await client.list_session_items(project_id=project_id)

    general = next(i for i in items if i.chat_session_id == general_id)
    assert general.id == f"gen:{general_id}"
    assert general.type == "general"
    assert general.capabilities.has_kagan_tools is False


async def test_session_items_capabilities_match_session_type(
    client_with_project: tuple[KaganCore, str],
) -> None:
    """Capabilities reflect the session kind."""
    client, project_id = client_with_project
    await _seed_chat_session(client, label="Chat", project_id=project_id)
    task_id = await _seed_task(client, "Task", project_id)
    await _seed_session(client, task_id, status=SessionStatus.RUNNING, role="worker")

    items = await client.list_session_items()

    chat_item = next(i for i in items if i.type == "orchestrator")
    task_item = next(i for i in items if i.type == "task")

    assert chat_item.capabilities == SessionCapabilities(
        can_chat=True,
        can_stream=True,
        can_replay=False,
        can_stop=True,
        can_close=True,
        has_kagan_tools=True,
    )
    assert task_item.capabilities == SessionCapabilities(
        can_chat=False,
        can_stream=False,
        can_replay=True,
        can_stop=True,
        can_close=False,
        has_kagan_tools=True,
    )


async def test_session_items_project_filter_excludes_other_projects(
    client: KaganCore,
) -> None:
    """project_id restricts results to matching chat sessions and task sessions."""
    proj_a = await client.projects.create("Project A")
    proj_b = await client.projects.create("Project B")

    chat_a = await _seed_chat_session(client, label="Chat A", project_id=proj_a.id)
    chat_b = await _seed_chat_session(client, label="Chat B", project_id=proj_b.id)
    task_a = await _seed_task(client, "Task A", proj_a.id)
    task_b = await _seed_task(client, "Task B", proj_b.id)
    sess_a = await _seed_session(client, task_a, status=SessionStatus.RUNNING, role="worker")
    sess_b = await _seed_session(client, task_b, status=SessionStatus.RUNNING, role="worker")

    items_a = await client.list_session_items(project_id=proj_a.id)
    items_b = await client.list_session_items(project_id=proj_b.id)

    ids_a = {i.id for i in items_a}
    ids_b = {i.id for i in items_b}

    assert f"orch:{chat_a}" in ids_a
    assert f"orch:{chat_b}" not in ids_a
    assert f"task:{sess_a}" in ids_a
    assert f"task:{sess_b}" not in ids_a

    assert f"orch:{chat_b}" in ids_b
    assert f"orch:{chat_a}" not in ids_b
    assert f"task:{sess_b}" in ids_b
    assert f"task:{sess_a}" not in ids_b
