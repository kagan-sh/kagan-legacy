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


# ---------------------------------------------------------------------------
# Slash-command behavioral tests: /attach and /detach through ChatController
# ---------------------------------------------------------------------------


async def test_handle_slash_attach_resolves_task_id_and_switches_transcript(
    client: KaganCore, monkeypatch
) -> None:
    """/attach <task-id> resolves to the active session and prints a breadcrumb."""
    project_id = client.active_project_id
    assert project_id is not None

    task_id = await _seed_task(client.engine, project_id, title="Attach test task")
    session_id = await _seed_session(client.engine, task_id, role="worker")

    chat = await client.chat_sessions.create(source="repl", label="Orchestrator")

    from typing import Any, cast

    from kagan.cli.chat.controller import ChatController

    lines: list[str] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            lines.append(str(args[0]))

    monkeypatch.setattr("kagan.cli.chat.repl._console.print", _capture_print)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    controller._chat_session_id = chat.id

    should_exit = await controller._handle_slash(f"/attach {task_id}")

    assert should_exit is False
    # A breadcrumb line was printed
    assert any("Attached" in line for line in lines)
    # The chat row now has attached_session_id set
    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id == session_id


async def test_handle_slash_detach_returns_to_orchestrator(client: KaganCore, monkeypatch) -> None:
    """/detach clears the attached session and prints 'Detached → Orchestrator'."""
    project_id = client.active_project_id
    assert project_id is not None

    task_id = await _seed_task(client.engine, project_id)
    session_id = await _seed_session(client.engine, task_id, role="worker")
    chat = await client.chat_sessions.create(source="repl", label="Orchestrator")

    # Pre-attach
    await client.attach_chat(chat.id, session_id, agent_role="worker")

    from typing import Any, cast

    from kagan.cli.chat.controller import ChatController

    lines: list[str] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            lines.append(str(args[0]))

    monkeypatch.setattr("kagan.cli.chat.repl._console.print", _capture_print)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    controller._chat_session_id = chat.id

    should_exit = await controller._handle_slash("/detach")

    assert should_exit is False
    assert any("Orchestrator" in line for line in lines)
    row = await _get_chat_row(client.engine, chat.id)
    assert row is not None
    assert row.attached_session_id is None


async def test_attach_state_persists_across_repl_restart_via_command(
    db_path,
) -> None:
    """Attach state written by _handle_slash /attach survives client close/reopen."""
    from typing import Any, cast

    from kagan.cli.chat.controller import ChatController

    async with KaganCore(db_path=db_path) as c1:
        project = await c1.projects.create("Persist2 Project")
        await c1.projects.set_active(project.id)

        task_id = await _seed_task(c1.engine, project.id, title="Persist task")
        session_id = await _seed_session(c1.engine, task_id, role="worker")
        chat = await c1.chat_sessions.create(source="repl", label="Orchestrator")

        lines: list[str] = []

        def _noop_print(*args, **kwargs) -> None:
            del kwargs
            if args:
                lines.append(str(args[0]))

        import unittest.mock as mock

        with mock.patch("kagan.cli.chat.repl._console.print", _noop_print):
            controller = ChatController(cast("Any", c1), agent_backend="claude-code")
            controller._chat_session_id = chat.id
            await controller._handle_slash(f"/attach {task_id}")

    # Re-open — attach_session_id must survive
    async with KaganCore(db_path=db_path) as c2:
        row = await _get_chat_row(c2.engine, chat.id)
        assert row is not None
        assert row.attached_session_id == session_id


async def test_handle_slash_attach_unknown_id_prints_error(client: KaganCore, monkeypatch) -> None:
    """/attach with an unknown id prints an error and leaves state unchanged."""
    from typing import Any, cast

    from kagan.cli.chat.controller import ChatController

    chat = await client.chat_sessions.create(source="repl", label="Orchestrator")

    lines: list[str] = []

    def _capture_print(*args, **kwargs) -> None:
        del kwargs
        if args:
            lines.append(str(args[0]))

    monkeypatch.setattr("kagan.cli.chat.repl._console.print", _capture_print)

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    controller._chat_session_id = chat.id
    original_session_id = controller._chat_session_id

    should_exit = await controller._handle_slash("/attach deadbeef")

    assert should_exit is False
    assert any("Unknown" in line or "not found" in line.lower() for line in lines)
    # REPL state unchanged
    assert controller._chat_session_id == original_session_id
