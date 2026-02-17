"""Unit tests for handle_task_wait request handler."""

from __future__ import annotations

import asyncio


async def test_task_wait_not_found(api_env):
    """tasks.wait returns TASK_NOT_FOUND for missing task with recovery hint."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    result = await handle_task_wait(ctx, {"task_id": "nonexistent"})
    assert result["success"] is False
    assert result["code"] == "TASK_NOT_FOUND"
    assert "task_list" in result["message"]


async def test_task_wait_invalid_timeout_bool(api_env):
    """tasks.wait rejects boolean timeout_seconds."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": True})
    assert result["code"] == "INVALID_TIMEOUT"
    assert result["changed"] is False


async def test_task_wait_invalid_timeout_negative(api_env):
    """tasks.wait rejects negative timeout_seconds."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": -1})
    assert result["code"] == "INVALID_TIMEOUT"


async def test_task_wait_timeout_exceeds_max(api_env):
    """tasks.wait rejects timeout_seconds exceeding server max."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": 9999})
    assert result["code"] == "INVALID_TIMEOUT"
    assert "exceeds" in result["message"]


async def test_task_wait_invalid_status_filter(api_env):
    """tasks.wait rejects invalid wait_for_status values."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    result = await handle_task_wait(
        ctx, {"task_id": task.id, "wait_for_status": ["INVALID_STATUS"]}
    )
    assert result["code"] == "INVALID_PARAMS"


async def test_task_wait_already_at_status(api_env):
    """tasks.wait returns immediately if task already at target status."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    # Task starts at BACKLOG
    result = await handle_task_wait(ctx, {"task_id": task.id, "wait_for_status": ["BACKLOG"]})
    assert result["changed"] is True
    assert result["timed_out"] is False
    assert result["code"] == "ALREADY_AT_STATUS"
    assert result["current_status"] == "BACKLOG"
    assert result["task"] is not None
    assert result["task"]["id"] == task.id


async def test_task_wait_race_safe_changed_since_cursor(api_env):
    """tasks.wait detects change since from_updated_at cursor."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    # Use a stale cursor
    result = await handle_task_wait(
        ctx,
        {
            "task_id": task.id,
            "from_updated_at": "2020-01-01T00:00:00+00:00",
        },
    )
    assert result["changed"] is True
    assert result["code"] == "CHANGED_SINCE_CURSOR"


async def test_task_wait_timeout(api_env):
    """tasks.wait returns timed_out=True after timeout elapses."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": 0.05})
    assert result["timed_out"] is True
    assert result["changed"] is False
    assert result["code"] == "WAIT_TIMEOUT"
    assert result["previous_status"] == "BACKLOG"


async def test_task_wait_event_driven_wakeup(api_env):
    """tasks.wait wakes up on TaskStatusChanged event."""
    from kagan.core.commands.automation import handle_task_wait
    from kagan.core.domain.enums import TaskStatus

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")

    async def _change_status_after_delay():
        await asyncio.sleep(0.05)
        await api.move_task(task.id, TaskStatus.IN_PROGRESS)

    change_task = asyncio.create_task(_change_status_after_delay())
    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": 5})
    await change_task

    assert result["changed"] is True
    assert result["timed_out"] is False
    assert result["code"] == "TASK_CHANGED"
    assert result["current_status"] == "IN_PROGRESS"
    assert result["task"] is not None


async def test_task_wait_does_not_miss_status_change_during_initial_read(api_env, monkeypatch):
    """tasks.wait should not lose updates that happen during the initial state read."""
    from kagan.core.commands.automation import handle_task_wait
    from kagan.core.domain.enums import TaskStatus

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Race-safe wait", "desc")
    original_get_task = api.get_task
    first_read = True

    async def _delayed_get_task(task_id: str):
        nonlocal first_read
        if first_read:
            first_read = False
            await asyncio.sleep(0.08)
        return await original_get_task(task_id)

    monkeypatch.setattr(api, "get_task", _delayed_get_task)

    async def _change_status_during_read_window():
        await asyncio.sleep(0.02)
        await api.move_task(task.id, TaskStatus.IN_PROGRESS)

    change_task = asyncio.create_task(_change_status_during_read_window())
    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": 0.4})
    await change_task

    assert result["changed"] is True
    assert result["timed_out"] is False
    assert result["code"] == "TASK_CHANGED"
    assert result["current_status"] == "IN_PROGRESS"


