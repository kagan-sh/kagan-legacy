from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from kagan.core.commands._parsing import (
    parse_events_limit,
    parse_events_offset,
    parse_json_dict_list,
    parse_proposal_status,
    parse_queue_lane,
    parse_runtime_session_event,
    parse_timeout_seconds,
    parse_wait_for_status_filter,
    parse_wait_timeout_seconds,
    str_object_dict,
)
from kagan.core.commands._serialization import (
    SESSION_PROMPT_PATH,
    build_handoff_payload,
    build_job_response,
    execution_log_entry_to_dict,
    execution_to_dict,
    invalid_job_id_response,
    invalid_task_id_response,
    job_not_found_response,
    parse_requested_worktree,
    resolve_pair_backend,
    runtime_context_to_dict,
    runtime_view_to_dict,
    session_create_error_response,
    startup_decision_to_dict,
)
from kagan.core.commands._transport_truncation import (
    DEFAULT_AUDIT_FIELD_CHAR_LIMIT as _DEFAULT_AUDIT_FIELD_CHAR_LIMIT,
)
from kagan.core.commands._transport_truncation import (
    truncate_for_transport as _truncate_for_transport,
)
from kagan.core.commands.job_action_executor import SUPPORTED_JOB_ACTIONS
from kagan.core.domain.errors import task_not_found_response
from kagan.core.policy import command
from kagan.core.scalars import non_empty_str
from kagan.core.services.runtime import runtime_snapshot_for_task

if TYPE_CHECKING:
    from datetime import datetime

    from kagan.core.adapters.db.schema import Task
    from kagan.core.api import KaganAPI
    from kagan.core.bootstrap import AppContext

logger = logging.getLogger(__name__)

_MAX_WAIT_WINDOW_SECONDS: float = 45.0


def _api(ctx: AppContext) -> KaganAPI:
    from kagan.core.api import KaganAPI

    if isinstance(ctx, KaganAPI):
        return ctx
    api = getattr(ctx, "api", None)
    if api is None:
        raise ValueError("API context is not initialized")
    return cast("KaganAPI", api)


def _task_not_found_response(task_id: str) -> dict[str, Any]:
    return dict(task_not_found_response(task_id))


