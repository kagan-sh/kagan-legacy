"""kagan.mcp.toolsets.tasks — Task domain MCP tools."""

import asyncio
import contextlib
import json
from typing import Any, TypedDict

from mcp.server.fastmcp import Context, FastMCP

from kagan.core import Priority, TaskStatus, WorkMode, parse_priority, parse_work_mode
from kagan.core.errors import KaganError, ValidationError
from kagan.mcp._policy import is_tool_allowed
from kagan.mcp.server import ServerOptions, get_context
from kagan.mcp.toolsets import mcp_error_boundary


class _BatchTaskEntry(TypedDict, total=False):
    title: str
    description: str
    execution_mode: str
    priority: str | int
    base_branch: str | None
    acceptance_criteria: list[str] | None
    agent_backend: str | None
    launcher: str | None


def _resolve_task_id(ctx: Context, task_id: str | None) -> str:
    if task_id is not None:
        return task_id
    app = get_context(ctx)
    if app.bound_task_id is not None:
        return app.bound_task_id
    raise ValueError("task_id is required unless the server is session-bound")


def _resolve_task_ids(ctx: Context, task_ids: list[str] | None) -> list[str]:
    if task_ids is None:
        return [_resolve_task_id(ctx, None)]
    normalized = [task_id.strip() for task_id in task_ids if task_id.strip()]
    if not normalized:
        raise ValidationError("task_ids", "At least one task id is required")
    return list(dict.fromkeys(normalized))


def _task_to_dict(task: Any) -> dict[str, Any]:
    return {
        "id": task.id,
        "title": task.title,
        "description": getattr(task, "description", ""),
        "status": task.status.value,
        "priority": task.priority.name,
        "execution_mode": task.execution_mode.value,
        "base_branch": getattr(task, "base_branch", None),
        "acceptance_criteria": getattr(task, "acceptance_criteria", []),
        "agent_backend": getattr(task, "agent_backend", None),
        "launcher": getattr(task, "launcher", None),
        "review_approved": getattr(task, "review_approved", False),
        "review_verdicts": getattr(task, "review_verdicts", []) or [],
    }


