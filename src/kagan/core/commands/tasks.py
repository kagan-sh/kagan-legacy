from __future__ import annotations

import asyncio
import contextlib
import logging
from typing import TYPE_CHECKING, Any

from kagan.core.domain.enums import TaskStatus, TaskType
from kagan.core.domain.task_rules import validate_transition
from kagan.core.plugins.sdk import PLUGIN_HOOK_VALIDATE_REVIEW
from kagan.core.policy import command
from kagan.core.time import utc_now

from ._parsing import (
    build_task_update_fields,
    parse_events_offset,
    parse_task_status,
    str_list,
)
from ._serialization import task_to_dict

if TYPE_CHECKING:
    from kagan.core.adapters.db.schema import Task
    from kagan.core.bootstrap import AppContext

logger = logging.getLogger(__name__)
_DEFAULT_TASK_SCRATCHPAD_CHAR_LIMIT = 16_000
_DEFAULT_TASK_LOG_ENTRY_CHAR_LIMIT = 6_000
_DEFAULT_TASK_LOG_TOTAL_CHAR_LIMIT = 18_000
_REVIEW_GUARDRAIL_TIMEOUT_SECONDS = 30.0


def _task_not_found_response(task_id: str) -> dict[str, Any]:
    return {
        "success": False,
        "task_id": task_id,
        "message": f"Task {task_id} not found. Check task_id with task_list.",
        "code": "TASK_NOT_FOUND",
    }


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


def _truncate_for_transport(content: str, *, limit: int) -> tuple[str, bool]:
    if limit <= 0:
        return "", bool(content)
    if len(content) <= limit:
        return content, False
    omitted_chars = len(content) - limit
    return f"{content[:limit]}\n\n[truncated {omitted_chars} chars for transport]", True


async def _set_latest_review_result(
    ctx: AppContext,
    task_id: str,
    *,
    status: str,
    summary: str,
    approved: bool,
) -> bool:
    execution_service = getattr(ctx, "execution_service", None)
    if execution_service is None:
        return False
    execution = await execution_service.get_latest_execution_for_task(task_id)
    if execution is None:
        return False

    review_result: dict[str, object] = {
        "status": status,
        "summary": summary,
        "approved": approved,
    }
    timestamp = utc_now().isoformat()
    if status == "approved":
        review_result["completed_at"] = timestamp
    else:
        review_result["requested_at"] = timestamp

    metadata = dict(execution.metadata_ or {})
    metadata["review_result"] = review_result
    await execution_service.update_execution(execution.id, metadata=metadata)
    return True


async def _check_review_guardrails(ctx: AppContext, task: Task) -> dict[str, Any]:
    plugin_registry = getattr(ctx, "plugin_registry", None)
    if plugin_registry is None:
        return {"allowed": True}
    operations_for_method = getattr(plugin_registry, "operations_for_method", None)
    if not callable(operations_for_method):
        return {"allowed": True}
    operations = tuple(operations_for_method(PLUGIN_HOOK_VALIDATE_REVIEW))
    if not operations:
        return {"allowed": True}

    for operation in operations:
        plugin_id = getattr(operation, "plugin_id", "<unknown-plugin>")
        try:
            result = await asyncio.wait_for(
                operation.handler(
                    ctx,
                    {
                        "task_id": task.id,
                        "project_id": task.project_id,
                    },
                ),
                timeout=_REVIEW_GUARDRAIL_TIMEOUT_SECONDS,
            )
        except TimeoutError as exc:
            return {
                "allowed": False,
                "code": "REVIEW_GUARDRAIL_TIMEOUT",
                "message": "REVIEW transition blocked: review guardrail check timed out.",
                "hint": (
                    "Retry, or investigate plugin health. Details: "
                    f"{plugin_id}.{PLUGIN_HOOK_VALIDATE_REVIEW} timed out after "
                    f"{_REVIEW_GUARDRAIL_TIMEOUT_SECONDS:.0f}s: {exc}"
                ),
            }
        except Exception as exc:
            return {
                "allowed": False,
                "code": "REVIEW_GUARDRAIL_CHECK_FAILED",
                "message": "REVIEW transition blocked: failed to verify review guardrails.",
                "hint": (
                    "Resolve plugin health and retry. Details: "
                    f"{plugin_id}.{PLUGIN_HOOK_VALIDATE_REVIEW} failed: {exc}"
                ),
            }

        if not isinstance(result, dict):
            return {
                "allowed": False,
                "code": "REVIEW_GUARDRAIL_CHECK_FAILED",
                "message": "REVIEW transition blocked: failed to verify review guardrails.",
                "hint": (
                    "Resolve plugin health and retry. Details: "
                    f"{plugin_id}.{PLUGIN_HOOK_VALIDATE_REVIEW} returned non-dict response."
                ),
            }
        if not isinstance(result.get("allowed"), bool):
            return {
                "allowed": False,
                "code": "REVIEW_GUARDRAIL_CHECK_FAILED",
                "message": "REVIEW transition blocked: failed to verify review guardrails.",
                "hint": (
                    "Resolve plugin health and retry. Details: "
                    f"{plugin_id}.{PLUGIN_HOOK_VALIDATE_REVIEW} response missing boolean 'allowed'."
                ),
            }
        if not bool(result["allowed"]):
            return result

    return {"allowed": True}


