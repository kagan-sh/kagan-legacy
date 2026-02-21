from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

from kagan.core.bootstrap import InMemoryEventBus
from kagan.core.commands import automation as automation_commands
from kagan.core.events import TaskUpdated


def _ctx(event_bus: InMemoryEventBus) -> SimpleNamespace:
    config = SimpleNamespace(
        general=SimpleNamespace(
            tasks_wait_default_timeout_seconds=0.25,
            tasks_wait_max_timeout_seconds=5.0,
        )
    )
    return SimpleNamespace(
        api=SimpleNamespace(),
        config=config,
        event_bus=event_bus,
    )


async def test_task_wait_any_returns_timeout_when_no_events_arrive() -> None:
    event_bus = InMemoryEventBus()

    result = await automation_commands.handle_task_wait_any(
        _ctx(event_bus),
        {"timeout_seconds": 0.01},
    )

    assert result["changed"] is False
    assert result["timed_out"] is True
    assert result["code"] == "WAIT_TIMEOUT"


async def test_task_wait_any_returns_changed_on_task_event() -> None:
    event_bus = InMemoryEventBus()
    ctx = _ctx(event_bus)

    async def _publish_event() -> None:
        await asyncio.sleep(0.01)
        await event_bus.publish(
            TaskUpdated(
                task_id="task-123",
                fields_changed=["status"],
                updated_at=datetime(2026, 2, 20, 12, 0, tzinfo=UTC),
            )
        )

    publisher = asyncio.create_task(_publish_event())
    result = await automation_commands.handle_task_wait_any(ctx, {"timeout_seconds": 0.5})
    await publisher

    assert result["changed"] is True
    assert result["timed_out"] is False
    assert result["task_id"] == "task-123"
    assert result["event_type"] == "task_updated"
    assert result["code"] == "TASK_EVENT"
