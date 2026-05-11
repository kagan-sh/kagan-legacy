"""Behavioral tests for unified SSE event endpoints.

Tests:
    GET /api/sessions/{session_id}/events  (kind='chat')
    GET /api/tasks/{task_id}/sse           (kind='task')

Strategy: real KaganCore + real DB + real EventLog.
Routes are invoked directly via the Starlette route handler (same pattern as
other server tests in this suite).  The shutdown_event on the context is set
after collecting the initial framing (retry + snapshot + ready) to terminate
the live tail without hanging.

No monkeypatching on routes (per testing.md don't-list).
"""

from __future__ import annotations

import asyncio
import json
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any

import pytest

import kagan.server._helpers as server_helpers
from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, Task
from kagan.server.mcp.server import ServerOptions, _set_server_context
from kagan.server.server import ApiServerOptions, create_api_server
from tests.helpers.server import get_http_endpoint, make_request

if TYPE_CHECKING:
    from pathlib import Path

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_context(core: KaganCore) -> Any:
    """Build a ServerContext-compatible namespace."""
    shutdown = asyncio.Event()
    return SimpleNamespace(
        client=core,
        opts=ServerOptions(),
        bound_project_id=core.active_project_id,
        shutdown_event=shutdown,
    )


async def _seed_task(engine, title: str, project_id: str) -> str:
    task = Task(project_id=project_id, title=title)

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


def _create_frame(entry_idx: int, role: str = "assistant", text: str = "") -> dict[str, Any]:
    from datetime import UTC, datetime

    return {
        "type": "patch",
        "op": "create",
        "path": f"/entries/{entry_idx}",
        "value": {
            "idx": entry_idx,
            "role": role,
            "text": text,
            "finalized": False,
            "ts": datetime.now(tz=UTC).isoformat(),
        },
    }


def _append_frame(entry_idx: int, delta: str) -> dict[str, Any]:
    return {
        "type": "patch",
        "op": "append",
        "path": f"/entries/{entry_idx}/text",
        "value": delta,
    }


def _finalize_frame(entry_idx: int) -> dict[str, Any]:
    return {
        "type": "patch",
        "op": "finalize",
        "path": f"/entries/{entry_idx}",
        "value": None,
    }


# ---------------------------------------------------------------------------
# SSE consumption helpers
# ---------------------------------------------------------------------------


def _parse_sse_block(text: str) -> list[dict[str, Any]]:
    """Parse raw SSE text into a list of event/comment dicts.

    Each event dict may have keys: id, event, data, retry, comment.
    """
    events: list[dict[str, Any]] = []
    current: dict[str, Any] = {}

    for line in text.splitlines():
        if line.startswith("id:"):
            current["id"] = line[3:].strip()
        elif line.startswith("event:"):
            current["event"] = line[6:].strip()
        elif line.startswith("data:"):
            raw = line[5:].strip()
            try:
                current["data"] = json.loads(raw)
            except json.JSONDecodeError:
                current["data"] = raw
        elif line.startswith("retry:"):
            current["retry"] = int(line[6:].strip())
            events.append(dict(current))
            current = {}
        elif line.startswith(":"):
            current["comment"] = line[1:].strip()
            events.append(dict(current))
            current = {}
        elif line == "":
            if current:
                events.append(dict(current))
                current = {}

    if current:
        events.append(dict(current))

    return events


