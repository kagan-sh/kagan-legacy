"""Task service CRUD and Wire protocol tests.

Covers:
- Task service CRUD through service layer
- Wire merged vs raw subscribers (StreamChunk coalescing)
- WireEventEnvelope round-trip serialization
"""

from __future__ import annotations

import pytest

from kagan.core.domain.enums import TaskStatus
from kagan.core.wire.events import (
    AgentCompleted,
    AgentStatus,
    JobStarted,
    PRCreated,
    StreamChunk,
    TaskTransitioned,
    WireEventEnvelope,
)
from kagan.core.wire.transport import Wire


class TestTaskServiceCRUD:
    """Task service CRUD through the service layer."""

    async def test_create_and_list_via_service(self, task_service) -> None:
        created = await task_service.create_task(
            "CLI-created task",
            "Created from TUI workflow",
        )
        assert created.id is not None
        assert created.title == "CLI-created task"

        fetched = await task_service.get_task(created.id)
        assert fetched is not None
        assert fetched.title == "CLI-created task"

    async def test_set_status_via_service(self, task_service) -> None:
        created = await task_service.create_task("Moveable", "")
        updated = await task_service.set_status(created.id, TaskStatus.IN_PROGRESS)
        assert updated is not None
        assert updated.status == TaskStatus.IN_PROGRESS

    async def test_update_fields_via_service(self, task_service) -> None:
        created = await task_service.create_task("Editable", "")
        updated = await task_service.update_fields(created.id, title="Edited title")
        assert updated is not None
        assert updated.title == "Edited title"

    async def test_delete_via_service(self, task_service) -> None:
        created = await task_service.create_task("Deleteable", "")
        result = await task_service.delete_task(created.id)
        assert result is True
        fetched = await task_service.get_task(created.id)
        assert fetched is None


class TestTaskServiceListAndSearch:
    """Task service list, filter by status, and search operations."""

    async def test_list_all_tasks(self, task_service) -> None:
        await task_service.create_task("Task A", "")
        await task_service.create_task("Task B", "")
        tasks = await task_service.list_tasks()
        assert len(tasks) >= 2

    async def test_list_tasks_by_status(self, task_service) -> None:
        t1 = await task_service.create_task("Backlog task", "")
        t2 = await task_service.create_task("IP task", "")
        await task_service.set_status(t2.id, TaskStatus.IN_PROGRESS)

        backlog = await task_service.list_tasks(status=TaskStatus.BACKLOG)
        assert any(t.id == t1.id for t in backlog)
        # t2 should not be in BACKLOG anymore
        assert not any(t.id == t2.id for t in backlog)

    async def test_get_by_status(self, task_service) -> None:
        created = await task_service.create_task("Status filter", "")
        # Default status is BACKLOG
        results = await task_service.get_by_status(TaskStatus.BACKLOG)
        assert any(t.id == created.id for t in results)

    async def test_search_by_title(self, task_service) -> None:
        await task_service.create_task("Unique search target XYZ", "")
        results = await task_service.search("XYZ")
        assert len(results) >= 1
        assert any("XYZ" in t.title for t in results)


class TestTaskServiceScratchpad:
    """Task service scratchpad read/write via service layer."""

    async def test_scratchpad_via_service(self, task_service) -> None:
        task = await task_service.create_task("Noted task", "")
        await task_service.update_scratchpad(task.id, "Agent note: tests passing")
        content = await task_service.get_scratchpad(task.id)
        assert "Agent note: tests passing" in content

    async def test_scratchpad_empty_default(self, task_service) -> None:
        task = await task_service.create_task("Empty scratch", "")
        content = await task_service.get_scratchpad(task.id)
        assert content == ""


class TestTaskServiceAgentSync:
    """sync_status_from_agent_complete drives transitions via service."""

    async def test_success_moves_to_review(self, task_service) -> None:
        task = await task_service.create_task("Sync test", "")
        await task_service.set_status(task.id, TaskStatus.IN_PROGRESS)
        result = await task_service.sync_status_from_agent_complete(task.id, success=True)
        assert result is not None
        assert result.status == TaskStatus.REVIEW

    async def test_failure_stays_in_progress(self, task_service) -> None:
        task = await task_service.create_task("Fail test", "")
        await task_service.set_status(task.id, TaskStatus.IN_PROGRESS)
        result = await task_service.sync_status_from_agent_complete(task.id, success=False)
        assert result is not None
        assert result.status == TaskStatus.IN_PROGRESS

    async def test_nonexistent_task_returns_none(self, task_service) -> None:
        result = await task_service.sync_status_from_agent_complete("nonexistent", success=True)
        assert result is None


