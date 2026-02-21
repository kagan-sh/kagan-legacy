from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core.commands._responses import (
    CommandCode,
    error_response,
    require_non_empty_param,
)
from kagan.core.commands._serialization import execution_log_entry_to_dict, execution_to_dict
from kagan.core.commands.automation_shared import api_from_context
from kagan.core.policy import command

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


@command(
    "automation",
    "get_execution",
    profile="pair_worker",
    description="Get an execution record by ID.",
)
async def handle_automation_get_execution(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    execution_id, execution_id_error = require_non_empty_param(params, "execution_id")
    if execution_id_error is not None:
        return execution_id_error

    assert execution_id is not None
    execution = await api.get_execution(execution_id)
    if execution is None:
        return error_response(
            message="Execution not found",
            code=CommandCode.NOT_FOUND,
            execution_id=execution_id,
        )
    return {"success": True, "execution": execution_to_dict(execution)}


@command(
    "automation",
    "get_execution_log_entries",
    profile="pair_worker",
    description="Get ordered execution log entries for an execution.",
)
async def handle_automation_get_execution_log_entries(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    execution_id, execution_id_error = require_non_empty_param(params, "execution_id")
    if execution_id_error is not None:
        return execution_id_error

    assert execution_id is not None
    entries = await api.get_execution_log_entries(execution_id)
    return {
        "success": True,
        "entries": [execution_log_entry_to_dict(entry) for entry in entries],
        "count": len(entries),
    }


@command(
    "automation",
    "get_latest_execution_for_task",
    profile="pair_worker",
    description="Get the most recent execution for a task.",
)
async def handle_automation_get_latest_execution(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    task_id, task_id_error = require_non_empty_param(params, "task_id")
    if task_id_error is not None:
        return task_id_error

    assert task_id is not None
    execution = await api.get_latest_execution_for_task(task_id)
    if execution is None:
        return {
            "success": True,
            "task_id": task_id,
            "execution": None,
            "message": "No executions found",
            "code": CommandCode.NO_EXECUTIONS.value,
        }
    return {"success": True, "task_id": task_id, "execution": execution_to_dict(execution)}


@command(
    "automation",
    "count_executions_for_task",
    profile="pair_worker",
    description="Return total execution count for a task.",
)
async def handle_automation_count_executions(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    task_id, task_id_error = require_non_empty_param(params, "task_id")
    if task_id_error is not None:
        return task_id_error

    assert task_id is not None
    count = await api.count_executions_for_task(task_id)
    return {"success": True, "task_id": task_id, "count": count}


__all__ = [
    "handle_automation_count_executions",
    "handle_automation_get_execution",
    "handle_automation_get_execution_log_entries",
    "handle_automation_get_latest_execution",
]
