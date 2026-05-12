"""Typed fakes for CLI REPL chat unit tests (no unittest.mock)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class FakeChatSessionRow:
    """Minimal row shape used by ``hydrate_persistent_session`` tests."""

    id: str
    label: str = "REPL session"
    source: str = "repl"
    agent_backend: str = "claude-code"
    project_id: str = "proj-1"
    session_type: str = "orchestrator"
    updated_at: str = "2024-01-01T00:00:00"


class FakeChatSessions:
    """Records chat session API calls; returns configurable rows."""

    def __init__(self, *, new_session_id: str = "new-session") -> None:
        self._new_session_id = new_session_id
        self.create_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.set_last_session_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.list_with_history_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self.get_with_history_calls: list[tuple[tuple[Any, ...], dict[str, Any]]] = []
        self._list_return: list[tuple[Any, list[Any]]] = []
        self._get_return: tuple[Any, list[Any]] | None = None

    def set_list_with_history(self, rows: list[tuple[Any, list[Any]]]) -> None:
        self._list_return = rows

    def set_get_with_history(self, value: tuple[Any, list[Any]] | None) -> None:
        self._get_return = value

    async def create(self, *args: Any, **kwargs: Any) -> FakeChatSessionRow:
        self.create_calls.append((args, kwargs))
        return FakeChatSessionRow(id=self._new_session_id)

    async def set_last_session_id(self, *args: Any, **kwargs: Any) -> None:
        self.set_last_session_calls.append((args, kwargs))

    async def list_with_history(self, *args: Any, **kwargs: Any) -> list[tuple[Any, list[Any]]]:
        self.list_with_history_calls.append((args, kwargs))
        return list(self._list_return)

    async def get_with_history(self, *args: Any, **kwargs: Any) -> tuple[Any, list[Any]] | None:
        self.get_with_history_calls.append((args, kwargs))
        return self._get_return


class FakeReplChatClient:
    """Minimal KaganCore-shaped client for REPL controller unit tests."""

    active_project_id = "proj-1"
    chat: object | None = None

    def __init__(self, *, new_session_id: str = "new-session") -> None:
        self.chat_sessions = FakeChatSessions(new_session_id=new_session_id)
