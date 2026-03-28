"""Session CRUD, history normalization, and persistence constants."""

import asyncio
import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from sqlmodel import Session as DBSession

from kagan.core.models import Session as TaskSession
from kagan.core.models import Task

CHAT_SESSIONS_SETTING_KEY = "chat_sessions_v1"
CHAT_SCOPE_PREFIX = "chat_scope_state_"
CHAT_LAST_SESSION_PREFIX = "chat_last_session_"
CHAT_LAST_ACTIVE_SESSION_KEY = "chat_last_active_session"
MAX_STORED_SESSIONS = 30
MAX_STORED_MESSAGES = 300
MAX_STORED_HISTORY = 120
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


def _utc_now() -> str:
    return datetime.now(UTC).isoformat()


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


def _normalize_history(value: Any) -> list[list[str]]:
    if not isinstance(value, list):
        return []
    normalized: list[list[str]] = []
    for item in value:
        if not isinstance(item, list | tuple) or len(item) != 2:
            continue
        role = str(item[0]).strip()
        text = str(item[1]).strip()
        if not role or not text:
            continue
        normalized.append([role, text])
    return normalized[-MAX_STORED_HISTORY:]


def _normalize_rendered_messages(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    messages = [str(item).rstrip() for item in value if str(item).strip()]
    return messages[-MAX_STORED_MESSAGES:]


def _normalize_session(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None
    session_id = str(raw.get("id") or "").strip()
    if not session_id:
        return None
    label = str(raw.get("label") or f"Session {session_id[:8]}").strip()
    source = str(raw.get("source") or "unknown").strip() or "unknown"
    agent_backend = raw.get("agent_backend")
    backend_value = str(agent_backend).strip() if isinstance(agent_backend, str) else None
    updated_at = str(raw.get("updated_at") or _utc_now())
    return {
        "id": session_id,
        "label": label,
        "source": source,
        "agent_backend": backend_value,
        "orchestrator_history": _normalize_history(raw.get("orchestrator_history")),
        "messages_rendered": _normalize_rendered_messages(raw.get("messages_rendered")),
        "updated_at": updated_at,
        "project_id": raw.get("project_id"),
    }


def _normalize_sessions_collection(value: Any) -> list[ChatSessionRecord]:
    if not isinstance(value, list):
        return []

    sessions: list[ChatSessionRecord] = []
    for item in value:
        normalized = _normalize_session(item)
        if normalized is not None:
            sessions.append(normalized)

    sessions.sort(key=lambda item: str(item.get("updated_at") or ""), reverse=True)

    unique: list[ChatSessionRecord] = []
    seen: set[str] = set()
    for session in sessions:
        session_id = session["id"]
        if session_id in seen:
            continue
        seen.add(session_id)
        unique.append(session)

    return unique[:MAX_STORED_SESSIONS]


def _parse_sessions_blob(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, dict):
        return []
    sessions_raw = payload.get("sessions")
    if not isinstance(sessions_raw, list):
        return []

    return _normalize_sessions_collection(sessions_raw)


def _serialize_sessions_blob(sessions: list[dict[str, Any]]) -> str:
    normalized = _normalize_sessions_collection(sessions)
    payload = {"version": 1, "sessions": normalized}
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def build_chat_session_list_items(
    sessions: Sequence[ChatSessionRecord],
    *,
    current_session_id: str | None = None,
) -> list[ChatSessionListItem]:
    normalized = _normalize_sessions_collection(list(sessions))
    items: list[ChatSessionListItem] = []
    for idx, session in enumerate(normalized, start=1):
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
    items: Sequence[ChatSessionListItem],
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


async def list_chat_sessions(
    client: Any, *, source: str | None = None, project_id: str | None = None
) -> list[dict[str, Any]]:
    settings = await client.settings.get()
    sessions = _parse_sessions_blob(settings.get(CHAT_SESSIONS_SETTING_KEY))
    if source is not None:
        sessions = [s for s in sessions if s.get("source") == source]
    if project_id is not None:
        sessions = [s for s in sessions if s.get("project_id") == project_id]
    return sessions


async def get_chat_session(client: Any, session_id: str) -> dict[str, Any] | None:
    normalized_id = session_id.strip()
    if not normalized_id:
        return None
    sessions = await list_chat_sessions(client)
    for session in sessions:
        if session.get("id") == normalized_id:
            return session
    return None


async def resolve_task_session_binding(client: Any, session_id: str) -> dict[str, Any] | None:
    normalized_id = session_id.strip()
    if not normalized_id:
        return None

    engine = getattr(client, "_engine", None)
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
    session_id = uuid4().hex[:8]
    session = {
        "id": session_id,
        "label": (label or f"Session {session_id}").strip(),
        "source": source,
        "agent_backend": agent_backend,
        "orchestrator_history": [],
        "messages_rendered": [],
        "updated_at": _utc_now(),
        "project_id": project_id,
    }
    await save_chat_session(client, session)
    return session


async def save_chat_session(client: Any, session: dict[str, Any]) -> None:
    normalized = _normalize_session(session)
    if normalized is None:
        return
    normalized["updated_at"] = _utc_now()
    sessions = await list_chat_sessions(client)
    merged = [item for item in sessions if item.get("id") != normalized["id"]]
    merged.append(normalized)
    await client.settings.set(
        {
            CHAT_SESSIONS_SETTING_KEY: _serialize_sessions_blob(merged),
            CHAT_LAST_ACTIVE_SESSION_KEY: normalized["id"],
        }
    )


async def delete_chat_session(client: Any, session_id: str) -> bool:
    normalized_id = session_id.strip()
    if not normalized_id:
        return False
    sessions = await list_chat_sessions(client)
    filtered = [s for s in sessions if s.get("id") != normalized_id]
    if len(filtered) == len(sessions):
        return False
    await client.settings.set(
        {
            CHAT_SESSIONS_SETTING_KEY: _serialize_sessions_blob(filtered),
            CHAT_LAST_ACTIVE_SESSION_KEY: str(filtered[0].get("id") or "") if filtered else "",
        }
    )
    return True


async def get_last_active_session_id(client: Any) -> str | None:
    settings = await client.settings.get()
    value = settings.get(CHAT_LAST_ACTIVE_SESSION_KEY)
    if value is None:
        return None
    normalized = value.strip()
    return normalized or None


async def get_last_session_id(client: Any, *, scope: str) -> str | None:
    settings = await client.settings.get()
    value = settings.get(f"{CHAT_LAST_SESSION_PREFIX}{scope}")
    if value is not None:
        normalized = value.strip()
        if normalized:
            return normalized
    return await get_last_active_session_id(client)


async def set_last_session_id(client: Any, *, scope: str, session_id: str) -> None:
    normalized = session_id.strip()
    if not normalized:
        return
    await client.settings.set(
        {
            f"{CHAT_LAST_SESSION_PREFIX}{scope}": normalized,
            CHAT_LAST_ACTIVE_SESSION_KEY: normalized,
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
