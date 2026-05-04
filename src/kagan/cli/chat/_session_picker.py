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

from kagan.core.chat.sessions import (
    ChatSessionView,
    chat_session_to_view,
    format_relative_time,
)

__all__ = [
    "ChatSessionListItem",
    "ChatSessionView",
    "build_chat_session_list_items",
    "chat_session_to_view",
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


def build_chat_session_list_items(
    sessions: list[ChatSessionView],
    *,
    current_session_id: str | None = None,
) -> list[ChatSessionListItem]:
    items: list[ChatSessionListItem] = []
    for idx, session in enumerate(sessions, start=1):
        sid = session.id.strip()
        label = session.label.strip() or sid
        source = session.source.strip() or "unknown"
        backend_value = session.agent_backend.strip() if session.agent_backend else None
        updated_at = session.updated_at
        updated_relative = format_relative_time(updated_at) if updated_at else ""

        items.append(
            ChatSessionListItem(
                index=idx,
                session_id=sid,
                label=label,
                source=source,
                agent_backend=backend_value,
                project_id=session.project_id,
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
