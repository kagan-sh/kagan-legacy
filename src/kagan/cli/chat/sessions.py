"""Session CRUD backed by the chat_sessions / chat_messages tables.

Public API (signatures unchanged from the JSON-blob era):

    list_chat_sessions(client, *, source, project_id) -> list[dict]
    get_chat_session(client, session_id) -> dict | None
    create_chat_session(client, *, source, label, agent_backend, project_id) -> dict
    save_chat_session(client, session) -> None
    delete_chat_session(client, session_id) -> bool
    append_chat_message(client, session_id, role, content, *, terminated) -> ChatMessage

The dict shape returned to callers preserves the legacy keys:
    id, label, source, agent_backend, orchestrator_history,
    messages_rendered, updated_at, project_id
so _chat_routes.py and the REPL do not need changes.
"""

import asyncio
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session as DBSession
from sqlmodel import select

from kagan.core.models import ChatMessage, ChatSession, Task
from kagan.core.models import Session as TaskSession

CHAT_SCOPE_PREFIX = "chat_scope_state_"
CHAT_LAST_SESSION_PREFIX = "chat_last_session_"

_SESSION_TITLE_MAX_LENGTH = 80

type ChatSessionRecord = dict[str, Any]


@dataclass(frozen=True, slots=True)
class ChatSessionListItem:
    index: int
    session_id: str
    label: str
    source: str
    agent_backend: str | None
    project_id: str | None
    updated_at: str
    updated_relative: str
    is_current: bool


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _format_relative_time(iso_timestamp: str) -> str:
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            minutes = seconds // 60
            return f"{minutes}m ago"
        if seconds < 86400:
            hours = seconds // 3600
            return f"{hours}h ago"
        days = seconds // 86400
        if days == 1:
            return "yesterday"
        if days < 30:
            return f"{days}d ago"
        return dt.strftime("%b %d")
    except (ValueError, TypeError):
        return ""


def _clean_generated_title(raw: str) -> str:
    import re

    cleaned = re.sub(r"<think>[\s\S]*?</think>\s*", "", raw)
    # Take first line only
    cleaned = cleaned.split("\n")[0].strip()
    # Remove surrounding quotes
    if len(cleaned) >= 2 and cleaned[0] in "\"'" and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1].strip()
    if not cleaned:
        return ""
    if len(cleaned) > _SESSION_TITLE_MAX_LENGTH:
        cleaned = cleaned[: _SESSION_TITLE_MAX_LENGTH - 3] + "..."
    return cleaned


def _session_to_dict(row: ChatSession, messages: list[ChatMessage]) -> dict[str, Any]:
    """Convert a ChatSession ORM row + messages list to the legacy dict shape."""
    history = [[m.role, m.content] for m in messages]
    updated_at = (
        row.updated_at.isoformat()
        if isinstance(row.updated_at, datetime)
        else str(row.updated_at)
    )
    return {
        "id": row.id,
        "label": row.label,
        "source": row.source,
        "agent_backend": row.agent_backend,
        "orchestrator_history": history,
        "messages_rendered": [],  # UI concern — no longer stored
        "updated_at": updated_at,
        "project_id": row.project_id,
    }


def _engine_from(client: Any):  # type: ignore[return]
    return getattr(client, "_engine", None)


# ---------------------------------------------------------------------------
# Core table CRUD
# ---------------------------------------------------------------------------


async def list_chat_sessions(
    client: Any, *, source: str | None = None, project_id: str | None = None
) -> list[dict[str, Any]]:
    engine = _engine_from(client)
    if engine is None:
        return []

    def _read() -> list[dict[str, Any]]:
        with DBSession(engine) as db:
            stmt = select(ChatSession)
            if source is not None:
                stmt = stmt.where(ChatSession.source == source)  # type: ignore[arg-type]
            if project_id is not None:
                stmt = stmt.where(ChatSession.project_id == project_id)  # type: ignore[arg-type]
            # Newest first
            stmt = stmt.order_by(ChatSession.updated_at.desc())  # type: ignore[attr-defined]
            sessions = db.exec(stmt).all()
            result: list[dict[str, Any]] = []
            for row in sessions:
                msgs = (
                    db.exec(
                        select(ChatMessage)
                        .where(ChatMessage.session_id == row.id)  # type: ignore[arg-type]
                        .order_by(ChatMessage.id)  # type: ignore[attr-defined]
                    ).all()
                )
                result.append(_session_to_dict(row, list(msgs)))
            return result

    return await asyncio.to_thread(_read)


