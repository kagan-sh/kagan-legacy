"""Unit tests for kagan.core.transitions — exhaustive (from, to) matrix.

Coverage:
- Every (TaskStatus x TaskStatus) pair across the 4-value enum.
- Every (SessionStatus x SessionStatus) pair across the 5-value enum.
- Happy paths (legal transitions complete without error).
- Rejected paths (illegal transitions raise IllegalTransition).
- Review gate: REVIEW → DONE blocked when is_review_approved returns False.
- Review gate: REVIEW → DONE allowed when is_review_approved returns True.
- Same-status no-op rejected for both task and session.

Design note: the review gate guard calls ``is_review_approved`` (a DB read
via ``_db_sync``).  We stub that via ``unittest.mock.patch`` at the helper
boundary so that unit tests remain DB-free.  All other transitions have no
guards and need no stubs.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.transitions import IllegalTransition, transition_session, transition_task

pytestmark = [pytest.mark.unit]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_task(status: TaskStatus) -> Any:
    """Return a minimal mock object that looks like a Task model."""
    m = MagicMock()
    m.id = "task-001"
    m.status = status
    return m


def _make_session(status: SessionStatus) -> Any:
    """Return a minimal mock object that looks like a Session model."""
    m = MagicMock()
    m.id = "session-001"
    m.status = status
    return m


def _make_client(task_status: TaskStatus) -> Any:
    """Return a minimal mock KaganCore with tasks.get and tasks.set_status wired."""
    task_mock = _make_task(task_status)
    client = MagicMock()
    client.tasks = MagicMock()
    client.tasks.get = AsyncMock(return_value=task_mock)
    updated_task = _make_task(task_status)  # will carry the new status in real code
    client.tasks.set_status = AsyncMock(return_value=updated_task)
    client.engine = MagicMock()
    return client


def _make_session_client(session_status: SessionStatus) -> Any:
    """Return a minimal mock KaganCore with engine wired for session transitions."""
    session_mock = _make_session(session_status)
    client = MagicMock()
    client.engine = MagicMock()
    return client, session_mock


# ---------------------------------------------------------------------------
# Task transition matrix
# ---------------------------------------------------------------------------
# Legal (from, to) pairs:
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
async def test_transition_task_legal(frm: TaskStatus, to: TaskStatus) -> None:
    """Legal task transitions complete without raising."""
    client = _make_client(frm)
    result = await transition_task(client, "task-001", to)
    # set_status was called with the right arguments
    client.tasks.set_status.assert_awaited_once_with("task-001", to)
    assert result is not None


@pytest.mark.parametrize("frm,to", _TASK_ILLEGAL)
@pytest.mark.asyncio
async def test_transition_task_illegal(frm: TaskStatus, to: TaskStatus) -> None:
    """Illegal task transitions raise IllegalTransition."""
    client = _make_client(frm)
    with pytest.raises(IllegalTransition):
        await transition_task(client, "task-001", to)
    # set_status must not have been called
    client.tasks.set_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_transition_task_review_to_done_blocked_when_no_passing_review() -> None:
    """REVIEW → DONE is rejected when is_review_approved returns False."""
    client = _make_client(TaskStatus.REVIEW)
    with patch(
        "kagan.core.transitions._has_passing_review",
        new=AsyncMock(return_value=False),
    ):
        with pytest.raises(IllegalTransition):
            await transition_task(client, "task-001", TaskStatus.DONE)
    client.tasks.set_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_transition_task_review_to_done_allowed_when_passing_review() -> None:
    """REVIEW → DONE is allowed when is_review_approved returns True."""
    client = _make_client(TaskStatus.REVIEW)
    with patch(
        "kagan.core.transitions._has_passing_review",
        new=AsyncMock(return_value=True),
    ):
        result = await transition_task(client, "task-001", TaskStatus.DONE)
    client.tasks.set_status.assert_awaited_once_with("task-001", TaskStatus.DONE)
    assert result is not None


@pytest.mark.asyncio
async def test_transition_task_propagates_actor_label() -> None:
    """The *by* keyword is accepted and does not change observable state."""
    client = _make_client(TaskStatus.BACKLOG)
    await transition_task(client, "task-001", TaskStatus.IN_PROGRESS, by="orchestrator")
    client.tasks.set_status.assert_awaited_once()


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
async def test_transition_session_legal(frm: SessionStatus, to: SessionStatus) -> None:
    """Legal session transitions complete without raising."""
    session_mock = _make_session(frm)
    client = MagicMock()
    client.engine = MagicMock()

    # Patch _db_async so we never hit the DB
    async def _fake_db_async(engine, op, **kwargs):
        # First call fetches the session; second call writes it.
        # We detect which call by inspecting what op does with our session.
        try:
            result = op(MagicMock())
        except Exception:
            return session_mock
        if result is None:
            return session_mock
        return result

    # The first op (get_session) will hit .get() — we need it to return the mock
    read_session = MagicMock()
    read_session.get = MagicMock(return_value=session_mock)

    write_session = MagicMock()
    write_session.get = MagicMock(return_value=session_mock)
    write_session.add = MagicMock()
    write_session.commit = MagicMock()
    write_session.refresh = MagicMock()

    call_count = 0

    async def _db_async_side_effect(engine, op, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return op(read_session)
        return op(write_session)

    with patch("kagan.core.transitions._db_async", side_effect=_db_async_side_effect):
        result = await transition_session(client, "session-001", to)
    assert result is not None  # type: ignore[truthy-bool]


@pytest.mark.parametrize("frm,to", _SESSION_ILLEGAL)
@pytest.mark.asyncio
async def test_transition_session_illegal(frm: SessionStatus, to: SessionStatus) -> None:
    """Illegal session transitions raise IllegalTransition."""
    session_mock = _make_session(frm)
    client = MagicMock()
    client.engine = MagicMock()

    read_session = MagicMock()
    read_session.get = MagicMock(return_value=session_mock)

    async def _db_async_side_effect(engine, op, **kwargs):
        return op(read_session)

    with patch("kagan.core.transitions._db_async", side_effect=_db_async_side_effect):
        with pytest.raises(IllegalTransition):
            await transition_session(client, "session-001", to)


@pytest.mark.asyncio
async def test_transition_session_propagates_actor_label() -> None:
    """The *by* keyword is accepted without error for session transitions."""
    session_mock = _make_session(SessionStatus.PENDING)
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

    async def _db_async_side_effect(engine, op, **kwargs):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return op(read_session)
        return op(write_session)

    with patch("kagan.core.transitions._db_async", side_effect=_db_async_side_effect):
        result = await transition_session(
            client, "session-001", SessionStatus.RUNNING, by="reviewer"
        )
    assert result is not None  # type: ignore[truthy-bool]


# ---------------------------------------------------------------------------
# IllegalTransition inherits from InvalidTransitionError
# ---------------------------------------------------------------------------


def test_illegal_transition_is_invalid_transition_error() -> None:
    """IllegalTransition must be a subclass of InvalidTransitionError.

    This ensures existing error handlers in _helpers.py (which catch
    InvalidTransitionError and return HTTP 409) also catch IllegalTransition.
    """
    from kagan.core.errors import InvalidTransitionError

    exc = IllegalTransition(TaskStatus.BACKLOG, TaskStatus.DONE)
    assert isinstance(exc, InvalidTransitionError)
    assert "BACKLOG" in str(exc)
    assert "DONE" in str(exc)
