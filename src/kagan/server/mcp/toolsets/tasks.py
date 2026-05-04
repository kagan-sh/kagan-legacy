"""kagan.server.mcp.toolsets.tasks — Task domain MCP tools.

7 tools: task_get, task_list, task_create, task_update, task_delete, task_events, task_wait.
"""

import asyncio
import contextlib
import json
from typing import Any

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

from kagan.core import Priority, TaskStatus, parse_priority
from kagan.core._io.tasks import TaskCreateRequest
from kagan.core.errors import KaganError, ValidationError
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary


def _resolve_task_id(ctx: Context, task_id: str | None) -> str:
    if task_id is not None:
        return task_id
    app = get_context(ctx)
    if app.bound_task_id is not None:
        return app.bound_task_id
    raise ValidationError("task_id", "required unless the server is session-bound")


async def _resolve_default_repo_id(ctx: Context) -> str | None:
    """Return the first repo for the active project, or None if no repos exist."""
    app = get_context(ctx)
    if app.bound_project_id is None:
        return None
    repos = await app.client.projects.repos(app.bound_project_id)
    return repos[0].id if repos else None


def _resolve_task_ids(ctx: Context, task_ids: list[str] | None) -> list[str]:
    if task_ids is None:
        return [_resolve_task_id(ctx, None)]
    normalized = [task_id.strip() for task_id in task_ids if task_id.strip()]
    if not normalized:
        raise ValidationError("task_ids", "At least one task id is required")
    return list(dict.fromkeys(normalized))


async def _task_to_dict(task: Any, engine: Any) -> dict[str, Any]:
    """Serialize a Task ORM row to a dict suitable for MCP tool responses.

    Loads acceptance_criteria from the AcceptanceCriterion table and computes
    review_approved from ReviewVerdict rows.
    """
    from sqlmodel import select as _select

    from kagan.core._db_helpers import _db_async
    from kagan.core._reviews import is_review_approved
    from kagan.core.models import AcceptanceCriterion as _AC

    criteria = await _db_async(
        engine,
        lambda s: [
            c.text
            for c in s.exec(
                _select(_AC).where(_AC.task_id == task.id).order_by(_AC.ordinal)  # type: ignore[arg-type]
            ).all()
        ],
    )
    approved = await asyncio.to_thread(is_review_approved, task.id, engine)
    return {
        "id": task.id,
        "title": task.title,
        "description": getattr(task, "description", ""),
        "status": task.status.value,
        "priority": task.priority.name,
        "base_branch": getattr(task, "base_branch", None),
        "acceptance_criteria": criteria,
        "agent_backend": getattr(task, "agent_backend", None),
        "launcher": getattr(task, "launcher", None),
        "repo_id": getattr(task, "repo_id", None),
        "github_issue": getattr(task, "github_issue", None),
        "review_approved": approved,
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
    base_branch: str | None,
    acceptance_criteria: list[str] | None,
    agent_backend: str | None,
    launcher: str | None,
    status: TaskStatus | None,
) -> dict[str, Any]:
    requested: dict[str, Any] = {}
    if title is not None:
        requested["title"] = title
    if description is not None:
        requested["description"] = description
    if priority is not None:
        requested["priority"] = priority.name
    if base_branch is not None:
        requested["base_branch"] = base_branch
    if acceptance_criteria is not None:
        requested["acceptance_criteria"] = acceptance_criteria
    if agent_backend is not None:
        requested["agent_backend"] = agent_backend
    if launcher is not None:
        requested["launcher"] = launcher
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
    result = await _task_to_dict(task, app.client.engine)
    if app.bound_session_id is not None:
        result["session_id"] = app.bound_session_id

    # Include worktree path so agents know where task files live
    try:
        ws = await app.client.worktrees.get(resolved_task_id)
        if ws is not None:
            result["worktree_path"] = ws.worktree_path
    except (KaganError, OSError) as exc:
        logger.debug("Failed to fetch worktree for task {}: {}", resolved_task_id, exc)

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
async def _task_list(
    ctx: Context,
    status: str | None = None,
    repo_id: str | None = None,
    query: str | None = None,
) -> dict:
    """List tasks, optionally filtered by status, repo, or free-text query.

    Use this to inspect project state before planning or mutating work.
    Pass ``query`` to search tasks by text within the active project.
    """
    app = get_context(ctx)

    # If a free-text query is provided, use search and apply filters in-memory
    if query is not None:
        tasks = await app.client.tasks.search(query)
        if status is not None:
            status_enum = TaskStatus(status)
            tasks = [t for t in tasks if t.status == status_enum]
        if repo_id is not None:
            tasks = [t for t in tasks if getattr(t, "repo_id", None) == repo_id]
    else:
        status_enum = TaskStatus(status) if status else None
        tasks = await app.client.tasks.list(status=status_enum, repo_id=repo_id)

    result_tasks = await asyncio.gather(*[_task_to_dict(t, app.client.engine) for t in tasks])
    result_list = list(result_tasks)
    if app.bound_session_id is not None:
        for t in result_list:
            t["session_id"] = app.bound_session_id
    return {"tasks": result_list}


