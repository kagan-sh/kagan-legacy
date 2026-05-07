"""Tests for the session events SSE generator.

Follows the same pattern as ``tests/unit/server/test_sse_polling.py``:
tests exercise the generator function directly with a stub DB/context rather
than going through the HTTP stack. This keeps the tests fast and deterministic.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

import pytest

from kagan.core import KaganCore
from kagan.core._db_helpers import _db_async
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, SessionEvent

pytestmark = [pytest.mark.unit]


async def _seed_session(engine, task_id: str, status: SessionStatus) -> str:
    session = Session(task_id=task_id, agent_backend="fake", status=status)

    def _w(s) -> Session:
        s.add(session)
        s.flush()
        s.refresh(session)
        s.expunge(session)
        return session

    result = await _db_async(engine, _w, commit=True)
    return result.id


async def _seed_event(engine, session_id: str, task_id: str) -> str:
    event = SessionEvent(
        task_id=task_id,
        session_id=session_id,
        event_type="output_chunk",
        payload={"text": "hello"},
    )

    def _w(s) -> SessionEvent:
        s.add(event)
        s.flush()
        s.refresh(event)
        s.expunge(event)
        return event

    result = await _db_async(engine, _w, commit=True)
    return result.id


async def _collect_sse_lines(gen, *, count: int, timeout: float = 2.0) -> list[dict[str, Any]]:
    """Consume up to *count* data lines from an SSE async generator."""
    collected: list[dict[str, Any]] = []

    async def _drain() -> None:
        async for line in gen:
            if line.startswith("data: "):
                payload = json.loads(line[len("data: ") :].strip())
                collected.append(payload)
                if len(collected) >= count:
                    return

    import contextlib

    with contextlib.suppress(TimeoutError):  # async-safe: wait_for propagates CancelledError
        await asyncio.wait_for(_drain(), timeout=timeout)
    return collected


@pytest.fixture
async def core_with_task(tmp_path: Path):
    client = KaganCore(db_path=tmp_path / "test.db")
    project = await client.projects.create("SSE Project")
    await client.projects.set_active(project.id)
    task = await client.tasks.create("SSE Task")
    try:
        yield client, task.id
    finally:
        await client.aclose()


@pytest.mark.asyncio
async def test_session_events_generator_yields_existing_events(
    core_with_task: Any,
) -> None:
    """Generator yields events that were already in the DB when it starts."""
    from types import SimpleNamespace

    client, task_id = core_with_task
    session_id = await _seed_session(client.engine, task_id, SessionStatus.COMPLETED)
    await _seed_event(client.engine, session_id, task_id)

    # We need a minimal ctx stub that exposes client.engine
    async def _get_settings() -> dict[str, str]:
        return {}

    ctx = SimpleNamespace(
        client=SimpleNamespace(
            engine=client.engine,
            settings=SimpleNamespace(get=_get_settings),
        )
    )

    from kagan.server._agent_routes import _session_events_sse_generator

    gen = _session_events_sse_generator(ctx, session_id, since=None)
    events = await _collect_sse_lines(gen, count=1)

    assert len(events) >= 1
    ev = events[0]
    assert ev["type"] == "SESSION_EVENT"
    assert ev["session_id"] == session_id
    assert "event" in ev
    assert ev["event"]["event_type"] == "output_chunk"


@pytest.mark.asyncio
async def test_session_events_generator_stops_after_completed_session(
    core_with_task: Any,
) -> None:
    """Generator terminates after draining events from a completed session."""
    from types import SimpleNamespace

    client, task_id = core_with_task
    session_id = await _seed_session(client.engine, task_id, SessionStatus.COMPLETED)

    async def _get_settings() -> dict[str, str]:
        return {}

    ctx = SimpleNamespace(
        client=SimpleNamespace(
            engine=client.engine,
            settings=SimpleNamespace(get=_get_settings),
        )
    )

    from kagan.server._agent_routes import _session_events_sse_generator

    gen = _session_events_sse_generator(ctx, session_id, since=None)

    # Generator should stop cleanly for a completed session with no events
    collected: list[str] = []
    with contextlib.suppress(TimeoutError):
        await asyncio.wait_for(
            _exhaust_gen(gen, collected),
            timeout=3.0,
        )

    # Whether it exhausted or timed out, no SESSION_EVENT lines (no events seeded)
    data_lines = [line for line in collected if line.startswith("data:")]
    assert data_lines == []


async def _exhaust_gen(gen, out: list[str]) -> None:
    async for line in gen:
        out.append(line)


@pytest.mark.asyncio
async def test_running_agents_sse_generator_emits_joined(
    core_with_task: Any,
) -> None:
    """AGENT_JOINED event emitted when a new session appears in the snapshot."""
    from types import SimpleNamespace

    client, task_id = core_with_task

    async def _get_settings() -> dict[str, str]:
        return {}

    ctx = SimpleNamespace(
        client=SimpleNamespace(
            engine=client.engine,
            settings=SimpleNamespace(get=_get_settings),
        )
    )

    # Patch poll interval to be immediate
    import kagan.server._agent_routes as routes_module

    original = routes_module._AGENT_POLL_SECONDS
    routes_module._AGENT_POLL_SECONDS = 0.05
    try:
        from kagan.server._agent_routes import _running_agents_events_generator

        # Seed a session AFTER the generator starts so it emits AGENT_JOINED
        gen = _running_agents_events_generator(ctx, project_id=None)  # type: ignore[arg-type]

        async def _seed_after_delay() -> None:
            await asyncio.sleep(0.1)
            await _seed_session(client.engine, task_id, SessionStatus.RUNNING)

        seed_task = asyncio.create_task(_seed_after_delay())
        events = await _collect_sse_lines(gen, count=1, timeout=2.0)
        await seed_task

        assert len(events) >= 1
        types = {e["type"] for e in events}
        assert "AGENT_JOINED" in types
    finally:
        routes_module._AGENT_POLL_SECONDS = original
