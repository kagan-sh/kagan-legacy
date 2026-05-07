"""Chat session attach helpers.

Provides two public helpers consumed by the orchestrator chat overlay:

- ``attach_chat_to_session`` — wire a ChatSession to a specific agent Session
  (or detach it by passing ``session_id=None``, which returns it to orchestrator
  mode).
- ``inject_agent_notification`` — append a structured ``system`` ChatMessage so
  the orchestrator model sees worker/reviewer state transitions on the next turn.
  Mirrors Claude Code's ``task-notification`` mode.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Literal

from loguru import logger

from kagan.core._db_helpers import _db_async
from kagan.core.models import ChatMessage, ChatSession

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
        agent_role: Role hint stored alongside the attach target
            (e.g. ``"worker"`` or ``"reviewer"``).  Cleared to ``None`` when
            ``session_id`` is ``None``.
    """

    def _write(s) -> None:
        row = s.get(ChatSession, chat_session_id)
        if row is None:
            logger.warning("attach_chat_to_session: chat session {} not found", chat_session_id)
            return
        row.attached_session_id = session_id
        row.attached_role = agent_role if session_id is not None else None
        row.updated_at = datetime.now(UTC)
        s.add(row)

    await _db_async(engine, _write, commit=True)
    logger.debug(
        "Chat session {} attached to session_id={} role={}",
        chat_session_id,
        session_id,
        agent_role,
    )


async def inject_agent_notification(
    engine: Engine,
    chat_session_id: str,
    *,
    kind: AgentNotificationKind,
    session_id: str,
    summary: str,
) -> None:
    """Append a system ChatMessage encoding an agent lifecycle transition.

    The message is stored with ``role="system"`` so the orchestrator model sees
    it as an out-of-band notification rather than user input.  The ``content``
    field is a JSON-encoded struct that downstream consumers (TUI, web, CLI) can
    parse to render a badge or inline notice.

    Args:
        engine: SQLAlchemy engine.
        chat_session_id: ID of the ChatSession to notify.
        kind: Lifecycle event kind — one of ``"agent_finished"``,
            ``"agent_stopped"``, or ``"agent_started"``.
        session_id: The agent Session ID that triggered the transition.
        summary: Short human-readable description of the transition.
    """
    payload = json.dumps(
        {
            "type": "agent_notification",
            "kind": kind,
            "session_id": session_id,
            "summary": summary,
        }
    )

    def _write(s) -> None:
        chat_row = s.get(ChatSession, chat_session_id)
        if chat_row is None:
            logger.warning("inject_agent_notification: chat session {} not found", chat_session_id)
            return
        msg = ChatMessage(
            session_id=chat_session_id,
            role="system",
            content=payload,
        )
        s.add(msg)
        chat_row.updated_at = datetime.now(UTC)
        s.add(chat_row)

    await _db_async(engine, _write, commit=True)
    logger.debug(
        "Injected {} notification into chat session {} for agent session {}",
        kind,
        chat_session_id,
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
    """Inject an agent notification into all orchestrator chat sessions for a project.

    Strategy:
    - Notify all ChatSessions where ``project_id`` matches AND the session is in
      orchestrator mode (``attached_session_id IS NULL`` or matches the agent
      session).  This intentionally excludes chat sessions attached to a *different*
      agent session; those belong to a different task context.
    - If no sessions match, the notification is silently dropped (best-effort).

    This is wired into the session-status transition hooks so the orchestrator
    model always sees agent completions on the next turn.
    """
    from sqlmodel import select

    def _find_sessions(s) -> list[str]:
        from kagan.core.models import ChatSession as CS

        stmt = select(CS.id).where(  # type: ignore[attr-defined]
            CS.project_id == project_id,  # type: ignore[attr-defined]
        )
        ids = list(s.exec(stmt).all())
        return ids

    chat_ids = await _db_async(engine, _find_sessions)
    if not chat_ids:
        return

    for cid in chat_ids:
        try:
            await inject_agent_notification(
                engine,
                cid,
                kind=kind,
                session_id=session_id,
                summary=summary,
            )
        except Exception:
            logger.opt(exception=True).warning(
                "Failed to inject notification into chat session {}", cid
            )


__all__ = [
    "AgentNotificationKind",
    "attach_chat_to_session",
    "inject_agent_notification",
    "notify_project_chat_sessions",
]
