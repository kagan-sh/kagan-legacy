"""Unit tests for kagan.core.transitions — exhaustive (from, to) matrix.

Coverage:
- Every (TaskStatus x TaskStatus) pair across the 4-value enum.
- Every (SessionStatus x SessionStatus) pair across the 5-value enum.
- Happy paths (legal transitions complete without error).
- Rejected paths (illegal transitions raise IllegalTransition).
- Review gate: REVIEW → DONE blocked when is_review_approved returns False.
- Review gate: REVIEW → DONE allowed when is_review_approved returns True.
- Same-status no-op rejected for both task and session.
- TOCTOU guard: IllegalTransition raised when status drifts before the write.

Design note: task transition tests drive against a real KaganCore (in-memory
SQLite) per testing.md "real everything, fake agent".  Session transition tests
mock _db_async because there is no ``sessions.create`` shortcut that bypasses
the session state machine — patching _db_async is the minimal seam.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock, patch

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from kagan.core import KaganCore
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.errors import InvalidTransitionError
from kagan.core.models import AcceptanceCriterion, ReviewVerdict
from kagan.core.transitions import IllegalTransition, transition_session, transition_task

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Real KaganCore fixture (in-memory SQLite via tmp_path)
# ---------------------------------------------------------------------------


@pytest.fixture
async def core(tmp_path: Path) -> KaganCore:
    """Boot a fresh KaganCore backed by a tmp-dir SQLite DB."""
    client = KaganCore(db_path=tmp_path / "test.db")
    yield client  # type: ignore[misc]
    client.close()


async def _seed_task(
    core: KaganCore,
    *,
    status: TaskStatus,
    criteria_texts: list[str] | None = None,
) -> str:
    """Create a project + task forced to *status* via _set_status.

    Returns the task_id.
    """
    project = await core.projects.create("Test Project")
    await core.projects.set_active(project.id)
    task = await core.tasks.create(
        "Test task",
        acceptance_criteria=criteria_texts,
    )
    # Force the task to the desired from-status without going through the
    # public set_status path (which enforces validate_move and would reject
    # moves like BACKLOG→REVIEW directly).
    if task.status != status:
        await asyncio.to_thread(core.tasks._set_status, task.id, status)
    return task.id


async def _add_pass_verdicts(core: KaganCore, task_id: str) -> None:
    """Stamp 'pass' verdicts on all acceptance criteria for *task_id*."""
    from sqlmodel import select

    from kagan.core._db_helpers import _db_async

    def _op(s) -> None:
        criteria = list(
            s.exec(select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task_id)).all()
        )
        for criterion in criteria:
            s.add(ReviewVerdict(criterion_id=criterion.id, verdict="pass", reason="test"))
        s.commit()

    await _db_async(core.engine, _op)


# ---------------------------------------------------------------------------
# Task transition matrix
# ---------------------------------------------------------------------------
# Legal (from, to) pairs (excluding the guarded REVIEW→DONE — tested below).
_TASK_LEGAL: list[tuple[TaskStatus, TaskStatus]] = [
    (TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS),
    (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW),
    (TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG),
    (TaskStatus.REVIEW, TaskStatus.IN_PROGRESS),
    (TaskStatus.REVIEW, TaskStatus.BACKLOG),
    (TaskStatus.DONE, TaskStatus.BACKLOG),
    # REVIEW → DONE is guarded; tested separately below.
]

# Illegal (from, to) pairs (every other cell in the 4x4 matrix):
_TASK_ILLEGAL: list[tuple[TaskStatus, TaskStatus]] = [
    # Same-status no-ops
    (TaskStatus.BACKLOG, TaskStatus.BACKLOG),
    (TaskStatus.IN_PROGRESS, TaskStatus.IN_PROGRESS),
    (TaskStatus.REVIEW, TaskStatus.REVIEW),
    (TaskStatus.DONE, TaskStatus.DONE),
    # Explicitly forbidden shortcuts
    (TaskStatus.IN_PROGRESS, TaskStatus.DONE),
    (TaskStatus.BACKLOG, TaskStatus.DONE),
    (TaskStatus.BACKLOG, TaskStatus.REVIEW),
    (TaskStatus.DONE, TaskStatus.IN_PROGRESS),
    (TaskStatus.DONE, TaskStatus.REVIEW),
]


@pytest.mark.parametrize("frm,to", _TASK_LEGAL)
@pytest.mark.asyncio
async def test_transition_task_legal(frm: TaskStatus, to: TaskStatus, core: KaganCore) -> None:
    """Legal task transitions complete without raising against a real DB."""
    task_id = await _seed_task(core, status=frm)
    result = await transition_task(core, task_id, to)
    assert result.status == to


@pytest.mark.parametrize("frm,to", _TASK_ILLEGAL)
@pytest.mark.asyncio
async def test_transition_task_illegal(frm: TaskStatus, to: TaskStatus, core: KaganCore) -> None:
    """Illegal task transitions raise IllegalTransition without touching the DB."""
    task_id = await _seed_task(core, status=frm)
    with pytest.raises(IllegalTransition):
        await transition_task(core, task_id, to)
    # Status in the DB must remain unchanged.
    task = await core.tasks.get(task_id)
    assert task.status == frm


@pytest.mark.asyncio
async def test_transition_task_review_to_done_blocked_when_no_passing_review(
    core: KaganCore,
) -> None:
    """REVIEW → DONE is rejected when the task has no passing verdicts.

    We use a task with one acceptance criterion and no verdicts so that
    is_review_approved() returns False via the real DB path.
    """
    task_id = await _seed_task(core, status=TaskStatus.REVIEW, criteria_texts=["Criterion A"])
    with pytest.raises(IllegalTransition):
        await transition_task(core, task_id, TaskStatus.DONE)
    task = await core.tasks.get(task_id)
    assert task.status == TaskStatus.REVIEW


@pytest.mark.asyncio
async def test_transition_task_review_to_done_allowed_when_passing_review(
    core: KaganCore,
) -> None:
    """REVIEW → DONE succeeds and persists in the real DB when all criteria pass.

    This test exercises the P1 fix: the write path now bypasses validate_move(),
    which previously blocked REVIEW→DONE unconditionally.
    """
    task_id = await _seed_task(core, status=TaskStatus.REVIEW, criteria_texts=["Criterion A"])
    await _add_pass_verdicts(core, task_id)
    result = await transition_task(core, task_id, TaskStatus.DONE)
    assert result.status == TaskStatus.DONE
    # Confirm the status was persisted, not just returned in memory.
    refreshed = await core.tasks.get(task_id)
    assert refreshed.status == TaskStatus.DONE


@pytest.mark.asyncio
async def test_transition_task_propagates_actor_label(core: KaganCore) -> None:
    """The *by* keyword is accepted and does not change observable state."""
    task_id = await _seed_task(core, status=TaskStatus.BACKLOG)
    result = await transition_task(core, task_id, TaskStatus.IN_PROGRESS, by="orchestrator")
    assert result.status == TaskStatus.IN_PROGRESS


@pytest.mark.asyncio
async def test_transition_task_toctou_guard(core: KaganCore) -> None:
    """TOCTOU guard: if status drifts between the read and the write, raise.

    We patch _db_async to intercept only the write callback (the one issued
    inside transition_task after the match block).  Before forwarding to the
    real DB, we flip the task's status via _set_status so the write callback
    sees a status that no longer matches the originally-read ``src``.
    """
    task_id = await _seed_task(core, status=TaskStatus.BACKLOG)

    from kagan.core._db_helpers import _db_async as _real_db_async

    # transition_task calls _db_async exactly once (for the write).
    # tasks.get() uses a different code path (Tasks.get → _db_async within Tasks).
    # We intercept the transition-level _db_async call to inject the drift.
    intercepted = False

    async def _patched_db_async(engine: Any, fn: Any, **kwargs: Any) -> Any:
        nonlocal intercepted
        if not intercepted:
            intercepted = True
            # Flip the task to IN_PROGRESS in the DB before the write runs.
            # This simulates a concurrent caller winning the race.
            await asyncio.to_thread(core.tasks._set_status, task_id, TaskStatus.IN_PROGRESS)
        return await _real_db_async(engine, fn, **kwargs)

    with patch("kagan.core.transitions._db_async", side_effect=_patched_db_async):
        with pytest.raises(IllegalTransition):
            # We try BACKLOG → IN_PROGRESS, but by the time the write runs the
            # DB already shows IN_PROGRESS, so the TOCTOU guard fires.
            await transition_task(core, task_id, TaskStatus.IN_PROGRESS)


# ---------------------------------------------------------------------------
# Session transition matrix
# ---------------------------------------------------------------------------
# Legal (from, to) pairs:
_SESSION_LEGAL: list[tuple[SessionStatus, SessionStatus]] = [
    (SessionStatus.PENDING, SessionStatus.RUNNING),
    (SessionStatus.PENDING, SessionStatus.CANCELLED),
    (SessionStatus.PENDING, SessionStatus.FAILED),
    (SessionStatus.RUNNING, SessionStatus.COMPLETED),
    (SessionStatus.RUNNING, SessionStatus.FAILED),
    (SessionStatus.RUNNING, SessionStatus.CANCELLED),
]

# Illegal (from, to) pairs:
_SESSION_ILLEGAL: list[tuple[SessionStatus, SessionStatus]] = [
    # Same-status no-ops
    (SessionStatus.PENDING, SessionStatus.PENDING),
    (SessionStatus.RUNNING, SessionStatus.RUNNING),
    (SessionStatus.COMPLETED, SessionStatus.COMPLETED),
    (SessionStatus.FAILED, SessionStatus.FAILED),
    (SessionStatus.CANCELLED, SessionStatus.CANCELLED),
    # Terminal states cannot transition to anything
    (SessionStatus.COMPLETED, SessionStatus.PENDING),
    (SessionStatus.COMPLETED, SessionStatus.RUNNING),
    (SessionStatus.COMPLETED, SessionStatus.FAILED),
    (SessionStatus.COMPLETED, SessionStatus.CANCELLED),
    (SessionStatus.FAILED, SessionStatus.PENDING),
    (SessionStatus.FAILED, SessionStatus.RUNNING),
    (SessionStatus.FAILED, SessionStatus.COMPLETED),
    (SessionStatus.FAILED, SessionStatus.CANCELLED),
    (SessionStatus.CANCELLED, SessionStatus.PENDING),
    (SessionStatus.CANCELLED, SessionStatus.RUNNING),
    (SessionStatus.CANCELLED, SessionStatus.COMPLETED),
    (SessionStatus.CANCELLED, SessionStatus.FAILED),
    # Non-standard forward paths
    (SessionStatus.RUNNING, SessionStatus.PENDING),
    (SessionStatus.PENDING, SessionStatus.COMPLETED),
]


def _make_session_mock(status: SessionStatus) -> Any:
    """Return a minimal mock object that looks like a Session model."""
    m = MagicMock()
    m.id = "session-001"
    m.status = status
    return m


@pytest.mark.parametrize("frm,to", _SESSION_LEGAL)
@pytest.mark.asyncio
async def test_transition_session_legal(frm: SessionStatus, to: SessionStatus) -> None:
    """Legal session transitions complete without raising."""
    session_mock = _make_session_mock(frm)
    client = MagicMock()
    client.engine = MagicMock()

    read_session = MagicMock()
    read_session.get = MagicMock(return_value=session_mock)

    write_session = MagicMock()
    write_session.get = MagicMock(return_value=session_mock)
    write_session.add = MagicMock()
    write_session.commit = MagicMock()
    write_session.refresh = MagicMock()

    call_count = 0

    async def _db_async_side_effect(engine: Any, op: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return op(read_session)
        return op(write_session)

    with patch("kagan.core.transitions._db_async", side_effect=_db_async_side_effect):
        result = await transition_session(client, "session-001", to)
    assert result.status == to


@pytest.mark.parametrize("frm,to", _SESSION_ILLEGAL)
@pytest.mark.asyncio
async def test_transition_session_illegal(frm: SessionStatus, to: SessionStatus) -> None:
    """Illegal session transitions raise IllegalTransition."""
    session_mock = _make_session_mock(frm)
    client = MagicMock()
    client.engine = MagicMock()

    read_session = MagicMock()
    read_session.get = MagicMock(return_value=session_mock)

    async def _db_async_side_effect(engine: Any, op: Any, **kwargs: Any) -> Any:
        return op(read_session)

    with patch("kagan.core.transitions._db_async", side_effect=_db_async_side_effect):
        with pytest.raises(IllegalTransition):
            await transition_session(client, "session-001", to)


@pytest.mark.asyncio
async def test_transition_session_propagates_actor_label() -> None:
    """The *by* keyword is accepted without error for session transitions."""
    session_mock = _make_session_mock(SessionStatus.PENDING)
    client = MagicMock()
    client.engine = MagicMock()

    read_session = MagicMock()
    read_session.get = MagicMock(return_value=session_mock)

    write_session = MagicMock()
    write_session.get = MagicMock(return_value=session_mock)
    write_session.add = MagicMock()
    write_session.commit = MagicMock()
    write_session.refresh = MagicMock()

    call_count = 0

    async def _db_async_side_effect(engine: Any, op: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return op(read_session)
        return op(write_session)

    with patch("kagan.core.transitions._db_async", side_effect=_db_async_side_effect):
        result = await transition_session(
            client, "session-001", SessionStatus.RUNNING, by="reviewer"
        )
    assert result.status == SessionStatus.RUNNING


@pytest.mark.asyncio
async def test_transition_session_toctou_guard() -> None:
    """TOCTOU guard: IllegalTransition raised when status drifts before the write."""
    # The read sees PENDING; the write callback sees RUNNING (drift).
    read_session_mock = _make_session_mock(SessionStatus.PENDING)
    drifted_session_mock = _make_session_mock(SessionStatus.RUNNING)

    client = MagicMock()
    client.engine = MagicMock()

    read_session = MagicMock()
    read_session.get = MagicMock(return_value=read_session_mock)

    write_session = MagicMock()
    # The write callback reads the drifted status from the DB.
    write_session.get = MagicMock(return_value=drifted_session_mock)
    write_session.add = MagicMock()
    write_session.commit = MagicMock()
    write_session.refresh = MagicMock()

    call_count = 0

    async def _db_async_side_effect(engine: Any, op: Any, **kwargs: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return op(read_session)
        return op(write_session)

    with patch("kagan.core.transitions._db_async", side_effect=_db_async_side_effect):
        with pytest.raises(IllegalTransition):
            # We try PENDING → CANCELLED, but the DB now shows RUNNING.
            await transition_session(client, "session-001", SessionStatus.CANCELLED)


# ---------------------------------------------------------------------------
# IllegalTransition inherits from InvalidTransitionError
# ---------------------------------------------------------------------------


def test_illegal_transition_is_invalid_transition_error() -> None:
    """IllegalTransition must be a subclass of InvalidTransitionError.

    This ensures existing error handlers in _helpers.py (which catch
    InvalidTransitionError and return HTTP 409) also catch IllegalTransition.
    """
    exc = IllegalTransition(TaskStatus.BACKLOG, TaskStatus.DONE)
    assert isinstance(exc, InvalidTransitionError)
    assert "BACKLOG" in str(exc)
    assert "DONE" in str(exc)
