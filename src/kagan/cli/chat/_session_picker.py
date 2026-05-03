"""Pure UI helpers for the chat-session picker (CLI, TUI, server SSE).

These helpers are presentation-only — they do not touch the database.
DB persistence flows through ``client.chat_sessions`` (the ``ChatSessions``
aggregate on :class:`kagan.core.KaganCore`); the UI surfaces consume the
returned rows + messages and feed them through the helpers below to render
session lists / pickers / sidebars.

Phase 6 of refactor R1: extracted from the deleted ``cli.chat.sessions``
shim. The ``ChatSessionListItem`` shape is the contract between the
aggregate and every chat UI in the project (REPL, TUI, web sidebar
formatting, VS Code tree view).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from kagan.core.chat.sessions import format_relative_time

if TYPE_CHECKING:
    from kagan.core.models import ChatMessage, ChatSession

__all__ = [
    "ChatSessionListItem",
    "build_chat_session_list_items",
    "chat_session_to_legacy_dict",
    "resolve_chat_session_selector",
]


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


def chat_session_to_legacy_dict(
    row: ChatSession,
    messages: list[ChatMessage],
) -> dict[str, Any]:
    """Convert a ``(ChatSession, list[ChatMessage])`` pair into the legacy dict shape.

    Several call sites (TUI orchestrator store, server SSE wire mapping, server
    REST shape) consume the dict shape that the deleted ``cli.chat.sessions``
    shim used to return. Rather than rewire every consumer in one phase, this
    helper sits at the boundary of those callers — they call
    ``client.chat_sessions.X`` directly for persistence and convert to dict
    here for display.
    """
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


def build_chat_session_list_items(
    sessions: list[dict[str, Any]],
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
