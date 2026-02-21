from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, cast

from kagan.core.commands._exception_boundary import map_command_exceptions
from kagan.core.commands._parsing import (
    ParseError,
    parse_events_limit,
    parse_events_offset,
    parse_timeout_seconds,
    parse_wait_for_status_filter,
    parse_wait_timeout_seconds,
    str_object_dict,
)
from kagan.core.commands._responses import CommandCode
from kagan.core.commands._serialization import (
    SESSION_PROMPT_PATH,
    build_handoff_payload,
    build_job_response,
    invalid_job_id_response,
    invalid_task_id_response,
    job_not_found_response,
    parse_requested_worktree,
    resolve_pair_backend,
    session_create_error_response,
)
from kagan.core.commands.automation_execution import (
    handle_automation_count_executions,
    handle_automation_get_execution,
    handle_automation_get_execution_log_entries,
    handle_automation_get_latest_execution,
)
from kagan.core.commands.automation_queue import (
    handle_automation_get_queue_status,
    handle_automation_get_queued_messages,
    handle_automation_queue_message,
    handle_automation_remove_queued_message,
    handle_automation_take_queued_message,
)
from kagan.core.commands.automation_runtime import (
    handle_automation_decide_startup,
    handle_automation_dispatch_runtime_session,
    handle_automation_get_running_task_ids,
    handle_automation_get_runtime_view,
    handle_automation_is_running,
    handle_automation_reconcile_running_tasks,
)
from kagan.core.commands.automation_shared import api_from_context
from kagan.core.commands.job_action_executor import SUPPORTED_JOB_ACTIONS
from kagan.core.domain.errors import task_not_found_response
from kagan.core.policy import command
from kagan.core.protocol_constants import TASK_WAIT_WINDOW_SECONDS
from kagan.core.scalars import non_empty_str
from kagan.core.services.runtime import runtime_snapshot_for_task

if TYPE_CHECKING:
    from datetime import datetime

    from kagan.core.adapters.db.schema import Task
    from kagan.core.api import KaganAPI
    from kagan.core.bootstrap import AppContext

logger = logging.getLogger(__name__)

_MAX_WAIT_WINDOW_SECONDS: float = TASK_WAIT_WINDOW_SECONDS


def _api(ctx: AppContext) -> KaganAPI:
    return api_from_context(ctx)


def _task_not_found_response(task_id: str) -> dict[str, Any]:
    return dict(task_not_found_response(task_id))


def _handler_params_from_call(args: tuple[Any, ...], kwargs: dict[str, Any]) -> dict[str, Any]:
    if len(args) >= 2 and isinstance(args[1], dict):
        return cast("dict[str, Any]", args[1])
    params = kwargs.get("params")
    return params if isinstance(params, dict) else {}


def _session_create_not_found_response(
    exc: Exception,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    del exc
    params = _handler_params_from_call(args, kwargs)
    return _task_not_found_response(str(params.get("task_id", "")))


def _session_create_domain_error_response(
    exc: Exception,
    args: tuple[Any, ...],
    kwargs: dict[str, Any],
) -> dict[str, Any]:
    from kagan.core.api import SessionCreateFailedError

    params = _handler_params_from_call(args, kwargs)
    task_id = str(params.get("task_id", ""))
    if isinstance(exc, SessionCreateFailedError):
        logger.warning("Failed to create PAIR session for %s: %s", task_id, exc.__cause__)
    return session_create_error_response(task_id, exc)


def _session_create_exception_map():
    from kagan.core.api import (
        InvalidWorktreePathError,
        SessionCreateFailedError,
        TaskNotFoundError,
        TaskTypeMismatchError,
        WorkspaceNotFoundError,
    )

    return {
        TaskNotFoundError: _session_create_not_found_response,
        TaskTypeMismatchError: _session_create_domain_error_response,
        WorkspaceNotFoundError: _session_create_domain_error_response,
        InvalidWorktreePathError: _session_create_domain_error_response,
        SessionCreateFailedError: _session_create_domain_error_response,
    }


def _compact_task_snapshot(
    task: Task,
    *,
    runtime_service: object | None = None,
) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "status": task.status.value,
        "priority": task.priority.value if task.priority else None,
        "task_type": task.task_type.value if task.task_type else None,
        "project_id": task.project_id,
        "updated_at": task.updated_at.isoformat(),
        "created_at": task.created_at.isoformat(),
        "runtime": dict(
            runtime_snapshot_for_task(
                task_id=task.id,
                runtime_service=runtime_service,
            )
        ),
    }