@mcp_error_boundary
async def _task_create(
    ctx: Context,
    tasks: list[dict[str, Any]] | None = None,
    title: str | None = None,
    description: str = "",
    priority: str | int | None = None,
    base_branch: str | None = None,
    acceptance_criteria: list[str] | None = None,
    agent_backend: str | None = None,
    launcher: str | None = None,
    repo_id: str | None = None,
    github_issue: str | None = None,
) -> dict:
    """Create one or more tasks on the active board.

    For a single task, pass ``title`` directly.
    For multiple tasks, pass ``tasks`` as a list of entries (each with at least a ``title``).
    Include acceptance criteria when you want downstream review to stay concrete.
    """
    app = get_context(ctx)
    default_repo_id = await _resolve_default_repo_id(ctx)

    # Normalize: single-task params → batch list
    if tasks is not None and title is not None:
        raise ValidationError("tasks", "pass either 'tasks' list or 'title', not both")
    if tasks is None:
        if title is None:
            raise ValidationError("title", "title is required when tasks list is not provided")
        tasks = [
            {
                "title": title,
                "description": description,
                "priority": priority,
                "base_branch": base_branch,
                "acceptance_criteria": acceptance_criteria,
                "agent_backend": agent_backend,
                "launcher": launcher,
                "repo_id": repo_id,
                "github_issue": github_issue,
            }
        ]

    created: list[dict[str, Any]] = []
    errors: list[dict[str, str]] = []
    for idx, raw_entry in enumerate(tasks):
        entry_title = str(raw_entry.get("title") or "").strip()
        if not entry_title:
            errors.append({"index": str(idx), "error": "title is required"})
            continue
        try:
            # Validate via shared model — enforces same constraints as REST surface.
            req = TaskCreateRequest.model_validate(
                {**raw_entry, "title": entry_title}
            )
            pri = parse_priority(req.priority)
            # MCP applies a project-level default_repo_id when the caller omits repo_id.
            # REST callers never receive this fallback — they must supply repo_id explicitly
            # or leave it null.  The fallback is runtime logic, not model logic.
            effective_repo_id = req.repo_id if req.repo_id is not None else default_repo_id
            task = await app.client.tasks.create(
                req.title,
                description=req.description,
                priority=pri,
                base_branch=req.base_branch,
                acceptance_criteria=req.acceptance_criteria,
                agent_backend=req.agent_backend,
                launcher=req.launcher,
                repo_id=effective_repo_id,
                github_issue=req.github_issue,
            )
            result = await _task_to_dict(task, app.client.engine)
            if app.bound_session_id is not None:
                result["session_id"] = app.bound_session_id
            created.append(result)
        except (KaganError, ValueError, TypeError, KeyError) as exc:
            errors.append({"index": str(idx), "error": str(exc)})

    return {
        "created": created,
        "errors": errors,
        "created_count": len(created),
        "error_count": len(errors),
    }


