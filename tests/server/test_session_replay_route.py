"""REST contract tests for GET /api/v1/sessions/{session_id}/replay."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

import kagan.server._helpers as server_helpers
from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, SessionEvent
from kagan.server.mcp.server import ServerOptions
from tests.helpers.server import get_http_endpoint, json_body, make_request
from tests.helpers.server_ws import make_api_server


async def _seed_session(engine, task_id: str) -> str:
    session = Session(task_id=task_id, agent_backend="fake", status=SessionStatus.COMPLETED)

    def _w(s) -> Session:
        s.add(session)
        s.flush()
        s.refresh(session)
        s.expunge(session)
        return session

    result = await _db_async(engine, _w, commit=True)
    return result.id


async def _seed_event(
    engine,
    session_id: str,
    task_id: str,
    event_type: str = "output_chunk",
    *,
    event_id: str | None = None,
    created_at: datetime | None = None,
) -> str:
    event = SessionEvent(
        task_id=task_id,
        session_id=session_id,
        event_type=event_type,
        payload={"text": f"chunk for {event_type}"},
    )
    if event_id is not None:
        event.id = event_id
    if created_at is not None:
        event.created_at = created_at

    def _w(s) -> SessionEvent:
        s.add(event)
        s.flush()
        s.refresh(event)
        s.expunge(event)
        return event

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
            projects=SimpleNamespace(repos=lambda _: [], resolve_repo_path=lambda **_: None),
        ),
        opts=ServerOptions(),
    )


@pytest.fixture
async def setup(tmp_path: Path):
    core = KaganCore(db_path=tmp_path / "test.db")
    project = await core.projects.create("Replay Project")
    await core.projects.set_active(project.id)

    # Create a real Task row to satisfy FK constraint
    task = await core.tasks.create("Replay Task")

    try:
        yield core, task.id
    finally:
        await core.aclose()


@pytest.mark.asyncio
async def test_replay_returns_404_for_unknown_session(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    core, _ = setup
    mcp = make_api_server()
    ctx = _make_ctx(core)
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/replay", "GET")
    req = make_request(
        "GET",
        "/api/v1/sessions/nosuchsession/replay",
        path_params={"session_id": "nosuchsession"},
    )
    body = json_body(await endpoint(req))

    assert body["ok"] is False


@pytest.mark.asyncio
async def test_replay_returns_events_in_forward_order(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """Events are returned oldest-first by default (forward direction)."""
    core, task_id = setup
    session_id = await _seed_session(core.engine, task_id)
    ev1 = await _seed_event(core.engine, session_id, task_id, "output_chunk")
    ev2 = await _seed_event(core.engine, session_id, task_id, "agent_completed")

    mcp = make_api_server()
    ctx = _make_ctx(core)
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/replay", "GET")
    req = make_request(
        "GET",
        f"/api/v1/sessions/{session_id}/replay",
        path_params={"session_id": session_id},
    )
    body = json_body(await endpoint(req))

    assert body["ok"] is True
    data = body["data"]
    events = data["events"]
    assert len(events) == 2
    assert events[0]["id"] == ev1
    assert events[1]["id"] == ev2
    assert data["has_more"] is False
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_replay_cursor_pagination(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """cursor advances through pages correctly."""
    core, task_id = setup
    session_id = await _seed_session(core.engine, task_id)
    # Seed 3 events
    ids = [await _seed_event(core.engine, session_id, task_id, f"event_{i}") for i in range(3)]

    mcp = make_api_server()
    ctx = _make_ctx(core)
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/replay", "GET")

    # Page 1: limit=2
    req = make_request(
        "GET",
        f"/api/v1/sessions/{session_id}/replay?limit=2",
        path_params={"session_id": session_id},
    )
    body = json_body(await endpoint(req))
    assert body["ok"] is True
    page1 = body["data"]
    assert len(page1["events"]) == 2
    assert page1["has_more"] is True
    cursor = page1["next_cursor"]
    assert cursor is not None

    # Page 2: use cursor
    req2 = make_request(
        "GET",
        f"/api/v1/sessions/{session_id}/replay?limit=2&cursor={cursor}",
        path_params={"session_id": session_id},
    )
    body2 = json_body(await endpoint(req2))
    page2 = body2["data"]
    assert len(page2["events"]) == 1
    assert page2["has_more"] is False
    assert page2["events"][0]["id"] == ids[2]


@pytest.mark.asyncio
async def test_replay_composite_cursor_preserves_created_at_order(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """Composite cursors continue after the last (created_at, id) pair."""
    core, task_id = setup
    session_id = await _seed_session(core.engine, task_id)
    await _seed_event(
        core.engine,
        session_id,
        task_id,
        "first",
        event_id="z_first",
        created_at=datetime(2026, 1, 1, 12, 0, tzinfo=UTC),
    )
    await _seed_event(
        core.engine,
        session_id,
        task_id,
        "second",
        event_id="a_second",
        created_at=datetime(2026, 1, 1, 12, 1, tzinfo=UTC),
    )
    await _seed_event(
        core.engine,
        session_id,
        task_id,
        "third",
        event_id="m_third",
        created_at=datetime(2026, 1, 1, 12, 2, tzinfo=UTC),
    )

    mcp = make_api_server()
    ctx = _make_ctx(core)
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/replay", "GET")
    req = make_request(
        "GET",
        f"/api/v1/sessions/{session_id}/replay?limit=2",
        path_params={"session_id": session_id},
    )
    page1 = json_body(await endpoint(req))["data"]

    assert [event["id"] for event in page1["events"]] == ["z_first", "a_second"]
    assert page1["next_cursor"].endswith("|a_second")

    req2 = make_request(
        "GET",
        f"/api/v1/sessions/{session_id}/replay?limit=2&cursor={page1['next_cursor']}",
        path_params={"session_id": session_id},
    )
    page2 = json_body(await endpoint(req2))["data"]

    assert [event["id"] for event in page2["events"]] == ["m_third"]
    assert page2["has_more"] is False


@pytest.mark.asyncio
async def test_replay_backward_direction(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """direction=backward returns events newest-first."""
    core, task_id = setup
    session_id = await _seed_session(core.engine, task_id)
    ev1 = await _seed_event(core.engine, session_id, task_id, "first")
    ev2 = await _seed_event(core.engine, session_id, task_id, "second")

    mcp = make_api_server()
    ctx = _make_ctx(core)
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/replay", "GET")
    req = make_request(
        "GET",
        f"/api/v1/sessions/{session_id}/replay?direction=backward",
        path_params={"session_id": session_id},
    )
    body = json_body(await endpoint(req))

    assert body["ok"] is True
    events = body["data"]["events"]
    assert len(events) == 2
    # Backward order: ev2 first (most recent)
    assert events[0]["id"] == ev2
    assert events[1]["id"] == ev1


@pytest.mark.asyncio
async def test_replay_limit_capped_at_max(
    monkeypatch: pytest.MonkeyPatch,
    setup: Any,
) -> None:
    """Limit above max (1000) is silently capped."""
    core, task_id = setup
    session_id = await _seed_session(core.engine, task_id)
    await _seed_event(core.engine, session_id, task_id, "ev")

    mcp = make_api_server()
    ctx = _make_ctx(core)
    monkeypatch.setattr(server_helpers, "get_server_context", lambda _: ctx)

    endpoint = get_http_endpoint(mcp, "/api/v1/sessions/{session_id}/replay", "GET")
    req = make_request(
        "GET",
        f"/api/v1/sessions/{session_id}/replay?limit=99999",
        path_params={"session_id": session_id},
    )
    body = json_body(await endpoint(req))

    # Should not error — silently caps
    assert body["ok"] is True
    assert len(body["data"]["events"]) == 1
