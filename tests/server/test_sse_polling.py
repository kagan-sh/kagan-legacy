"""Tests for SSE DB polling — detects cross-process task mutations."""

from __future__ import annotations

import asyncio
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from kagan.server._sse import _poll_db_changes

pytestmark = [pytest.mark.unit]


def _task(task_id: str, updated_at: str) -> SimpleNamespace:
    return SimpleNamespace(id=task_id, updated_at=datetime.fromisoformat(updated_at))


class _FakeTasks:
    """Minimal stub returning canned task lists for each successive call."""

    def __init__(self, *rounds: list[SimpleNamespace]) -> None:
        self._rounds = list(rounds)
        self._call = 0

    async def list(self, **_kw: Any) -> list[SimpleNamespace]:
        idx = min(self._call, len(self._rounds) - 1)
        self._call += 1
        return self._rounds[idx]


async def _collect_events(
    queue: asyncio.Queue[dict[str, Any]],
    timeout: float = 0.1,
) -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    try:
        while True:
            events.append(await asyncio.wait_for(queue.get(), timeout=timeout))
    except TimeoutError:
        pass
    return events


@pytest.mark.asyncio
async def test_poll_emits_task_updated_for_new_task(monkeypatch: pytest.MonkeyPatch) -> None:
    """A task created by an external process triggers TASK_UPDATED."""
    monkeypatch.setattr("kagan.server._sse._DB_POLL_SECONDS", 0.01)

    initial = [_task("t1", "2026-01-01T00:00:00")]
    after = [_task("t1", "2026-01-01T00:00:00"), _task("t2", "2026-01-01T00:01:00")]

    fake = _FakeTasks(initial, after)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    poll = asyncio.create_task(_poll_db_changes(fake, queue))  # type: ignore[arg-type]

    try:
        events = await _collect_events(queue, timeout=0.15)
    finally:
        poll.cancel()
        await asyncio.gather(poll, return_exceptions=True)

    task_ids = {e["task_id"] for e in events}
    assert "t2" in task_ids
    assert all(e["type"] == "TASK_UPDATED" for e in events)


@pytest.mark.asyncio
async def test_poll_emits_task_updated_for_changed_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An externally-updated task (changed updated_at) triggers TASK_UPDATED."""
    monkeypatch.setattr("kagan.server._sse._DB_POLL_SECONDS", 0.01)

    before = [_task("t1", "2026-01-01T00:00:00")]
    after = [_task("t1", "2026-01-01T00:05:00")]

    fake = _FakeTasks(before, after)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    poll = asyncio.create_task(_poll_db_changes(fake, queue))  # type: ignore[arg-type]

    try:
        events = await _collect_events(queue, timeout=0.15)
    finally:
        poll.cancel()
        await asyncio.gather(poll, return_exceptions=True)

    assert any(e["task_id"] == "t1" for e in events)


@pytest.mark.asyncio
async def test_poll_emits_task_updated_for_deleted_task(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A task deleted by an external process triggers TASK_UPDATED."""
    monkeypatch.setattr("kagan.server._sse._DB_POLL_SECONDS", 0.01)

    before = [_task("t1", "2026-01-01T00:00:00"), _task("t2", "2026-01-01T00:00:00")]
    after = [_task("t1", "2026-01-01T00:00:00")]

    fake = _FakeTasks(before, after)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    poll = asyncio.create_task(_poll_db_changes(fake, queue))  # type: ignore[arg-type]

    try:
        events = await _collect_events(queue, timeout=0.15)
    finally:
        poll.cancel()
        await asyncio.gather(poll, return_exceptions=True)

    assert any(e["task_id"] == "t2" for e in events)


@pytest.mark.asyncio
async def test_poll_silent_when_nothing_changed(monkeypatch: pytest.MonkeyPatch) -> None:
    """No events emitted when the board is unchanged."""
    monkeypatch.setattr("kagan.server._sse._DB_POLL_SECONDS", 0.01)

    stable = [_task("t1", "2026-01-01T00:00:00")]

    fake = _FakeTasks(stable, stable, stable)
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
    poll = asyncio.create_task(_poll_db_changes(fake, queue))  # type: ignore[arg-type]

    try:
        events = await _collect_events(queue, timeout=0.15)
    finally:
        poll.cancel()
        await asyncio.gather(poll, return_exceptions=True)

    assert events == []
