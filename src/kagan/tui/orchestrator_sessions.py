import asyncio
from collections.abc import Sequence
from typing import Any

from kagan.cli.chat._session_picker import (
    ChatSessionListItem,
    build_chat_session_list_items,
    chat_session_to_legacy_dict,
)
from kagan.cli.chat._title import ensure_session_title, is_default_title
from kagan.core.enums import SessionKind

_TUI_ORCHESTRATOR_SOURCE = "tui-orchestrator"
_TUI_ORCHESTRATOR_SCOPE = "tui-orchestrator"
_ORCHESTRATOR_KEY_PREFIX = "orchestrator:"


def is_orchestrator_session_key(key: str) -> bool:
    return key == SessionKind.ORCHESTRATOR or key.startswith(_ORCHESTRATOR_KEY_PREFIX)


class TuiOrchestratorSessionStore:
    """TUI-only cache + UX state on top of ``client.chat_sessions``.

    Owns the **transient** TUI bits that don't fit on the core aggregate:

    * the in-memory cache of session dicts the picker renders without a DB
      round-trip on every keystroke,
    * the ``active_key`` pointer driven by the session switcher,
    * the per-source rendering helpers (``(cli)`` / ``(web)`` badges),
    * the title-generation kick-off cadence.

    Persistence flows through ``client.chat_sessions`` directly. The dict
    shape returned to ``ChatPanel.set_sessions`` is built locally via
    :func:`chat_session_to_legacy_dict` rather than imported from the
    deleted ``cli.chat.sessions`` shim.
    """

    def __init__(self, client: Any, *, startup_session_id: str | None = None) -> None:
        self._client = client
        self._startup_session_id = startup_session_id.strip() if startup_session_id else None
        self._loaded = False
        self._loaded_project_id: str | None = None
        self._lock = asyncio.Lock()
        self._sessions_by_key: dict[str, dict[str, Any]] = {}
        self._active_key: str | None = None

    def _current_project_id(self) -> str | None:
        project_id = getattr(self._client, "active_project_id", None)
        if not isinstance(project_id, str):
            return None
        normalized = project_id.strip()
        return normalized or None

    async def ensure_loaded(self) -> None:
        current_project_id = self._current_project_id()
        if self._loaded and self._loaded_project_id == current_project_id:
            return
        async with self._lock:
            current_project_id = self._current_project_id()
            if self._loaded and self._loaded_project_id == current_project_id:
                return

            if current_project_id is None:
                self._sessions_by_key = {}
                self._active_key = None
                self._loaded = True
                self._loaded_project_id = None
                return

            pairs = await self._client.chat_sessions.list_with_history(
                project_id=current_project_id,
            )
            sessions = [chat_session_to_legacy_dict(row, msgs) for row, msgs in pairs]
            selected = await self._resolve_initial_session(sessions, project_id=current_project_id)
            if selected is None:
                row = await self._client.chat_sessions.create(
                    source=_TUI_ORCHESTRATOR_SOURCE,
                    label="TUI session",
                    project_id=current_project_id,
                )
                selected = chat_session_to_legacy_dict(row, [])
                sessions.append(selected)

            self._sessions_by_key = {
                self._session_key(str(session.get("id") or "")): session
                for session in sessions
                if str(session.get("id") or "").strip()
            }
            self._active_key = self._session_key(str(selected.get("id") or ""))
            await self._client.chat_sessions.set_last_session_id(
                scope=_TUI_ORCHESTRATOR_SCOPE,
                session_id=str(selected.get("id") or ""),
            )
            self._loaded = True
            self._loaded_project_id = current_project_id

    async def switch(self, key: str) -> list[tuple[str, str]]:
        await self.ensure_loaded()
        session = self._sessions_by_key.get(key)
        if session is None:
            return self.active_history()
        self._active_key = key
        await self._client.chat_sessions.set_last_session_id(
            scope=_TUI_ORCHESTRATOR_SCOPE,
            session_id=str(session.get("id") or ""),
        )
        return self._normalize_history(session.get("orchestrator_history") or [])

    async def create_new(self, *, agent_backend: str | None = None) -> str:
        await self.ensure_loaded()
        project_id = self._current_project_id()
        if project_id is None:
            return self.active_key()
        row = await self._client.chat_sessions.create(
            source=_TUI_ORCHESTRATOR_SOURCE,
            label="TUI session",
            agent_backend=agent_backend,
            project_id=project_id,
        )
        created = chat_session_to_legacy_dict(row, [])
        key = self._session_key(str(created.get("id") or ""))
        self._sessions_by_key[key] = created
        self._active_key = key
        await self._client.chat_sessions.set_last_session_id(
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
            "project_id": self._current_project_id() or session.get("project_id"),
        }
        history_pairs: list[tuple[str, str]] = [
            (str(role), str(content))
            for role, content in (
                pair
                for pair in (normalized.get("orchestrator_history") or [])
                if isinstance(pair, list | tuple) and len(pair) == 2
            )
            if str(role).strip() and str(content).strip()
        ]
        raw_backend = normalized.get("agent_backend")
        backend_value: str | None = (
            raw_backend if isinstance(raw_backend, str) and raw_backend.strip() else None
        )
        raw_project = normalized.get("project_id")
        project_value: str | None = (
            raw_project if isinstance(raw_project, str) and raw_project.strip() else None
        )
        await self._client.chat_sessions.upsert_with_history(
            session_id,
            label=label,
            source=str(normalized.get("source") or _TUI_ORCHESTRATOR_SOURCE),
            agent_backend=backend_value,
            project_id=project_value,
            history=history_pairs,
        )
        self._sessions_by_key[self._active_key] = normalized
        await self._client.chat_sessions.set_last_session_id(
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
            backend_tag = f" · {item.agent_backend}" if getattr(item, "agent_backend", None) else ""
            source_tag = self._source_badge(item.source)
            label = f"{item.label} [{item.session_id}]{backend_tag}{source_tag}"
            options.append((label, self._session_key(item.session_id)))
        return options

    @staticmethod
    def _source_badge(source: str) -> str:
        normalized = source.strip().casefold()
        if normalized == "repl":
            return " (cli)"
        if normalized == "web":
            return " (web)"
        return ""

    def list_items(self) -> list[ChatSessionListItem]:
        if not self._sessions_by_key:
            return []
        current_id = self.current_session_id()
        return build_chat_session_list_items(
            list(self._sessions_by_key.values()),
            current_session_id=current_id,
        )

    async def reload(self) -> None:
        active_session_id = self.current_session_id()
        self._loaded = False
        self._loaded_project_id = None
        self._sessions_by_key = {}
        self._active_key = None
        if active_session_id:
            self._startup_session_id = active_session_id
        await self.ensure_loaded()

    async def delete(self, key: str) -> str | None:
        await self.ensure_loaded()
        session = self._sessions_by_key.get(key)
        if session is None:
            return self._active_key

        session_id = str(session.get("id") or "").strip()
        preserved_backend = self.agent_backend_for_key(key)
        if not session_id:
            return self._active_key

        deleted = await self._client.chat_sessions.delete(session_id)
        if not deleted:
            return self._active_key

        self._sessions_by_key.pop(key, None)

        if not self._sessions_by_key:
            project_id = self._current_project_id()
            if project_id is None:
                self._active_key = None
                return None
            row = await self._client.chat_sessions.create(
                source=_TUI_ORCHESTRATOR_SOURCE,
                label="TUI session",
                agent_backend=preserved_backend,
                project_id=project_id,
            )
            created = chat_session_to_legacy_dict(row, [])
            next_key = self._session_key(str(created.get("id") or ""))
            self._sessions_by_key[next_key] = created
            self._active_key = next_key
        elif self._active_key == key:
            items = build_chat_session_list_items(list(self._sessions_by_key.values()))
            next_session_id = items[0].session_id if items else ""
            self._active_key = self._session_key(next_session_id)

        current_session_id = self.current_session_id()
        if current_session_id:
            await self._client.chat_sessions.set_last_session_id(
                scope=_TUI_ORCHESTRATOR_SCOPE,
                session_id=current_session_id,
            )
        return self._active_key

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

    def source_for_key(self, key: str) -> str:
        session = self._sessions_by_key.get(key)
        if session is None:
            return ""
        return str(session.get("source") or "").strip()

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
        self,
        sessions: Sequence[dict[str, Any]],
        *,
        project_id: str,
    ) -> dict[str, Any] | None:
        if self._startup_session_id:
            pair = await self._client.chat_sessions.get_with_history(self._startup_session_id)
            self._startup_session_id = None
            if pair is not None:
                row, msgs = pair
                explicit = chat_session_to_legacy_dict(row, msgs)
                if self._is_project_session(explicit, project_id=project_id):
                    return explicit

        last_session_id = await self._client.chat_sessions.get_last_session_id(
            scope=_TUI_ORCHESTRATOR_SCOPE
        )
        if last_session_id:
            for session in sessions:
                if str(session.get("id") or "") == last_session_id:
                    return session

        if sessions:
            return sessions[-1]
        return None

    @staticmethod
    def _is_project_session(session: dict[str, Any], *, project_id: str) -> bool:
        session_id = str(session.get("id") or "").strip()
        session_project_id = str(session.get("project_id") or "").strip()
        return bool(session_id) and session_project_id == project_id

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
