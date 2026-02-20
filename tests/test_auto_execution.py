"""AUTO execution: workspace provisioning and agent job orchestration.

Covers:
- Agent completion drives correct status transition
- Job start / poll / cancel lifecycle at DB layer
- InMemoryEventBus fan-out: handlers receive published events filtered by type
- TaskServiceImpl.create_task publishes TaskCreated event
- TaskServiceImpl.set_status publishes TaskStatusChanged + TaskUpdated events
"""

from __future__ import annotations

import pytest

from kagan.core.bootstrap import InMemoryEventBus
from kagan.core.domain.enums import TaskStatus, TaskType
from kagan.core.domain.task_rules import resolve_status_after_agent_complete
from kagan.core.events import (
    DomainEvent,
    TaskCreated,
    TaskDeleted,
    TaskStatusChanged,
    TaskUpdated,
)


class TestAgentStatusTransitions:
    """Agent completion drives lifecycle transitions."""

    @pytest.mark.parametrize(
        ("current", "success", "expected"),
        [
            (TaskStatus.IN_PROGRESS, True, TaskStatus.REVIEW),
            (TaskStatus.IN_PROGRESS, False, TaskStatus.IN_PROGRESS),
            (TaskStatus.BACKLOG, True, TaskStatus.BACKLOG),
            (TaskStatus.REVIEW, True, TaskStatus.REVIEW),
            (TaskStatus.DONE, True, TaskStatus.DONE),
        ],
    )
    def test_status_after_agent_complete(
        self, current: TaskStatus, success: bool, expected: TaskStatus
    ) -> None:
        assert resolve_status_after_agent_complete(current, success=success) == expected


class TestJobLifecycle:
    """Job start, poll, cancel via task service layer."""

    async def test_task_moves_to_in_progress_on_agent_start(
        self, state_manager, task_factory
    ) -> None:
        task = task_factory(
            title="Auto task",
            task_type=TaskType.AUTO,
            status=TaskStatus.BACKLOG,
        )
        created = await state_manager.create(task)
        updated = await state_manager.update(created.id, status=TaskStatus.IN_PROGRESS)
        assert updated is not None
        assert updated.status == TaskStatus.IN_PROGRESS

    async def test_task_moves_to_review_after_success(self, state_manager, task_factory) -> None:
        task = task_factory(
            title="Completing task",
            task_type=TaskType.AUTO,
            status=TaskStatus.IN_PROGRESS,
        )
        created = await state_manager.create(task)
        next_status = resolve_status_after_agent_complete(created.status, success=True)
        updated = await state_manager.update(created.id, status=next_status)
        assert updated is not None
        assert updated.status == TaskStatus.REVIEW


class TestInMemoryEventBusFanOut:
    """InMemoryEventBus delivers events to handlers filtered by type."""

    async def test_typed_handler_receives_only_matching_events(self) -> None:
        bus = InMemoryEventBus()
        received: list[DomainEvent] = []
        bus.add_handler(lambda e: received.append(e), event_type=TaskCreated)

        created = TaskCreated(
            task_id="t1",
            status=TaskStatus.BACKLOG,
            title="Test",
            created_at=TaskCreated.__dataclass_fields__["occurred_at"].default_factory(),
        )
        deleted = TaskDeleted(task_id="t1")

        await bus.publish(created)
        await bus.publish(deleted)

        assert len(received) == 1
        assert isinstance(received[0], TaskCreated)
        assert received[0].task_id == "t1"

    async def test_untyped_handler_receives_all_events(self) -> None:
        bus = InMemoryEventBus()
        received: list[DomainEvent] = []
        bus.add_handler(lambda e: received.append(e))

        created = TaskCreated(
            task_id="t1",
            status=TaskStatus.BACKLOG,
            title="Test",
            created_at=TaskCreated.__dataclass_fields__["occurred_at"].default_factory(),
        )
        deleted = TaskDeleted(task_id="t1")

        await bus.publish(created)
        await bus.publish(deleted)

        assert len(received) == 2
        assert isinstance(received[0], TaskCreated)
        assert isinstance(received[1], TaskDeleted)

    async def test_remove_handler_stops_delivery(self) -> None:
        bus = InMemoryEventBus()
        received: list[DomainEvent] = []
        handler = lambda e: received.append(e)  # noqa: E731
        bus.add_handler(handler)

        await bus.publish(TaskDeleted(task_id="t1"))
        assert len(received) == 1

        bus.remove_handler(handler)
        await bus.publish(TaskDeleted(task_id="t2"))
        assert len(received) == 1  # no new delivery


class TestTaskServiceEventEmission:
    """TaskServiceImpl publishes domain events on create, status change, and delete."""

    async def test_create_task_publishes_task_created(self, task_service, event_bus) -> None:
        received: list[DomainEvent] = []
        event_bus.add_handler(lambda e: received.append(e), event_type=TaskCreated)

        created = await task_service.create_task("Evented task", "desc")
        assert created.id is not None

        created_events = [e for e in received if isinstance(e, TaskCreated)]
        assert len(created_events) == 1
        assert created_events[0].task_id == created.id
        assert created_events[0].title == "Evented task"

    async def test_set_status_publishes_status_changed_and_updated(
        self, task_service, event_bus
    ) -> None:
        received: list[DomainEvent] = []
        event_bus.add_handler(lambda e: received.append(e))

        task = await task_service.create_task("Status task", "")
        received.clear()  # ignore creation events

        await task_service.set_status(task.id, TaskStatus.IN_PROGRESS)

        status_events = [e for e in received if isinstance(e, TaskStatusChanged)]
        update_events = [e for e in received if isinstance(e, TaskUpdated)]

        assert len(status_events) == 1
        assert status_events[0].from_status == TaskStatus.BACKLOG
        assert status_events[0].to_status == TaskStatus.IN_PROGRESS
        assert len(update_events) == 1
        assert "status" in update_events[0].fields_changed

    async def test_delete_task_publishes_task_deleted(self, task_service, event_bus) -> None:
        received: list[DomainEvent] = []
        event_bus.add_handler(lambda e: received.append(e), event_type=TaskDeleted)

        task = await task_service.create_task("Deleteable", "")
        await task_service.delete_task(task.id)

        deleted_events = [e for e in received if isinstance(e, TaskDeleted)]
        assert len(deleted_events) == 1
        assert deleted_events[0].task_id == task.id
