"""Unit tests for orphan session reaping (src/kagan/core/_orphan_reap.py)."""

from __future__ import annotations

import asyncio
import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from kagan.core._db import create_db_engine
from kagan.core._db_helpers import _db_sync
from kagan.core._orphan_reap import reap_orphan_sessions
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.models import Project, Repository, Session, Task

pytestmark = [pytest.mark.core, pytest.mark.unit]


def _make_engine(tmp_path: Path):
    return create_db_engine(tmp_path / "test.db")


def _seed_session(engine, *, status: str, pid: int | None) -> str:
    """Insert a minimal project/task/session and return the session id."""

    def op(s) -> str:
        project = Project(name="Test Project")
        s.add(project)
        s.flush()

        repo = Repository(
            project_id=project.id,
            name="repo",
            path=f"/tmp/repo-{project.id}",
        )
        s.add(repo)
        s.flush()

        task = Task(
            project_id=project.id,
            repo_id=repo.id,
            title="Test Task",
            status="BACKLOG",
            priority=1,
        )
        s.add(task)
        s.flush()

        session = Session(
            task_id=task.id,
            agent_backend="codex",
            status=status,
            pid=pid,
        )
        s.add(session)
        s.commit()
        return session.id

    return _db_sync(engine, op)


def _seed_in_progress_task_with_sessions(
    engine, *, session_pids: list[int | None]
) -> tuple[str, list[str]]:
    """Seed a task in IN_PROGRESS with one RUNNING session per pid.

    Returns (task_id, [session_id, ...]) in pid-list order.
    """

    def op(s) -> tuple[str, list[str]]:
        project = Project(name="Cascade Test Project")
        s.add(project)
        s.flush()

        repo = Repository(
            project_id=project.id,
            name="repo",
            path=f"/tmp/cascade-repo-{project.id}",
        )
        s.add(repo)
        s.flush()

        task = Task(
            project_id=project.id,
            repo_id=repo.id,
            title="Cascade Task",
            status="IN_PROGRESS",
            priority=1,
        )
        s.add(task)
        s.flush()

        session_ids = []
        for pid in session_pids:
            session = Session(
                task_id=task.id,
                agent_backend="codex",
                status="RUNNING",
                pid=pid,
            )
            s.add(session)
            s.flush()
            session_ids.append(session.id)

        s.commit()
        return task.id, session_ids

    return _db_sync(engine, op)


def test_reap_marks_dead_pid_session_as_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = _make_engine(tmp_path)
    # Use a PID that is guaranteed to not exist
    dead_pid = 99999999

    session_id = _seed_session(engine, status="RUNNING", pid=dead_pid)

    def mock_kill(pid: int, sig: int) -> None:
        if pid == dead_pid:
            raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(os, "kill", mock_kill)
    reaped = asyncio.run(reap_orphan_sessions(engine))

    assert reaped == 1

    def check(s):
        sess = s.get(Session, session_id)
        assert sess is not None
        assert sess.status == SessionStatus.FAILED
        assert sess.fail_reason is not None
        assert "orphan" in sess.fail_reason

    _db_sync(engine, check)
    engine.dispose()


def test_reap_skips_live_pid_session(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    live_pid = os.getpid()  # current process is alive

    session_id = _seed_session(engine, status="RUNNING", pid=live_pid)

    reaped = asyncio.run(reap_orphan_sessions(engine))
    assert reaped == 0

    def check(s):
        sess = s.get(Session, session_id)
        assert sess is not None
        assert sess.status == SessionStatus.RUNNING

    _db_sync(engine, check)
    engine.dispose()


def test_reap_no_running_sessions_returns_zero(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    _seed_session(engine, status="COMPLETED", pid=12345)

    reaped = asyncio.run(reap_orphan_sessions(engine))
    assert reaped == 0

    engine.dispose()


def test_reap_treats_none_pid_as_dead(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    session_id = _seed_session(engine, status="RUNNING", pid=None)

    reaped = asyncio.run(reap_orphan_sessions(engine))
    assert reaped == 1

    def check(s):
        sess = s.get(Session, session_id)
        assert sess is not None
        assert sess.status == SessionStatus.FAILED

    _db_sync(engine, check)
    engine.dispose()


# ── Task cascade tests ────────────────────────────────────────────────────────


def test_reap_cascades_in_progress_task_to_backlog(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the reaped session is the last RUNNING session, the owning task
    must move from IN_PROGRESS back to BACKLOG."""
    engine = _make_engine(tmp_path)
    dead_pid = 99999999
    task_id, session_ids = _seed_in_progress_task_with_sessions(engine, session_pids=[dead_pid])

    def mock_kill(pid: int, sig: int) -> None:
        if pid == dead_pid:
            raise ProcessLookupError(3, "No such process")

    monkeypatch.setattr(os, "kill", mock_kill)
    reaped = asyncio.run(reap_orphan_sessions(engine))

    assert reaped == 1

    def check(s):
        task = s.get(Task, task_id)
        assert task is not None
        assert task.status == TaskStatus.BACKLOG
        sess = s.get(Session, session_ids[0])
        assert sess is not None
        assert sess.status == SessionStatus.FAILED

    _db_sync(engine, check)
    engine.dispose()


def test_reap_does_not_cascade_task_when_other_running_sessions_exist(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When another RUNNING session for the same task still exists (e.g. pair
    mode), the task must remain IN_PROGRESS after the orphan is reaped."""
    engine = _make_engine(tmp_path)
    dead_pid = 99999999
    live_pid = os.getpid()
    task_id, session_ids = _seed_in_progress_task_with_sessions(
        engine, session_pids=[dead_pid, live_pid]
    )
    dead_session_id, live_session_id = session_ids

    def mock_kill(pid: int, sig: int) -> None:
        if pid == dead_pid:
            raise ProcessLookupError(3, "No such process")
        # live_pid: do nothing (process exists)

    monkeypatch.setattr(os, "kill", mock_kill)
    reaped = asyncio.run(reap_orphan_sessions(engine))

    assert reaped == 1

    def check(s):
        task = s.get(Task, task_id)
        assert task is not None
        # Task must NOT have been moved — a sibling session is still running.
        assert task.status == TaskStatus.IN_PROGRESS
        dead_sess = s.get(Session, dead_session_id)
        assert dead_sess is not None
        assert dead_sess.status == SessionStatus.FAILED
        live_sess = s.get(Session, live_session_id)
        assert live_sess is not None
        assert live_sess.status == SessionStatus.RUNNING

    _db_sync(engine, check)
    engine.dispose()
