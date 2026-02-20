from __future__ import annotations

import contextlib
import logging
from typing import TYPE_CHECKING, Any

from kagan.core.domain.enums import TaskStatus
from kagan.core.domain.errors import (
    ReviewApprovalContextMissingError,
    ReviewGuardrailBlockedError,
    ReviewOperationError,
    task_not_found_response,
)
from kagan.core.domain.task_rules import validate_transition
from kagan.core.policy import command

from ._parsing import (
    build_task_update_fields,
    parse_events_offset,
    parse_task_status,
    str_list,
)
from ._serialization import task_to_dict
from ._transport_truncation import truncate_for_transport as _truncate_for_transport

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext

logger = logging.getLogger(__name__)
_DEFAULT_TASK_SCRATCHPAD_CHAR_LIMIT = 16_000
_DEFAULT_TASK_LOG_ENTRY_CHAR_LIMIT = 6_000
_DEFAULT_TASK_LOG_TOTAL_CHAR_LIMIT = 18_000


def _task_error_response(
    task_id: str,
    *,
    code: str,
    message: str,
    hint: str | None = None,
) -> dict[str, Any]:
    response: dict[str, Any] = {
        "success": False,
        "task_id": task_id,
        "message": message,
        "code": code,
    }
    if hint is not None and hint.strip():
        response["hint"] = hint
    return response


def _review_error_response(task_id: str, exc: ReviewOperationError) -> dict[str, Any]:
    return {"success": False, "task_id": task_id, **exc.to_payload()}


def _task_not_found_response(task_id: str) -> dict[str, Any]:
    return dict(task_not_found_response(task_id))


