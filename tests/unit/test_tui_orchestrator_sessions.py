from importlib import util
from pathlib import Path
from typing import Any, cast

import pytest

from kagan.cli.chat._session_picker import chat_session_to_view


async def save_chat_session(client: Any, session: dict[str, Any]) -> None:
    """Local test helper — upsert a session dict via the aggregate."""
    sid = str(session.get("id") or "").strip()
    if not sid:
        return
    history: list[tuple[str, str]] = []
    for pair in session.get("orchestrator_history") or []:
        if isinstance(pair, list | tuple) and len(pair) == 2:
            role = str(pair[0]).strip()
            content = str(pair[1]).strip()
            if role and content:
                history.append((role, content))
    raw_backend = session.get("agent_backend")
    backend: str | None = (
        raw_backend if isinstance(raw_backend, str) and raw_backend.strip() else None
    )
    raw_project = session.get("project_id")
    project: str | None = (
        raw_project if isinstance(raw_project, str) and raw_project.strip() else None
    )
    await client.chat_sessions.upsert_with_history(
        sid,
        label=str(session.get("label") or f"Session {sid[:8]}").strip(),
        source=str(session.get("source") or "repl") or "repl",
        agent_backend=backend,
        project_id=project,
        history=history,
    )


async def get_chat_session(client: Any, session_id: str) -> dict[str, Any] | None:
    pair = await client.chat_sessions.get_with_history(session_id)
    if pair is None:
        return None
    return chat_session_to_view(*pair).model_dump()


def _load_tui_orchestrator_sessions_module() -> Any:
    module_path = Path(__file__).resolve().parents[2] / "src/kagan/tui/orchestrator_sessions.py"
    spec = util.spec_from_file_location("test_tui_orchestrator_sessions_module", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


TuiOrchestratorSessionStore = _load_tui_orchestrator_sessions_module().TuiOrchestratorSessionStore

pytestmark = [pytest.mark.unit]


class _FakeSettingsOps:
    def __init__(self) -> None:
        self._store: dict[str, str] = {}

    async def get(self) -> dict[str, str]:
        return dict(self._store)

    async def set(self, updates: dict[str, str]) -> None:
        self._store.update(updates)


def _make_test_engine(*, seed_project_id: str | None = None):  # type: ignore[return]
    """File-based SQLite engine so asyncio.to_thread can access it across threads.

    If seed_project_id is given, a minimal project row is inserted so that
    chat_sessions FK(project_id) constraints pass.
    """
    import sqlite3
    import tempfile
    from pathlib import Path

    from kagan.core._db import create_db_engine

    tmpdir = tempfile.mkdtemp()
    db_path = Path(tmpdir) / "test.db"
    engine = create_db_engine(db_path)
    if seed_project_id is not None:
        conn = sqlite3.connect(str(db_path))
        try:
            conn.execute("PRAGMA foreign_keys=OFF")
            conn.execute(
                "INSERT OR IGNORE INTO projects (id, name, description, created_at, updated_at) "
                "VALUES (?, ?, '', datetime('now'), datetime('now'))",
                (seed_project_id, seed_project_id),
            )
            conn.commit()
        finally:
            conn.close()
    return engine


class _FakeClient:
    def __init__(self, *, active_project_id: str | None = None) -> None:
        from kagan.core.chat import ChatSessions

        self.settings = _FakeSettingsOps()
        self.active_project_id = active_project_id
        self._engine = _make_test_engine(seed_project_id=active_project_id)
        self.chat_sessions = ChatSessions(self._engine, self.settings)


@pytest.mark.asyncio
async def test_store_bootstraps_first_session_when_none_exist() -> None:
    client = _FakeClient(active_project_id="project-123")
    store = TuiOrchestratorSessionStore(cast("Any", client))

    await store.ensure_loaded()

    active_key = store.active_key()
    assert active_key.startswith("orchestrator:")
    assert store.options()
    settings = await client.settings.get()
    assert settings.get("chat_last_session_tui-orchestrator")
    active_id = store.current_session_id()
    assert active_id is not None
    persisted = await get_chat_session(cast("Any", client), active_id)
    assert persisted is not None
    assert persisted.get("project_id") == "project-123"


@pytest.mark.asyncio
async def test_store_uses_explicit_startup_session_id_when_present_for_active_project() -> None:
    client = _FakeClient(active_project_id="project-123")
    await save_chat_session(
        cast("Any", client),
        {
            "id": "tuiabcd1",
            "label": "TUI retained",
            "source": "tui-orchestrator",
            "agent_backend": "opencode",
            "orchestrator_history": [["user", "hi"], ["assistant", "hello"]],
            "messages_rendered": ["You: hi", "Agent: hello"],
            "project_id": "project-123",
        },
    )
    store = TuiOrchestratorSessionStore(cast("Any", client), startup_session_id="tuiabcd1")

    await store.ensure_loaded()

    assert store.active_key() == "orchestrator:tuiabcd1"
    assert store.active_history() == [("user", "hi"), ("assistant", "hello")]
    assert store.agent_backend_for_key("orchestrator:tuiabcd1") == "opencode"


@pytest.mark.asyncio
async def test_store_persists_active_history_and_backend() -> None:
    client = _FakeClient(active_project_id="project-123")
    store = TuiOrchestratorSessionStore(cast("Any", client))
    await store.ensure_loaded()
    active_id = store.current_session_id()
    assert active_id is not None

    await store.persist_active(
        history=[("user", "plan"), ("assistant", "execute")],
        rendered_messages=["You: plan", "Agent: execute"],
        agent_backend="claude-code",
    )

    persisted = await get_chat_session(cast("Any", client), active_id)
    assert persisted is not None
    assert persisted.get("agent_backend") == "claude-code"
    assert persisted.get("orchestrator_history") == [["user", "plan"], ["assistant", "execute"]]
    assert persisted.get("project_id") == "project-123"


@pytest.mark.asyncio
async def test_store_ignores_legacy_startup_session_without_project_binding() -> None:
    client = _FakeClient(active_project_id="project-123")
    await save_chat_session(
        cast("Any", client),
        {
            "id": "legacy01",
            "label": "Legacy session",
            "source": "tui-orchestrator",
            "agent_backend": "codex",
            "orchestrator_history": [["user", "continue"], ["assistant", "ready"]],
            "messages_rendered": ["You: continue", "Agent: ready"],
        },
    )
    store = TuiOrchestratorSessionStore(cast("Any", client), startup_session_id="legacy01")

    await store.ensure_loaded()

    active_id = store.current_session_id()
    assert active_id is not None
    assert active_id != "legacy01"
    active_session = await get_chat_session(cast("Any", client), active_id)
    assert active_session is not None
    assert active_session.get("project_id") == "project-123"


@pytest.mark.asyncio
async def test_store_does_not_fall_back_to_global_last_active_session() -> None:
    client = _FakeClient(active_project_id="project-123")
    await save_chat_session(
        cast("Any", client),
        {
            "id": "legacy02",
            "label": "Legacy web session",
            "source": "web",
            "agent_backend": "codex",
            "orchestrator_history": [["user", "continue"], ["assistant", "ready"]],
            "messages_rendered": ["You: continue", "Agent: ready"],
        },
    )
    await client.settings.set({"chat_last_active_session": "legacy02"})

    store = TuiOrchestratorSessionStore(cast("Any", client))
    await store.ensure_loaded()

    active_id = store.current_session_id()
    assert active_id is not None
    assert active_id != "legacy02"
    active_session = await get_chat_session(cast("Any", client), active_id)
    assert active_session is not None
    assert active_session.get("project_id") == "project-123"
