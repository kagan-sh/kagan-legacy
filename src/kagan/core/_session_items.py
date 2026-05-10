"""Unified session read model.

Merges ChatSession (orchestrator/general) and Session (task worker/reviewer)
into a single SessionItem type.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlmodel import select

from kagan.core._db_helpers import _db_async, _sa_col
from kagan.core.models import ChatSession, Session, Task

if TYPE_CHECKING:
    from sqlalchemy import Engine


@dataclass(frozen=True, slots=True)
class SessionCapabilities:
    can_chat: bool
    can_stream: bool
    can_replay: bool
    can_stop: bool
    can_close: bool
    has_kagan_tools: bool


@dataclass(frozen=True, slots=True)
class SessionItem:
    id: str
    type: str
    role: str | None
    status: str
    title: str
    backend: str | None
    project_id: str | None
    task_id: str | None
    task_status: str | None
    session_id: str | None
    chat_session_id: str | None
    updated_at: str
    capabilities: SessionCapabilities


def _format_dt(value: datetime | None) -> str:
    if value is None:
        return ""
    return value.isoformat() if isinstance(value, datetime) else str(value)


def _chat_to_item(chat: ChatSession) -> SessionItem:
    is_general = chat.session_type == "general"
    capabilities = SessionCapabilities(
        can_chat=True,
        can_stream=True,
        can_replay=False,
        can_stop=True,
        can_close=True,
        has_kagan_tools=not is_general,
    )
    return SessionItem(
        id=f"{'gen' if is_general else 'orch'}:{chat.id}",
        type="general" if is_general else "orchestrator",
        role=None,
        status="idle",
        title=chat.label,
        backend=chat.agent_backend,
        project_id=chat.project_id,
        task_id=None,
        task_status=None,
        session_id=None,
        chat_session_id=chat.id,
        updated_at=_format_dt(chat.updated_at),
        capabilities=capabilities,
    )


def _task_session_to_item(session: Session, task: Task) -> SessionItem:
    updated_at_raw = session.ended_at if session.ended_at is not None else session.started_at
    status_value = session.status.value if hasattr(session.status, "value") else str(session.status)
    task_status_value = task.status.value if hasattr(task.status, "value") else str(task.status)
    capabilities = SessionCapabilities(
        can_chat=False,
        can_stream=False,
        can_replay=True,
        can_stop=True,
        can_close=False,
        has_kagan_tools=True,
    )
    return SessionItem(
        id=f"task:{session.id}",
        type="task",
        role=session.agent_role,
        status=status_value.lower(),
        title=task.title,
        backend=session.agent_backend,
        project_id=task.project_id,
        task_id=task.id,
        task_status=task_status_value,
        session_id=session.id,
        chat_session_id=None,
        updated_at=_format_dt(updated_at_raw),
        capabilities=capabilities,
    )


def _status_group(status: str) -> int:
    if status in ("running", "pending"):
        return 0
    if status == "idle":
        return 1
    return 2


async def list_session_items(
    engine: Engine,
    project_id: str | None = None,
) -> list[SessionItem]:
    """Return all sessions (chat + task) unified as SessionItem."""

    def _query(s) -> list[SessionItem]:
        items: list[SessionItem] = []

        # 1. ChatSession rows -> orchestrator (all chat sessions for now)
        chat_stmt = select(ChatSession)
        if project_id is not None:
            chat_stmt = chat_stmt.where(_sa_col(ChatSession.project_id) == project_id)
        for chat in s.exec(chat_stmt).all():
            items.append(_chat_to_item(chat))

        # 2. Session rows joined with Task
        sess_stmt = select(Session, Task).join(Task, _sa_col(Session.task_id) == _sa_col(Task.id))
        if project_id is not None:
            sess_stmt = sess_stmt.where(_sa_col(Task.project_id) == project_id)
        for session, task in s.exec(sess_stmt).all():
            items.append(_task_session_to_item(session, task))

        # 3. Sort: active -> idle -> terminal; newest first within each group
        active = [i for i in items if _status_group(i.status) == 0]
        idle = [i for i in items if _status_group(i.status) == 1]
        terminal = [i for i in items if _status_group(i.status) == 2]

        active.sort(key=lambda i: i.updated_at, reverse=True)
        idle.sort(key=lambda i: i.updated_at, reverse=True)
        terminal.sort(key=lambda i: i.updated_at, reverse=True)

        return active + idle + terminal

    return await _db_async(engine, _query)
