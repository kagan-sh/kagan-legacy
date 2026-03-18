import asyncio
from collections.abc import Sequence
from typing import Any

from kagan.chat._title import ensure_session_title, is_default_title
from kagan.chat.sessions import (
    build_chat_session_list_items,
    create_chat_session,
    get_chat_session,
    get_last_session_id,
    list_chat_sessions,
    save_chat_session,
    set_last_session_id,
)
from kagan.core.enums import SessionKind

_TUI_ORCHESTRATOR_SOURCE = "tui-orchestrator"
_TUI_ORCHESTRATOR_SCOPE = "tui-orchestrator"
_ORCHESTRATOR_KEY_PREFIX = "orchestrator:"


def is_orchestrator_session_key(key: str) -> bool:
    return key == SessionKind.ORCHESTRATOR or key.startswith(_ORCHESTRATOR_KEY_PREFIX)


class TuiOrchestratorSessionStore:
    def __init__(self, client: Any, *, startup_session_id: str | None = None) -> None:
        self._client = client
        self._startup_session_id = startup_session_id.strip() if startup_session_id else None
        self._loaded = False
        self._lock = asyncio.Lock()
        self._sessions_by_key: dict[str, dict[str, Any]] = {}
        self._active_key: str | None = None

    async def ensure_loaded(self) -> None:
        if self._loaded:
            return
        async with self._lock:
            if self._loaded:
                return

            sessions = await list_chat_sessions(self._client)
            selected = await self._resolve_initial_session(sessions)
            if selected is None:
                selected = await create_chat_session(
                    self._client,
                    source=_TUI_ORCHESTRATOR_SOURCE,
                    label="TUI session",
                )
                sessions.append(selected)

            self._sessions_by_key = {
                self._session_key(str(session.get("id") or "")): session
                for session in sessions
                if str(session.get("id") or "").strip()
            }
            self._active_key = self._session_key(str(selected.get("id") or ""))
            await set_last_session_id(
                self._client,
                scope=_TUI_ORCHESTRATOR_SCOPE,
                session_id=str(selected.get("id") or ""),
            )
            self._loaded = True

    async def switch(self, key: str) -> list[tuple[str, str]]:
        await self.ensure_loaded()
        session = self._sessions_by_key.get(key)
        if session is None:
            return self.active_history()
        self._active_key = key
        await set_last_session_id(
            self._client,
            scope=_TUI_ORCHESTRATOR_SCOPE,
            session_id=str(session.get("id") or ""),
        )
        return self._normalize_history(session.get("orchestrator_history") or [])

    async def create_new(self, *, agent_backend: str | None = None) -> str:
        await self.ensure_loaded()
        created = await create_chat_session(
            self._client,
            source=_TUI_ORCHESTRATOR_SOURCE,
            label="TUI session",
            agent_backend=agent_backend,
        )
        key = self._session_key(str(created.get("id") or ""))
        self._sessions_by_key[key] = created
        self._active_key = key
        await set_last_session_id(
            self._client,
            scope=_TUI_ORCHESTRATOR_SCOPE,
            session_id=str(created.get("id") or ""),
        )
        return key

    async def persist_active(
        self,
        *,
        history: Sequence[tuple[str, str]],
        rendered_messages: Sequence[str],
        agent_backend: str | None,
    ) -> None:
        await self.ensure_loaded()
        if self._active_key is None:
            return
        session = self._sessions_by_key.get(self._active_key)
        if session is None:
            return

        session_id = str(session.get("id") or "").strip()
        if not session_id:
            return

        label = str(session.get("label") or f"TUI session {session_id}").strip()
        normalized = {
            "id": session_id,
            "label": label,
            "source": str(session.get("source") or _TUI_ORCHESTRATOR_SOURCE),
            "agent_backend": agent_backend or session.get("agent_backend"),
            "orchestrator_history": [[role, content] for role, content in history],
            "messages_rendered": [line for line in rendered_messages if line.strip()],
        }
        await save_chat_session(self._client, normalized)
        self._sessions_by_key[self._active_key] = normalized
        await set_last_session_id(
            self._client,
            scope=_TUI_ORCHESTRATOR_SCOPE,
            session_id=session_id,
        )

    def options(self) -> list[tuple[str, str]]:
        if not self._sessions_by_key:
            return [("Orchestrator", "orchestrator")]

        sessions = list(self._sessions_by_key.values())
        current_id = self.current_session_id()
        items = build_chat_session_list_items(sessions, current_session_id=current_id)
        options: list[tuple[str, str]] = []
        for item in items:
            label = f"{item.label} [{item.session_id}]"
            options.append((label, self._session_key(item.session_id)))
        return options

    def active_key(self) -> str:
        return self._active_key or "orchestrator"

    def active_history(self) -> list[tuple[str, str]]:
        key = self.active_key()
        return self.history_for_key(key)

    def history_for_key(self, key: str) -> list[tuple[str, str]]:
        session = self._sessions_by_key.get(key)
        if session is None:
            return []
        return self._normalize_history(session.get("orchestrator_history") or [])

    def should_generate_title(self, key: str | None = None) -> bool:
        target = key or self.active_key()
        session = self._sessions_by_key.get(target)
        if session is None:
            return False
        return is_default_title(str(session.get("label") or ""))

    async def generate_title(
        self,
        *,
        user_message: str,
        assistant_reply: str,
        agent_backend: str,
        key: str | None = None,
    ) -> str | None:
        target = key or self.active_key()
        session = self._sessions_by_key.get(target)
        if session is None:
            return None
        title = await ensure_session_title(
            self._client,
            session,
            user_message=user_message,
            assistant_reply=assistant_reply,
            agent_backend=agent_backend,
        )
        if title:
            self._sessions_by_key[target] = session
        return title

    def agent_backend_for_key(self, key: str) -> str | None:
        session = self._sessions_by_key.get(key)
        if session is None:
            return None
        backend = session.get("agent_backend")
        if isinstance(backend, str) and backend.strip():
            return backend
        return None

    def current_session_id(self) -> str | None:
        key = self.active_key()
        if key.startswith(_ORCHESTRATOR_KEY_PREFIX):
            return key.removeprefix(_ORCHESTRATOR_KEY_PREFIX)
        return None

    async def _resolve_initial_session(
        self, sessions: Sequence[dict[str, Any]]
    ) -> dict[str, Any] | None:
        if self._startup_session_id:
            explicit = await get_chat_session(self._client, self._startup_session_id)
            self._startup_session_id = None
            if explicit is not None:
                return explicit

        last_session_id = await get_last_session_id(self._client, scope=_TUI_ORCHESTRATOR_SCOPE)
        if last_session_id:
            for session in sessions:
                if str(session.get("id") or "") == last_session_id:
                    return session

        if sessions:
            return sessions[-1]
        return None

    @staticmethod
    def _session_key(session_id: str) -> str:
        normalized = session_id.strip()
        if not normalized:
            return "orchestrator"
        return f"{_ORCHESTRATOR_KEY_PREFIX}{normalized}"

    @staticmethod
    def _normalize_history(raw_history: Sequence[Any]) -> list[tuple[str, str]]:
        history: list[tuple[str, str]] = []
        for entry in raw_history:
            if not isinstance(entry, list | tuple) or len(entry) != 2:
                continue
            role = str(entry[0]).strip()
            content = str(entry[1]).strip()
            if role and content:
                history.append((role, content))
        return history
