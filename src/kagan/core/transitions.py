"""Funnel functions for task and session status transitions.

All status mutations MUST go through ``transition_task`` or
``transition_session``.  Direct field assignment (``task.status = X``) is
forbidden outside of the implementation internals called by these two
functions.

Legal task (from, to) pairs
────────────────────────────
BACKLOG        → IN_PROGRESS  (start work)
IN_PROGRESS    → REVIEW       (agent done)
IN_PROGRESS    → BACKLOG      (agent cancelled / requeue)
REVIEW         → IN_PROGRESS  (review rejected / requeue)
REVIEW         → BACKLOG      (requeue from review)
REVIEW         → DONE         (merge — requires passing review gate)
DONE           → BACKLOG      (requeue a completed task)
ANY            → (same)       n/a — same-status "no-op" calls are rejected

Legal session (from, to) pairs
────────────────────────────────
PENDING   → RUNNING
PENDING   → CANCELLED
PENDING   → FAILED
RUNNING   → COMPLETED
RUNNING   → FAILED
RUNNING   → CANCELLED
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from loguru import logger

from kagan.core._db_helpers import _db_async, _utc_now
from kagan.core._reviews import is_review_approved
from kagan.core._tasks import _record_task_audit
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.errors import InvalidTransitionError, NotFoundError
from kagan.core.models import Session, Task

if TYPE_CHECKING:
    from kagan.core.client import KaganCore


class IllegalTransition(InvalidTransitionError):
    """Raised when a requested status transition is not permitted.

    Extends ``InvalidTransitionError`` so existing ``_helpers.py`` error
    handling (which maps ``InvalidTransitionError`` → HTTP 409) continues
    to work for both the legacy direct-validate path and the new funnel.
    """


async def _has_passing_review(client: KaganCore, task_id: str) -> bool:
    """Return True if every acceptance criterion has a passing verdict.

    Delegates to the existing helper in ``_reviews`` so no logic is
    duplicated here.  The call is offloaded to a thread because
    ``is_review_approved`` is synchronous (it uses ``_db_sync``).
    """
    return await asyncio.to_thread(is_review_approved, task_id, client.engine)


async def transition_task(
    client: KaganCore,
    task_id: str,
    to: TaskStatus,
    *,
    by: str = "system",
) -> Task:
    """Move *task_id* to *to*, enforcing the legal transition matrix.

    Raises ``IllegalTransition`` when the (from, to) pair is not in the
    matrix, or when a guard (e.g. the review gate for REVIEW → DONE)
    rejects the move.

    Args:
        client: Live ``KaganCore`` instance (owns engine + task service).
        task_id: ID of the task to transition.
        to: Target ``TaskStatus``.
        by: Free-form actor label for the audit trail (default "system").

    Returns:
        The refreshed ``Task`` model after the status write.
    """
    task = await client.tasks.get(task_id)
    src = task.status

    if src == to:
        raise IllegalTransition(src, to)

    match (src, to):
        # ── Happy paths (no guard needed) ──────────────────────────────────
        case (TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS):
            pass

        case (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW):
            pass

        case (TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG):
            pass

        case (TaskStatus.REVIEW, TaskStatus.IN_PROGRESS):
            pass

        case (TaskStatus.REVIEW, TaskStatus.BACKLOG):
            pass

        case (TaskStatus.DONE, TaskStatus.BACKLOG):
            pass

        # ── Guarded path: review gate ───────────────────────────────────────
        case (TaskStatus.REVIEW, TaskStatus.DONE):
            if not await _has_passing_review(client, task_id):
                raise IllegalTransition(
                    src,
                    to,
                )

        # ── Explicitly forbidden shortcuts ─────────────────────────────────
        case (TaskStatus.IN_PROGRESS, TaskStatus.DONE):
            raise IllegalTransition(src, to)

        case (TaskStatus.BACKLOG, TaskStatus.DONE):
            raise IllegalTransition(src, to)

        case (TaskStatus.BACKLOG, TaskStatus.REVIEW):
            raise IllegalTransition(src, to)

        case (TaskStatus.DONE, TaskStatus.IN_PROGRESS):
            raise IllegalTransition(src, to)

        case (TaskStatus.DONE, TaskStatus.REVIEW):
            raise IllegalTransition(src, to)

        # ── Catch-all: any other (from, to) pair is rejected ───────────────
        case _:
            raise IllegalTransition(src, to)

    logger.debug(
        "transition_task: task={} {} → {} (by={})",
        task_id,
        src.value,
        to.value,
        by,
    )

    # Write the status inside a single _db_async transaction so that the read
    # (above) and write are not split across two round-trips (TOCTOU fix, P2).
    # The write mirrors _set_status() semantics: updated_at + audit record.
    def _write_task(s):
        obj = s.get(Task, task_id)
        if obj is None:
            raise NotFoundError("Task", task_id)
        # TOCTOU guard: abort if the status drifted between our read and now.
        if obj.status != src:
            raise IllegalTransition(obj.status, to)
        obj.status = to
        obj.updated_at = _utc_now()
        _record_task_audit(
            s,
            action="task.status_change",
            task_id=task_id,
            detail={"from": src.value, "to": to.value},
        )
        s.add(obj)
        s.commit()
        s.refresh(obj)
        _ = list(obj.criteria)  # Eagerly load criteria while session is open
        logger.info("Task {} moved to {} (by={})", task_id, to.value, by)
        return obj

    moved: Task = await _db_async(client.engine, _write_task)
    await client.tasks.events.emit(
        task_id,
        "task_status_changed",
        {"from": src.value, "to": to.value},
    )
    return moved


async def transition_session(
    client: KaganCore,
    session_id: str,
    to: SessionStatus,
    *,
    by: str = "system",
) -> Session:
    """Move *session_id* to *to*, enforcing the legal session transition matrix.

    Session status is managed internally by ``Sessions`` methods
    (``_mark_session_running``, ``_complete_session``, ``_fail_session``,
    ``cancel``).  This function is the external-facing funnel for callers that
    need to change session status from outside the ``Sessions`` class (e.g.
    REST routes or MCP tools).

    Raises ``IllegalTransition`` when the (from, to) pair is not legal.

    Args:
        client: Live ``KaganCore`` instance.
        session_id: ID of the session to transition.
        to: Target ``SessionStatus``.
        by: Free-form actor label (default "system").

    Returns:
        The refreshed ``Session`` model after the status write.
    """
    def _get_session(s):
        obj = s.get(Session, session_id)
        if obj is None:
            raise NotFoundError("Session", session_id)
        return obj

    session = await _db_async(client.engine, _get_session)
    src = session.status

    if src == to:
        raise IllegalTransition(src, to)

    match (src, to):
        case (SessionStatus.PENDING, SessionStatus.RUNNING):
            pass
        case (SessionStatus.PENDING, SessionStatus.CANCELLED):
            pass
        case (SessionStatus.PENDING, SessionStatus.FAILED):
            pass
        case (SessionStatus.RUNNING, SessionStatus.COMPLETED):
            pass
        case (SessionStatus.RUNNING, SessionStatus.FAILED):
            pass
        case (SessionStatus.RUNNING, SessionStatus.CANCELLED):
            pass
        case _:
            raise IllegalTransition(src, to)

    logger.debug(
        "transition_session: session={} {} → {} (by={})",
        session_id,
        src.value,
        to.value,
        by,
    )

    def _write(s):
        obj = s.get(Session, session_id)
        if obj is None:
            raise NotFoundError("Session", session_id)
        # TOCTOU guard: abort if status drifted between the read above and now.
        if obj.status != src:
            raise IllegalTransition(obj.status, to)
        obj.status = to
        if to in {SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED}:
            obj.ended_at = _utc_now()
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj  # type: ignore[return-value]  # SQLModel refresh returns None

    return await _db_async(client.engine, _write)