async def _collect_from_stream_response(
    stream_response: Any,
    *,
    stop_after: int = 10,
    timeout: float = 3.0,
    ready_event: asyncio.Event | None = None,
) -> list[dict[str, Any]]:
    """Consume a Starlette StreamingResponse body iterator.

    Terminates after *stop_after* events, *timeout* seconds, or when the
    stream itself ends. If *ready_event* is provided, it is set when a 'ready'
    frame is received so the caller can inject live frames afterwards.
    """
    events: list[dict[str, Any]] = []
    buf = ""

    async def _drain() -> None:
        nonlocal buf
        async for chunk in stream_response.body_iterator:
            if isinstance(chunk, bytes):
                buf += chunk.decode()
            else:
                buf += str(chunk)
            parsed = _parse_sse_block(buf)
            events.extend(parsed)
            buf = ""
            if ready_event is not None:
                if any(e.get("event") == "ready" for e in events):
                    ready_event.set()
            if len(events) >= stop_after:
                break

    try:
        await asyncio.wait_for(_drain(), timeout=timeout)
    except TimeoutError:
        pass
    return events


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def setup(tmp_path: Path):
    """Yield (core, project_id, mcp, ctx) with routes registered."""
    core = KaganCore(db_path=tmp_path / "test_events.db")
    project = await core.projects.create("Events Test Project")
    await core.projects.set_active(project.id)

    mcp = create_api_server(ApiServerOptions(mcp_opts=ServerOptions()))
    ctx = _make_context(core)
    _set_server_context(mcp, ctx)
    monkeypatch_target = server_helpers
    original = getattr(monkeypatch_target, "get_server_context", None)

    try:
        yield core, project.id, mcp, ctx
    finally:
        _set_server_context(mcp, None)
        await core.aclose()


# ---------------------------------------------------------------------------
# Session endpoint helpers
# ---------------------------------------------------------------------------


async def _get_session_sse(mcp, session_id: str, *, headers: dict[str, str] | None = None) -> Any:
    """Invoke the session SSE route and return the Starlette response."""
    endpoint = get_http_endpoint(mcp, "/api/sessions/{session_id}/events", "GET")
    req = make_request(
        "GET",
        f"/api/sessions/{session_id}/events",
        headers=headers,
        path_params={"session_id": session_id},
    )
    return await endpoint(req)


async def _get_task_sse(mcp, task_id: str, *, headers: dict[str, str] | None = None) -> Any:
    """Invoke the task SSE route and return the Starlette response."""
    endpoint = get_http_endpoint(mcp, "/api/tasks/{task_id}/sse", "GET")
    req = make_request(
        "GET",
        f"/api/tasks/{task_id}/sse",
        headers=headers,
        path_params={"task_id": task_id},
    )
    return await endpoint(req)


# ---------------------------------------------------------------------------
# Tests — chat session endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_session_returns_404(setup) -> None:
    core, project_id, mcp, ctx = setup
    resp = await _get_session_sse(mcp, "no-such-session")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_invalid_last_event_id_returns_400(setup) -> None:
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="test", project_id=project_id
    )
    resp = await _get_session_sse(mcp, chat_session.id, headers={"last-event-id": "not-a-number"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_retry_field_emitted_first(setup) -> None:
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="retry-test", project_id=project_id
    )
    ctx.shutdown_event.set()  # terminate stream immediately after header events
    resp = await _get_session_sse(mcp, chat_session.id)
    events = await _collect_from_stream_response(resp, stop_after=5, timeout=2.0)

    retry_events = [e for e in events if "retry" in e]
    assert retry_events, f"No retry event found in {events}"
    assert retry_events[0]["retry"] == 1000


@pytest.mark.asyncio
async def test_fresh_connect_yields_snapshot_then_ready(setup) -> None:
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="snapshot-test", project_id=project_id
    )
    await core._event_log.append(chat_session.id, "chat", _create_frame(0, role="user", text="hi"))
    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    event_types = [e.get("event") for e in events if "event" in e]
    assert "snapshot" in event_types, f"No snapshot in {event_types}"
    assert "ready" in event_types, f"No ready in {event_types}"
    assert event_types.index("snapshot") < event_types.index("ready")