def _bounded_int(
    value: object,
    *,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    if isinstance(value, int) and not isinstance(value, bool):
        return max(minimum, min(value, maximum))
    return default


@command("tasks", "get", description="Get a single task by ID.")
async def get_task(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task = await ctx.task_service.get_task(params["task_id"])
    if task is None:
        return {"found": False, "task": None}
    return {
        "found": True,
        "task": task_to_dict(task, runtime_service=getattr(ctx, "runtime_service", None)),
    }


@command("tasks", "list", description="List tasks with optional project/status filter.")
async def list_tasks(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    project_id = params.get("project_id")
    include_scratchpad = bool(params.get("include_scratchpad", False))
    status: TaskStatus | None = None
    status_filter = params.get("filter")
    if isinstance(status_filter, str) and status_filter.strip():
        status = TaskStatus(status_filter.strip().upper())

    tasks = await ctx.task_service.list_tasks(project_id=project_id, status=status)
    excluded_task_ids = set(str_list(params.get("exclude_task_ids")))
    filtered_tasks = [task for task in tasks if task.id not in excluded_task_ids]

    runtime_service = getattr(ctx, "runtime_service", None)
    serialized_tasks: list[dict[str, Any]] = []
    for task in filtered_tasks:
        payload = task_to_dict(task, runtime_service=runtime_service)
        if include_scratchpad:
            payload["scratchpad"] = await ctx.task_service.get_scratchpad(task.id)
        serialized_tasks.append(payload)
    return {"tasks": serialized_tasks, "count": len(filtered_tasks)}


@command("tasks", "search", description="Search tasks by text query.")
async def search_tasks(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    query = str(params.get("query", "")).strip()
    if not query:
        return {"tasks": [], "count": 0}
    tasks = await ctx.task_service.search(query)
    runtime_service = getattr(ctx, "runtime_service", None)
    return {
        "tasks": [task_to_dict(task, runtime_service=runtime_service) for task in tasks],
        "count": len(tasks),
    }


@command("tasks", "scratchpad", description="Get a task's scratchpad content.")
async def get_scratchpad(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    content_limit = _bounded_int(
        params.get("content_char_limit"),
        default=_DEFAULT_TASK_SCRATCHPAD_CHAR_LIMIT,
        minimum=256,
        maximum=200_000,
    )
    scratchpad = await ctx.task_service.get_scratchpad(task_id)
    content, truncated = _truncate_for_transport(scratchpad, limit=content_limit)
    return {"task_id": task_id, "content": content, "truncated": truncated}


@command("tasks", "context", description="Get task context for AI tools.")
async def get_task_context(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        return {"found": False, "task": None}

    scratchpad = await ctx.task_service.get_scratchpad(task_id)
    linked_task_ids = await ctx.task_service.get_task_links(task_id)
    linked_tasks: list[dict[str, Any]] = []
    for linked_task_id in linked_task_ids:
        linked = await ctx.task_service.get_task(linked_task_id)
        if linked is None:
            continue
        linked_tasks.append(
            {
                "task_id": linked.id,
                "title": linked.title,
                "status": linked.status.value,
                "description": linked.description,
            }
        )
    linked_tasks.sort(key=lambda item: item["task_id"])

    workspace_id: str | None = None
    workspace_branch: str | None = None
    workspace_path: str | None = None
    repos: list[dict[str, Any]] = []

    workspaces = await ctx.workspace_service.list_workspaces(task_id=task_id)
    if workspaces:
        workspace = workspaces[0]
        workspace_id = workspace.id
        workspace_branch = workspace.branch_name
        workspace_path = workspace.path
        try:
            workspace_repos = await ctx.workspace_service.get_workspace_repos(workspace.id)
            repos = [
                {
                    "repo_id": repo["repo_id"],
                    "name": repo["repo_name"],
                    "path": repo["repo_path"],
                    "worktree_path": repo.get("worktree_path"),
                    "target_branch": repo.get("target_branch"),
                    "has_changes": repo.get("has_changes"),
                }
                for repo in workspace_repos
            ]
        except (AttributeError, KeyError, LookupError, OSError, RuntimeError) as exc:
            logger.warning("commands.tasks: workspace repos unavailable: %s", exc)

    if not repos:
        try:
            project_repos = await ctx.project_service.get_project_repos(task.project_id)
            repos = [
                {
                    "repo_id": repo.id,
                    "name": repo.name,
                    "path": repo.path,
                    "worktree_path": None,
                    "target_branch": repo.default_branch,
                    "has_changes": None,
                }
                for repo in project_repos
            ]
        except (AttributeError, KeyError, LookupError, OSError, RuntimeError) as exc:
            logger.warning("commands.tasks: project repos unavailable: %s", exc)

    return {
        "task_id": task.id,
        "project_id": task.project_id,
        "title": task.title,
        "description": task.description,
        "status": task.status.value,
        "acceptance_criteria": task.acceptance_criteria,
        "scratchpad": scratchpad,
        "workspace_id": workspace_id,
        "workspace_branch": workspace_branch,
        "workspace_path": workspace_path,
        "repos": repos,
        "repo_count": len(repos),
        "linked_tasks": linked_tasks,
    }


@command("tasks", "logs", description="Return execution logs for a task.")
async def get_task_logs(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    raw_limit = params.get("limit", 5)
    limit = 5
    if isinstance(raw_limit, int) and not isinstance(raw_limit, bool):
        limit = max(1, min(raw_limit, 20))

    offset_value = parse_events_offset(params.get("offset"))
    if isinstance(offset_value, str):
        return {
            "success": False,
            "task_id": task_id,
            "message": offset_value,
            "code": "INVALID_OFFSET",
        }

    content_limit = _bounded_int(
        params.get("content_char_limit"),
        default=_DEFAULT_TASK_LOG_ENTRY_CHAR_LIMIT,
        minimum=256,
        maximum=200_000,
    )
    total_limit = _bounded_int(
        params.get("total_char_limit"),
        default=_DEFAULT_TASK_LOG_TOTAL_CHAR_LIMIT,
        minimum=content_limit,
        maximum=1_000_000,
    )
    raw_logs = await _task_logs_page(ctx, task_id=task_id, limit=limit, offset=offset_value)
    logs = raw_logs.get("logs", [])

    bounded_logs: list[dict[str, Any]] = []
    truncated = False
    used_chars = 0
    per_entry_overhead = 128
    for log in logs:
        if not isinstance(log, dict):
            continue
        raw_content = str(log.get("content", ""))
        content, entry_truncated = _truncate_for_transport(raw_content, limit=content_limit)
        if entry_truncated:
            truncated = True

        remaining = total_limit - used_chars - per_entry_overhead
        if remaining <= 0:
            truncated = True
            break
        if len(content) > remaining:
            content, _ = _truncate_for_transport(content, limit=remaining)
            truncated = True
        if not content:
            continue

        bounded_log = dict(log)
        bounded_log["content"] = content
        bounded_logs.append(bounded_log)
        used_chars += len(content) + per_entry_overhead

    total_runs_raw = raw_logs.get("total_runs")
    total_runs = total_runs_raw if isinstance(total_runs_raw, int) else offset_value + len(logs)
    page_limit_raw = raw_logs.get("limit")
    page_limit = page_limit_raw if isinstance(page_limit_raw, int) else limit
    returned_runs_raw = raw_logs.get("returned_runs")
    source_returned_runs = returned_runs_raw if isinstance(returned_runs_raw, int) else len(logs)
    next_offset_raw = raw_logs.get("next_offset")
    next_offset = next_offset_raw if isinstance(next_offset_raw, int) else None
    has_more_raw = raw_logs.get("has_more")
    has_more = has_more_raw if isinstance(has_more_raw, bool) else next_offset is not None
    if truncated and len(bounded_logs) < source_returned_runs:
        has_more = True
        next_offset = offset_value + len(bounded_logs)

    return {
        "task_id": task_id,
        "logs": bounded_logs,
        "count": len(bounded_logs),
        "total_runs": total_runs,
        "returned_runs": len(bounded_logs),
        "offset": offset_value,
        "limit": page_limit,
        "has_more": has_more,
        "next_offset": next_offset if has_more else None,
        "truncated": truncated,
    }


async def _task_logs_page(
    ctx: AppContext,
    *,
    task_id: str,
    limit: int,
    offset: int,
) -> dict[str, Any]:
    limit = max(1, min(limit, 20))
    offset = max(0, offset)
    executions = await ctx.execution_service.list_executions_for_task(
        task_id,
        limit=limit,
        offset=offset,
    )
    total_runs = offset + len(executions)
    with contextlib.suppress(AttributeError, KeyError, RuntimeError):
        total_runs = max(total_runs, await ctx.execution_service.count_executions_for_task(task_id))

    logs: list[dict[str, Any]] = []
    run_start = max(1, total_runs - offset - len(executions) + 1)
    for run_number, execution in enumerate(reversed(executions), start=run_start):
        try:
            log_entries = await ctx.execution_service.get_execution_log_entries(execution.id)
            content = "\n".join(entry.logs for entry in log_entries if entry.logs).strip()
            if not content:
                continue
            logs.append(
                {
                    "run": run_number,
                    "content": content,
                    "created_at": execution.created_at.isoformat(),
                }
            )
        except (AttributeError, KeyError, RuntimeError):
            pass

    next_offset = offset + len(executions)
    has_more = next_offset < total_runs
    return {
        "task_id": task_id,
        "logs": logs,
        "count": len(logs),
        "total_runs": total_runs,
        "returned_runs": len(logs),
        "offset": offset,
        "limit": limit,
        "has_more": has_more,
        "next_offset": next_offset if has_more else None,
    }


@command("tasks", "create", profile="operator", mutating=True, description="Create a new task.")
async def create_task(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    title = params["title"]
    description = params.get("description", "")
    project_id = params.get("project_id")
    created_by = params.get("created_by")

    task = await ctx.task_service.create_task(
        title=title,
        description=description,
        project_id=project_id,
        created_by=created_by,
    )

    fields = build_task_update_fields(params)
    for field in ("project_id", "title", "description"):
        fields.pop(field, None)
    if fields:
        updated = await ctx.task_service.update_fields(task.id, **fields)
        if updated is not None:
            task = updated
    return {"success": True, "task_id": task.id, "title": task.title, "status": task.status.value}


@command("tasks", "update", profile="operator", mutating=True, description="Update task fields.")
async def update_task(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    fields = build_task_update_fields(params)
    requested_done = fields.get("status") is TaskStatus.DONE

    try:
        task = await ctx.api.update_task(task_id, **fields)
    except ValueError as exc:
        if not requested_done:
            raise
        return _task_error_response(
            task_id,
            code="INVALID_STATUS_TRANSITION",
            message=str(exc),
            hint="Use review merge (or close no-change flow) from REVIEW to reach DONE.",
        )
    if task is None:
        return _task_not_found_response(task_id)
    return {"success": True, "task_id": task.id, "code": "UPDATED"}


@command(
    "tasks",
    "move",
    profile="operator",
    mutating=True,
    description="Move a task to a new status column.",
)
async def move_task(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    new_status = parse_task_status(params["status"])
    try:
        validate_transition(TaskStatus.BACKLOG, new_status)
        task = await ctx.task_service.move(task_id, new_status)
    except ValueError as exc:
        if new_status is not TaskStatus.DONE:
            raise
        return _task_error_response(
            task_id,
            code="INVALID_STATUS_TRANSITION",
            message=str(exc),
            hint="Use review merge (or close no-change flow) from REVIEW to reach DONE.",
        )
    if task is None:
        return _task_not_found_response(task_id)
    return {"success": True, "task_id": task.id, "new_status": task.status.value, "code": "MOVED"}


@command("tasks", "delete", profile="maintainer", mutating=True, description="Delete a task.")
async def delete_task(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        success, message = (False, f"Task {task_id} not found. Check task_id with task_list.")
    else:
        success, message = await ctx.workspace_service.delete_task(task)
    return {"success": success, "task_id": task_id, "message": message}


@command(
    "tasks",
    "update_scratchpad",
    profile="pair_worker",
    mutating=True,
    description="Append to task scratchpad.",
)
async def update_scratchpad(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    content = params["content"]
    existing = await ctx.task_service.get_scratchpad(task_id)
    updated = f"{existing}\n{content}".strip() if existing else content
    await ctx.task_service.update_scratchpad(task_id, updated)
    return {"success": True, "task_id": task_id}


@command(
    "review",
    "request",
    profile="pair_worker",
    mutating=True,
    description="Mark task ready for review.",
)
async def request_review(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    summary = params.get("summary", "")
    try:
        task = await ctx.api.request_review(task_id, summary)
    except ReviewGuardrailBlockedError as exc:
        return _review_error_response(task_id, exc)
    if task is None:
        return _task_not_found_response(task_id)
    return {
        "success": True,
        "task_id": task.id,
        "status": task.status.value,
        "code": "REVIEW_REQUESTED",
    }


@command(
    "review",
    "approve",
    profile="operator",
    mutating=True,
    description="Approve a task review.",
)
async def approve_review(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    try:
        task = await ctx.api.approve_task(task_id)
    except ReviewApprovalContextMissingError as exc:
        return _review_error_response(task_id, exc)

    if task is None:
        return _task_not_found_response(task_id)
    if task.status is not TaskStatus.REVIEW:
        return _task_error_response(
            task_id,
            code="REVIEW_NOT_READY",
            message=(
                f"Task is not in REVIEW (current: {task.status.value}). "
                "Move task to REVIEW before approving."
            ),
            hint="Use task_patch with transition='request_review' to move task to REVIEW.",
        )

    return {
        "success": True,
        "task_id": task.id,
        "status": "approved",
        "task_status": task.status.value,
        "code": "APPROVED",
    }


@command(
    "review",
    "reject",
    profile="operator",
    mutating=True,
    description="Reject a task review with feedback.",
)
async def reject_review(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    feedback = params.get("feedback", "")
    action = params.get("action", "reopen")
    updated = await ctx.api.reject_task(task_id, feedback, action)
    if updated is None:
        return _task_not_found_response(task_id)
    return {
        "success": True,
        "task_id": updated.id,
        "status": updated.status.value,
        "code": "REJECTED",
    }


@command(
    "tasks",
    "apply_rejection_feedback",
    profile="operator",
    mutating=True,
    description="Apply rejection feedback and move a task out of REVIEW.",
)
async def apply_rejection_feedback(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    feedback = params.get("feedback")
    action = params.get("action", "reopen")
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        return _task_not_found_response(task_id)
    updated = await ctx.api.apply_rejection_feedback(task, feedback, action)
    if updated is None:
        return _task_not_found_response(task_id)
    return {
        "success": True,
        "task_id": updated.id,
        "status": updated.status.value,
    }


@command(
    "tasks",
    "close_exploratory",
    profile="operator",
    mutating=True,
    description="Close a no-change task by marking DONE and archiving its workspace.",
)
async def close_exploratory(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        return _task_not_found_response(task_id)
    success, message = await ctx.api.close_exploratory(task)
    return {"success": success, "task_id": task_id, "message": message}


@command(
    "tasks",
    "has_no_changes",
    description="Check if a task has no uncommitted changes or new commits.",
)
async def has_no_changes(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        return _task_not_found_response(task_id)
    result = await ctx.api.has_no_changes(task)
    return {"task_id": task_id, "has_no_changes": result}


@command(
    "tasks",
    "merge_task_direct",
    profile="operator",
    mutating=True,
    description="Merge task changes directly.",
)
async def merge_task_direct(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        return _task_not_found_response(task_id)
    success, message = await ctx.api.merge_task_direct(task)
    return {"success": success, "task_id": task_id, "message": message}


@command(
    "tasks",
    "prepare_auto_output",
    description="Prepare AUTO output modal readiness for a task.",
)
async def prepare_auto_output(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        return _task_not_found_response(task_id)
    readiness = await ctx.api.prepare_auto_output(task)
    return {
        "task_id": task_id,
        "can_open_output": readiness.can_open_output,
        "execution_id": readiness.execution_id,
        "is_running": readiness.is_running,
        "recovered_stale_execution": readiness.recovered_stale_execution,
        "message": readiness.message,
        "output_mode": readiness.output_mode.value,
    }


@command(
    "tasks",
    "recover_stale_auto_output",
    description="Recover stale AUTO output for a task.",
)
async def recover_stale_auto_output(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        return _task_not_found_response(task_id)
    result = await ctx.api.recover_stale_auto_output(task)
    return {
        "task_id": task_id,
        "success": result.success,
        "message": result.message,
    }


@command(
    "tasks",
    "resolve_task_base_branch",
    description="Resolve effective base branch for a task.",
)
async def resolve_task_base_branch(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    task_id = params["task_id"]
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        return _task_not_found_response(task_id)
    branch = await ctx.api.resolve_task_base_branch(task)
    return {"task_id": task_id, "branch": branch}


__all__ = [
    "apply_rejection_feedback",
    "approve_review",
    "close_exploratory",
    "create_task",
    "delete_task",
    "get_scratchpad",
    "get_task",
    "get_task_context",
    "get_task_logs",
    "has_no_changes",
    "list_tasks",
    "merge_task_direct",
    "move_task",
    "prepare_auto_output",
    "recover_stale_auto_output",
    "reject_review",
    "request_review",
    "resolve_task_base_branch",
    "search_tasks",
    "update_scratchpad",
    "update_task",
]