def _clamp_int(value: int, *, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _payload_json(payload: Any) -> str:
    return json.dumps(
        payload, ensure_ascii=True, sort_keys=True, separators=(",", ":"), default=str
    )


def _parse_wait_for_task_statuses(
    wait_for_status: list[str] | str | None,
) -> set[TaskStatus] | None:
    if wait_for_status is None:
        return None
    values = [wait_for_status] if isinstance(wait_for_status, str) else wait_for_status
    normalized = [value.strip().upper() for value in values if value.strip()]
    if not normalized:
        return None
    try:
        return {TaskStatus(value) for value in normalized}
    except ValueError as exc:
        allowed = ", ".join(status.value for status in TaskStatus)
        raise ValidationError(
            "wait_for_status",
            f"Unknown task status in {normalized!r}. Allowed values: {allowed}",
        ) from exc


def _build_update_verification(
    task_payload: dict[str, Any],
    *,
    title: str | None,
    description: str | None,
    priority: Priority | None,
    execution_mode: WorkMode | None,
    base_branch: str | None,
    acceptance_criteria: list[str] | None,
    agent_backend: str | None,
    status: TaskStatus | None,
) -> dict[str, Any]:
    requested: dict[str, Any] = {}
    if title is not None:
        requested["title"] = title
    if description is not None:
        requested["description"] = description
    if priority is not None:
        requested["priority"] = priority.name
    if execution_mode is not None:
        requested["execution_mode"] = execution_mode.value
    if base_branch is not None:
        requested["base_branch"] = base_branch
    if acceptance_criteria is not None:
        requested["acceptance_criteria"] = acceptance_criteria
    if agent_backend is not None:
        requested["agent_backend"] = agent_backend
    if status is not None:
        requested["status"] = status.value

    applied = {field: task_payload.get(field) for field in requested}
    mismatched_fields = [
        field for field, expected in requested.items() if applied.get(field) != expected
    ]
    return {
        "requested": requested,
        "applied": applied,
        "all_applied": not mismatched_fields,
        "mismatched_fields": mismatched_fields,
    }


@mcp_error_boundary
async def _task_get(ctx: Context, task_id: str | None = None) -> dict:
    """Get a task by ID.

    The response includes a ``board_hint`` field summarizing other active
    tasks in the same project so the agent can decide whether to call
    ``task_list()`` for coordination.
    """
    app = get_context(ctx)
    resolved_task_id = _resolve_task_id(ctx, task_id)
    task = await app.client.tasks.get(resolved_task_id)
    result = _task_to_dict(task)
    if app.bound_session_id is not None:
        result["session_id"] = app.bound_session_id

    try:
        all_tasks = await app.client.tasks.list()
        siblings = [t for t in all_tasks if t.id != resolved_task_id]
        active = [t for t in siblings if t.status in (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW)]
        if active:
            hint_lines = [f"{len(active)} active sibling task(s):"]
            for t in active[:5]:
                hint_lines.append(f"- {t.id} | {t.title} | {t.status.value}")
            if len(active) > 5:
                hint_lines.append(f"  ... and {len(active) - 5} more")
            hint_lines.append("Call task_list() or task_get(id) for full details.")
            result["board_hint"] = "\n".join(hint_lines)
        elif siblings:
            result["board_hint"] = (
                f"{len(siblings)} other task(s) in project (none currently active)."
            )
    except Exception:
        pass  # Board hint is best-effort; never block task_get

    return result


@mcp_error_boundary
async def _task_list(ctx: Context, status: str | None = None) -> dict:
    app = get_context(ctx)
    status_enum = TaskStatus(status) if status else None
    tasks = await app.client.tasks.list(status=status_enum)
    result_tasks = [_task_to_dict(t) for t in tasks]
    if app.bound_session_id is not None:
        for t in result_tasks:
            t["session_id"] = app.bound_session_id
    return {"tasks": result_tasks}


@mcp_error_boundary
async def _task_create(
    ctx: Context,
    title: str,
    description: str = "",
    execution_mode: str | None = None,
    priority: str | int | None = None,
    base_branch: str | None = None,
    acceptance_criteria: list[str] | None = None,
    agent_backend: str | None = None,
    launcher: str | None = None,
) -> dict:
    app = get_context(ctx)
    priority_enum = parse_priority(priority)
    mode_enum = parse_work_mode(execution_mode)
    task = await app.client.tasks.create(
        title,
        description=description,
        execution_mode=mode_enum,
        priority=priority_enum,
        base_branch=base_branch,
        acceptance_criteria=acceptance_criteria,
        agent_backend=agent_backend,
        launcher=launcher,
    )
    result = _task_to_dict(task)
    if app.bound_session_id is not None:
        result["session_id"] = app.bound_session_id
    return result


@mcp_error_boundary
async def _task_update(
    ctx: Context,
    task_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    priority: str | int | None = None,
    execution_mode: str | None = None,
    base_branch: str | None = None,
    acceptance_criteria: list[str] | None = None,
    agent_backend: str | None = None,
    launcher: str | None = None,
    status: str | None = None,
) -> dict:
    app = get_context(ctx)
    resolved_task_id = _resolve_task_id(ctx, task_id)
    priority_enum = parse_priority(priority) if priority is not None else None
    mode_enum = parse_work_mode(execution_mode) if execution_mode is not None else None
    status_enum = TaskStatus(status) if status is not None else None
    task = await app.client.tasks.update(
        resolved_task_id,
        title=title,
        description=description,
        priority=priority_enum,
        execution_mode=mode_enum,
        base_branch=base_branch,
        acceptance_criteria=acceptance_criteria,
        agent_backend=agent_backend,
        launcher=launcher,
    )
    if status_enum is not None:
        task = await app.client.tasks.set_status(resolved_task_id, status_enum)
    result = _task_to_dict(task)
    result["verification"] = _build_update_verification(
        result,
        title=title,
        description=description,
        priority=priority_enum,
        execution_mode=mode_enum,
        base_branch=base_branch,
        acceptance_criteria=acceptance_criteria,
        agent_backend=agent_backend,
        status=status_enum,
    )
    return result


@mcp_error_boundary
async def _task_add_note(ctx: Context, note: str, task_id: str | None = None) -> dict:
    app = get_context(ctx)
    resolved_task_id = _resolve_task_id(ctx, task_id)
    await app.client.tasks.add_note(resolved_task_id, note)
    return {"task_id": resolved_task_id, "success": True}


@mcp_error_boundary
async def _task_search(ctx: Context, query: str) -> dict:
    app = get_context(ctx)
    tasks = await app.client.tasks.search(query)
    return {"tasks": [_task_to_dict(t) for t in tasks]}


@mcp_error_boundary
async def _task_events(
    ctx: Context,
    task_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_payload: bool = False,
    max_payload_bytes: int = 16384,
    max_total_bytes: int = 262144,
) -> dict:
    app = get_context(ctx)
    resolved_task_id = _resolve_task_id(ctx, task_id)
    safe_limit = _clamp_int(limit, minimum=1, maximum=200)
    safe_offset = max(0, offset)
    safe_max_payload_bytes = _clamp_int(max_payload_bytes, minimum=256, maximum=131072)
    safe_max_total_bytes = _clamp_int(max_total_bytes, minimum=4096, maximum=1048576)

    events = await app.client.tasks.events.list(
        resolved_task_id, offset=safe_offset, limit=safe_limit
    )

    logs: list[dict[str, Any]] = []
    bytes_used = 0
    truncated_by_budget = False

    for event in events:
        serialized_payload = _payload_json(event.payload)
        payload_size_bytes = len(serialized_payload.encode("utf-8"))
        preview = serialized_payload.encode("utf-8")[:safe_max_payload_bytes].decode(
            "utf-8", errors="ignore"
        )
        payload_truncated = payload_size_bytes > safe_max_payload_bytes

        item: dict[str, Any] = {
            "event_type": event.event_type.value,
            "payload_size_bytes": payload_size_bytes,
            "payload_truncated": payload_truncated,
            "payload_preview": preview,
        }
        if include_payload:
            if payload_truncated:
                item["payload"] = {
                    "truncated": True,
                    "preview": preview,
                    "original_size_bytes": payload_size_bytes,
                }
            else:
                item["payload"] = event.payload

        item_size = len(_payload_json(item).encode("utf-8"))
        if logs and bytes_used + item_size > safe_max_total_bytes:
            truncated_by_budget = True
            break
        if not logs and item_size > safe_max_total_bytes:
            item["payload_preview"] = (
                item["payload_preview"].encode("utf-8")[:2048].decode("utf-8", errors="ignore")
            )
            item["payload_truncated"] = True
            if include_payload:
                item["payload"] = {
                    "truncated": True,
                    "preview": item["payload_preview"],
                    "original_size_bytes": payload_size_bytes,
                }
            logs.append(item)
            truncated_by_budget = True
            break
        bytes_used += item_size
        logs.append(item)

    return {
        "task_id": resolved_task_id,
        "offset": safe_offset,
        "limit": safe_limit,
        "returned": len(logs),
        "truncated_by_total_bytes": truncated_by_budget,
        "logs": logs,
    }


@mcp_error_boundary
async def _tasks_wait(
    ctx: Context,
    task_ids: list[str] | None = None,
    timeout_seconds: float | None = None,
    wait_for_status: list[str] | str | None = None,
    resolve_when_any: bool = False,
) -> dict:
    app = get_context(ctx)
    resolved_task_ids = _resolve_task_ids(ctx, task_ids)
    statuses = _parse_wait_for_task_statuses(wait_for_status)
    resolved: list[str] = []
    latest_by_id: dict[str, Any] = {}

    if resolve_when_any:
        waiters = {
            task_id: asyncio.create_task(
                app.client.tasks.wait_for_completion(
                    task_id,
                    timeout=timeout_seconds,
                    wait_for_status=statuses,
                )
            )
            for task_id in resolved_task_ids
        }
        waiter_to_task_id = {waiter: task_id for task_id, waiter in waiters.items()}
        done, pending = await asyncio.wait(
            set(waiters.values()),
            return_when=asyncio.FIRST_COMPLETED,
        )
        first_done = next(iter(done))
        winner_task_id = waiter_to_task_id[first_done]
        winner_task, winner_timed_out = await first_done

        for waiter in pending:
            waiter.cancel()
        for waiter in pending:
            with contextlib.suppress(asyncio.CancelledError):
                await waiter

        for task_id in resolved_task_ids:
            if task_id == winner_task_id:
                latest_by_id[task_id] = winner_task
            else:
                latest_by_id[task_id] = await app.client.tasks.get(task_id)

        if not winner_timed_out:
            resolved = [winner_task_id]
        timed_out = winner_timed_out
    else:
        results = await asyncio.gather(
            *[
                app.client.tasks.wait_for_completion(
                    task_id,
                    timeout=timeout_seconds,
                    wait_for_status=statuses,
                )
                for task_id in resolved_task_ids
            ]
        )
        timed_out = False
        for task_id, (task, task_timed_out) in zip(resolved_task_ids, results, strict=True):
            latest_by_id[task_id] = task
            if task_timed_out:
                timed_out = True
            else:
                resolved.append(task_id)

    pending_task_ids = [task_id for task_id in resolved_task_ids if task_id not in set(resolved)]
    return {
        "task_ids": resolved_task_ids,
        "tasks": [
            {"task_id": task_id, "status": latest_by_id[task_id].status.value}
            for task_id in resolved_task_ids
        ],
        "resolved_task_ids": resolved,
        "pending_task_ids": pending_task_ids,
        "resolve_when_any": resolve_when_any,
        "timed_out": timed_out,
    }


@mcp_error_boundary
async def _task_counts(ctx: Context) -> dict:
    app = get_context(ctx)
    return await app.client.tasks.counts()


@mcp_error_boundary
async def _task_delete(ctx: Context, task_id: str) -> dict:
    app = get_context(ctx)
    await app.client.tasks.delete(task_id)
    return {"task_id": task_id, "deleted": True}


@mcp_error_boundary
async def _task_batch_create(ctx: Context, tasks: list[_BatchTaskEntry]) -> dict:
    """Create multiple tasks at once.

    Each entry must have a ``title`` key and may include ``description``,
    ``execution_mode`` (AUTO or PAIR), ``priority``, ``base_branch``,
    ``acceptance_criteria``, and ``agent_backend``.
    Returns the list of created tasks.
    """
    app = get_context(ctx)
    created: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for idx, entry in enumerate(tasks):
        title = entry.get("title", "").strip()
        if not title:
            errors.append({"index": str(idx), "error": "title is required"})
            continue
        try:
            mode = parse_work_mode(entry.get("execution_mode"))
            pri = parse_priority(entry.get("priority"))
            criteria_raw = entry.get("acceptance_criteria")
            criteria = criteria_raw if isinstance(criteria_raw, list) else None
            task = await app.client.tasks.create(
                title,
                description=entry.get("description", ""),
                execution_mode=mode,
                priority=pri,
                base_branch=entry.get("base_branch"),
                acceptance_criteria=criteria,
                agent_backend=entry.get("agent_backend"),
                launcher=entry.get("launcher"),
            )
            created.append(_task_to_dict(task))
        except (KaganError, ValueError, TypeError, KeyError) as exc:
            errors.append({"index": str(idx), "error": str(exc)})
    return {
        "created": created,
        "errors": errors,
        "created_count": len(created),
        "error_count": len(errors),
    }


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register task domain tools on mcp, filtered by opts."""
    _tools = [
        ("task_get", _task_get),
        ("task_list", _task_list),
        ("task_create", _task_create),
        ("task_update", _task_update),
        ("task_add_note", _task_add_note),
        ("task_search", _task_search),
        ("task_events", _task_events),
        ("tasks_wait", _tasks_wait),
        ("task_counts", _task_counts),
        ("task_delete", _task_delete),
        ("task_batch_create", _task_batch_create),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
