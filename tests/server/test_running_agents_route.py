"""REST contract tests for GET /api/v1/agents/running."""

from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

import kagan.server._helpers as server_helpers
from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.models import Session, Task
from kagan.server.mcp.server import ServerOptions
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server


async def _seed_task(engine, title: str, project_id: str) -> str:
    task = Task(project_id=project_id, title=title, status=TaskStatus.IN_PROGRESS)

    def _w(s) -> Task:
        s.add(task)
        s.flush()
        s.refresh(task)
        s.expunge(task)
        return task

    result = await _db_async(engine, _w, commit=True)
    return result.id


async def _seed_session(
    engine, task_id: str, *, status: SessionStatus = SessionStatus.RUNNING, role: str = "worker"
) -> str:
    session = Session(task_id=task_id, agent_backend="fake", status=status, agent_role=role)

    def _w(s) -> Session:
        s.add(session)
        s.flush()
        s.refresh(session)
        s.expunge(session)
        return session

    result = await _db_async(engine, _w, commit=True)
    return result.id


def _make_ctx(core: KaganCore) -> SimpleNamespace:
    async def _get_settings() -> dict[str, str]:
        return {}

    return SimpleNamespace(
        client=SimpleNamespace(
            tasks=core.tasks,
            settings=SimpleNamespace(get=_get_settings),
            worktrees=core.worktrees,
            engine=core.engine,
            active_project_id=core.active_project_id,
            projects=SimpleNamespace(
                repos=lambda _: [],
                resolve_repo_path=lambda **_: None,
            ),
        ),
        opts=ServerOptions(),
    )


@pytest.fixture
async def setup(tmp_path: Path):
    core = KaganCore(db_path=tmp_path / "test.db")
    project = await core.projects.create("Test Project")
    await core.projects.set_active(project.id)
    try:
        yield core, project.id
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_running_agents_empty_returns_empty_list(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """With no active sessions, the endpoint returns an empty agents list."""
    core, _ = setup
    mcp = make_api_server()
    ctx = _make_ctx(core)
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

    endpoint = get_http_endpoint(mcp, "/api/v1/agents/running", "GET")
    body = json_body(await endpoint(make_request("GET", "/api/v1/agents/running")))

    assert body["ok"] is True
    assert body["data"]["agents"] == []


@pytest.mark.asyncio
async def test_running_agents_returns_active_session(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """An active session appears in the response with correct shape."""
    core, project_id = setup
    task_id = await _seed_task(core.engine, "My Task", project_id)
    session_id = await _seed_session(core.engine, task_id, status=SessionStatus.RUNNING)

    mcp = make_api_server()
    ctx = _make_ctx(core)
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

    endpoint = get_http_endpoint(mcp, "/api/v1/agents/running", "GET")
    body = json_body(await endpoint(make_request("GET", "/api/v1/agents/running")))

    assert body["ok"] is True
    agents = body["data"]["agents"]
    assert len(agents) == 1
    agent = agents[0]
    assert agent["task_id"] == task_id
    assert agent["task_title"] == "My Task"
    assert agent["session_id"] == session_id
    assert agent["session_status"] == "RUNNING"
    assert agent["agent_backend"] == "fake"
    assert "started_at" in agent


@pytest.mark.asyncio
async def test_running_agents_excludes_completed(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """Completed sessions are not included in the response."""
    core, project_id = setup
    task_id = await _seed_task(core.engine, "Done", project_id)
    await _seed_session(core.engine, task_id, status=SessionStatus.COMPLETED)

    mcp = make_api_server()
    ctx = _make_ctx(core)
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

    endpoint = get_http_endpoint(mcp, "/api/v1/agents/running", "GET")
    body = json_body(await endpoint(make_request("GET", "/api/v1/agents/running")))

    assert body["ok"] is True
    assert body["data"]["agents"] == []


@pytest.mark.asyncio
async def test_running_agents_project_filter_via_query_param(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """The project_id query param filters to only that project's sessions."""
    core = KaganCore(db_path=tmp_path / "test2.db")
    try:
        proj_a = await core.projects.create("A")
        proj_b = await core.projects.create("B")

        task_a = await _seed_task(core.engine, "Task A", proj_a.id)
        task_b = await _seed_task(core.engine, "Task B", proj_b.id)

        await _seed_session(core.engine, task_a, status=SessionStatus.RUNNING)
        await _seed_session(core.engine, task_b, status=SessionStatus.RUNNING)

        mcp = make_api_server()

        async def _get_settings() -> dict[str, str]:
            return {}

        ctx = SimpleNamespace(
            client=SimpleNamespace(
                tasks=core.tasks,
                settings=SimpleNamespace(get=_get_settings),
                worktrees=core.worktrees,
                engine=core.engine,
                active_project_id=proj_a.id,
                projects=SimpleNamespace(
                    repos=lambda _: [],
                    resolve_repo_path=lambda **_: None,
                ),
            ),
            opts=ServerOptions(),
        )
        monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

        endpoint = get_http_endpoint(mcp, "/api/v1/agents/running", "GET")
        body = json_body(
            await endpoint(make_request("GET", f"/api/v1/agents/running?project_id={proj_a.id}"))
        )

        assert body["ok"] is True
        agents = body["data"]["agents"]
        assert len(agents) == 1
        assert agents[0]["task_id"] == task_a
    finally:
        await core.aclose()