async def get_chat_session(client: Any, session_id: str) -> dict[str, Any] | None:
    normalized_id = session_id.strip()
    if not normalized_id:
        return None
    engine = _engine_from(client)
    if engine is None:
        return None

    def _read() -> dict[str, Any] | None:
        with DBSession(engine) as db:
            row = db.get(ChatSession, normalized_id)
            if row is None:
                return None
            msgs = list(
                db.exec(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == normalized_id)  # type: ignore[arg-type]
                    .order_by(ChatMessage.id)  # type: ignore[attr-defined]
                ).all()
            )
            return _session_to_dict(row, msgs)

    return await asyncio.to_thread(_read)


async def resolve_task_session_binding(client: Any, session_id: str) -> dict[str, Any] | None:
    normalized_id = session_id.strip()
    if not normalized_id:
        return None

    engine = _engine_from(client)
    if engine is None:
        return None

    def _read() -> dict[str, Any] | None:
        with DBSession(engine) as db:
            bound = db.get(TaskSession, normalized_id)
            if bound is None:
                return None
            task = db.get(Task, bound.task_id)
            if task is None:
                return None
            status_value = getattr(bound.status, "value", str(bound.status))
            return {
                "id": bound.id,
                "label": f"Task {task.id[:8]} - {task.title}",
                "source": "task-session",
                "agent_backend": bound.agent_backend,
                "orchestrator_history": [],
                "messages_rendered": [
                    f"System: Attached to task session {bound.id} (status: {status_value})."
                ],
            }

    return await asyncio.to_thread(_read)