async def _handle_task_type_transition(
    ctx: AppContext,
    *,
    task_id: str,
    current_type: TaskType,
    new_type: TaskType,
    fields: dict[str, object],
) -> None:
    if current_type == new_type:
        return
    if current_type == TaskType.PAIR and new_type == TaskType.AUTO:
        if await ctx.session_service.session_exists(task_id):
            await ctx.session_service.kill_session(task_id)
        fields["terminal_backend"] = None
        return
    if current_type == TaskType.AUTO and new_type == TaskType.PAIR:
        if ctx.automation_service.is_running(task_id):
            await ctx.automation_service.stop_task(task_id)


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

    current = await ctx.task_service.get_task(task_id)
    if current is None:
        return _task_not_found_response(task_id)

    status_value = fields.get("status")
    if status_value is not None:
        target = TaskStatus(status_value) if isinstance(status_value, str) else status_value
        validate_transition(current.status, target)

    new_task_type = fields.get("task_type")
    if isinstance(new_task_type, TaskType) and new_task_type != current.task_type:
        await _handle_task_type_transition(
            ctx,
            task_id=task_id,
            current_type=current.task_type,
            new_type=new_task_type,
            fields=fields,
        )

    try:
        task = await ctx.task_service.update_fields(task_id, **fields)
    except ValueError as exc:
        if not requested_done:
            raise
        return {
            "success": False,
            "task_id": task_id,
            "message": str(exc),
            "code": "INVALID_STATUS_TRANSITION",
            "hint": "Use review merge (or close no-change flow) from REVIEW to reach DONE.",
        }
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
        return {
            "success": False,
            "task_id": task_id,
            "message": str(exc),
            "code": "INVALID_STATUS_TRANSITION",
            "hint": "Use review merge (or close no-change flow) from REVIEW to reach DONE.",
        }
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
    from kagan.core.api import ReviewGuardrailBlockedError

    task_id = params["task_id"]
    summary = params.get("summary", "")
    try:
        task = await ctx.api.request_review(task_id, summary)
    except ReviewGuardrailBlockedError as exc:
        response: dict[str, Any] = {
            "success": False,
            "task_id": task_id,
            "code": exc.code,
            "message": exc.message,
        }
        if exc.hint is not None and exc.hint.strip():
            response["hint"] = exc.hint
        return response
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
    current_task = await ctx.task_service.get_task(task_id)
    if current_task is None:
        return _task_not_found_response(task_id)
    if current_task.status is not TaskStatus.REVIEW:
        return {
            "success": False,
            "task_id": task_id,
            "message": (
                f"Task is not in REVIEW (current: {current_task.status.value}). "
                "Move task to REVIEW before approving."
            ),
            "code": "REVIEW_NOT_READY",
            "hint": "Use task_patch with transition='request_review' to move task to REVIEW.",
        }

    persisted = await _set_latest_review_result(
        ctx,
        task_id,
        status="approved",
        summary="",
        approved=True,
    )
    if not persisted:
        return {
            "success": False,
            "task_id": task_id,
            "code": "REVIEW_APPROVAL_CONTEXT_MISSING",
            "message": (
                "Cannot approve review: no execution context exists for this task. "
                "Run or attach review execution before approving."
            ),
            "hint": "Create a review execution for this task, then retry approve.",
        }

    return {
        "success": True,
        "task_id": current_task.id,
        "status": "approved",
        "task_status": current_task.status.value,
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
    task = await ctx.task_service.get_task(task_id)
    if task is None:
        return _task_not_found_response(task_id)
    updated = await ctx.workspace_service.apply_rejection_feedback(task, feedback, action)
    if updated is None:
        return _task_not_found_response(task_id)
    return {
        "success": True,
        "task_id": updated.id,
        "status": updated.status.value,
        "code": "REJECTED",
    }


__all__ = [
    "approve_review",
    "create_task",
    "delete_task",
    "get_scratchpad",
    "get_task",
    "get_task_context",
    "get_task_logs",
    "list_tasks",
    "move_task",
    "reject_review",
    "request_review",
    "search_tasks",
    "update_scratchpad",
    "update_task",
]
