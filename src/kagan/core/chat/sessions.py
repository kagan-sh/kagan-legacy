"""ChatSessions aggregate — the only place chat persistence is performed.

Replaces the raw-SQL helpers that used to live in `kagan.cli.chat.sessions`.
Callers now use `client.chat_sessions.X(...)` rather than importing module
functions. Returned types are real SQLModel rows (detached from the DB
session), not the legacy dict shape.
"""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any
from uuid import uuid4

from sqlmodel import Session as DBSession
from sqlmodel import select

from kagan.core.models import ChatMessage, ChatSession, Task
from kagan.core.models import Session as TaskSession

if TYPE_CHECKING:
    import builtins

    from sqlalchemy import Engine

CHAT_SCOPE_PREFIX = "chat_scope_state_"
CHAT_LAST_SESSION_PREFIX = "chat_last_session_"

_SESSION_TITLE_MAX_LENGTH = 80


def _utc_now() -> datetime:
    return datetime.now(UTC)


def format_relative_time(iso_timestamp: str) -> str:
    """Render an ISO timestamp as a 'just now' / '5m ago' / 'yesterday' string."""
    try:
        dt = datetime.fromisoformat(iso_timestamp)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        delta = datetime.now(UTC) - dt
        seconds = int(delta.total_seconds())
        if seconds < 60:
            return "just now"
        if seconds < 3600:
            return f"{seconds // 60}m ago"
        if seconds < 86400:
            return f"{seconds // 3600}h ago"
        days = seconds // 86400
        if days == 1:
            return "yesterday"
        if days < 30:
            return f"{days}d ago"
        return dt.strftime("%b %d")
    except (ValueError, TypeError):
        return ""


def clean_generated_title(raw: str) -> str:
    """Normalize an LLM-generated title: strip <think>, quotes, truncate."""
    cleaned = re.sub(r"<think>[\s\S]*?</think>\s*", "", raw)
    cleaned = cleaned.split("\n")[0].strip()
    if len(cleaned) >= 2 and cleaned[0] in "\"'" and cleaned[-1] == cleaned[0]:
        cleaned = cleaned[1:-1].strip()
    if not cleaned:
        return ""
    if len(cleaned) > _SESSION_TITLE_MAX_LENGTH:
        cleaned = cleaned[: _SESSION_TITLE_MAX_LENGTH - 3] + "..."
    return cleaned


@dataclass(frozen=True, slots=True)
class TaskBinding:
    """A `task-session` source resolves to an agent-Session row, not a chat session."""

    id: str
    label: str
    source: str
    agent_backend: str | None
    task_id: str
    status: str


def _detached(row: Any) -> Any:
    """Return a copy of a SQLModel row that is safe to use after the DB session closes."""
    if row is None:
        return None
    return type(row).model_validate(row.model_dump())


