"""Chat session attach helpers.

Provides two public helpers consumed by the orchestrator chat overlay:

- ``attach_chat_to_session`` — wire a ChatSession to a specific agent Session
  (or detach it by passing ``session_id=None``, which returns it to orchestrator
  mode).
- ``record_agent_lifecycle_event`` — append a structured task event for
  worker/reviewer lifecycle transitions without polluting chat history.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from loguru import logger

from kagan.core._db_helpers import _db_async
from kagan.core.models import ChatSession, Session, SessionEvent, Task

if TYPE_CHECKING:
    from sqlalchemy import Engine

AgentNotificationKind = Literal["agent_finished", "agent_stopped", "agent_started"]


async def attach_chat_to_session(
    engine: Engine,
    chat_session_id: str,
    session_id: str | None,
    *,
    agent_role: str | None = None,
) -> None:
    """Attach or detach a ChatSession from an agent Session.

    Args:
        engine: SQLAlchemy engine.
        chat_session_id: ID of the ChatSession to update.
        session_id: Target agent Session ID, or ``None`` to return the chat to
            orchestrator mode (detached from any specific session).
        agent_role: Deprecated compatibility hint. The role is derived from
            ``Session.agent_role`` whenever callers need it.
    """

    def _write(s) -> None:
        row = s.get(ChatSession, chat_session_id)
        if row is None:
            logger.warning("attach_chat_to_session: chat session {} not found", chat_session_id)
            return
        row.attached_session_id = session_id
        row.updated_at = datetime.now(UTC)
        s.add(row)

    await _db_async(engine, _write, commit=True)
    logger.debug(
        "Chat session {} attached to session_id={} role={}",
        chat_session_id,
        session_id,
        agent_role,
    )


async def record_agent_lifecycle_event(
    engine: Engine,
    *,
    task_id: str,
    kind: AgentNotificationKind,
    session_id: str,
    summary: str,
) -> None:
    """Append a task event encoding an agent lifecycle transition.

    Lifecycle state belongs to the task/session event stream. Chat transcripts
    stay limited to conversation history so session replay does not invent
    messages the user or model never authored.

    Args:
        engine: SQLAlchemy engine.
        task_id: ID of the task whose agent session changed state.
        kind: Lifecycle event kind — one of ``"agent_finished"``,
            ``"agent_stopped"``, or ``"agent_started"``.
        session_id: The agent Session ID that triggered the transition.
        summary: Short human-readable description of the transition.
    """

    def _write(s) -> None:
        task_row = s.get(Task, task_id)
        session_row = s.get(Session, session_id)
        if task_row is None or session_row is None:
            logger.warning(
                "record_agent_lifecycle_event: task/session missing task={} session={}",
                task_id,
                session_id,
            )
            return

        event = SessionEvent(
            task_id=task_id,
            session_id=session_id,
            event_type="agent_lifecycle",
            payload={
                "kind": kind,
                "session_id": session_id,
                "summary": summary,
            },
        )
        s.add(event)

    await _db_async(engine, _write, commit=True)
    logger.debug(
        "Recorded {} lifecycle event for task {} agent session {}",
        kind,
        task_id,
        session_id,
    )


async def notify_project_chat_sessions(
    engine: Engine,
    *,
    project_id: str,
    kind: AgentNotificationKind,
    session_id: str,
    summary: str,
) -> None:
    """Compatibility wrapper that records one lifecycle event for the session.

    ``project_id`` is accepted for older callers but no longer controls fan-out:
    lifecycle state is stored once on the task event stream instead of once per
    chat session.
    """
    del project_id

    def _task_id_for_session(s) -> str | None:
        row = s.get(Session, session_id)
        return row.task_id if row is not None else None

    task_id = await _db_async(engine, _task_id_for_session)
    if task_id is None:
        return
    await record_agent_lifecycle_event(
        engine,
        task_id=task_id,
        kind=kind,
        session_id=session_id,
        summary=summary,
    )


__all__ = [
    "AgentNotificationKind",
    "attach_chat_to_session",
    "notify_project_chat_sessions",
    "record_agent_lifecycle_event",
]