async def create_chat_session(
    client: Any,
    *,
    source: str,
    label: str | None = None,
    agent_backend: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    session_id = uuid4().hex[:16]
    engine = _engine_from(client)
    now = _utc_now()

    record = {
        "id": session_id,
        "label": (label or f"Session {session_id}").strip(),
        "source": source,
        "agent_backend": agent_backend,
        "orchestrator_history": [],
        "messages_rendered": [],
        "updated_at": now.isoformat(),
        "project_id": project_id,
    }

    if engine is None:
        return record

    def _create() -> None:
        with DBSession(engine) as db:
            row = ChatSession(
                id=session_id,
                label=(label or f"Session {session_id}").strip(),
                source=source,
                agent_backend=agent_backend,
                project_id=project_id,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.commit()

    await asyncio.to_thread(_create)
    return record


async def save_chat_session(client: Any, session: dict[str, Any]) -> None:
    """Upsert session metadata and replace its messages from orchestrator_history."""
    session_id = str(session.get("id") or "").strip()
    if not session_id:
        return
    engine = _engine_from(client)
    if engine is None:
        return

    label = str(session.get("label") or f"Session {session_id[:8]}").strip()
    source = str(session.get("source") or "unknown").strip() or "unknown"
    agent_backend = session.get("agent_backend")
    if not isinstance(agent_backend, str) or not agent_backend.strip():
        agent_backend = None
    project_id = session.get("project_id")
    if not isinstance(project_id, str) or not project_id.strip():
        project_id = None

    history: list[list[str]] = []
    for pair in (session.get("orchestrator_history") or []):
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            role = str(pair[0]).strip()
            content = str(pair[1]).strip()
            if role and content:
                history.append([role, content])

    now = _utc_now()

    def _upsert() -> None:
        with DBSession(engine) as db:
            row = db.get(ChatSession, session_id)
            if row is None:
                row = ChatSession(
                    id=session_id,
                    label=label,
                    source=source,
                    agent_backend=agent_backend,
                    project_id=project_id,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.label = label
                row.source = source
                row.agent_backend = agent_backend
                row.project_id = project_id
                row.updated_at = now
                db.add(row)

            # Replace all messages with the current history list
            # (legacy save_chat_session semantics: full overwrite)
            existing = db.exec(
                select(ChatMessage).where(ChatMessage.session_id == session_id)  # type: ignore[arg-type]
            ).all()
            for msg in existing:
                db.delete(msg)

            for role, content in history:
                db.add(
                    ChatMessage(
                        session_id=session_id,
                        role=role,
                        content=content,
                        terminated_at_user_request=False,
                        created_at=now,
                    )
                )
            db.commit()

    await asyncio.to_thread(_upsert)


async def delete_chat_session(client: Any, session_id: str) -> bool:
    normalized_id = session_id.strip()
    if not normalized_id:
        return False
    engine = _engine_from(client)
    if engine is None:
        return False

    def _delete() -> bool:
        with DBSession(engine) as db:
            row = db.get(ChatSession, normalized_id)
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    return await asyncio.to_thread(_delete)


async def append_chat_message(
    client: Any,
    session_id: str,
    role: str,
    content: str,
    *,
    terminated: bool = False,
) -> ChatMessage:
    """Append a single turn to the session and update session.updated_at.

    This is the preferred write path for T3 / streaming completions.
    Returns the persisted ChatMessage instance (detached from DB session).
    """
    normalized_id = session_id.strip()
    engine = _engine_from(client)
    now = _utc_now()

    msg = ChatMessage(
        session_id=normalized_id,
        role=role,
        content=content,
        terminated_at_user_request=terminated,
        created_at=now,
    )

    if engine is None:
        return msg

    def _append() -> ChatMessage:
        with DBSession(engine) as db:
            db.add(msg)
            # Touch updated_at on the parent session
            row = db.get(ChatSession, normalized_id)
            if row is not None:
                row.updated_at = now
                db.add(row)
            db.commit()
            db.refresh(msg)
            return msg

    return await asyncio.to_thread(_append)


async def get_messages_after(
    client: Any,
    session_id: str,
    *,
    after_id: int,
    limit: int = 200,
) -> list[ChatMessage]:
    """Return messages for a session with id > after_id (cursor-tail query).

    Used by the /messages?after_id=N endpoint so reconnecting clients can
    catch up on messages they missed during a /watch disconnect.
    """
    normalized_id = session_id.strip()
    engine = _engine_from(client)
    if engine is None:
        return []

    def _read() -> list[ChatMessage]:
        with DBSession(engine) as db:
            stmt = (
                select(ChatMessage)
                .where(ChatMessage.session_id == normalized_id)  # type: ignore[arg-type]
                .where(ChatMessage.id > after_id)  # type: ignore[operator]
                .order_by(ChatMessage.id)  # type: ignore[attr-defined]
                .limit(limit)
            )
            rows = db.exec(stmt).all()
            # Detach from session before returning
            return [ChatMessage.model_validate(r.model_dump()) for r in rows]

    return await asyncio.to_thread(_read)


# ---------------------------------------------------------------------------
# List helpers (unchanged from legacy)
# ---------------------------------------------------------------------------


def build_chat_session_list_items(
    sessions: list[ChatSessionRecord],
    *,
    current_session_id: str | None = None,
) -> list[ChatSessionListItem]:
    items: list[ChatSessionListItem] = []
    for idx, session in enumerate(sessions, start=1):
        sid = str(session.get("id") or "").strip()
        label = str(session.get("label") or sid).strip() or sid
        source = str(session.get("source") or "unknown").strip() or "unknown"
        agent_backend = session.get("agent_backend")
        backend_value = str(agent_backend).strip() if isinstance(agent_backend, str) else None
        updated_at = str(session.get("updated_at") or "")
        updated_relative = _format_relative_time(updated_at) if updated_at else ""

        items.append(
            ChatSessionListItem(
                index=idx,
                session_id=sid,
                label=label,
                source=source,
                agent_backend=backend_value,
                project_id=session.get("project_id"),
                updated_at=updated_at,
                updated_relative=updated_relative,
                is_current=bool(current_session_id) and sid == current_session_id,
            )
        )
    return items


def resolve_chat_session_selector(
    items: list[ChatSessionListItem],
    query: str | None,
) -> ChatSessionListItem | None:
    if not query:
        return None
    normalized = query.strip()
    if not normalized:
        return None

    if normalized.isdigit():
        index = int(normalized) - 1
        if 0 <= index < len(items):
            return items[index]
        return None

    for item in items:
        if item.session_id == normalized or item.session_id.startswith(normalized):
            return item
    return None


# ---------------------------------------------------------------------------
# Scope / last-session state (unchanged — still lives in settings)
# ---------------------------------------------------------------------------


async def get_last_session_id(client: Any, *, scope: str) -> str | None:
    settings = await client.settings.get()
    value = settings.get(f"{CHAT_LAST_SESSION_PREFIX}{scope}")
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


async def set_last_session_id(client: Any, *, scope: str, session_id: str) -> None:
    normalized = session_id.strip()
    if not normalized:
        return
    await client.settings.set(
        {
            f"{CHAT_LAST_SESSION_PREFIX}{scope}": normalized,
        }
    )


async def get_scope_state(client: Any, *, scope: str) -> dict[str, Any]:
    settings = await client.settings.get()
    raw = settings.get(f"{CHAT_SCOPE_PREFIX}{scope}")
    if not raw:
        return {}
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


async def save_scope_state(client: Any, *, scope: str, state: dict[str, Any]) -> None:
    payload = json.dumps(state, separators=(",", ":"), ensure_ascii=True)
    await client.settings.set({f"{CHAT_SCOPE_PREFIX}{scope}": payload})
