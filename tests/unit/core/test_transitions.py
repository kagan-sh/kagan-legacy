"""Unit tests for kagan.core.transitions — task and session (from, to) matrix.

Coverage:
- Every (TaskStatus x TaskStatus) pair across the 4-value enum.
- Every (SessionStatus x SessionStatus) pair across the 5-value enum.
- Happy paths (legal transitions complete without error).
- Rejected paths (illegal transitions raise IllegalTransition).
- Review gate: REVIEW → DONE blocked when is_review_approved returns False.
- Review gate: REVIEW → DONE allowed when is_review_approved returns True.
- Same-status no-op rejected for both task and session.
- TOCTOU guard: IllegalTransition raised when status drifts before the write.

Design note: task and session matrix tests use a real KaganCore (SQLite on
``tmp_path``) with rows inserted via ``_db_async``, matching testing.md
"real everything, fake agent".  TOCTOU cases replace ``transition*``'s
``_db_async`` binding via ``monkeypatch`` to inject a concurrent status drift.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from kagan.core import KaganCore
from kagan.core import transitions as transitions_mod
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.errors import InvalidTransitionError
from kagan.core.models import AcceptanceCriterion, ReviewVerdict, Session
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


async def _seed_session(core: KaganCore, *, status: SessionStatus) -> str:
    """Attach a Session row to a fresh task at *status* (direct DB insert)."""
    from kagan.core._db_helpers import _db_async

    task_id = await _seed_task(core, status=TaskStatus.IN_PROGRESS)
    sid = uuid4().hex[:16]

    def _add(s) -> None:
        row = Session(
            id=sid,
            task_id=task_id,
            agent_backend="claude-code",
            status=status,
        )
        s.add(row)
        s.commit()

    await _db_async(core.engine, _add)
    return sid


async def _session_status(core: KaganCore, session_id: str) -> SessionStatus:
    from kagan.core._db_helpers import _db_async

    def _get(s) -> SessionStatus:
        obj = s.get(Session, session_id)
        assert obj is not None
        return obj.status

    return await _db_async(core.engine, _get)


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

# Illegal (from, to) pairs:
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
async def test_transition_task_toctou_guard(
    core: KaganCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TOCTOU guard: if status drifts between the read and the write, raise.

    We wrap ``transitions._db_async`` so the single write round-trip runs after
    another task flips the row — simulating a concurrent caller winning the race.
    """
    task_id = await _seed_task(core, status=TaskStatus.BACKLOG)

    from kagan.core._db_helpers import _db_async as _real_db_async

    intercepted = False

    async def _patched_db_async(engine: Any, fn: Any, **kwargs: Any) -> Any:
        nonlocal intercepted
        if not intercepted:
            intercepted = True
            await asyncio.to_thread(core.tasks._set_status, task_id, TaskStatus.IN_PROGRESS)
        return await _real_db_async(engine, fn, **kwargs)

    monkeypatch.setattr(transitions_mod, "_db_async", _patched_db_async)
    with pytest.raises(IllegalTransition):
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


@pytest.mark.parametrize("frm,to", _SESSION_LEGAL)
@pytest.mark.asyncio
async def test_transition_session_legal(
    frm: SessionStatus, to: SessionStatus, core: KaganCore
) -> None:
    """Legal session transitions complete without raising."""
    sid = await _seed_session(core, status=frm)
    result = await transition_session(core, sid, to)
    assert result.status == to


@pytest.mark.parametrize("frm,to", _SESSION_ILLEGAL)
@pytest.mark.asyncio
async def test_transition_session_illegal(
    frm: SessionStatus, to: SessionStatus, core: KaganCore
) -> None:
    """Illegal session transitions raise IllegalTransition."""
    sid = await _seed_session(core, status=frm)
    with pytest.raises(IllegalTransition):
        await transition_session(core, sid, to)
    assert await _session_status(core, sid) == frm


@pytest.mark.asyncio
async def test_transition_session_propagates_actor_label(core: KaganCore) -> None:
    """The *by* keyword is accepted without error for session transitions."""
    sid = await _seed_session(core, status=SessionStatus.PENDING)
    result = await transition_session(core, sid, SessionStatus.RUNNING, by="reviewer")
    assert result.status == SessionStatus.RUNNING


@pytest.mark.asyncio
async def test_transition_session_toctou_guard(
    core: KaganCore, monkeypatch: pytest.MonkeyPatch
) -> None:
    """TOCTOU guard: IllegalTransition raised when status drifts before the write."""
    sid = await _seed_session(core, status=SessionStatus.PENDING)

    from kagan.core._db_helpers import _db_async as _real_db_async

    def _flip_to_running(s) -> None:
        obj = s.get(Session, sid)
        assert obj is not None
        obj.status = SessionStatus.RUNNING
        s.add(obj)
        s.commit()

    async def _wrap(engine: Any, fn: Any, **kwargs: Any) -> Any:
        if getattr(fn, "__name__", None) == "_write":
            await _real_db_async(engine, _flip_to_running)
        return await _real_db_async(engine, fn, **kwargs)

    monkeypatch.setattr(transitions_mod, "_db_async", _wrap)
    with pytest.raises(IllegalTransition):
        await transition_session(core, sid, SessionStatus.CANCELLED)


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
