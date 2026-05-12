"""Chat session lifecycle helpers.

Provides helpers for recording agent lifecycle events without polluting
chat history.  The attach/detach surface has been removed in the unified
sessions refactor.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from loguru import logger

from kagan.core._db_helpers import _db_async
from kagan.core.models import Session, SessionEvent, Task

if TYPE_CHECKING:
    from sqlalchemy import Engine

AgentNotificationKind = Literal["agent_finished", "agent_stopped", "agent_started"]


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
    "notify_project_chat_sessions",
    "record_agent_lifecycle_event",
]
