from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from kagan.core.commands._parsing import parse_runtime_session_event
from kagan.core.commands._responses import (
    CommandCode,
    error_response,
    invalid_params_response,
    require_non_empty_param,
)
from kagan.core.commands._serialization import (
    runtime_context_to_dict,
    runtime_view_to_dict,
    startup_decision_to_dict,
)
from kagan.core.commands.automation_shared import api_from_context
from kagan.core.policy import command
from kagan.core.scalars import non_empty_str

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


@command(
    "automation",
    "is_automation_running",
    profile="pair_worker",
    description="Check if automation is running for a task.",
)
async def handle_automation_is_running(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    task_id, task_id_error = require_non_empty_param(params, "task_id")
    if task_id_error is not None:
        return task_id_error

    assert task_id is not None
    is_running = api.is_automation_running(task_id)
    return {"success": True, "task_id": task_id, "is_running": is_running}


@command(
    "automation",
    "decide_startup",
    profile="operator",
    description="Determine startup flow based on persisted runtime state and cwd.",
)
async def handle_automation_decide_startup(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    cwd_raw, cwd_error = require_non_empty_param(params, "cwd")
    if cwd_error is not None:
        return cwd_error

    assert cwd_raw is not None
    decision = await api.decide_startup(Path(cwd_raw))
    return {"success": True, **startup_decision_to_dict(decision)}


@command(
    "automation",
    "get_running_task_ids",
    profile="pair_worker",
    description="Return the set of currently running task IDs.",
)
async def handle_automation_get_running_task_ids(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    del params
    task_ids = api.get_running_task_ids()
    return {"success": True, "task_ids": sorted(task_ids), "count": len(task_ids)}


@command(
    "automation",
    "get_runtime_view",
    profile="pair_worker",
    description="Get the runtime task view for a task.",
)
async def handle_automation_get_runtime_view(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    task_id, task_id_error = require_non_empty_param(params, "task_id")
    if task_id_error is not None:
        return task_id_error

    assert task_id is not None
    view = api.get_runtime_view(task_id)
    runtime_service = getattr(ctx, "runtime_service", None)
    return {
        "success": True,
        **runtime_view_to_dict(task_id=task_id, view=view, runtime_service=runtime_service),
    }


@command(
    "automation",
    "reconcile_running_tasks",
    profile="operator",
    mutating=True,
    description="Synchronize runtime task projections and return refreshed snapshots.",
)
async def handle_automation_reconcile_running_tasks(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    task_ids_raw = params.get("task_ids")
    if not isinstance(task_ids_raw, list):
        return invalid_params_response("task_ids must be a list")

    task_ids = [str(task_id) for task_id in task_ids_raw]
    snapshots = await api.reconcile_running_tasks(task_ids)
    return {"success": True, "tasks": snapshots, "count": len(snapshots)}


@command(
    "automation",
    "dispatch_runtime_session",
    profile="operator",
    mutating=True,
    description="Dispatch a runtime session event.",
)
async def handle_automation_dispatch_runtime_session(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = api_from_context(ctx)
    event_raw = params.get("event")
    event = parse_runtime_session_event(event_raw)
    if event is None:
        return error_response(
            message=(
                f"Invalid event: {event_raw!r}. "
                "Use one of: project_selected, repo_selected, repo_cleared, reset"
            ),
            code=CommandCode.INVALID_EVENT,
        )

    project_id = non_empty_str(params.get("project_id"))
    repo_id = non_empty_str(params.get("repo_id"))
    state = await api.dispatch_runtime_session(event, project_id=project_id, repo_id=repo_id)
    return {"success": True, **runtime_context_to_dict(state)}


__all__ = [
    "handle_automation_decide_startup",
    "handle_automation_dispatch_runtime_session",
    "handle_automation_get_running_task_ids",
    "handle_automation_get_runtime_view",
    "handle_automation_is_running",
    "handle_automation_reconcile_running_tasks",
]