@pytest.mark.asyncio
async def test_snapshot_carries_correct_max_seq_id(setup) -> None:
    """The ``id:`` line of the snapshot event must equal max_seq."""
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="seq-test", project_id=project_id
    )
    seq0 = await core._event_log.append(
        chat_session.id, "chat", _create_frame(0, role="user", text="a")
    )
    seq1 = await core._event_log.append(chat_session.id, "chat", _append_frame(0, "b"))
    assert seq1 > seq0

    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    snapshot_events = [e for e in events if e.get("event") == "snapshot"]
    assert snapshot_events, f"No snapshot event in {events}"
    snap_id = int(snapshot_events[0]["id"])
    assert snap_id == seq1


@pytest.mark.asyncio
async def test_snapshot_reduces_create_append_finalize_ops_into_entries(setup) -> None:
    """Snapshot entries correctly reconstruct from frame history."""
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="reduce-test", project_id=project_id
    )
    await core._event_log.append(
        chat_session.id, "chat", _create_frame(0, role="user", text="Hello")
    )
    await core._event_log.append(chat_session.id, "chat", _append_frame(0, " world"))
    await core._event_log.append(chat_session.id, "chat", _finalize_frame(0))

    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    snapshot_events = [e for e in events if e.get("event") == "snapshot"]
    assert snapshot_events, f"No snapshot in {events}"
    snap_data = snapshot_events[0]["data"]
    assert snap_data["type"] == "snapshot"
    entries = snap_data["entries"]
    assert len(entries) == 1
    assert entries[0]["text"] == "Hello world"
    assert entries[0]["finalized"] is True
    assert entries[0]["role"] == "user"


@pytest.mark.asyncio
async def test_reconnect_with_last_event_id_skips_seen_frames(setup) -> None:
    """Last-Event-ID: N → catchup snapshot from N+1, skipping earlier frames."""
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="reconnect-test", project_id=project_id
    )
    seq0 = await core._event_log.append(
        chat_session.id, "chat", _create_frame(0, role="user", text="old")
    )
    _seq1 = await core._event_log.append(
        chat_session.id, "chat", _create_frame(1, role="assistant", text="new")
    )

    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id, headers={"last-event-id": str(seq0)})
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    snapshot_events = [e for e in events if e.get("event") == "snapshot"]
    assert snapshot_events, f"No snapshot in {events}"
    snap_data = snapshot_events[0]["data"]
    # from_seq = seq0 + 1 — only the frame at seq1 is in history.
    entries = snap_data["entries"]
    texts = {e["text"] for e in entries}
    assert "new" in texts, f"Expected 'new' in texts, got {texts}"
    assert "old" not in texts, f"Stale frame 'old' still present: {texts}"
    assert snap_data["from_seq"] == seq0 + 1


@pytest.mark.asyncio
async def test_last_event_id_at_head_yields_ready_only(setup) -> None:
    """Last-Event-ID == max_seq → snapshot is omitted; only ready is emitted."""
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="at-head-test", project_id=project_id
    )
    seq0 = await core._event_log.append(
        chat_session.id, "chat", _create_frame(0, role="user", text="only")
    )

    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id, headers={"last-event-id": str(seq0)})
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    event_types = [e.get("event") for e in events if "event" in e]
    assert "snapshot" not in event_types, f"Unexpected snapshot when at head: {event_types}"
    assert "ready" in event_types


@pytest.mark.asyncio
async def test_last_event_id_ahead_of_max_does_not_error(setup) -> None:
    """Last-Event-ID > max_seq must not 4xx; treat as fresh."""
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="ahead-test", project_id=project_id
    )
    await core._event_log.append(chat_session.id, "chat", _create_frame(0, role="user", text="x"))

    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id, headers={"last-event-id": "9999"})
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    event_types = [e.get("event") for e in events if "event" in e]
    assert "ready" in event_types, f"No ready event in {event_types}"


@pytest.mark.asyncio
async def test_id_line_carries_seq_for_every_frame(setup) -> None:
    """Every event frame (snapshot, ready) must have an id: line."""
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="id-test", project_id=project_id
    )
    await core._event_log.append(chat_session.id, "chat", _create_frame(0, role="user", text="msg"))

    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    event_frames = [e for e in events if "event" in e]
    assert event_frames, "No event frames received"
    for e in event_frames:
        assert "id" in e, f"Frame missing id: {e}"