@command("tasks", "wait", description="Wait for task status change.")
async def handle_task_wait(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    """Wait for a task status change using event-driven wakeup."""
    import asyncio

    from kagan.core.events import TaskDeleted, TaskStatusChanged

    task_id = params["task_id"]

    config = ctx.config
    parsed_timeout = parse_wait_timeout_seconds(
        params.get("timeout_seconds"),
        default_timeout=config.general.tasks_wait_default_timeout_seconds,
        max_timeout=config.general.tasks_wait_max_timeout_seconds,
    )
    if isinstance(parsed_timeout, ParseError):
        return {
            "changed": False,
            "timed_out": False,
            "task_id": task_id,
            "code": parsed_timeout.code,
            "message": parsed_timeout.message,
        }
    timeout_seconds = parsed_timeout

    parsed_wait_for_status = parse_wait_for_status_filter(params.get("wait_for_status"))
    if isinstance(parsed_wait_for_status, ParseError):
        return {
            "changed": False,
            "timed_out": False,
            "task_id": task_id,
            "code": parsed_wait_for_status.code,
            "message": parsed_wait_for_status.message,
        }
    wait_for_status = parsed_wait_for_status

    from_updated_at = non_empty_str(params.get("from_updated_at"))

    wake_event = asyncio.Event()
    change_info: dict[str, Any] = {}
    latest_observed_updated_at: datetime | None = None

    def _on_event(event: object) -> None:
        nonlocal latest_observed_updated_at
        if isinstance(event, TaskStatusChanged) and event.task_id == task_id:
            if latest_observed_updated_at is None or event.updated_at > latest_observed_updated_at:
                latest_observed_updated_at = event.updated_at
            if wait_for_status is not None and event.to_status.value not in wait_for_status:
                return
            change_info["from_status"] = event.from_status.value
            change_info["to_status"] = event.to_status.value
            change_info["changed_at"] = event.updated_at.isoformat()
            wake_event.set()
        elif isinstance(event, TaskDeleted) and event.task_id == task_id:
            change_info["deleted"] = True
            wake_event.set()

    event_bus = ctx.event_bus
    event_bus.add_handler(_on_event)
    runtime_service = getattr(ctx, "runtime_service", None)
    previous_status: str | None = None
    try:
        task = await api.get_task(task_id)
        if task is None:
            return _task_not_found_response(task_id)

        previous_status = task.status.value
        previous_updated_at = task.updated_at.isoformat()
        latest_observed_updated_at = task.updated_at

        if wait_for_status is not None and previous_status in wait_for_status:
            return {
                "changed": True,
                "timed_out": False,
                "task_id": task_id,
                "previous_status": previous_status,
                "current_status": previous_status,
                "changed_at": previous_updated_at,
                "task": _compact_task_snapshot(task, runtime_service=runtime_service),
                "code": "ALREADY_AT_STATUS",
                "message": f"Task already at target status {previous_status}",
            }

        if from_updated_at is not None and previous_updated_at != from_updated_at:
            if wait_for_status is None or previous_status in wait_for_status:
                return {
                    "changed": True,
                    "timed_out": False,
                    "task_id": task_id,
                    "previous_status": None,
                    "current_status": previous_status,
                    "changed_at": previous_updated_at,
                    "task": _compact_task_snapshot(task, runtime_service=runtime_service),
                    "code": "CHANGED_SINCE_CURSOR",
                    "message": "Task changed since from_updated_at cursor",
                }

        remaining = timeout_seconds
        while remaining > 0:
            window = min(remaining, _MAX_WAIT_WINDOW_SECONDS)
            try:
                await asyncio.wait_for(wake_event.wait(), timeout=window)
                break
            except TimeoutError:
                remaining -= window
                if remaining <= 0:
                    return {
                        "changed": False,
                        "timed_out": True,
                        "task_id": task_id,
                        "previous_status": previous_status,
                        "current_status": previous_status,
                        "changed_at": None,
                        "task": None,
                        "code": "WAIT_TIMEOUT",
                        "message": (f"No status change detected within {timeout_seconds}s"),
                    }
                elapsed = timeout_seconds - remaining
                return {
                    "changed": False,
                    "timed_out": False,
                    "task_id": task_id,
                    "previous_status": previous_status,
                    "current_status": previous_status,
                    "changed_at": (
                        latest_observed_updated_at.isoformat()
                        if latest_observed_updated_at is not None
                        else None
                    ),
                    "task": None,
                    "elapsed_seconds": elapsed,
                    "remaining_seconds": remaining,
                    "code": "WAIT_WINDOW",
                    "message": (
                        f"No change in {window}s window "
                        f"({elapsed:.0f}s elapsed, {remaining:.0f}s remaining). "
                        "Re-call task_wait with from_updated_at to continue."
                    ),
                }
        else:
            return {
                "changed": False,
                "timed_out": True,
                "task_id": task_id,
                "previous_status": previous_status,
                "current_status": previous_status,
                "changed_at": None,
                "task": None,
                "code": "WAIT_TIMEOUT",
                "message": f"No status change detected within {timeout_seconds}s",
            }
    except asyncio.CancelledError:
        return {
            "changed": False,
            "timed_out": False,
            "task_id": task_id,
            "previous_status": previous_status,
            "current_status": previous_status,
            "changed_at": None,
            "task": None,
            "code": "WAIT_INTERRUPTED",
            "message": "Wait was interrupted",
        }
    finally:
        event_bus.remove_handler(_on_event)

    if change_info.get("deleted"):
        return {
            "changed": True,
            "timed_out": False,
            "task_id": task_id,
            "previous_status": previous_status,
            "current_status": None,
            "changed_at": change_info.get("changed_at"),
            "task": None,
            "code": "TASK_DELETED",
            "message": f"Task {task_id} was deleted during wait",
        }

    updated_task = await api.get_task(task_id)
    current_status = (
        updated_task.status.value if updated_task is not None else change_info.get("to_status")
    )
    return {
        "changed": True,
        "timed_out": False,
        "task_id": task_id,
        "previous_status": change_info.get("from_status", previous_status),
        "current_status": current_status,
        "changed_at": change_info.get("changed_at"),
        "task": (
            _compact_task_snapshot(updated_task, runtime_service=runtime_service)
            if updated_task
            else None
        ),
        "code": "TASK_CHANGED",
        "message": f"Task status changed: {previous_status} -> {current_status}",
    }


@command("tasks", "wait_any", description="Wait for any task lifecycle change.")
async def handle_task_wait_any(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Wait for any task lifecycle event using event-driven wakeup."""
    import asyncio

    from kagan.core.events import (
        AutomationAgentAttached,
        AutomationReviewAgentAttached,
        AutomationTaskEnded,
        AutomationTaskStarted,
        TaskCreated,
        TaskDeleted,
        TaskStatusChanged,
        TaskUpdated,
    )

    config = ctx.config
    parsed_timeout = parse_wait_timeout_seconds(
        params.get("timeout_seconds"),
        default_timeout=config.general.tasks_wait_default_timeout_seconds,
        max_timeout=config.general.tasks_wait_max_timeout_seconds,
    )
    if isinstance(parsed_timeout, ParseError):
        return {
            "changed": False,
            "timed_out": False,
            "task_id": "",
            "event_type": None,
            "changed_at": None,
            "code": parsed_timeout.code,
            "message": parsed_timeout.message,
        }
    timeout_seconds = parsed_timeout

    wake_event = asyncio.Event()
    change_info: dict[str, Any] = {
        "task_id": "",
        "event_type": None,
        "changed_at": None,
    }

    def _record_change(task_id: str, event_type: str, changed_at: str) -> None:
        if wake_event.is_set():
            return
        change_info["task_id"] = task_id
        change_info["event_type"] = event_type
        change_info["changed_at"] = changed_at
        wake_event.set()

    def _on_event(event: object) -> None:
        if isinstance(event, TaskCreated):
            _record_change(event.task_id, "task_created", event.created_at.isoformat())
            return
        if isinstance(event, TaskUpdated):
            _record_change(event.task_id, "task_updated", event.updated_at.isoformat())
            return
        if isinstance(event, TaskDeleted):
            _record_change(event.task_id, "task_deleted", event.occurred_at.isoformat())
            return
        if isinstance(event, TaskStatusChanged):
            _record_change(event.task_id, "task_status_changed", event.updated_at.isoformat())
            return
        if isinstance(event, AutomationTaskStarted):
            _record_change(event.task_id, "automation_started", event.occurred_at.isoformat())
            return
        if isinstance(event, AutomationAgentAttached):
            _record_change(
                event.task_id,
                "automation_agent_attached",
                event.occurred_at.isoformat(),
            )
            return
        if isinstance(event, AutomationReviewAgentAttached):
            _record_change(
                event.task_id,
                "automation_review_agent_attached",
                event.occurred_at.isoformat(),
            )
            return
        if isinstance(event, AutomationTaskEnded):
            _record_change(event.task_id, "automation_ended", event.occurred_at.isoformat())

    event_bus = ctx.event_bus
    event_bus.add_handler(_on_event)
    try:
        await asyncio.wait_for(wake_event.wait(), timeout=timeout_seconds)
    except TimeoutError:
        return {
            "changed": False,
            "timed_out": True,
            "task_id": "",
            "event_type": None,
            "changed_at": None,
            "code": "WAIT_TIMEOUT",
            "message": f"No task lifecycle change detected within {timeout_seconds}s",
        }
    except asyncio.CancelledError:
        return {
            "changed": False,
            "timed_out": False,
            "task_id": "",
            "event_type": None,
            "changed_at": None,
            "code": "WAIT_INTERRUPTED",
            "message": "Wait was interrupted",
        }
    finally:
        event_bus.remove_handler(_on_event)

    task_id = str(change_info.get("task_id") or "")
    event_type = change_info.get("event_type")
    changed_at = change_info.get("changed_at")
    return {
        "changed": True,
        "timed_out": False,
        "task_id": task_id,
        "event_type": event_type,
        "changed_at": changed_at,
        "code": "TASK_EVENT",
        "message": f"Task lifecycle event: {event_type}",
    }


@command("review", "merge", profile="maintainer", mutating=True, description="Merge review.")
async def handle_review_merge(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    task_id = params["task_id"]
    success, message = await api.merge_task(task_id)
    return {
        "success": success,
        "task_id": task_id,
        "message": message,
        "code": "MERGED" if success else "MERGE_FAILED",
    }


@command("review", "rebase", profile="maintainer", mutating=True, description="Rebase review.")
async def handle_review_rebase(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    task_id = params["task_id"]
    base_branch = non_empty_str(params.get("base_branch"))
    success, message, conflict_files = await api.rebase_task(task_id, base_branch=base_branch)
    code = "REBASED" if success else ("REBASE_CONFLICT" if conflict_files else "REBASE_FAILED")
    return {
        "success": success,
        "task_id": task_id,
        "message": message,
        "conflict_files": conflict_files,
        "code": code,
    }


@command("jobs", "submit", profile="pair_worker", mutating=True, description="Submit a job.")
async def handle_job_submit(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    task_id_raw = non_empty_str(params.get("task_id"))
    action_raw = non_empty_str(params.get("action"))

    if task_id_raw is None:
        return {
            "success": False,
            "message": "task_id is required. Use task_list to find valid task IDs.",
            "code": CommandCode.INVALID_TASK_ID.value,
        }
    if action_raw is None or action_raw not in SUPPORTED_JOB_ACTIONS:
        supported = sorted(SUPPORTED_JOB_ACTIONS)
        unsupported_message = (
            f"Unsupported action {action_raw!r}" if action_raw else "Unsupported action"
        )
        return {
            "success": False,
            "task_id": task_id_raw,
            "message": unsupported_message,
            "code": "UNSUPPORTED_ACTION",
            "hint": f"Use one of: {', '.join(supported)}",
            "next_tool": "job_start",
            "next_arguments": {"task_id": task_id_raw, "action": supported[0]},
            "supported_actions": supported,
        }

    task = await api.get_task(task_id_raw)
    if task is None:
        return _task_not_found_response(task_id_raw)

    arguments = str_object_dict(params.get("arguments"))
    job = await api.submit_job(task_id_raw, action_raw, arguments=arguments)
    return {
        "success": True,
        "job_id": job.job_id,
        "task_id": job.task_id,
        "action": job.action,
        "status": job.status.value,
        "created_at": job.created_at.isoformat(),
        "updated_at": job.updated_at.isoformat(),
        "code": "JOB_SUBMITTED",
    }


@command("jobs", "cancel", profile="pair_worker", mutating=True, description="Cancel a job.")
async def handle_job_cancel(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    job_id_raw = non_empty_str(params.get("job_id"))
    task_id_raw = non_empty_str(params.get("task_id"))

    if job_id_raw is None:
        return invalid_job_id_response()
    if task_id_raw is None:
        return invalid_task_id_response(job_id_raw)

    cancelled = await api.cancel_job(job_id_raw, task_id=task_id_raw)
    if cancelled is None:
        return job_not_found_response(job_id_raw, task_id_raw)

    return {
        "success": True,
        "job_id": cancelled.job_id,
        "task_id": cancelled.task_id,
        "action": cancelled.action,
        "status": cancelled.status.value,
        "created_at": cancelled.created_at.isoformat(),
        "updated_at": cancelled.updated_at.isoformat(),
        "message": cancelled.message,
        "code": cancelled.code or "JOB_CANCELLED",
    }


@command("jobs", "get", profile="pair_worker", description="Get a job.")
async def handle_job_get(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    job_id_raw = non_empty_str(params.get("job_id"))
    task_id_raw = non_empty_str(params.get("task_id"))

    if job_id_raw is None:
        return invalid_job_id_response()
    if task_id_raw is None:
        return invalid_task_id_response(job_id_raw)

    job = await api.get_job(job_id_raw, task_id=task_id_raw)
    if job is None:
        return job_not_found_response(job_id_raw, task_id_raw)
    return build_job_response(job)


@command("jobs", "wait", profile="pair_worker", description="Wait for a job.")
async def handle_job_wait(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    job_id_raw = non_empty_str(params.get("job_id"))
    task_id_raw = non_empty_str(params.get("task_id"))

    if job_id_raw is None:
        return invalid_job_id_response()
    if task_id_raw is None:
        return invalid_task_id_response(job_id_raw)

    timeout_value = parse_timeout_seconds(params.get("timeout_seconds"))
    if isinstance(timeout_value, ParseError):
        return {
            "success": False,
            "job_id": job_id_raw,
            "task_id": task_id_raw,
            "message": timeout_value.message,
            "code": timeout_value.code,
        }

    job = await api.wait_job(job_id_raw, task_id=task_id_raw, timeout_seconds=timeout_value)
    if job is None:
        return job_not_found_response(job_id_raw, task_id_raw)
    return build_job_response(job, timed_out=True)


@command("jobs", "events", profile="pair_worker", description="List job events.")
async def handle_job_events(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    job_id_raw = non_empty_str(params.get("job_id"))
    task_id_raw = non_empty_str(params.get("task_id"))

    if job_id_raw is None:
        return invalid_job_id_response()
    if task_id_raw is None:
        return invalid_task_id_response(job_id_raw)

    limit_value = parse_events_limit(params.get("limit"))
    if isinstance(limit_value, ParseError):
        return {
            "success": False,
            "job_id": job_id_raw,
            "task_id": task_id_raw,
            "message": limit_value.message,
            "code": limit_value.code,
        }
    offset_value = parse_events_offset(params.get("offset"))
    if isinstance(offset_value, ParseError):
        return {
            "success": False,
            "job_id": job_id_raw,
            "task_id": task_id_raw,
            "message": offset_value.message,
            "code": offset_value.code,
        }

    events = await api.get_job_events(job_id_raw, task_id=task_id_raw)
    if events is None:
        return job_not_found_response(job_id_raw, task_id_raw)

    total_events = len(events)
    page = events[offset_value : offset_value + limit_value]
    next_offset = offset_value + len(page)
    has_more = next_offset < total_events
    return {
        "success": True,
        "job_id": job_id_raw,
        "task_id": task_id_raw,
        "events": [event.to_dict() for event in page],
        "total_events": total_events,
        "returned_events": len(page),
        "offset": offset_value,
        "limit": limit_value,
        "has_more": has_more,
        "next_offset": next_offset if has_more else None,
    }


@map_command_exceptions(_session_create_exception_map)
@command(
    "sessions",
    "create",
    profile="pair_worker",
    mutating=True,
    description="Create or reuse a session for a task.",
)
async def handle_session_create(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)

    task_id = params["task_id"]
    reuse_if_exists = bool(params.get("reuse_if_exists", True))

    worktree_path, worktree_error = parse_requested_worktree(
        task_id=task_id,
        raw_worktree=params.get("worktree_path"),
    )
    if worktree_error is not None:
        return worktree_error

    result = await api.create_session(
        task_id,
        worktree_path=worktree_path,
        reuse_if_exists=reuse_if_exists,
    )

    backend = resolve_pair_backend(ctx, result.task)
    return build_handoff_payload(
        task_id=task_id,
        backend=backend,
        session_name=result.session_name,
        worktree_path=result.worktree_path,
        already_exists=result.already_exists,
    )


@command("sessions", "attach", profile="pair_worker", description="Attach to a task session.")
async def handle_session_attach(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    task_id = params["task_id"]
    attached = await api.attach_session(task_id)
    return {
        "success": attached,
        "message": (
            "Attached"
            if attached
            else "Session not found. Use session_manage(action='open') to create one."
        ),
    }


@command("sessions", "exists", profile="pair_worker", description="Check session existence.")
async def handle_session_exists(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    task_id = params["task_id"]
    task = await api.get_task(task_id)
    backend = resolve_pair_backend(ctx, task)
    worktree_path = await ctx.workspace_service.get_task_workspace_path(task_id)
    prompt_path = str(worktree_path / SESSION_PROMPT_PATH) if worktree_path else None
    exists = await api.session_exists(task_id)
    return {
        "task_id": task_id,
        "exists": exists,
        "session_name": f"kagan-{task_id}",
        "backend": backend,
        "worktree_path": str(worktree_path) if worktree_path else None,
        "prompt_path": prompt_path,
    }


@command(
    "sessions",
    "kill",
    profile="pair_worker",
    mutating=True,
    description="Terminate a session.",
)
async def handle_session_kill(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    task_id = params["task_id"]
    await api.kill_session(task_id)
    return {"success": True, "task_id": task_id, "message": "Session terminated"}


@command(
    "diagnostics",
    "instrumentation",
    profile="maintainer",
    description="Get diagnostics instrumentation snapshot.",
)
async def handle_diagnostics_instrumentation(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    api = _api(ctx)
    del params
    return {"instrumentation": await api.get_instrumentation()}


__all__ = [
    "_MAX_WAIT_WINDOW_SECONDS",
    "handle_automation_count_executions",
    "handle_automation_decide_startup",
    "handle_automation_dispatch_runtime_session",
    "handle_automation_get_execution",
    "handle_automation_get_execution_log_entries",
    "handle_automation_get_latest_execution",
    "handle_automation_get_queue_status",
    "handle_automation_get_queued_messages",
    "handle_automation_get_running_task_ids",
    "handle_automation_get_runtime_view",
    "handle_automation_is_running",
    "handle_automation_queue_message",
    "handle_automation_reconcile_running_tasks",
    "handle_automation_remove_queued_message",
    "handle_automation_take_queued_message",
    "handle_diagnostics_instrumentation",
    "handle_job_cancel",
    "handle_job_events",
    "handle_job_get",
    "handle_job_submit",
    "handle_job_wait",
    "handle_review_merge",
    "handle_review_rebase",
    "handle_session_attach",
    "handle_session_create",
    "handle_session_exists",
    "handle_session_kill",
    "handle_task_wait",
    "handle_task_wait_any",
]