async def test_task_wait_status_filter_waits_for_target(api_env):
    """tasks.wait with status filter ignores non-matching transitions."""
    from kagan.core.commands.automation import handle_task_wait
    from kagan.core.domain.enums import TaskStatus

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")

    async def _move_through_statuses():
        await asyncio.sleep(0.05)
        # Move to IN_PROGRESS (not target)
        await api.move_task(task.id, TaskStatus.IN_PROGRESS)
        await asyncio.sleep(0.05)
        # Move to REVIEW (target)
        await api.move_task(task.id, TaskStatus.REVIEW)

    change_task = asyncio.create_task(_move_through_statuses())
    result = await handle_task_wait(
        ctx,
        {
            "task_id": task.id,
            "wait_for_status": ["REVIEW", "DONE"],
            "timeout_seconds": 5,
        },
    )
    await change_task

    assert result["changed"] is True
    assert result["current_status"] == "REVIEW"


async def test_task_wait_ignores_non_status_updates(api_env):
    """tasks.wait should not wake on TaskUpdated when status is unchanged."""
    from kagan.core.commands.automation import handle_task_wait
    from kagan.core.events import TaskUpdated
    from kagan.core.time import utc_now

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")

    async def _emit_update_after_delay():
        await asyncio.sleep(0.05)
        await ctx.event_bus.publish(
            TaskUpdated(
                task_id=task.id,
                fields_changed=["description"],
                updated_at=utc_now(),
            )
        )

    emit_task = asyncio.create_task(_emit_update_after_delay())
    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": 0.12})
    await emit_task

    assert result["changed"] is False
    assert result["timed_out"] is True
    assert result["code"] == "WAIT_TIMEOUT"


async def test_task_wait_handler_cleanup_on_timeout(api_env):
    """Handler removes event listener after timeout."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")

    bus = ctx.event_bus
    added_handlers: list[object] = []
    removed_handlers: list[object] = []
    original_add_handler = bus.add_handler
    original_remove_handler = bus.remove_handler

    def _track_add(handler: object) -> None:
        added_handlers.append(handler)
        original_add_handler(handler)

    def _track_remove(handler: object) -> None:
        removed_handlers.append(handler)
        original_remove_handler(handler)

    bus.add_handler = _track_add  # type: ignore[method-assign]
    bus.remove_handler = _track_remove  # type: ignore[method-assign]
    try:
        result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": 0.05})
    finally:
        bus.add_handler = original_add_handler  # type: ignore[method-assign]
        bus.remove_handler = original_remove_handler  # type: ignore[method-assign]

    assert result["timed_out"] is True
    assert len(added_handlers) == 1
    assert removed_handlers == added_handlers


async def test_task_wait_task_deleted_during_wait(api_env):
    """tasks.wait returns TASK_DELETED when task is deleted during wait."""
    from kagan.core.commands.automation import handle_task_wait
    from kagan.core.events import TaskDeleted

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")

    async def _emit_delete_after_delay():
        await asyncio.sleep(0.05)
        await ctx.event_bus.publish(TaskDeleted(task_id=task.id))

    emit_task = asyncio.create_task(_emit_delete_after_delay())
    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": 5})
    await emit_task

    assert result["changed"] is True
    assert result["code"] == "TASK_DELETED"
    assert result["task"] is None


async def test_task_wait_default_timeout_from_config(api_env):
    """tasks.wait uses configured default timeout when none specified."""
    from kagan.core.commands.automation import handle_task_wait
    from kagan.core.domain.enums import TaskStatus

    _, api, ctx = api_env
    ctx.api = api
    ctx.config.general.tasks_wait_default_timeout_seconds = 1
    ctx.config.general.tasks_wait_max_timeout_seconds = 1
    task = await api.create_task("Wait test", "desc")

    async def _change_status_after_delay():
        await asyncio.sleep(0.05)
        await api.move_task(task.id, TaskStatus.IN_PROGRESS)

    change_task = asyncio.create_task(_change_status_after_delay())
    result = await handle_task_wait(ctx, {"task_id": task.id})
    await change_task

    assert result["changed"] is True
    assert result["timed_out"] is False
    assert result["current_status"] == "IN_PROGRESS"


async def test_task_wait_non_list_status_filter(api_env):
    """tasks.wait rejects unsupported wait_for_status types."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    result = await handle_task_wait(ctx, {"task_id": task.id, "wait_for_status": 123})
    assert result["code"] == "INVALID_PARAMS"
    assert "wait_for_status" in result["message"]