@mcp_error_boundary
async def _task_update(
    ctx: Context,
    task_id: str | None = None,
    title: str | None = None,
    description: str | None = None,
    priority: str | int | None = None,
    base_branch: str | None = None,
    acceptance_criteria: list[str] | None = None,
    agent_backend: str | None = None,
    launcher: str | None = None,
    status: str | None = None,
    repo_id: str | None = None,
) -> dict:
    """Update task fields or transition task status.

    Check the verification payload to confirm the requested changes were applied.
    """
    app = get_context(ctx)
    resolved_task_id = _resolve_task_id(ctx, task_id)
    priority_enum = parse_priority(priority) if priority is not None else None
    status_enum = TaskStatus(status) if status is not None else None
    task = await app.client.tasks.update(
        resolved_task_id,
        title=title,
        description=description,
        priority=priority_enum,
        base_branch=base_branch,
        acceptance_criteria=acceptance_criteria,
        agent_backend=agent_backend,
        launcher=launcher,
        repo_id=repo_id,
    )
    if status_enum is not None:
        task = await app.client.tasks.set_status(resolved_task_id, status_enum)
    result = await _task_to_dict(task, app.client.engine)
    result["verification"] = _build_update_verification(
        result,
        title=title,
        description=description,
        priority=priority_enum,
        base_branch=base_branch,
        acceptance_criteria=acceptance_criteria,
        agent_backend=agent_backend,
        launcher=launcher,
        status=status_enum,
    )
    return result


@mcp_error_boundary
async def _task_delete(ctx: Context, task_id: str) -> dict:
    """Delete a task permanently."""
    app = get_context(ctx)
    await app.client.tasks.delete(task_id)
    return {"task_id": task_id, "deleted": True}


_MAX_PAYLOAD_BYTES = 16384
_MAX_TOTAL_BYTES = 262144


@mcp_error_boundary
async def _task_events(
    ctx: Context,
    task_id: str | None = None,
    limit: int = 20,
    offset: int = 0,
    include_payload: bool = False,
) -> dict:
    """Fetch paginated execution events for a task.

    Use ``include_payload=True`` to inspect full event data.
    Payloads are automatically truncated to keep responses bounded.
    """
    app = get_context(ctx)
    resolved_task_id = _resolve_task_id(ctx, task_id)
    safe_limit = _clamp_int(limit, minimum=1, maximum=200)
    safe_offset = max(0, offset)

    events = await app.client.tasks.events.list(
        resolved_task_id, offset=safe_offset, limit=safe_limit
    )

    logs: list[dict[str, Any]] = []
    bytes_used = 0
    truncated_by_budget = False

    for event in events:
        serialized_payload = _payload_json(event.payload)
        payload_size_bytes = len(serialized_payload.encode("utf-8"))
        preview = serialized_payload.encode("utf-8")[:_MAX_PAYLOAD_BYTES].decode(
            "utf-8", errors="ignore"
        )
        payload_truncated = payload_size_bytes > _MAX_PAYLOAD_BYTES

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
        if logs and bytes_used + item_size > _MAX_TOTAL_BYTES:
            truncated_by_budget = True
            break
        if not logs and item_size > _MAX_TOTAL_BYTES:
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
async def _task_wait(
    ctx: Context,
    task_ids: list[str] | None = None,
    timeout_seconds: float | None = None,
    wait_for_status: list[str] | str | None = None,
    resolve_when_any: bool = False,
) -> dict:
    """Wait for tasks to reach completion or target statuses.

    Use this to gate dependent work or synchronize concurrent agents.
    """
    app = get_context(ctx)
    resolved_task_ids = _resolve_task_ids(ctx, task_ids)
    statuses = _parse_wait_for_task_statuses(wait_for_status)
    resolved: list[str] = []
    latest_by_id: dict[str, Any] = {}

    if resolve_when_any:
        if statuses:
            for task_id in resolved_task_ids:
                latest = await app.client.tasks.get(task_id)
                latest_by_id[task_id] = latest
                if latest.status in statuses:
                    resolved = [task_id]
                    timed_out = False
                    break
            if resolved:
                for task_id in resolved_task_ids:
                    if task_id not in latest_by_id:
                        latest_by_id[task_id] = await app.client.tasks.get(task_id)
                pending_task_ids = [
                    task_id for task_id in resolved_task_ids if task_id not in set(resolved)
                ]
                return {
                    "task_ids": resolved_task_ids,
                    "tasks": [
                        {"task_id": task_id, "status": latest_by_id[task_id].status.value}
                        for task_id in resolved_task_ids
                    ],
                    "resolved_task_ids": resolved,
                    "pending_task_ids": pending_task_ids,
                    "resolve_when_any": resolve_when_any,
                    "timed_out": False,
                }

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


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register task domain tools on mcp, filtered by opts."""
    _tools = [
        ("task_get", _task_get),
        ("task_list", _task_list),
        ("task_create", _task_create),
        ("task_update", _task_update),
        ("task_delete", _task_delete),
        ("task_events", _task_events),
        ("task_wait", _task_wait),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
