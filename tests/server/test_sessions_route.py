"""Tests for canonical unified session routes (GET / POST /api/v1/sessions)."""

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


def _make_ctx(core: KaganCore) -> SimpleNamespace:
    return SimpleNamespace(
        client=core,
        opts=ServerOptions(),
        bound_project_id=core.active_project_id,
    )


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
async def test_list_sessions_returns_unified_session_items(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """GET /api/v1/sessions returns both chat and task sessions."""
    core, project_id = setup
    chat = await core.chat_sessions.create(
        source="web",
        label="Orchestrator",
        agent_backend="claude-code",
        project_id=project_id,
    )
    task_id = await _seed_task(core.engine, "Task Session", project_id)
    session_id = await _seed_session(core.engine, task_id, status=SessionStatus.RUNNING)

    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions", "GET")
    body = json_body(await endpoint(make_request("GET", "/api/v1/sessions")))

    assert body["ok"] is True
    sessions = body["data"]["sessions"]
    ids = {s["id"] for s in sessions}
    assert f"orch:{chat.id}" in ids
    assert f"task:{session_id}" in ids


@pytest.mark.asyncio
async def test_create_orchestrator_session(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """POST /api/v1/sessions creates an orchestrator chat session."""
    core, _project_id = setup
    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions", "POST")
    body = json_body(
        await endpoint(
            make_request(
                "POST",
                "/api/v1/sessions",
                body={"type": "orchestrator", "backend": "claude-code", "title": "My Orchestrator"},
            )
        )
    )

    assert body["ok"] is True
    assert body["data"]["type"] == "orchestrator"
    assert body["data"]["title"] == "My Orchestrator"
    assert body["data"]["backend"] == "claude-code"
    assert body["data"]["id"].startswith("orch:")
    assert body["data"]["capabilities"]["has_kagan_tools"] is True


@pytest.mark.asyncio
async def test_create_general_session(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """POST /api/v1/sessions creates a general chat session."""
    core, _project_id = setup
    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions", "POST")
    body = json_body(
        await endpoint(
            make_request(
                "POST",
                "/api/v1/sessions",
                body={"type": "general", "backend": "fake", "title": "My General"},
            )
        )
    )

    assert body["ok"] is True
    assert body["data"]["type"] == "general"
    assert body["data"]["title"] == "My General"
    assert body["data"]["backend"] == "fake"
    assert body["data"]["id"].startswith("gen:")
    assert body["data"]["capabilities"]["has_kagan_tools"] is False


@pytest.mark.asyncio
async def test_create_session_rejects_unknown_type(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """POST /api/v1/sessions returns 400 for an unknown session type."""
    core, _ = setup
    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions", "POST")
    response = await endpoint(make_request("POST", "/api/v1/sessions", body={"type": "unknown"}))
    body = json_body(response)

    assert response.status_code == 400
    assert body["ok"] is False
