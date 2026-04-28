"""Unit tests for Analytics._aggregate_stats — named-column mapping correctness.

Specifically validates that multi-row result sets return correct per-row values
after the col_idx bug fix (col_idx was never reset between rows, corrupting all
rows after the first when more than one backend is present).
"""

from pathlib import Path

import pytest  # noqa: F401 (pytestmark)

from kagan.core._analytics import Analytics
from kagan.core._db import create_db_engine
from kagan.core._db_helpers import _db_sync
from kagan.core.enums import SessionStatus
from kagan.core.models import Project, Session, Task

pytestmark = [pytest.mark.core]


def _seed_sessions(engine, project_id: str) -> None:
    """Insert tasks and sessions for two backends across three rows."""

    def _write(s) -> None:
        # Task A — belongs to backend "alpha"
        task_a = Task(project_id=project_id, title="Task A")
        s.add(task_a)
        s.flush()

        # Task B — belongs to backend "beta"
        task_b = Task(project_id=project_id, title="Task B")
        s.add(task_b)
        s.flush()

        # Task C — also backend "gamma"
        task_c = Task(project_id=project_id, title="Task C")
        s.add(task_c)
        s.flush()

        sessions = [
            Session(
                task_id=task_a.id,
                agent_backend="alpha",
                status=SessionStatus.COMPLETED,
                agent_role="worker",
            ),
            Session(
                task_id=task_a.id,
                agent_backend="alpha",
                status=SessionStatus.COMPLETED,
                agent_role="worker",
            ),
            Session(
                task_id=task_b.id,
                agent_backend="beta",
                status=SessionStatus.FAILED,
                agent_role="worker",
            ),
            Session(
                task_id=task_c.id,
                agent_backend="gamma",
                status=SessionStatus.COMPLETED,
                agent_role="reviewer",
            ),
        ]
        for sess in sessions:
            s.add(sess)
        s.commit()

    _db_sync(engine, _write)


@pytest.fixture
def analytics_engine(tmp_path: Path):
    db_path = tmp_path / "analytics_test.db"
    engine = create_db_engine(db_path)
    return engine


@pytest.fixture
def project_id(analytics_engine) -> str:
    def _write(s) -> str:
        project = Project(name="Analytics Test Project")
        s.add(project)
        s.commit()
        s.refresh(project)
        return project.id

    return _db_sync(analytics_engine, _write)


async def test_backend_by_role_stats_multi_row_correct_values(
    analytics_engine, project_id: str
) -> None:
    """Each row must have the correct agent_backend and count after the col_idx fix.

    Before the fix: col_idx accumulated across rows, so row[1] for the second row
    read the 'count' column as 'agent_backend', returning an integer instead of
    the backend name string.
    """
    _seed_sessions(analytics_engine, project_id)

    analytics = Analytics(analytics_engine)
    results = await analytics.backend_by_role_stats(project_id)

    # Must return 3 distinct (backend, role) combinations
    assert len(results) == 3, f"Expected 3 rows, got {len(results)}: {results}"

    by_backend = {r["agent_backend"]: r for r in results}

    # agent_backend must be the string name, not an integer or offset value
    assert "alpha" in by_backend, f"'alpha' missing from {list(by_backend)}"
    assert "beta" in by_backend, f"'beta' missing from {list(by_backend)}"
    assert "gamma" in by_backend, f"'gamma' missing from {list(by_backend)}"

    assert by_backend["alpha"]["count"] == 2
    assert by_backend["beta"]["count"] == 1
    assert by_backend["gamma"]["count"] == 1

    # agent_role must also be the correct string (not a shifted index value)
    assert by_backend["alpha"]["agent_role"] == "worker"
    assert by_backend["beta"]["agent_role"] == "worker"
    assert by_backend["gamma"]["agent_role"] == "reviewer"
