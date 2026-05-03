"""Legacy chat-session module — thin shim over `client.chat_sessions`.

The single source of truth for chat-session persistence is now
`kagan.core.chat.ChatSessions` (aggregate on `KaganCore.chat_sessions`).
The functions below remain as a *transitional* compatibility surface so
existing callers in CLI/TUI/server keep working while R1 migrates them.

New code MUST use `client.chat_sessions.X(...)` directly. Importing functions
from this module is deprecated and will be removed in the next R1 commit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from kagan.core.chat.sessions import (
    CHAT_LAST_SESSION_PREFIX,
    CHAT_SCOPE_PREFIX,
    clean_generated_title,
    format_relative_time,
)
from kagan.core.models import ChatMessage, ChatSession

# Re-export for backwards compatibility — tests reach into private helpers
_clean_generated_title = clean_generated_title
_format_relative_time = format_relative_time

__all__ = [
    "CHAT_LAST_SESSION_PREFIX",
    "CHAT_SCOPE_PREFIX",
    "ChatSessionListItem",
    "ChatSessionRecord",
    "_clean_generated_title",
    "_format_relative_time",
    "append_chat_message",
    "build_chat_session_list_items",
    "create_chat_session",
    "delete_chat_session",
    "get_chat_session",
    "get_last_session_id",
    "get_messages_after",
    "get_scope_state",
    "list_chat_sessions",
    "resolve_chat_session_selector",
    "resolve_task_session_binding",
    "save_chat_session",
    "save_scope_state",
    "set_last_session_id",
]

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
# Legacy dict-shape conversion
# ---------------------------------------------------------------------------


def _row_to_dict(row: ChatSession, messages: list[ChatMessage]) -> dict[str, Any]:
    history = [[m.role, m.content] for m in messages]
    updated_at = (
        row.updated_at.isoformat() if isinstance(row.updated_at, datetime) else str(row.updated_at)
    )
    return {
        "id": row.id,
        "label": row.label,
        "source": row.source,
        "agent_backend": row.agent_backend,
        "orchestrator_history": history,
        "messages_rendered": [],
        "updated_at": updated_at,
        "project_id": row.project_id,
    }


def _aggregate(client: Any) -> Any:
    """Return the ChatSessions aggregate, or None for null clients.

    Falls back to constructing one from `client._engine` + `client.settings`
    so test fakes that only expose those two attributes keep working until
    they migrate to the real `KaganCore`.
    """
    cs = getattr(client, "chat_sessions", None)
    if cs is not None:
        return cs
    engine = getattr(client, "_engine", None)
    if engine is None:
        return None
    settings = getattr(client, "settings", None)
    if settings is None:
        return None
    from kagan.core.chat import ChatSessions

    return ChatSessions(engine, settings)


# ---------------------------------------------------------------------------
# Read API
# ---------------------------------------------------------------------------


async def list_chat_sessions(
    client: Any, *, source: str | None = None, project_id: str | None = None
) -> list[dict[str, Any]]:
    cs = _aggregate(client)
    if cs is None:
        return []
    pairs = await cs.list_with_history(source=source, project_id=project_id)
    return [_row_to_dict(row, msgs) for row, msgs in pairs]


async def get_chat_session(client: Any, session_id: str) -> dict[str, Any] | None:
    cs = _aggregate(client)
    if cs is None:
        return None
    pair = await cs.get_with_history(session_id)
    if pair is None:
        return None
    row, msgs = pair
    return _row_to_dict(row, msgs)


async def resolve_task_session_binding(client: Any, session_id: str) -> dict[str, Any] | None:
    cs = _aggregate(client)
    if cs is None:
        return None
    binding = await cs.resolve_task_binding(session_id)
    if binding is None:
        return None
    return {
        "id": binding.id,
        "label": binding.label,
        "source": binding.source,
        "agent_backend": binding.agent_backend,
        "orchestrator_history": [],
        "messages_rendered": [
            f"System: Attached to task session {binding.id} (status: {binding.status})."
        ],
    }


async def get_messages_after(
    client: Any,
    session_id: str,
    *,
    after_id: int,
    limit: int = 200,
) -> list[ChatMessage]:
    cs = _aggregate(client)
    if cs is None:
        return []
    return await cs.messages_after(session_id, after_id=after_id, limit=limit)


# ---------------------------------------------------------------------------
# Write API
# ---------------------------------------------------------------------------


async def create_chat_session(
    client: Any,
    *,
    source: str,
    label: str | None = None,
    agent_backend: str | None = None,
    project_id: str | None = None,
) -> dict[str, Any]:
    cs = _aggregate(client)
    if cs is None:
        # Null-client path used by tests with no DB
        from datetime import UTC
        from uuid import uuid4

        sid = uuid4().hex[:16]
        return {
            "id": sid,
            "label": (label or f"Session {sid}").strip(),
            "source": source,
            "agent_backend": agent_backend,
            "orchestrator_history": [],
            "messages_rendered": [],
            "updated_at": datetime.now(UTC).isoformat(),
            "project_id": project_id,
        }
    row = await cs.create(
        source=source, label=label, agent_backend=agent_backend, project_id=project_id
    )
    return _row_to_dict(row, [])


async def save_chat_session(client: Any, session: dict[str, Any]) -> None:
    """Upsert metadata + replace history (legacy semantics — overwrite-all).

    Single transaction via `cs.upsert_with_history` so a concurrent delete
    cannot race between metadata write and history replacement.
    """
    cs = _aggregate(client)
    if cs is None:
        return

    session_id = str(session.get("id") or "").strip()
    if not session_id:
        return

    label = str(session.get("label") or f"Session {session_id[:8]}").strip()
    source = str(session.get("source") or "unknown").strip() or "unknown"
    raw_backend = session.get("agent_backend")
    agent_backend: str | None = (
        raw_backend if isinstance(raw_backend, str) and raw_backend.strip() else None
    )
    raw_project = session.get("project_id")
    project_id: str | None = (
        raw_project if isinstance(raw_project, str) and raw_project.strip() else None
    )

    history: list[tuple[str, str]] = []
    for pair in session.get("orchestrator_history") or []:
        if isinstance(pair, (list, tuple)) and len(pair) == 2:
            role = str(pair[0]).strip()
            content = str(pair[1]).strip()
            if role and content:
                history.append((role, content))

    await cs.upsert_with_history(
        session_id,
        label=label,
        source=source,
        agent_backend=agent_backend,
        project_id=project_id,
        history=history,
    )


async def delete_chat_session(client: Any, session_id: str) -> bool:
    cs = _aggregate(client)
    if cs is None:
        return False
    return await cs.delete(session_id)


async def append_chat_message(
    client: Any,
    session_id: str,
    role: str,
    content: str,
    *,
    terminated: bool = False,
) -> ChatMessage:
    cs = _aggregate(client)
    if cs is None:
        from datetime import UTC

        return ChatMessage(
            session_id=session_id.strip(),
            role=role,
            content=content,
            terminated_at_user_request=terminated,
            created_at=datetime.now(UTC),
        )
    return await cs.append_message(session_id, role, content, terminated=terminated)


# ---------------------------------------------------------------------------
# UI helpers — pure, no DB
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
        updated_relative = format_relative_time(updated_at) if updated_at else ""

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
# Scope / last-session state — delegate to aggregate
# ---------------------------------------------------------------------------


async def get_last_session_id(client: Any, *, scope: str) -> str | None:
    cs = _aggregate(client)
    if cs is None:
        return None
    return await cs.get_last_session_id(scope=scope)


async def set_last_session_id(client: Any, *, scope: str, session_id: str) -> None:
    cs = _aggregate(client)
    if cs is None:
        return
    await cs.set_last_session_id(scope=scope, session_id=session_id)


async def get_scope_state(client: Any, *, scope: str) -> dict[str, Any]:
    cs = _aggregate(client)
    if cs is None:
        return {}
    return await cs.get_scope_state(scope=scope)


async def save_scope_state(client: Any, *, scope: str, state: dict[str, Any]) -> None:
    cs = _aggregate(client)
    if cs is None:
        return
    await cs.save_scope_state(scope=scope, state=state)
