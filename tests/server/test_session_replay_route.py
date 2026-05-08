"""Tests for GET /api/v1/sessions/:id/replay."""

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
from kagan.core.models import ChatMessage, ChatSession, Session, SessionEvent, Task
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


async def _seed_event(engine, task_id: str, session_id: str, event_type: str, payload: dict) -> str:
    event = SessionEvent(
        task_id=task_id,
        session_id=session_id,
        event_type=event_type,
        payload=payload,
    )

    def _w(s) -> SessionEvent:
        s.add(event)
        s.flush()
        s.refresh(event)
        s.expunge(event)
        return event

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


async def _seed_chat_message(engine, session_id: str, role: str, content: str) -> None:
    msg = ChatMessage(session_id=session_id, role=role, content=content)

    def _w(s) -> None:
        s.add(msg)

    await _db_async(engine, _w, commit=True)


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
async def test_replay_task_session_events(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """GET /api/v1/sessions/task:{id}/replay returns task session events."""
    core, project_id = setup
    task_id = await _seed_task(core.engine, "Replay Task", project_id)
    session_id = await _seed_session(core.engine, task_id, status=SessionStatus.RUNNING)
    await _seed_event(core.engine, task_id, session_id, "agent_start", {"backend": "fake"})
    await _seed_event(core.engine, task_id, session_id, "output_chunk", {"text": "hello"})

    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/replay", "GET")
    body = json_body(
        await endpoint(
            make_request(
                "GET",
                f"/api/v1/sessions/task:{session_id}/replay",
                path_params={"session_id": f"task:{session_id}"},
            )
        )
    )

    assert body.get("ok") is True, f"body={body}"
    events = body["data"]["events"]
    assert len(events) == 2
    assert events[0]["event_type"] == "agent_start"
    assert events[1]["event_type"] == "output_chunk"
    assert events[1]["payload"]["text"] == "hello"


@pytest.mark.asyncio
async def test_replay_chat_session_messages(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """GET /api/v1/sessions/orch:{id}/replay returns chat messages as replay events."""
    core, project_id = setup
    chat_id = await _seed_chat_session(core.engine, "Chat Replay", project_id)
    await _seed_chat_message(core.engine, chat_id, "user", "Hello")
    await _seed_chat_message(core.engine, chat_id, "assistant", "Hi there")

    mcp = make_api_server()
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: _make_ctx(core))

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/replay", "GET")
    body = json_body(
        await endpoint(
            make_request(
                "GET",
                f"/api/v1/sessions/orch:{chat_id}/replay",
                path_params={"session_id": f"orch:{chat_id}"},
            )
        )
    )

    assert body.get("ok") is True, f"body={body}"
    events = body["data"]["events"]
    assert len(events) == 2
    assert events[0]["event_type"] == "chat_message"
    assert events[0]["payload"]["role"] == "user"
    assert events[0]["payload"]["content"] == "Hello"
    assert events[1]["payload"]["role"] == "assistant"
    assert events[1]["payload"]["content"] == "Hi there"
