"""Fixtures and helpers for EventLog unit tests."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from kagan.core._db import create_db_engine
from kagan.core._db_helpers import _db_sync
from kagan.core._event_log import EventLog
from kagan.core.models import Project, Session, Task

if TYPE_CHECKING:
    from sqlalchemy import Engine


@pytest.fixture
def event_log_engine(tmp_path: Path) -> Engine:
    db_path = tmp_path / "event_log_test.db"
    return create_db_engine(db_path)


@pytest.fixture
def session_id(event_log_engine: Engine) -> str:
    """A real Session row for FK validation."""

    def _write(s) -> str:
        project = Project(name="EventLog Test Project")
        s.add(project)
        s.flush()

        task = Task(project_id=project.id, title="EventLog Test Task")
        s.add(task)
        s.flush()

        session = Session(
            task_id=task.id,
            agent_backend="fake",
        )
        s.add(session)
        s.commit()
        s.refresh(session)
        return session.id

    return _db_sync(event_log_engine, _write)


@pytest.fixture
def event_log(event_log_engine: Engine) -> EventLog:
    return EventLog(event_log_engine)


__all__ = ["event_log", "event_log_engine", "session_id"]