class TestWireMergedVsRaw:
    """Wire merged subscribers coalesce StreamChunks; raw get every event."""

    def test_raw_subscriber_receives_every_chunk_individually(self) -> None:
        wire = Wire()
        raw = wire.subscribe(merge=False)

        wire.emit(StreamChunk(task_id="t1", text="Hello"))
        wire.emit(StreamChunk(task_id="t1", text=" world"))
        wire.emit(AgentStatus(task_id="t1", status="ready"))

        events = []
        while (evt := raw.receive_nowait()) is not None:
            events.append(evt)

        chunks = [e for e in events if isinstance(e, StreamChunk)]
        assert len(chunks) == 2
        assert chunks[0].text == "Hello"
        assert chunks[1].text == " world"

    def test_merged_subscriber_coalesces_same_task_chunks(self) -> None:
        wire = Wire()
        merged = wire.subscribe(merge=True)

        wire.emit(StreamChunk(task_id="t1", text="Hello"))
        wire.emit(StreamChunk(task_id="t1", text=" world"))
        # Flush to push merged buffer
        wire.soul_side.flush()

        events = []
        while (evt := merged.receive_nowait()) is not None:
            events.append(evt)

        chunks = [e for e in events if isinstance(e, StreamChunk)]
        assert len(chunks) == 1
        assert chunks[0].text == "Hello world"

    def test_merged_flushes_on_non_chunk_event(self) -> None:
        wire = Wire()
        merged = wire.subscribe(merge=True)

        wire.emit(StreamChunk(task_id="t1", text="part1"))
        wire.emit(StreamChunk(task_id="t1", text="part2"))
        wire.emit(AgentStatus(task_id="t1", status="thinking"))

        events = []
        while (evt := merged.receive_nowait()) is not None:
            events.append(evt)

        # Should have: coalesced StreamChunk + AgentStatus
        chunks = [e for e in events if isinstance(e, StreamChunk)]
        statuses = [e for e in events if isinstance(e, AgentStatus)]
        assert len(chunks) == 1
        assert chunks[0].text == "part1part2"
        assert len(statuses) == 1

    def test_different_task_ids_break_merge(self) -> None:
        wire = Wire()
        merged = wire.subscribe(merge=True)

        wire.emit(StreamChunk(task_id="t1", text="A"))
        wire.emit(StreamChunk(task_id="t2", text="B"))
        wire.soul_side.flush()

        events = []
        while (evt := merged.receive_nowait()) is not None:
            events.append(evt)

        chunks = [e for e in events if isinstance(e, StreamChunk)]
        assert len(chunks) == 2
        assert chunks[0].text == "A"
        assert chunks[1].text == "B"


class TestWireEventEnvelopeRoundTrip:
    """WireEventEnvelope serialization: from_wire_event → to_wire_event round-trip."""

    @pytest.mark.parametrize(
        "event",
        [
            StreamChunk(task_id="t1", text="Hello world"),
            AgentStatus(task_id="t1", status="thinking", tokens_used=42),
            AgentCompleted(task_id="t1", outcome="success"),
            TaskTransitioned(task_id="t1", from_status="BACKLOG", to_status="IN_PROGRESS"),
            JobStarted(task_id="t1", job_id="job-abc"),
            PRCreated(task_id="t1", pr_number=123, url="https://github.com/org/repo/pull/123"),
        ],
        ids=[
            "StreamChunk",
            "AgentStatus",
            "AgentCompleted",
            "TaskTransitioned",
            "JobStarted",
            "PRCreated",
        ],
    )
    def test_round_trip_preserves_type_and_fields(self, event) -> None:
        envelope = WireEventEnvelope.from_wire_event(event)
        assert envelope.type == type(event).__name__

        restored = envelope.to_wire_event()
        assert type(restored) is type(event)
        # Compare model data (excludes timestamp precision differences)
        original_data = event.model_dump(exclude={"timestamp"})
        restored_data = restored.model_dump(exclude={"timestamp"})
        assert original_data == restored_data

    def test_unknown_type_raises_on_deserialize(self) -> None:
        envelope = WireEventEnvelope(type="NonExistentEvent", payload={})
        with pytest.raises(ValueError, match="Unknown wire event type"):
            envelope.to_wire_event()