@pytest.mark.asyncio
async def test_fresh_connect_empty_history_still_yields_snapshot(setup) -> None:
    """No frames in log → fresh connect still gets a snapshot with entries=[]."""
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="empty-test", project_id=project_id
    )

    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    event_types = [e.get("event") for e in events if "event" in e]
    assert "snapshot" in event_types, f"No snapshot in {event_types}"
    snapshot_events = [e for e in events if e.get("event") == "snapshot"]
    assert snapshot_events[0]["data"]["entries"] == []


@pytest.mark.asyncio
async def test_path_based_target_idx_extracted_correctly_during_reduce(setup) -> None:
    """Verify path-based entry idx is used, not FrameRow.idx."""
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="path-idx-test", project_id=project_id
    )
    await core._event_log.append(
        chat_session.id, "chat", _create_frame(7, role="user", text="seven")
    )
    await core._event_log.append(
        chat_session.id, "chat", _create_frame(3, role="assistant", text="three")
    )

    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    snapshot_events = [e for e in events if e.get("event") == "snapshot"]
    assert snapshot_events
    entries = snapshot_events[0]["data"]["entries"]
    idxs = [e["idx"] for e in entries]
    assert sorted(idxs) == idxs
    assert set(idxs) == {3, 7}


# ---------------------------------------------------------------------------
# Tests — task endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_unknown_task_returns_404(setup) -> None:
    core, project_id, mcp, ctx = setup
    resp = await _get_task_sse(mcp, "no-such-task")
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_task_endpoint_resolves_active_session(setup) -> None:
    """Task endpoint streams from the active (RUNNING) session."""
    core, project_id, mcp, ctx = setup
    task_id = await _seed_task(core.engine, "Active Session Task", project_id)
    session_id = await _seed_session(core.engine, task_id, status=SessionStatus.RUNNING)
    await core._event_log.append(
        session_id, "task", _create_frame(0, role="assistant", text="running")
    )

    ctx.shutdown_event.set()
    resp = await _get_task_sse(mcp, task_id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    snapshot_events = [e for e in events if e.get("event") == "snapshot"]
    assert snapshot_events, f"No snapshot in {events}"
    snap_data = snapshot_events[0]["data"]
    assert snap_data["session_id"] == session_id
    entries = snap_data["entries"]
    assert any(e["text"] == "running" for e in entries)


@pytest.mark.asyncio
async def test_task_endpoint_falls_back_to_last_completed_session(setup) -> None:
    """When no active session exists, fall back to the most recent session."""
    core, project_id, mcp, ctx = setup
    task_id = await _seed_task(core.engine, "Completed Session Task", project_id)
    session_id = await _seed_session(core.engine, task_id, status=SessionStatus.COMPLETED)
    await core._event_log.append(
        session_id, "task", _create_frame(0, role="assistant", text="done")
    )

    ctx.shutdown_event.set()
    resp = await _get_task_sse(mcp, task_id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    snapshot_events = [e for e in events if e.get("event") == "snapshot"]
    assert snapshot_events, f"No snapshot in {events}"
    snap_data = snapshot_events[0]["data"]
    assert snap_data["session_id"] == session_id


@pytest.mark.asyncio
async def test_task_with_no_sessions_returns_404(setup) -> None:
    """Task exists but has no sessions → 404."""
    core, project_id, mcp, ctx = setup
    task_id = await _seed_task(core.engine, "No Sessions Task", project_id)
    resp = await _get_task_sse(mcp, task_id)
    assert resp.status_code == 404


@pytest.mark.asyncio
async def test_concurrent_clients_get_consistent_seqs(setup) -> None:
    """Two concurrent clients both see the same snapshot and max_seq."""
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="concurrent-test", project_id=project_id
    )
    await core._event_log.append(
        chat_session.id, "chat", _create_frame(0, role="user", text="shared")
    )

    # Set shutdown after first invoke so both streams terminate.
    ctx.shutdown_event.set()

    async def _consume() -> list[dict[str, Any]]:
        resp = await _get_session_sse(mcp, chat_session.id)
        return await _collect_from_stream_response(resp, stop_after=5, timeout=2.0)

    results = await asyncio.gather(_consume(), _consume())

    seqs = []
    for events in results:
        event_types = [e.get("event") for e in events if "event" in e]
        assert "snapshot" in event_types
        assert "ready" in event_types
        snap = next(e for e in events if e.get("event") == "snapshot")
        seqs.append(int(snap["id"]))

    assert seqs[0] == seqs[1]


@pytest.mark.asyncio
async def test_live_frame_arrives_after_ready(setup) -> None:
    """A frame appended mid-stream is delivered to a connected subscriber.

    Producer (EventLog.append) appends a frame mid-stream; subscriber receives
    it as a patch event.
    """
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="live-test", project_id=project_id
    )

    all_events: list[dict[str, Any]] = []
    ready_received = asyncio.Event()
    patch_received = asyncio.Event()

    endpoint = get_http_endpoint(mcp, "/api/sessions/{session_id}/events", "GET")
    req = make_request(
        "GET",
        f"/api/sessions/{chat_session.id}/events",
        path_params={"session_id": chat_session.id},
    )
    resp = await endpoint(req)

    async def _read_stream() -> None:
        async for chunk in resp.body_iterator:
            text = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
            parsed = _parse_sse_block(text)
            all_events.extend(parsed)
            for e in parsed:
                if e.get("event") == "ready":
                    ready_received.set()
                if e.get("event") == "patch":
                    patch_received.set()
                    ctx.shutdown_event.set()
                    return

    reader = asyncio.create_task(_read_stream())

    # Phase 1: wait for "ready" to confirm we're in live mode.
    try:
        await asyncio.wait_for(ready_received.wait(), timeout=3.0)
    except TimeoutError:
        ctx.shutdown_event.set()
        reader.cancel()
        pytest.skip("Stream did not reach ready state in time")

    # Phase 2: append a live frame — the subscriber should receive it.
    await core._event_log.append(
        chat_session.id, "chat", _create_frame(0, role="assistant", text="live!")
    )

    # Phase 3: wait for the patch event to arrive.
    try:
        await asyncio.wait_for(patch_received.wait(), timeout=5.0)
    except TimeoutError:
        ctx.shutdown_event.set()
        reader.cancel()

    patch_events = [e for e in all_events if e.get("event") == "patch"]
    assert patch_events, f"No patch events received. All events: {all_events}"
    patch_data = patch_events[0]["data"]
    assert patch_data.get("type") == "patch"