async def test_task_wait_accepts_timeout_string(api_env):
    """tasks.wait accepts numeric timeout_seconds sent as string."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": "0.05"})
    assert result["timed_out"] is True
    assert result["code"] == "WAIT_TIMEOUT"


async def test_task_wait_accepts_csv_status_filter(api_env):
    """tasks.wait accepts comma-separated wait_for_status strings."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    result = await handle_task_wait(ctx, {"task_id": task.id, "wait_for_status": "BACKLOG,REVIEW"})
    assert result["changed"] is True
    assert result["code"] == "ALREADY_AT_STATUS"
    assert result["current_status"] == "BACKLOG"


async def test_task_wait_accepts_json_status_filter_string(api_env):
    """tasks.wait accepts JSON list strings for wait_for_status."""
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")
    result = await handle_task_wait(ctx, {"task_id": task.id, "wait_for_status": '["BACKLOG"]'})
    assert result["changed"] is True
    assert result["code"] == "ALREADY_AT_STATUS"


async def test_task_wait_normalizes_empty_status_filter_to_wait_for_any_status(api_env):
    """tasks.wait treats empty wait_for_status payloads as no status filter."""
    from kagan.core.commands.automation import handle_task_wait
    from kagan.core.domain.enums import TaskStatus

    _, api, ctx = api_env
    ctx.api = api

    for empty_filter in ([], "[]"):
        task = await api.create_task("Wait test", "desc")

        async def _change_status_after_delay(task_id: str) -> None:
            await asyncio.sleep(0.05)
            await api.move_task(task_id, TaskStatus.IN_PROGRESS)

        change_task = asyncio.create_task(_change_status_after_delay(task.id))
        result = await handle_task_wait(
            ctx,
            {"task_id": task.id, "wait_for_status": empty_filter, "timeout_seconds": 0.4},
        )
        await change_task

        assert result["changed"] is True
        assert result["timed_out"] is False
        assert result["code"] == "TASK_CHANGED"
        assert result["current_status"] == "IN_PROGRESS"


async def test_task_wait_returns_window_continuation_for_long_timeout(api_env, monkeypatch):
    """tasks.wait returns WAIT_WINDOW when timeout exceeds the transport-safe window."""
    import kagan.core.commands.automation as rh
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")

    # Shrink the window so the test finishes quickly.
    monkeypatch.setattr(rh, "_MAX_WAIT_WINDOW_SECONDS", 0.05)

    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": 0.2})

    assert result["changed"] is False
    assert result["timed_out"] is False
    assert result["code"] == "WAIT_WINDOW"
    assert result["changed_at"] == task.updated_at.isoformat()
    assert result["remaining_seconds"] > 0
    assert result["elapsed_seconds"] > 0
    assert "Re-call task_wait" in result["message"]


async def test_task_wait_short_timeout_returns_timeout_not_window(api_env, monkeypatch):
    """tasks.wait with timeout <= window returns WAIT_TIMEOUT, not WAIT_WINDOW."""
    import kagan.core.commands.automation as rh
    from kagan.core.commands.automation import handle_task_wait

    _, api, ctx = api_env
    ctx.api = api
    task = await api.create_task("Wait test", "desc")

    # Window is larger than the timeout, so no chunking happens.
    monkeypatch.setattr(rh, "_MAX_WAIT_WINDOW_SECONDS", 1.0)

    result = await handle_task_wait(ctx, {"task_id": task.id, "timeout_seconds": 0.05})

    assert result["timed_out"] is True
    assert result["code"] == "WAIT_TIMEOUT"
    assert result["code"] != "WAIT_WINDOW"
