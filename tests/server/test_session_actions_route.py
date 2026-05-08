"""Tests for POST /api/v1/sessions/:id/stop and /close."""

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
from kagan.core.models import ChatSession, Session, Task
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
    engine, task_id: str, *, status: SessionStatus = SessionStatus.RUNNING
) -> str:
    session = Session(task_id=task_id, agent_backend="fake", status=status)

    def _w(s) -> Session:
        s.add(session)
        s.flush()
        s.refresh(session)
        s.expunge(session)
        return session

    result = await _db_async(engine, _w, commit=True)
    return result.id


async def _seed_chat_session(engine, label: str, project_id: str) -> str:
    chat = ChatSession(label=label, source="web", project_id=project_id)

    def _w(s) -> ChatSession:
        s.add(chat)
        s.flush()
        s.refresh(chat)
        s.expunge(chat)
        return chat

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
async def test_stop_task_session(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """POST /api/v1/sessions/task:{id}/stop returns 204."""
    core, project_id = setup
    task_id = await _seed_task(core.engine, "Stop Task", project_id)
    session_id = await _seed_session(core.engine, task_id, status=SessionStatus.RUNNING)

    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/stop", "POST")
    response = await endpoint(
        make_request(
            "POST",
            f"/api/v1/sessions/task:{session_id}/stop",
            path_params={"session_id": f"task:{session_id}"},
        )
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_stop_chat_session(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """POST /api/v1/sessions/orch:{id}/stop returns 204."""
    core, project_id = setup
    chat_id = await _seed_chat_session(core.engine, "Stop Chat", project_id)

    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/stop", "POST")
    response = await endpoint(
        make_request(
            "POST",
            f"/api/v1/sessions/orch:{chat_id}/stop",
            path_params={"session_id": f"orch:{chat_id}"},
        )
    )

    assert response.status_code == 204


@pytest.mark.asyncio
async def test_close_chat_session(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """POST /api/v1/sessions/orch:{id}/close returns 204 and deletes the session."""
    core, project_id = setup
    chat_id = await _seed_chat_session(core.engine, "Close Chat", project_id)

    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/close", "POST")
    response = await endpoint(
        make_request(
            "POST",
            f"/api/v1/sessions/orch:{chat_id}/close",
            path_params={"session_id": f"orch:{chat_id}"},
        )
    )

    assert response.status_code == 204

    # Verify deletion
    remaining = await core.chat_sessions.get_with_history(chat_id)
    assert remaining is None


@pytest.mark.asyncio
async def test_close_task_session_returns_400(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """POST /api/v1/sessions/task:{id}/close returns 400."""
    core, project_id = setup
    task_id = await _seed_task(core.engine, "Close Task", project_id)
    session_id = await _seed_session(core.engine, task_id, status=SessionStatus.RUNNING)

    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/close", "POST")
    response = await endpoint(
        make_request(
            "POST",
            f"/api/v1/sessions/task:{session_id}/close",
            path_params={"session_id": f"task:{session_id}"},
        )
    )
    body = json_body(response)

    assert response.status_code == 400
    assert body["ok"] is False
    assert "cannot be closed" in body["error"].lower()