class ChatSessions:
    """Aggregate for `chat_sessions` and `chat_messages`.

    All writes go through this class; `cli.chat.sessions` raw functions are
    gone. The aggregate exposes async methods that wrap a thread-pooled DB
    session — same convention as `Tasks`, `Sessions`, `Projects`.
    """

    def __init__(self, engine: Engine, settings_ns: Any) -> None:
        self._engine = engine
        self._settings = settings_ns

    # ------------------------------------------------------------------ list

    async def list(
        self,
        *,
        source: str | None = None,
        project_id: str | None = None,
    ) -> list[ChatSession]:
        def _read() -> list[ChatSession]:
            with DBSession(self._engine) as db:
                stmt = select(ChatSession)
                if source is not None:
                    stmt = stmt.where(ChatSession.source == source)  # type: ignore[arg-type]
                if project_id is not None:
                    stmt = stmt.where(ChatSession.project_id == project_id)  # type: ignore[arg-type]
                stmt = stmt.order_by(ChatSession.updated_at.desc())  # type: ignore[attr-defined]
                rows = db.exec(stmt).all()
                return [_detached(r) for r in rows]

        return await asyncio.to_thread(_read)

    # ------------------------------------------------------------------ get

    async def get(self, session_id: str) -> ChatSession | None:
        normalized = session_id.strip()
        if not normalized:
            return None

        def _read() -> ChatSession | None:
            with DBSession(self._engine) as db:
                row = db.get(ChatSession, normalized)
                return _detached(row) if row is not None else None

        return await asyncio.to_thread(_read)

    # ------------------------------------------------------------------ history

    async def history(self, session_id: str) -> builtins.list[ChatMessage]:
        """Full ordered message list for a session."""
        normalized = session_id.strip()
        if not normalized:
            return []

        def _read() -> list[ChatMessage]:
            with DBSession(self._engine) as db:
                rows = db.exec(
                    select(ChatMessage)
                    .where(ChatMessage.session_id == normalized)  # type: ignore[arg-type]
                    .order_by(ChatMessage.id)  # type: ignore[attr-defined]
                ).all()
                return [_detached(r) for r in rows]

        return await asyncio.to_thread(_read)

    async def messages_after(
        self,
        session_id: str,
        *,
        after_id: int,
        limit: int = 200,
    ) -> builtins.list[ChatMessage]:
        """Cursor-tail query: return messages with id > after_id."""
        normalized = session_id.strip()
        if not normalized:
            return []

        def _read() -> list[ChatMessage]:
            with DBSession(self._engine) as db:
                stmt = (
                    select(ChatMessage)
                    .where(ChatMessage.session_id == normalized)  # type: ignore[arg-type]
                    .where(ChatMessage.id > after_id)  # type: ignore[operator]
                    .order_by(ChatMessage.id)  # type: ignore[attr-defined]
                    .limit(limit)
                )
                return [_detached(r) for r in db.exec(stmt).all()]

        return await asyncio.to_thread(_read)

    # ------------------------------------------------------------------ create

    async def create(
        self,
        *,
        source: str,
        label: str | None = None,
        agent_backend: str | None = None,
        project_id: str | None = None,
        session_id: str | None = None,
    ) -> ChatSession:
        sid = (session_id or uuid4().hex[:16]).strip()
        now = _utc_now()
        row = ChatSession(
            id=sid,
            label=(label or f"Session {sid}").strip(),
            source=source,
            agent_backend=agent_backend,
            project_id=project_id,
            created_at=now,
            updated_at=now,
        )

        def _write() -> ChatSession:
            with DBSession(self._engine) as db:
                db.add(row)
                db.commit()
                db.refresh(row)
                return _detached(row)

        return await asyncio.to_thread(_write)

    # ------------------------------------------------------------------ update

    async def update(
        self,
        session_id: str,
        *,
        label: str | None = None,
        agent_backend: str | None = None,
        project_id: str | None = None,
    ) -> ChatSession | None:
        """Patch metadata on an existing session. Returns the updated row, or None if missing."""
        normalized = session_id.strip()
        now = _utc_now()

        def _write() -> ChatSession | None:
            with DBSession(self._engine) as db:
                row = db.get(ChatSession, normalized)
                if row is None:
                    return None
                if label is not None:
                    row.label = label.strip() or row.label
                if agent_backend is not None:
                    row.agent_backend = agent_backend
                if project_id is not None:
                    row.project_id = project_id
                row.updated_at = now
                db.add(row)
                db.commit()
                db.refresh(row)
                return _detached(row)

        return await asyncio.to_thread(_write)

    async def touch(self, session_id: str) -> None:
        """Bump `updated_at` to now."""
        normalized = session_id.strip()
        now = _utc_now()

        def _write() -> None:
            with DBSession(self._engine) as db:
                row = db.get(ChatSession, normalized)
                if row is None:
                    return
                row.updated_at = now
                db.add(row)
                db.commit()

        await asyncio.to_thread(_write)

    # ------------------------------------------------------------------ delete

    async def delete(self, session_id: str) -> bool:
        normalized = session_id.strip()

        def _write() -> bool:
            with DBSession(self._engine) as db:
                row = db.get(ChatSession, normalized)
                if row is None:
                    return False
                db.delete(row)
                db.commit()
                return True

        return await asyncio.to_thread(_write)

    # ------------------------------------------------------------------ messages

    async def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        terminated: bool = False,
    ) -> ChatMessage:
        """Append a single message. Touches `updated_at` on the parent row."""
        normalized = session_id.strip()
        now = _utc_now()
        msg = ChatMessage(
            session_id=normalized,
            role=role,
            content=content,
            terminated_at_user_request=terminated,
            created_at=now,
        )

        def _write() -> ChatMessage:
            with DBSession(self._engine) as db:
                db.add(msg)
                row = db.get(ChatSession, normalized)
                if row is not None:
                    row.updated_at = now
                    db.add(row)
                db.commit()
                db.refresh(msg)
                return _detached(msg)

        return await asyncio.to_thread(_write)

    async def replace_history(
        self,
        session_id: str,
        history: builtins.list[tuple[str, str]],
    ) -> None:
        """Replace the entire message list for a session.

        Used by the legacy CLI `save_chat_session` codepath and the TUI
        orchestrator session blob. New code should `append_message` instead —
        this exists only because the CLI reconstructs history from
        `_chat_history` every turn. Will be removed once the CLI migrates to
        ChatEngine.
        """
        normalized = session_id.strip()
        if not normalized:
            return
        now = _utc_now()

        def _write() -> None:
            with DBSession(self._engine) as db:
                row = db.get(ChatSession, normalized)
                if row is None:
                    return
                row.updated_at = now
                db.add(row)
                existing = db.exec(
                    select(ChatMessage).where(ChatMessage.session_id == normalized)  # type: ignore[arg-type]
                ).all()
                for m in existing:
                    db.delete(m)
                for role, content in history:
                    db.add(
                        ChatMessage(
                            session_id=normalized,
                            role=role,
                            content=content,
                            terminated_at_user_request=False,
                            created_at=now,
                        )
                    )
                db.commit()

        await asyncio.to_thread(_write)

    # ------------------------------------------------------------------ task binding

    async def resolve_task_binding(self, session_id: str) -> TaskBinding | None:
        """Resolve a `task-session` source: the id refers to an agent-Session row."""
        normalized = session_id.strip()
        if not normalized:
            return None

        def _read() -> TaskBinding | None:
            with DBSession(self._engine) as db:
                bound = db.get(TaskSession, normalized)
                if bound is None:
                    return None
                task = db.get(Task, bound.task_id)
                if task is None:
                    return None
                status_value = getattr(bound.status, "value", str(bound.status))
                return TaskBinding(
                    id=bound.id,
                    label=f"Task {task.id[:8]} - {task.title}",
                    source="task-session",
                    agent_backend=bound.agent_backend,
                    task_id=task.id,
                    status=status_value,
                )

        return await asyncio.to_thread(_read)

    # ------------------------------------------------------------------ scope state

    async def get_last_session_id(self, *, scope: str) -> str | None:
        settings = await self._settings.get()
        value = settings.get(f"{CHAT_LAST_SESSION_PREFIX}{scope}")
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    async def set_last_session_id(self, *, scope: str, session_id: str) -> None:
        normalized = session_id.strip()
        if not normalized:
            return
        await self._settings.set({f"{CHAT_LAST_SESSION_PREFIX}{scope}": normalized})

    async def get_scope_state(self, *, scope: str) -> dict[str, Any]:
        settings = await self._settings.get()
        raw = settings.get(f"{CHAT_SCOPE_PREFIX}{scope}")
        if not raw:
            return {}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return payload if isinstance(payload, dict) else {}

    async def save_scope_state(self, *, scope: str, state: dict[str, Any]) -> None:
        payload = json.dumps(state, separators=(",", ":"), ensure_ascii=True)
        await self._settings.set({f"{CHAT_SCOPE_PREFIX}{scope}": payload})
