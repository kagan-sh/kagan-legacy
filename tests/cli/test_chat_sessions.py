"""Tests for unified CLI chat session commands.

Verifies the new /sessions, /switch, /stop, /close, /new general flow
replaces the old attach/detach behaviour.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

import pytest

from kagan.cli.chat.controller import ChatController
from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.models import Session, Task

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


@pytest.fixture
async def client(tmp_path: Path) -> KaganCore:
    async with KaganCore(db_path=tmp_path / "chat_sessions.db") as c:
        project = await c.projects.create("CLI Session Project")
        await c.projects.set_active(project.id)
        yield c


@pytest.fixture
def capture_print(monkeypatch: pytest.MonkeyPatch):
    lines: list[str] = []

    def _capture(*args, **kwargs) -> None:
        del kwargs
        if args:
            lines.append(str(args[0]))

    monkeypatch.setattr("kagan.cli.chat.repl._console.print", _capture)
    return lines


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_sessions_command_shows_orchestrator_task_and_general(
    client: KaganCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """/sessions lists orchestrator, task, and general sessions together."""
    project_id = client.active_project_id
    assert project_id is not None

    # Seed an orchestrator chat session
    orch = await client.chat_sessions.create(
        source="repl", label="Orch session", project_id=project_id
    )

    # Seed a task + agent session
    task_id = await _seed_task(client.engine, project_id, title="Task session")
    await _seed_session(client.engine, task_id, role="worker")

    # Seed a general session
    general = await client.chat_sessions.create_general(
        backend="test-backend", project_id=project_id
    )

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    controller._chat_session_id = orch.id
    controller._selected_session_id = f"orch:{orch.id}"

    # Non-interactive mode (no tty)
    monkeypatch.setattr("kagan.cli.chat.repl.supports_interactive_picker", lambda: False)

    # Capture the items passed to print_session_list
    recorded_items: list[Any] = []

    def _capture_print_session_list(items: list[Any]) -> None:
        recorded_items.extend(items)

    monkeypatch.setattr("kagan.cli.chat.controller.print_session_list", _capture_print_session_list)

    should_exit = await controller._handle_slash("/sessions")

    assert should_exit is False
    labels = [getattr(item, "label", "") for item in recorded_items]
    assert "Orch session" in labels
    assert "Task session" in labels
    assert general.label in labels


async def test_new_general_creates_raw_backend_session(
    client: KaganCore, capture_print: list[str]
) -> None:
    """/new general --agent <backend> creates a general session with that backend."""
    controller = ChatController(cast("Any", client), agent_backend="claude-code")

    should_exit = await controller._handle_slash("/new general --agent my-backend")

    # Creating a general session with a different backend triggers a restart
    assert should_exit is True
    assert any("general" in line.lower() for line in capture_print)
    assert any("my-backend" in line for line in capture_print)

    # The selected session should be a general session
    assert controller._selected_session_type == "gen"
    assert controller._selected_session_id is not None
    assert controller._selected_session_id.startswith("gen:")


async def test_switch_changes_selected_session(client: KaganCore, capture_print: list[str]) -> None:
    """/switch <id> updates the controller's selected session."""
    project_id = client.active_project_id
    assert project_id is not None

    task_id = await _seed_task(client.engine, project_id, title="Switch task")
    session_id = await _seed_session(client.engine, task_id, role="worker")

    controller = ChatController(cast("Any", client), agent_backend="claude-code")

    should_exit = await controller._handle_slash(f"/switch task:{session_id}")

    assert should_exit is False
    assert controller._selected_session_id == f"task:{session_id}"
    assert controller._selected_session_type == "task"
    assert any("Switched to task session" in line for line in capture_print)


async def test_stop_stops_selected_live_task_session(
    client: KaganCore, capture_print: list[str]
) -> None:
    """/stop on a selected task session cancels the underlying task."""
    project_id = client.active_project_id
    assert project_id is not None

    task_id = await _seed_task(client.engine, project_id, title="Stop task")
    session_id = await _seed_session(client.engine, task_id, role="worker")

    controller = ChatController(cast("Any", client), agent_backend="claude-code")
    controller._selected_session_id = f"task:{session_id}"
    controller._selected_session_type = "task"

    should_exit = await controller._handle_slash("/stop")

    assert should_exit is False
    assert any("Stopped" in line for line in capture_print)

    # Verify the session was cancelled
    row = await _db_async(client.engine, lambda s: s.get(Session, session_id))
    assert row is not None
    assert row.status == SessionStatus.CANCELLED


async def test_removed_attach_is_unknown_command(
    client: KaganCore, capture_print: list[str]
) -> None:
    """Typing /attach now reports an unknown command."""
    controller = ChatController(cast("Any", client), agent_backend="claude-code")

    should_exit = await controller._handle_slash("/attach some-id")

    assert should_exit is False
    output = " ".join(capture_print)
    assert "Unknown command" in output


async def test_removed_detach_is_unknown_command(
    client: KaganCore, capture_print: list[str]
) -> None:
    """Typing /detach now reports an unknown command."""
    controller = ChatController(cast("Any", client), agent_backend="claude-code")

    should_exit = await controller._handle_slash("/detach")

    assert should_exit is False
    output = " ".join(capture_print)
    assert "Unknown command" in output
