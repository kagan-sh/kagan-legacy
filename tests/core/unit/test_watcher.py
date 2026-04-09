"""Tests for DBWatcher -- polling-based task board change tracker."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import datetime
from types import SimpleNamespace
from typing import Any

import pytest

from kagan.core._events import BoardEvent
from kagan.core._watcher import DBWatcher, _TaskState

pytestmark = [pytest.mark.unit]


# ── Helpers ───────────────────────────────────────────────────────────


def _task(
    task_id: str,
    title: str = "Task",
    status: str = "backlog",
    updated_at: str = "2026-01-01T00:00:00",
    project_id: str = "proj-1",
) -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        title=title,
        status=SimpleNamespace(value=status),
        updated_at=datetime.fromisoformat(updated_at),
        project_id=project_id,
    )


class _FakeEvents:
    """Minimal stub for the events subsystem."""

    def __init__(self, events: list[BoardEvent] | None = None, *, raise_on_stream: bool = False) -> None:
        self._events = events or []
        self._raise_on_stream = raise_on_stream
        self._stream_call_count = 0

    async def stream_board(self) -> AsyncIterator[BoardEvent]:
        self._stream_call_count += 1
        if self._raise_on_stream and self._stream_call_count == 1:
            raise RuntimeError("stream failed")
        for event in self._events:
            yield event


class _FakeTasks:
    """Minimal stub for the tasks subsystem."""

    def __init__(self, *rounds: list[SimpleNamespace]) -> None:
        self._rounds = list(rounds)
        self._call = 0
        self._get_store: dict[str, SimpleNamespace] = {}
        self.events = _FakeEvents()

    async def list(self, **_kw: Any) -> list[SimpleNamespace]:
        idx = min(self._call, len(self._rounds) - 1)
        self._call += 1
        return self._rounds[idx]

    async def get(self, task_id: str) -> SimpleNamespace:
        if task_id in self._get_store:
            return self._get_store[task_id]
        raise Exception(f"task {task_id} not found")


class _FakeCore:
    """Minimal stub for KaganCore."""

    def __init__(self, tasks: _FakeTasks, project_id: str = "proj-1") -> None:
        self.tasks = tasks
        self.active_project_id = project_id


# ── Snapshot diffing tests ────────────────────────────────────────────


def test_task_state_includes_updated_at() -> None:
    """_TaskState has an updated_at field."""
    state = _TaskState("title", "backlog", "2026-01-01T00:00:00")
    assert state.updated_at == "2026-01-01T00:00:00"


@pytest.mark.asyncio
async def test_poll_detects_updated_at_change() -> None:
    """A change to updated_at (same title/status) is detected by _diff_snapshot."""
    before = [_task("t1", "Task A", "backlog", "2026-01-01T00:00:00")]
    after = [_task("t1", "Task A", "backlog", "2026-01-01T00:05:00")]

    fake_tasks = _FakeTasks(before, after)
    core = _FakeCore(fake_tasks)
    watcher = DBWatcher(core)  # type: ignore[arg-type]
    await watcher.initialize()

    # Simulate a poll cycle: take new snapshot and diff
    current = {
        t.id: _TaskState(t.title, t.status.value, t.updated_at.isoformat())
        for t in after
    }
    changed = watcher._diff_snapshot(current)

    assert changed is True
    assert len(watcher._pending) == 1
    assert "updated" in watcher._pending[0]


@pytest.mark.asyncio
async def test_poll_ignores_unchanged_updated_at() -> None:
    """No change when updated_at is identical."""
    stable = [_task("t1", "Task A", "backlog", "2026-01-01T00:00:00")]

    fake_tasks = _FakeTasks(stable, stable)
    core = _FakeCore(fake_tasks)
    watcher = DBWatcher(core)  # type: ignore[arg-type]
    await watcher.initialize()

    current = {
        t.id: _TaskState(t.title, t.status.value, t.updated_at.isoformat())
        for t in stable
    }
    changed = watcher._diff_snapshot(current)

    assert changed is False
    assert len(watcher._pending) == 0


@pytest.mark.asyncio
async def test_poll_detects_status_change_with_descriptive_message() -> None:
    """Status change generates a 'moved X -> Y' message."""
    before = [_task("t1", "Task A", "backlog", "2026-01-01T00:00:00")]
    after = [_task("t1", "Task A", "in_progress", "2026-01-01T00:05:00")]

    fake_tasks = _FakeTasks(before, after)
    core = _FakeCore(fake_tasks)
    watcher = DBWatcher(core)  # type: ignore[arg-type]
    await watcher.initialize()

    current = {
        t.id: _TaskState(t.title, t.status.value, t.updated_at.isoformat())
        for t in after
    }
    changed = watcher._diff_snapshot(current)

    assert changed is True
    assert "moved backlog → in_progress" in watcher._pending[0]


@pytest.mark.asyncio
async def test_poll_detects_title_change_with_descriptive_message() -> None:
    """Title change generates a 'title updated' message."""
    before = [_task("t1", "Old Title", "backlog", "2026-01-01T00:00:00")]
    after = [_task("t1", "New Title", "backlog", "2026-01-01T00:05:00")]

    fake_tasks = _FakeTasks(before, after)
    core = _FakeCore(fake_tasks)
    watcher = DBWatcher(core)  # type: ignore[arg-type]
    await watcher.initialize()

    current = {
        t.id: _TaskState(t.title, t.status.value, t.updated_at.isoformat())
        for t in after
    }
    changed = watcher._diff_snapshot(current)

    assert changed is True
    assert "title updated" in watcher._pending[0]


# ── Event handler snapshot sync tests ─────────────────────────────────


@pytest.mark.asyncio
async def test_event_handler_syncs_snapshot_on_created() -> None:
    """After handling a 'created' event, snapshot includes correct updated_at."""
    task = _task("t1", "New Task", "backlog", "2026-01-01T00:10:00")

    fake_tasks = _FakeTasks([])
    fake_tasks._get_store["t1"] = task
    core = _FakeCore(fake_tasks)
    watcher = DBWatcher(core)  # type: ignore[arg-type]
    await watcher.initialize()

    event = BoardEvent(task_id="t1", kind="created", title="New Task", status="backlog")
    await watcher._handle_event(event)

    assert "t1" in watcher._snapshot
    assert watcher._snapshot["t1"].updated_at == "2026-01-01T00:10:00"


@pytest.mark.asyncio
async def test_event_handler_syncs_snapshot_on_updated() -> None:
    """After handling an 'updated' event, snapshot reflects new updated_at."""
    initial = [_task("t1", "Task A", "backlog", "2026-01-01T00:00:00")]
    updated_task = _task("t1", "Task A v2", "backlog", "2026-01-01T00:15:00")

    fake_tasks = _FakeTasks(initial)
    fake_tasks._get_store["t1"] = updated_task
    core = _FakeCore(fake_tasks)
    watcher = DBWatcher(core)  # type: ignore[arg-type]
    await watcher.initialize()

    event = BoardEvent(task_id="t1", kind="updated", title="Task A v2")
    await watcher._handle_event(event)

    assert watcher._snapshot["t1"].updated_at == "2026-01-01T00:15:00"
    assert watcher._snapshot["t1"].title == "Task A v2"


@pytest.mark.asyncio
async def test_event_handler_syncs_snapshot_on_status_changed() -> None:
    """After handling a 'status_changed' event, snapshot reflects new updated_at."""
    initial = [_task("t1", "Task A", "backlog", "2026-01-01T00:00:00")]
    changed_task = _task("t1", "Task A", "in_progress", "2026-01-01T00:20:00")

    fake_tasks = _FakeTasks(initial)
    fake_tasks._get_store["t1"] = changed_task
    core = _FakeCore(fake_tasks)
    watcher = DBWatcher(core)  # type: ignore[arg-type]
    await watcher.initialize()

    event = BoardEvent(
        task_id="t1",
        kind="status_changed",
        from_status="backlog",
        to_status="in_progress",
    )
    await watcher._handle_event(event)

    assert watcher._snapshot["t1"].updated_at == "2026-01-01T00:20:00"
    assert watcher._snapshot["t1"].status == "in_progress"


# ── Event stream resilience tests ─────────────────────────────────────


@pytest.mark.asyncio
async def test_consume_events_retries_on_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """_consume_events retries after stream failure instead of dying."""
    monkeypatch.setattr(DBWatcher, "_EVENT_STREAM_RETRY_DELAY", 0.01)

    call_count = 0
    received_events: list[BoardEvent] = []

    async def _fake_stream() -> AsyncIterator[BoardEvent]:
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            raise RuntimeError("stream failed")
        yield BoardEvent(task_id="t1", kind="updated")

    initial = [_task("t1", "Task A", "backlog", "2026-01-01T00:00:00")]
    fake_tasks = _FakeTasks(initial)
    fake_tasks._get_store["t1"] = initial[0]
    core = _FakeCore(fake_tasks)
    watcher = DBWatcher(core)  # type: ignore[arg-type]
    await watcher.initialize()

    # Monkey-patch the stream_board method
    watcher._core.tasks.events.stream_board = _fake_stream  # type: ignore[assignment]

    # Run _consume_events with a timeout — it should retry and process events
    consume_task = asyncio.create_task(watcher._consume_events())
    try:
        await asyncio.sleep(0.1)
    finally:
        consume_task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await consume_task

    # The stream was called at least twice: first failed, then retried
    assert call_count >= 2
