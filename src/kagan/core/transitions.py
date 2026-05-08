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


_TERMINAL_STATUSES: frozenset[SessionStatus] = frozenset(
    [SessionStatus.COMPLETED, SessionStatus.FAILED, SessionStatus.CANCELLED]
)

_ALLOWED_SESSION_TRANSITIONS: frozenset[tuple[SessionStatus, SessionStatus]] = frozenset(
    {
        (SessionStatus.PENDING, SessionStatus.RUNNING),
        (SessionStatus.PENDING, SessionStatus.CANCELLED),
        (SessionStatus.PENDING, SessionStatus.FAILED),
        (SessionStatus.RUNNING, SessionStatus.COMPLETED),
        (SessionStatus.RUNNING, SessionStatus.FAILED),
        (SessionStatus.RUNNING, SessionStatus.CANCELLED),
    }
)


def _session_transition_allowed(
    src: SessionStatus,
    to: SessionStatus,
    *,
    allow_pending_completed: bool = False,
) -> bool:
    if allow_pending_completed and src == SessionStatus.PENDING and to == SessionStatus.COMPLETED:
        return True
    return (src, to) in _ALLOWED_SESSION_TRANSITIONS


def transition_session_in_db(
    db_session,
    session_id: str,
    to: SessionStatus,
    *,
    strict: bool = True,
    allow_pending_completed: bool = False,
) -> tuple[Session, SessionStatus] | None:
    """Sync-safe session transition primitive for code already inside _db_async.

    ``transition_session`` is the public async funnel. Internal lifecycle code
    that already owns a SQLModel session uses this helper so the same transition
    matrix is enforced without nesting async DB calls inside a sync transaction.
    Non-strict mode preserves legacy best-effort behavior for monitor callbacks:
    missing, same-status, or already-terminal sessions become no-ops.
    """
    obj = db_session.get(Session, session_id)
    if obj is None:
        if strict:
            raise NotFoundError("Session", session_id)
        return None

    src = obj.status
    if src == to:
        if strict:
            raise IllegalTransition(src, to)
        return None

    if not _session_transition_allowed(
        src,
        to,
        allow_pending_completed=allow_pending_completed,
    ):
        if strict:
            raise IllegalTransition(src, to)
        return None

    obj.status = to
    if to in _TERMINAL_STATUSES:
        obj.ended_at = _utc_now()
    db_session.add(obj)
    return obj, src


_ALLOWED_TASK_TRANSITIONS: frozenset[tuple[TaskStatus, TaskStatus]] = frozenset(
    {
        (TaskStatus.BACKLOG, TaskStatus.IN_PROGRESS),
        (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW),
        (TaskStatus.IN_PROGRESS, TaskStatus.BACKLOG),
        (TaskStatus.REVIEW, TaskStatus.IN_PROGRESS),
        (TaskStatus.REVIEW, TaskStatus.BACKLOG),
        (TaskStatus.REVIEW, TaskStatus.DONE),
        (TaskStatus.DONE, TaskStatus.BACKLOG),
    }
)


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

    if (src, to) == (TaskStatus.REVIEW, TaskStatus.DONE):
        if not await _has_passing_review(client, task_id):
            raise IllegalTransition(src, to)
    elif (src, to) not in _ALLOWED_TASK_TRANSITIONS:
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

    if not _session_transition_allowed(src, to):
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
        # TOCTOU guard: status must not have drifted between the initial read
        # and this write transaction.
        if obj.status != src:
            raise IllegalTransition(obj.status, to)
        # Apply the mutation directly on the already-loaded row rather than
        # delegating to transition_session_in_db, which would redundantly call
        # s.get(Session, session_id) again on the same SQLModel session.
        obj.status = to
        if to in _TERMINAL_STATUSES:
            obj.ended_at = _utc_now()
        s.add(obj)
        s.commit()
        s.refresh(obj)
        return obj  # type: ignore[return-value]  # SQLModel refresh returns None

    updated = await _db_async(client.engine, _write)
    await _notify_chat_on_session_transition(client, updated, src=src, to=to)
    return updated


async def _notify_chat_on_session_transition(
    client: KaganCore,
    session: Session,
    *,
    src: SessionStatus,
    to: SessionStatus,
) -> None:
    """Fire an agent lifecycle notification into orchestrator chat sessions.

    Runs after the DB commit so chat-injection failures never block the
    transition.  All errors are caught and logged as warnings — the caller
    always receives the updated Session regardless.

    Fires on:
    - Any → RUNNING (first time entering RUNNING state): kind="agent_started"
    - Any → terminal (COMPLETED): kind="agent_finished"
    - Any → terminal (FAILED / CANCELLED): kind="agent_stopped"

    Skips silently when task or project lookup fails.
    """
    # Only notify on meaningful lifecycle boundaries.
    entering_running = to == SessionStatus.RUNNING and src != SessionStatus.RUNNING
    entering_terminal = to in _TERMINAL_STATUSES

    if not (entering_running or entering_terminal):
        return

    try:
        from kagan.core._db_helpers import _db_async as _dba
        from kagan.core.chat._attach import record_agent_lifecycle_event
        from kagan.core.models import Task as _Task

        def _lookup(s) -> str | None:
            task = s.get(_Task, session.task_id)
            if task is None:
                return None
            return task.title

        task_info = await _dba(client.engine, _lookup)
        if task_info is None:
            logger.warning(
                "_notify_chat: task {} not found for session {}; skipping",
                session.task_id,
                session.id,
            )
            return

        task_title = task_info
        role_label = f" ({session.agent_role})" if session.agent_role else ""

        if entering_running:
            kind = "agent_started"
            summary = f"{task_title}{role_label} started"
        elif to == SessionStatus.COMPLETED:
            kind = "agent_finished"
            summary = f"{task_title}{role_label} finished"
        else:
            kind = "agent_stopped"
            summary = f"{task_title}{role_label} stopped ({to.value.lower()})"

        await record_agent_lifecycle_event(
            client.engine,
            task_id=session.task_id,
            kind=kind,
            session_id=session.id,
            summary=summary,
        )

    except Exception:
        logger.opt(exception=True).warning(
            "_notify_chat: failed to inject notification for session {}; "
            "transition already committed",
            session.id,
        )