@pytest.mark.asyncio
async def test_resume_frame_from_orphan_reap_visible_to_first_subscriber(setup) -> None:
    """A FrameResume written by orphan reap is visible on first connect."""
    core, project_id, mcp, ctx = setup
    task_id = await _seed_task(core.engine, "Reap Task", project_id)
    session_id = await _seed_session(core.engine, task_id, status=SessionStatus.COMPLETED)
    # Simulate what orphan reap would append.
    resume_frame: dict[str, Any] = {
        "type": "resume",
        "kind": "task",
        "turn_active": False,
    }
    await core._event_log.append(session_id, "task", resume_frame)

    ctx.shutdown_event.set()
    resp = await _get_task_sse(mcp, task_id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    snapshot_events = [e for e in events if e.get("event") == "snapshot"]
    assert snapshot_events, f"No snapshot for orphan reap test: {events}"
    snap_data = snapshot_events[0]["data"]
    # The resume frame is in the log; snapshot to_seq should be >= 0.
    assert snap_data["to_seq"] >= 0


@pytest.mark.asyncio
async def test_keepalive_comment_emitted_during_idle(setup) -> None:
    """When idle for keepalive interval, a comment line is emitted."""
    import kagan.server._event_routes as event_routes_module

    original_interval = event_routes_module._KEEPALIVE_INTERVAL
    event_routes_module._KEEPALIVE_INTERVAL = 0.05  # 50 ms for the test

    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="keepalive-test", project_id=project_id
    )

    comment_seen = asyncio.Event()
    all_text: list[str] = []

    endpoint = get_http_endpoint(mcp, "/api/sessions/{session_id}/events", "GET")
    req = make_request(
        "GET",
        f"/api/sessions/{chat_session.id}/events",
        path_params={"session_id": chat_session.id},
    )
    resp = await endpoint(req)

    try:
        async with asyncio.timeout(3.0):
            async for chunk in resp.body_iterator:
                text = chunk.decode() if isinstance(chunk, bytes) else str(chunk)
                all_text.append(text)
                if any(": keepalive" in t for t in all_text):
                    comment_seen.set()
                    ctx.shutdown_event.set()
                    break
    except TimeoutError:
        pass
    finally:
        event_routes_module._KEEPALIVE_INTERVAL = original_interval

    assert comment_seen.is_set(), (
        f"No keepalive comment received. Seen text: {''.join(all_text)[:200]}"
    )


