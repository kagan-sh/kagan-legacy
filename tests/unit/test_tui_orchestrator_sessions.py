from importlib import util
from pathlib import Path
from typing import Any, cast

import pytest

from kagan.chat.sessions import get_chat_session, save_chat_session


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


class _FakeClient:
    def __init__(self, *, active_project_id: str | None = None) -> None:
        self.settings = _FakeSettingsOps()
        self.active_project_id = active_project_id


@pytest.mark.asyncio
async def test_store_bootstraps_first_session_when_none_exist() -> None:
    client = _FakeClient()
    store = TuiOrchestratorSessionStore(cast("Any", client))

    await store.ensure_loaded()

    active_key = store.active_key()
    assert active_key.startswith("orchestrator:")
    assert store.options()
    settings = await client.settings.get()
    assert settings.get("chat_last_session_tui-orchestrator")


@pytest.mark.asyncio
async def test_store_uses_explicit_startup_session_id_when_present() -> None:
    client = _FakeClient()
    await save_chat_session(
        cast("Any", client),
        {
            "id": "tuiabcd1",
            "label": "TUI retained",
            "source": "tui-orchestrator",
            "agent_backend": "opencode",
            "orchestrator_history": [["user", "hi"], ["assistant", "hello"]],
            "messages_rendered": ["You: hi", "Agent: hello"],
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
async def test_store_falls_back_to_global_last_active_session() -> None:
    client = _FakeClient()
    await save_chat_session(
        cast("Any", client),
        {
            "id": "webabcd1",
            "label": "Web handoff",
            "source": "web",
            "agent_backend": "codex",
            "orchestrator_history": [["user", "continue"], ["assistant", "ready"]],
            "messages_rendered": ["You: continue", "Agent: ready"],
        },
    )

    store = TuiOrchestratorSessionStore(cast("Any", client))
    await store.ensure_loaded()

    assert store.active_key() == "orchestrator:webabcd1"
    assert store.active_history() == [("user", "continue"), ("assistant", "ready")]