# Local alias preserves existing call sites while using shared coercion.
_non_empty_str = non_empty_str


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
    if isinstance(parsed_timeout, str):
        return {
            "changed": False,
            "timed_out": False,
            "task_id": task_id,
            "code": "INVALID_TIMEOUT",
            "message": parsed_timeout,
        }
    timeout_seconds = parsed_timeout

    parsed_wait_for_status = parse_wait_for_status_filter(params.get("wait_for_status"))
    if isinstance(parsed_wait_for_status, str):
        return {
            "changed": False,
            "timed_out": False,
            "task_id": task_id,
            "code": "INVALID_PARAMS",
            "message": parsed_wait_for_status,
        }
    wait_for_status = parsed_wait_for_status

    from_updated_at = _non_empty_str(params.get("from_updated_at"))

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
    base_branch = _non_empty_str(params.get("base_branch"))
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
    task_id_raw = _non_empty_str(params.get("task_id"))
    action_raw = _non_empty_str(params.get("action"))

    if task_id_raw is None:
        return {
            "success": False,
            "message": "task_id is required. Use task_list to find valid task IDs.",
            "code": "INVALID_TASK_ID",
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
    job_id_raw = _non_empty_str(params.get("job_id"))
    task_id_raw = _non_empty_str(params.get("task_id"))

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
    job_id_raw = _non_empty_str(params.get("job_id"))
    task_id_raw = _non_empty_str(params.get("task_id"))

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
    job_id_raw = _non_empty_str(params.get("job_id"))
    task_id_raw = _non_empty_str(params.get("task_id"))

    if job_id_raw is None:
        return invalid_job_id_response()
    if task_id_raw is None:
        return invalid_task_id_response(job_id_raw)

    timeout_value = parse_timeout_seconds(params.get("timeout_seconds"))
    if isinstance(timeout_value, str):
        return {
            "success": False,
            "job_id": job_id_raw,
            "task_id": task_id_raw,
            "message": timeout_value,
            "code": "INVALID_TIMEOUT",
        }

    job = await api.wait_job(job_id_raw, task_id=task_id_raw, timeout_seconds=timeout_value)
    if job is None:
        return job_not_found_response(job_id_raw, task_id_raw)
    return build_job_response(job, timed_out=True)


@command("jobs", "events", profile="pair_worker", description="List job events.")
async def handle_job_events(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    job_id_raw = _non_empty_str(params.get("job_id"))
    task_id_raw = _non_empty_str(params.get("task_id"))

    if job_id_raw is None:
        return invalid_job_id_response()
    if task_id_raw is None:
        return invalid_task_id_response(job_id_raw)

    limit_value = parse_events_limit(params.get("limit"))
    if isinstance(limit_value, str):
        return {
            "success": False,
            "job_id": job_id_raw,
            "task_id": task_id_raw,
            "message": limit_value,
            "code": "INVALID_LIMIT",
        }
    offset_value = parse_events_offset(params.get("offset"))
    if isinstance(offset_value, str):
        return {
            "success": False,
            "job_id": job_id_raw,
            "task_id": task_id_raw,
            "message": offset_value,
            "code": "INVALID_OFFSET",
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


@command(
    "sessions",
    "create",
    profile="pair_worker",
    mutating=True,
    description="Create or reuse a session for a task.",
)
async def handle_session_create(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    from kagan.core.api import (
        InvalidWorktreePathError,
        SessionCreateFailedError,
        TaskNotFoundError,
        TaskTypeMismatchError,
        WorkspaceNotFoundError,
    )

    task_id = params["task_id"]
    reuse_if_exists = bool(params.get("reuse_if_exists", True))

    worktree_path, worktree_error = parse_requested_worktree(
        task_id=task_id,
        raw_worktree=params.get("worktree_path"),
    )
    if worktree_error is not None:
        return worktree_error

    result = None
    error_response: dict[str, Any] | None = None
    try:
        result = await api.create_session(
            task_id,
            worktree_path=worktree_path,
            reuse_if_exists=reuse_if_exists,
        )
    except TaskNotFoundError:
        error_response = _task_not_found_response(task_id)
    except (
        TaskTypeMismatchError,
        WorkspaceNotFoundError,
        InvalidWorktreePathError,
        SessionCreateFailedError,
    ) as exc:
        if isinstance(exc, SessionCreateFailedError):
            logger.warning("Failed to create PAIR session for %s: %s", task_id, exc.__cause__)
        error_response = session_create_error_response(task_id, exc)

    if error_response is not None:
        return error_response

    assert result is not None
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
    worktree_path = await ctx.workspace_service.get_path(task_id)
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


# ── Automation @command handlers ──────────────────────────────────────


@command(
    "automation",
    "queue_message",
    profile="pair_worker",
    mutating=True,
    description="Queue a follow-up message for a session lane.",
)
async def handle_automation_queue_message(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    session_id = _non_empty_str(params.get("session_id"))
    content = _non_empty_str(params.get("content"))
    if session_id is None:
        return {"success": False, "message": "session_id is required", "code": "INVALID_PARAMS"}
    if content is None:
        return {"success": False, "message": "content is required", "code": "INVALID_PARAMS"}
    lane = parse_queue_lane(params.get("lane"))
    if lane not in {"implementation", "review", "planner"}:
        return {"success": False, "message": lane, "code": "INVALID_LANE"}
    author = _non_empty_str(params.get("author"))
    metadata = str_object_dict(params.get("metadata"))
    msg = await api.queue_message(session_id, content, lane=lane, author=author, metadata=metadata)
    return {
        "success": True,
        "content": msg.content,
        "author": msg.author,
        "queued_at": msg.queued_at.isoformat(),
        "code": "QUEUED",
    }


@command(
    "automation",
    "get_queue_status",
    profile="pair_worker",
    description="Get queue status for a session lane.",
)
async def handle_automation_get_queue_status(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    session_id = _non_empty_str(params.get("session_id"))
    if session_id is None:
        return {"success": False, "message": "session_id is required", "code": "INVALID_PARAMS"}
    lane = parse_queue_lane(params.get("lane"))
    if lane not in {"implementation", "review", "planner"}:
        return {"success": False, "message": lane, "code": "INVALID_LANE"}
    status = await api.get_queue_status(session_id, lane=lane)
    return {
        "success": True,
        "has_queued": status.has_queued,
        "queued_at": status.queued_at.isoformat() if status.queued_at else None,
        "content_preview": status.content_preview,
        "author": status.author,
        "lane": lane,
    }


@command(
    "automation",
    "get_queued_messages",
    profile="pair_worker",
    description="List queued messages for a session lane.",
)
async def handle_automation_get_queued_messages(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    session_id = _non_empty_str(params.get("session_id"))
    if session_id is None:
        return {"success": False, "message": "session_id is required", "code": "INVALID_PARAMS"}
    lane = parse_queue_lane(params.get("lane"))
    if lane not in {"implementation", "review", "planner"}:
        return {"success": False, "message": lane, "code": "INVALID_LANE"}
    messages = await api.get_queued_messages(session_id, lane=lane)
    return {
        "success": True,
        "messages": [
            {
                "content": m.content,
                "author": m.author,
                "metadata": m.metadata,
                "queued_at": m.queued_at.isoformat(),
            }
            for m in messages
        ],
        "count": len(messages),
    }


@command(
    "automation",
    "take_queued_message",
    profile="pair_worker",
    mutating=True,
    description="Consume and return the next queued message for a session lane.",
)
async def handle_automation_take_queued_message(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    session_id = _non_empty_str(params.get("session_id"))
    if session_id is None:
        return {"success": False, "message": "session_id is required", "code": "INVALID_PARAMS"}
    lane = parse_queue_lane(params.get("lane"))
    if lane not in {"implementation", "review", "planner"}:
        return {"success": False, "message": lane, "code": "INVALID_LANE"}
    msg = await api.take_queued_message(session_id, lane=lane)
    if msg is None:
        return {"success": True, "message": None, "code": "QUEUE_EMPTY"}
    return {
        "success": True,
        "message": {
            "content": msg.content,
            "author": msg.author,
            "metadata": msg.metadata,
            "queued_at": msg.queued_at.isoformat(),
        },
        "code": "MESSAGE_TAKEN",
    }


@command(
    "automation",
    "remove_queued_message",
    profile="pair_worker",
    mutating=True,
    description="Remove a queued message by index from a session lane.",
)
async def handle_automation_remove_queued_message(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    session_id = _non_empty_str(params.get("session_id"))
    if session_id is None:
        return {"success": False, "message": "session_id is required", "code": "INVALID_PARAMS"}
    lane = parse_queue_lane(params.get("lane"))
    if lane not in {"implementation", "review", "planner"}:
        return {"success": False, "message": lane, "code": "INVALID_LANE"}
    index_raw = params.get("index")
    if not isinstance(index_raw, int) or isinstance(index_raw, bool):
        return {"success": False, "message": "index must be an integer", "code": "INVALID_PARAMS"}
    removed = await api.remove_queued_message(session_id, index_raw, lane=lane)
    return {
        "success": removed,
        "message": "Removed" if removed else "Message not found at index",
        "code": "REMOVED" if removed else "NOT_FOUND",
    }


@command(
    "automation",
    "is_automation_running",
    profile="pair_worker",
    description="Check if automation is running for a task.",
)
async def handle_automation_is_running(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    task_id = _non_empty_str(params.get("task_id"))
    if task_id is None:
        return {"success": False, "message": "task_id is required", "code": "INVALID_PARAMS"}
    is_running = api.is_automation_running(task_id)
    return {"success": True, "task_id": task_id, "is_running": is_running}


@command(
    "automation",
    "decide_startup",
    profile="operator",
    description="Determine startup flow based on persisted runtime state and cwd.",
)
async def handle_automation_decide_startup(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    cwd_raw = _non_empty_str(params.get("cwd"))
    if cwd_raw is None:
        return {"success": False, "message": "cwd is required", "code": "INVALID_PARAMS"}
    decision = await api.decide_startup(Path(cwd_raw))
    return {"success": True, **startup_decision_to_dict(decision)}


@command(
    "automation",
    "get_execution",
    profile="pair_worker",
    description="Get an execution record by ID.",
)
async def handle_automation_get_execution(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    execution_id = _non_empty_str(params.get("execution_id"))
    if execution_id is None:
        return {"success": False, "message": "execution_id is required", "code": "INVALID_PARAMS"}
    execution = await api.get_execution(execution_id)
    if execution is None:
        return {
            "success": False,
            "execution_id": execution_id,
            "message": "Execution not found",
            "code": "NOT_FOUND",
        }
    return {"success": True, "execution": execution_to_dict(execution)}


@command(
    "automation",
    "get_execution_log_entries",
    profile="pair_worker",
    description="Get ordered execution log entries for an execution.",
)
async def handle_automation_get_execution_log_entries(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    execution_id = _non_empty_str(params.get("execution_id"))
    if execution_id is None:
        return {"success": False, "message": "execution_id is required", "code": "INVALID_PARAMS"}
    entries = await api.get_execution_log_entries(execution_id)
    return {
        "success": True,
        "entries": [execution_log_entry_to_dict(e) for e in entries],
        "count": len(entries),
    }


@command(
    "automation",
    "get_latest_execution_for_task",
    profile="pair_worker",
    description="Get the most recent execution for a task.",
)
async def handle_automation_get_latest_execution(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    task_id = _non_empty_str(params.get("task_id"))
    if task_id is None:
        return {"success": False, "message": "task_id is required", "code": "INVALID_PARAMS"}
    execution = await api.get_latest_execution_for_task(task_id)
    if execution is None:
        return {
            "success": True,
            "task_id": task_id,
            "execution": None,
            "message": "No executions found",
            "code": "NO_EXECUTIONS",
        }
    return {"success": True, "task_id": task_id, "execution": execution_to_dict(execution)}


@command(
    "automation",
    "count_executions_for_task",
    profile="pair_worker",
    description="Return total execution count for a task.",
)
async def handle_automation_count_executions(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    task_id = _non_empty_str(params.get("task_id"))
    if task_id is None:
        return {"success": False, "message": "task_id is required", "code": "INVALID_PARAMS"}
    count = await api.count_executions_for_task(task_id)
    return {"success": True, "task_id": task_id, "count": count}


@command(
    "automation",
    "get_running_task_ids",
    profile="pair_worker",
    description="Return the set of currently running task IDs.",
)
async def handle_automation_get_running_task_ids(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
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
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    task_id = _non_empty_str(params.get("task_id"))
    if task_id is None:
        return {"success": False, "message": "task_id is required", "code": "INVALID_PARAMS"}
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
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    task_ids_raw = params.get("task_ids")
    if not isinstance(task_ids_raw, list):
        return {"success": False, "message": "task_ids must be a list", "code": "INVALID_PARAMS"}
    task_ids = [str(tid) for tid in task_ids_raw]
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
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    event_raw = params.get("event")
    event = parse_runtime_session_event(event_raw)
    if event is None:
        return {
            "success": False,
            "message": f"Invalid event: {event_raw!r}. "
            "Use one of: project_selected, repo_selected, repo_cleared, reset",
            "code": "INVALID_EVENT",
        }
    project_id = _non_empty_str(params.get("project_id"))
    repo_id = _non_empty_str(params.get("repo_id"))
    state = await api.dispatch_runtime_session(event, project_id=project_id, repo_id=repo_id)
    return {"success": True, **runtime_context_to_dict(state)}


@command(
    "automation",
    "save_planner_draft",
    profile="operator",
    mutating=True,
    description="Persist a planner draft proposal.",
)
async def handle_automation_save_planner_draft(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    project_id = _non_empty_str(params.get("project_id"))
    if project_id is None:
        return {"success": False, "message": "project_id is required", "code": "INVALID_PARAMS"}
    tasks_json = parse_json_dict_list(params.get("tasks_json"), field_name="tasks_json")
    if isinstance(tasks_json, str):
        return {"success": False, "message": tasks_json, "code": "INVALID_PARAMS"}
    repo_id = _non_empty_str(params.get("repo_id"))
    todos_raw = params.get("todos_json")
    todos_json: list[dict[str, Any]] | None = None
    if todos_raw is not None:
        parsed_todos = parse_json_dict_list(todos_raw, field_name="todos_json")
        if isinstance(parsed_todos, str):
            return {"success": False, "message": parsed_todos, "code": "INVALID_PARAMS"}
        todos_json = parsed_todos
    proposal = await api.save_planner_draft(
        project_id=project_id,
        repo_id=repo_id,
        tasks_json=tasks_json,
        todos_json=todos_json,
    )
    if proposal is None:
        return {"success": False, "message": "Planner not available", "code": "UNAVAILABLE"}
    return {
        "success": True,
        "proposal_id": getattr(proposal, "id", None),
        "status": getattr(proposal, "status", None),
        "code": "SAVED",
    }


@command(
    "automation",
    "list_pending_planner_drafts",
    profile="operator",
    description="List pending planner draft proposals for a project.",
)
async def handle_automation_list_pending_planner_drafts(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    project_id = _non_empty_str(params.get("project_id"))
    if project_id is None:
        return {"success": False, "message": "project_id is required", "code": "INVALID_PARAMS"}
    repo_id = _non_empty_str(params.get("repo_id"))
    drafts = await api.list_pending_planner_drafts(project_id, repo_id=repo_id)

    def _serialize_created_at(val: object) -> str | None:
        if val is None:
            return None
        iso = getattr(val, "isoformat", None)
        return iso() if callable(iso) else str(val)

    return {
        "success": True,
        "drafts": [
            {
                "id": getattr(d, "id", None),
                "project_id": getattr(d, "project_id", None),
                "repo_id": getattr(d, "repo_id", None),
                "status": getattr(d, "status", None),
                "created_at": _serialize_created_at(getattr(d, "created_at", None)),
                "tasks_json": getattr(d, "tasks_json", []),
                "todos_json": getattr(d, "todos_json", []),
            }
            for d in drafts
        ],
        "count": len(drafts),
    }


@command(
    "automation",
    "update_planner_draft_status",
    profile="operator",
    mutating=True,
    description="Update planner draft status (approved/rejected).",
)
async def handle_automation_update_planner_draft_status(
    ctx: AppContext, params: dict[str, Any]
) -> dict[str, Any]:
    api = _api(ctx)
    proposal_id = _non_empty_str(params.get("proposal_id"))
    if proposal_id is None:
        return {"success": False, "message": "proposal_id is required", "code": "INVALID_PARAMS"}
    status_raw = params.get("status")
    status = parse_proposal_status(status_raw)
    if status is None:
        return {
            "success": False,
            "message": f"Invalid status: {status_raw!r}. Use one of: draft, approved, rejected",
            "code": "INVALID_STATUS",
        }
    result = await api.update_planner_draft_status(proposal_id, status)
    if result is None:
        return {"success": False, "message": "Planner not available", "code": "UNAVAILABLE"}
    return {
        "success": True,
        "proposal_id": getattr(result, "id", None),
        "status": getattr(result, "status", None),
        "code": "UPDATED",
    }


async def handle_audit_list(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = _api(ctx)
    capability = params.get("capability")
    limit = params.get("limit", 50)
    cursor = params.get("cursor")
    events = await api.list_audit_events(capability=capability, limit=limit, cursor=cursor)
    result_events = []
    truncated = False
    for event in events:
        payload = event.payload_json or ""
        result = event.result_json or ""
        payload, payload_truncated = _truncate_for_transport(
            payload,
            limit=_DEFAULT_AUDIT_FIELD_CHAR_LIMIT,
        )
        result, result_truncated = _truncate_for_transport(
            result,
            limit=_DEFAULT_AUDIT_FIELD_CHAR_LIMIT,
        )
        if payload_truncated or result_truncated:
            truncated = True
        result_events.append(
            {
                "id": event.id,
                "occurred_at": event.occurred_at.isoformat() if event.occurred_at else None,
                "actor_type": event.actor_type,
                "actor_id": event.actor_id,
                "session_id": event.session_id,
                "capability": event.capability,
                "command_name": event.command_name,
                "payload_json": payload,
                "result_json": result,
                "success": event.success,
            }
        )

    return {
        "events": result_events,
        "count": len(result_events),
        "truncated": truncated,
    }


async def dispatch_tui_automation_method(
    ctx: AppContext,
    method_name: str,
    kwargs: dict[str, Any],
) -> tuple[bool, Any]:
    api = _api(ctx)

    def _required_non_empty(key: str) -> str:
        value = _non_empty_str(kwargs.get(key))
        if value is None:
            raise ValueError(f"{key} is required")
        return value

    match method_name:
        case "is_automation_running":
            task_id = _required_non_empty("task_id")
            return True, api.is_automation_running(task_id)
        case "submit_job":
            task_id = _required_non_empty("task_id")
            action = _required_non_empty("action")
            arguments_raw = kwargs.get("arguments")
            if arguments_raw is not None and not isinstance(arguments_raw, dict):
                raise ValueError("arguments must be an object when provided")
            arguments = dict(arguments_raw) if isinstance(arguments_raw, dict) else None
            return True, await api.submit_job(task_id, action, arguments=arguments)
        case "wait_job":
            job_id = _required_non_empty("job_id")
            task_id = _required_non_empty("task_id")
            timeout = parse_timeout_seconds(kwargs.get("timeout_seconds"))
            if isinstance(timeout, str):
                raise ValueError(timeout)
            return True, await api.wait_job(job_id, task_id=task_id, timeout_seconds=timeout)
        case "cancel_job":
            job_id = _required_non_empty("job_id")
            task_id = _required_non_empty("task_id")
            return True, await api.cancel_job(job_id, task_id=task_id)
        case "create_session":
            task_id = _required_non_empty("task_id")
            reuse_if_exists = bool(kwargs.get("reuse_if_exists", True))
            worktree_value = _non_empty_str(kwargs.get("worktree_path"))
            worktree_path = (
                Path(worktree_value).expanduser().resolve(strict=False)
                if worktree_value is not None
                else None
            )
            return True, await api.create_session(
                task_id,
                worktree_path=worktree_path,
                reuse_if_exists=reuse_if_exists,
            )
        case "attach_session":
            task_id = _required_non_empty("task_id")
            return True, await api.attach_session(task_id)
        case "session_exists":
            task_id = _required_non_empty("task_id")
            return True, await api.session_exists(task_id)
        case "kill_session":
            task_id = _required_non_empty("task_id")
            await api.kill_session(task_id)
            return True, None
        case "queue_message":
            session_id = _required_non_empty("session_id")
            content = _required_non_empty("content")
            lane = parse_queue_lane(kwargs.get("lane"))
            if lane not in {"implementation", "review", "planner"}:
                raise ValueError(lane)
            author = _non_empty_str(kwargs.get("author"))
            metadata = str_object_dict(kwargs.get("metadata"))
            return True, await api.queue_message(
                session_id,
                content,
                lane=lane,
                author=author,
                metadata=metadata,
            )
        case "get_queue_status":
            session_id = _required_non_empty("session_id")
            lane = parse_queue_lane(kwargs.get("lane"))
            if lane not in {"implementation", "review", "planner"}:
                raise ValueError(lane)
            return True, await api.get_queue_status(session_id, lane=lane)
        case "get_queued_messages":
            session_id = _required_non_empty("session_id")
            lane = parse_queue_lane(kwargs.get("lane"))
            if lane not in {"implementation", "review", "planner"}:
                raise ValueError(lane)
            return True, await api.get_queued_messages(session_id, lane=lane)
        case "take_queued_message":
            session_id = _required_non_empty("session_id")
            lane = parse_queue_lane(kwargs.get("lane"))
            if lane not in {"implementation", "review", "planner"}:
                raise ValueError(lane)
            return True, await api.take_queued_message(session_id, lane=lane)
        case "remove_queued_message":
            session_id = _required_non_empty("session_id")
            lane = parse_queue_lane(kwargs.get("lane"))
            if lane not in {"implementation", "review", "planner"}:
                raise ValueError(lane)
            index_raw = kwargs.get("index")
            if not isinstance(index_raw, int) or isinstance(index_raw, bool):
                raise ValueError("index must be an integer")
            return True, await api.remove_queued_message(session_id, index_raw, lane=lane)
        case _:
            return False, None


__all__ = [
    "_DEFAULT_AUDIT_FIELD_CHAR_LIMIT",
    "_MAX_WAIT_WINDOW_SECONDS",
    "dispatch_tui_automation_method",
    "handle_audit_list",
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
    "handle_automation_list_pending_planner_drafts",
    "handle_automation_queue_message",
    "handle_automation_reconcile_running_tasks",
    "handle_automation_remove_queued_message",
    "handle_automation_save_planner_draft",
    "handle_automation_take_queued_message",
    "handle_automation_update_planner_draft_status",
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
]
