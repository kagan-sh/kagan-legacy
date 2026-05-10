"""Unit tests for resolve_active_session priority matrix.

Tests the pure function that picks the most relevant session from a task's
session history. 8+ cases covering the full priority matrix.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from kagan.core._sessions_query import resolve_active_session
from kagan.core.enums import SessionStatus
from kagan.core.models import Session

pytestmark = [pytest.mark.unit]


def _session(
    sid: str,
    *,
    role: str | None = "worker",
    status: SessionStatus = SessionStatus.COMPLETED,
    started_offset_seconds: int = 0,
) -> Session:
    """Build a minimal in-memory Session for testing (not persisted)."""
    base = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    return Session(
        id=sid,
        task_id="task-test",
        agent_backend="fake",
        status=status,
        agent_role=role,
        started_at=base + timedelta(seconds=started_offset_seconds),
    )


# ---------------------------------------------------------------------------
# Priority 1: Active worker beats everything
# ---------------------------------------------------------------------------


def test_active_worker_beats_active_reviewer() -> None:
    """An active worker session is preferred over an active reviewer session."""
    worker = _session("w1", role="worker", status=SessionStatus.RUNNING)
    reviewer = _session("r1", role="reviewer", status=SessionStatus.RUNNING)
    result = resolve_active_session([reviewer, worker])
    assert result is not None
    assert result.id == "w1"


def test_active_worker_beats_completed_reviewer() -> None:
    """An active worker session beats a completed reviewer."""
    worker = _session("w1", role="worker", status=SessionStatus.RUNNING)
    reviewer = _session(
        "r1", role="reviewer", status=SessionStatus.COMPLETED, started_offset_seconds=10
    )
    result = resolve_active_session([reviewer, worker])
    assert result is not None
    assert result.id == "w1"


def test_active_worker_pending_status_counts() -> None:
    """PENDING is also an active status."""
    worker = _session("w1", role="worker", status=SessionStatus.PENDING)
    reviewer = _session("r1", role="reviewer", status=SessionStatus.RUNNING)
    result = resolve_active_session([reviewer, worker])
    assert result is not None
    assert result.id == "w1"


# ---------------------------------------------------------------------------
# Priority 2: Active reviewer when no active worker
# ---------------------------------------------------------------------------


def test_active_reviewer_wins_when_no_active_worker() -> None:
    """Active reviewer is picked when no worker is in an active status."""
    worker = _session("w1", role="worker", status=SessionStatus.COMPLETED)
    reviewer = _session("r1", role="reviewer", status=SessionStatus.RUNNING)
    result = resolve_active_session([worker, reviewer])
    assert result is not None
    assert result.id == "r1"


# ---------------------------------------------------------------------------
# Priority 3: Most-recent reviewer (any status) when none active
# ---------------------------------------------------------------------------


def test_most_recent_reviewer_wins_when_none_active() -> None:
    """When nothing is active, the most recent reviewer session is returned."""
    r_old = _session("r_old", role="reviewer", status=SessionStatus.COMPLETED)
    r_new = _session(
        "r_new", role="reviewer", status=SessionStatus.FAILED, started_offset_seconds=100
    )
    w = _session("w1", role="worker", status=SessionStatus.COMPLETED, started_offset_seconds=50)
    result = resolve_active_session([r_old, r_new, w])
    assert result is not None
    assert result.id == "r_new"


# ---------------------------------------------------------------------------
# Priority 4: Most-recent worker (any status) as last resort
# ---------------------------------------------------------------------------


def test_most_recent_worker_returned_when_no_reviewer_exists() -> None:
    """With only worker sessions (no reviewers) and none active, the latest worker wins."""
    w_old = _session("w_old", role="worker", status=SessionStatus.COMPLETED)
    w_new = _session(
        "w_new", role="worker", status=SessionStatus.CANCELLED, started_offset_seconds=100
    )
    result = resolve_active_session([w_old, w_new])
    assert result is not None
    assert result.id == "w_new"


# ---------------------------------------------------------------------------
# Priority 5: None when list is empty
# ---------------------------------------------------------------------------


def test_empty_list_returns_none() -> None:
    """Empty session list returns None — does not raise."""
    assert resolve_active_session([]) is None


# ---------------------------------------------------------------------------
# Multiple active workers — most recent wins
# ---------------------------------------------------------------------------


def test_multiple_active_workers_most_recent_wins() -> None:
    """When multiple workers are active, the one with the latest started_at wins."""
    w1 = _session("w1", role="worker", status=SessionStatus.RUNNING, started_offset_seconds=0)
    w2 = _session("w2", role="worker", status=SessionStatus.RUNNING, started_offset_seconds=60)
    result = resolve_active_session([w1, w2])
    assert result is not None
    assert result.id == "w2"


# ---------------------------------------------------------------------------
# Role-agnostic fallback (role=None)
# ---------------------------------------------------------------------------


def test_session_with_no_role_treated_as_neither_worker_nor_reviewer() -> None:
    """A session with agent_role=None falls through to the fallback (max started_at)."""
    s1 = _session("s1", role=None, status=SessionStatus.COMPLETED, started_offset_seconds=200)
    s2 = _session("s2", role="worker", status=SessionStatus.COMPLETED, started_offset_seconds=100)
    # s2 is worker (priority 4), s1 is role=None (falls back to overall max).
    # The function should return the worker session as "most-recent worker".
    # s1 has later started_at but no role, so worker bucket returns s2, then
    # since no reviewer exists it falls through to worker bucket which holds s2.
    # s1 is ONLY returned if even the worker bucket is empty — here it is not.
    result = resolve_active_session([s1, s2])
    assert result is not None
    # s2 is worker (priority 4) — returned even though s1 has a later timestamp
    assert result.id == "s2"


def test_all_sessions_role_none_returns_most_recent() -> None:
    """When ALL sessions have no role, the overall most-recent session is returned."""
    s1 = _session("s1", role=None, status=SessionStatus.COMPLETED, started_offset_seconds=10)
    s2 = _session("s2", role=None, status=SessionStatus.FAILED, started_offset_seconds=200)
    result = resolve_active_session([s1, s2])
    assert result is not None
    assert result.id == "s2"