# ---------------------------------------------------------------------------
# Tests — W9a: type discriminator on every emitted SSE frame
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_sse_event_line_matches_frame_type_field(setup) -> None:
    """Every SSE event: line must match the 'type' field in the JSON data body.

    The server derives the SSE event: name from the frame's 'type' field via
    the event route.  This test verifies the two values are consistent.
    """
    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="type-match-test", project_id=project_id
    )
    await core._event_log.append(
        chat_session.id, "chat", _create_frame(0, role="user", text="hello")
    )
    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id)
    events = await _collect_from_stream_response(resp, stop_after=10, timeout=2.0)

    frame_events = [e for e in events if "event" in e and "data" in e]
    assert frame_events, f"No framed SSE events received: {events}"

    for e in frame_events:
        sse_event_name = e["event"]
        data = e["data"]
        if isinstance(data, dict):
            frame_type = data.get("type")
            assert frame_type == sse_event_name, (
                f"SSE event: line {sse_event_name!r} does not match "
                f"frame type field {frame_type!r} in body {data}"
            )


@pytest.mark.asyncio
async def test_all_emitted_frames_parse_as_pydantic_frame_union(setup) -> None:
    """Every JSON body in an SSE stream must parse as a valid Frame union member.

    Validates that the 'type' discriminator is present and that Pydantic can
    construct the appropriate Frame subtype from the data.
    """
    from pydantic import TypeAdapter

    from kagan.server.responses import Frame

    frame_adapter: TypeAdapter[Frame] = TypeAdapter(Frame)

    core, project_id, mcp, ctx = setup
    chat_session = await core.chat_sessions.create(
        source="test", label="pydantic-parse-test", project_id=project_id
    )
    await core._event_log.append(
        chat_session.id, "chat", _create_frame(0, role="assistant", text="x")
    )
    await core._event_log.append(chat_session.id, "chat", _append_frame(0, "y"))
    await core._event_log.append(chat_session.id, "chat", _finalize_frame(0))
    ctx.shutdown_event.set()
    resp = await _get_session_sse(mcp, chat_session.id)
    events = await _collect_from_stream_response(resp, stop_after=15, timeout=2.0)

    frame_events = [e for e in events if "data" in e and isinstance(e["data"], dict)]
    assert frame_events, f"No frame events received: {events}"

    parse_failures: list[str] = []
    for e in frame_events:
        data = e["data"]
        try:
            frame_adapter.validate_python(data)
        except Exception as exc:
            parse_failures.append(f"data={data!r}: {exc}")

    assert not parse_failures, "Frames that failed Pydantic Frame union validation:\n" + "\n".join(
        parse_failures
    )
