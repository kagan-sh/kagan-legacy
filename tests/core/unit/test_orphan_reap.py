"""Unit tests for orphan session reaping (src/kagan/core/_orphan_reap.py)."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING
from unittest.mock import patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from kagan.core._db import create_db_engine
from kagan.core._db_helpers import _db_sync
from kagan.core._orphan_reap import reap_orphan_sessions
from kagan.core.enums import SessionStatus
from kagan.core.models import Project, Repository, Session, Task

pytestmark = [pytest.mark.core]


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


def test_reap_marks_dead_pid_session_as_failed(tmp_path: Path) -> None:
    engine = _make_engine(tmp_path)
    # Use a PID that is guaranteed to not exist
    dead_pid = 99999999

    session_id = _seed_session(engine, status="RUNNING", pid=dead_pid)

    # Patch os.kill to simulate ProcessLookupError for this pid
    def mock_kill(pid: int, sig: int) -> None:
        if pid == dead_pid:
            raise ProcessLookupError(3, "No such process")
        return None

    with patch("kagan.core._orphan_reap.os.kill", side_effect=mock_kill):
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
    import os

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
