from __future__ import annotations

import asyncio
import re
from typing import TYPE_CHECKING, Any, cast

from loguru import logger

from kagan.core import TaskStatus, parse_priority, resolve_default_agent_backend, resolve_launcher
from kagan.core._backend_selector import BackendSelector
from kagan.core._utils import utc_iso
from kagan.runtime_env import build_sanitized_subprocess_environment
from kagan.server._access import AccessTier
from kagan.server._helpers import (
    _ok,
    _require_access,
    handle_errors,
    parse_body,
    require_context,
    task_to_wire_dict,
)
from kagan.server.requests import (
    CreateTaskRequest,
    FollowUpRequest,
    ReviewDecideRequest,
    RunTaskRequest,
    UpdateTaskRequest,
    UpdateTaskStatusRequest,
)
from kagan.server.responses import EventResponse

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse


def _event_dict(event: Any) -> dict[str, Any]:
    return EventResponse.model_validate(event).model_dump(mode="json")




async def _select_backend_intelligently(
    ctx: Any,
    task_id: str,
    agent_backend: str | None,
    task_title: str,
    task_description: str,
) -> tuple[str, dict[str, Any]]:
    """Select backend using BackendSelector if enabled, else use default.

    Returns: (selected_backend, selection_metadata)
    """
    settings = await ctx.client.settings.get()
    use_recommended = settings.get("use_recommended_backend") == "true"
    default_backend = resolve_default_agent_backend(settings)

    # If user explicitly specified backend, use it (unless recommendation is enabled)
    if agent_backend and not use_recommended:
        return agent_backend, {
            "backend": agent_backend,
            "reason": "user_specified",
            "confidence": 0.0,
            "alternatives": [],
        }

    # If no intelligent selection, use default
    if not use_recommended:
        return default_backend, {
            "backend": default_backend,
            "reason": "default_backend",
            "confidence": 0.0,
            "alternatives": [],
        }

    # Perform intelligent selection
    try:
        from kagan.core._agent import list_available_backends

        # Get task details
        task = await ctx.client.tasks.get(task_id)

        # Infer agent role (same logic as _sessions._infer_agent_role)
        agent_role = "reviewer" if task.status == TaskStatus.REVIEW else "worker"

        # Get available backends
        available_map = list_available_backends()
        available = [name for name, is_installed in available_map.items() if is_installed]

        if not available:
            available = [default_backend]

        # Create selector and select backend
        project_id = task.project_id
        selector = BackendSelector(ctx.client.analytics, project_id)

        result = await selector.select_backend(
            title=task_title,
            description=task_description,
            agent_role=agent_role,
            available_backends=available,
            fallback_backend=default_backend,
        )

        selected = result.get("backend", default_backend)
        logger.info(
            "Backend selection: task={}, role={}, selected={}, confidence={}, reason={}",
            task_id,
            agent_role,
            selected,
            result.get("confidence", 0),
            result.get("reason", "unknown"),
        )

        return selected, result

    except Exception as exc:
        logger.warning(
            "BackendSelector failed for task={}: {}. Using default backend: {}",
            task_id,
            exc,
            default_backend,
        )
        return default_backend, {
            "backend": default_backend,
            "reason": "selector_error",
            "confidence": 0.0,
            "alternatives": [],
        }


def _manual_review_required(task_id: str) -> JSONResponse:
    return _ok(
        {
            "task_id": task_id,
            "action": "blocked",
            "reason_code": "MANUAL_REVIEW_REQUIRED",
            "reason": "This task has no acceptance criteria. Manual human review is required.",
        }
    )


async def _load_task_branch_commits(
    worktree_path: str,
    base_branch: str,
) -> list[dict[str, str]]:
    if not re.match(r"^[a-zA-Z0-9/_.\-]+$", base_branch):
        return []
    proc = await asyncio.create_subprocess_exec(
        "git",
        "-C",
        worktree_path,
        "log",
        "--pretty=format:%h%x09%s",
        f"{base_branch}..HEAD",
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    stdout, _stderr = await proc.communicate()
    if proc.returncode != 0 or not stdout:
        return []

    commits: list[dict[str, str]] = []
    for line in stdout.decode("utf-8", errors="replace").splitlines():
        short_hash, _tab, message = line.partition("\t")
        if short_hash and message:
            commits.append(
                {
                    "short_hash": short_hash.strip(),
                    "message": message.strip(),
                }
            )
    return commits


def register_task_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/api/tasks", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_tasks(request: Request, *, ctx: Any) -> JSONResponse:
        status_value = request.query_params.get("status")
        status_enum = TaskStatus(status_value) if status_value else None
        repo_id = request.query_params.get("repo_id") or None
        tasks = await ctx.client.tasks.list(status=status_enum, repo_id=repo_id)
        runtime = await ctx.client.tasks.runtime_summaries([task.id for task in tasks])
        return _ok([task_to_wire_dict(task, runtime=runtime.get(task.id)) for task in tasks])

    @mcp.custom_route("/api/tasks", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def create_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Task creation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        body = await parse_body(request, CreateTaskRequest)
        task = await ctx.client.tasks.create(
            body.title,
            description=body.description,
            priority=parse_priority(body.priority),
            base_branch=body.base_branch,
            acceptance_criteria=body.acceptance_criteria,
            agent_backend=body.agent_backend,
            launcher=body.launcher,
            repo_id=body.repo_id,
        )
        runtime = await ctx.client.tasks.runtime_summary(task.id)
        return _ok(task_to_wire_dict(task, runtime=runtime))

    @mcp.custom_route("/api/tasks/counts", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def task_counts(_request: Request, *, ctx: Any) -> JSONResponse:
        counts = await ctx.client.tasks.counts()
        payload = {status.value: count for status, count in counts.items()}
        return _ok(payload)

    @mcp.custom_route("/api/tasks/{task_id}", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_task(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        task = await ctx.client.tasks.get(task_id)
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        return _ok(task_to_wire_dict(task, runtime=runtime))

    @mcp.custom_route("/api/tasks/{task_id}", methods=["PATCH"])
    @require_context(mcp)
    @handle_errors
    async def update_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(ctx, operation="Task updates", minimum_tier=AccessTier.STANDARD)
        if forbidden is not None:
            return forbidden
        task_id = cast("str", request.path_params["task_id"])
        body = await parse_body(request, UpdateTaskRequest)
        update_args: dict[str, Any] = {}
        for field in body.model_fields_set:
            value = getattr(body, field)
            if field == "priority":
                value = parse_priority(value)
            update_args[field] = value
        task = await ctx.client.tasks.update(task_id, **update_args)
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        return _ok(task_to_wire_dict(task, runtime=runtime))

    @mcp.custom_route("/api/tasks/{task_id}", methods=["DELETE"])
    @require_context(mcp)
    @handle_errors
    async def delete_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(ctx, operation="Task deletion", minimum_tier=AccessTier.ADMIN)
        if forbidden is not None:
            return forbidden
        task_id = cast("str", request.path_params["task_id"])
        await ctx.client.tasks.delete(task_id)
        return _ok({"task_id": task_id, "deleted": True})

    @mcp.custom_route("/api/tasks/{task_id}/status", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def update_task_status(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Task status changes", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        task_id = cast("str", request.path_params["task_id"])
        body = await parse_body(request, UpdateTaskStatusRequest)
        task = await ctx.client.tasks.set_status(task_id, TaskStatus(body.status))
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        return _ok(task_to_wire_dict(task, runtime=runtime))

    @mcp.custom_route("/api/tasks/{task_id}/run", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def run_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Task execution", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        task_id = cast("str", request.path_params["task_id"])
        body = await parse_body(request, RunTaskRequest)

        # Get task for title/description
        task = await ctx.client.tasks.get(task_id)

        # Select backend intelligently if enabled
        agent_backend, selection_metadata = await _select_backend_intelligently(
            ctx,
            task_id,
            body.agent_backend,
            task.title,
            task.description or "",
        )

        launcher = None
        ide = None
        if body.launcher and body.launcher.strip():
            launcher, ide = resolve_launcher(body.launcher.strip().lower())

        await ctx.client.tasks.run(
            task_id,
            agent_backend=agent_backend,
            launcher=launcher,
            ide=ide,
            persona=body.persona,
        )

        runtime = await ctx.client.tasks.runtime_summary(task_id)
        task = await ctx.client.tasks.get(task_id)

        # Include selection metadata in response
        wire_dict = task_to_wire_dict(task, runtime=runtime)
        wire_dict["backend_selection"] = {
            "selected_backend": selection_metadata.get("backend"),
            "backend_confidence": selection_metadata.get("confidence"),
            "backend_reason": selection_metadata.get("reason"),
            "alternatives": selection_metadata.get("alternatives", []),
        }

        return _ok(wire_dict)

    @mcp.custom_route("/api/tasks/{task_id}/cancel", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def cancel_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Task cancellation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        task_id = cast("str", request.path_params["task_id"])
        await ctx.client.tasks.cancel(task_id)
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        task = await ctx.client.tasks.get(task_id)
        return _ok(task_to_wire_dict(task, runtime=runtime))

    @mcp.custom_route("/api/tasks/{task_id}/detach", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def detach_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Attached session detach", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        task_id = cast("str", request.path_params["task_id"])
        result = await ctx.client.tasks.detach(task_id)
        return _ok(result)

    @mcp.custom_route("/api/tasks/{task_id}/events", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def task_events(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        try:
            limit = min(max(int(request.query_params.get("limit", "20")), 1), 1000)
        except ValueError:
            limit = 20
        try:
            offset = min(max(int(request.query_params.get("offset", "0")), 0), 100_000)
        except ValueError:
            offset = 0
        tail = request.query_params.get("tail", "0") in {"1", "true", "yes"}
        before = request.query_params.get("before") or None
        before_id = request.query_params.get("before_id") or None
        after = request.query_params.get("after") or None
        after_id = request.query_params.get("after_id") or None
        session_id = request.query_params.get("session_id") or None
        if before:
            events = await ctx.client.tasks.events.list_before(
                task_id,
                before=before,
                before_id=before_id,
                limit=max(limit, 1),
                session_id=session_id,
            )
        elif after:
            events = await ctx.client.tasks.events.list_after(
                task_id,
                after_ts=after,
                after_id=after_id or "",
                limit=max(limit, 1),
                session_id=session_id,
            )
        elif tail:
            events = await ctx.client.tasks.events.list_recent(
                task_id,
                limit=max(limit, 1),
                session_id=session_id,
            )
        else:
            events = await ctx.client.tasks.events.list(
                task_id,
                offset=max(offset, 0),
                limit=max(limit, 1),
                session_id=session_id,
            )
        return _ok([_event_dict(event) for event in events])

    @mcp.custom_route("/api/tasks/{task_id}/sessions", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def task_sessions(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        sessions = await ctx.client.tasks.sessions.list_for_task(task_id)
        return _ok(
            [
                {
                    "id": session.id,
                    "launcher": session.launcher,
                    "status": session.status.value,
                    "agent_backend": session.agent_backend,
                    "started_at": utc_iso(session.started_at) or "",
                }
                for session in sessions
            ]
        )

    @mcp.custom_route("/api/tasks/{task_id}/review", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def review_status(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        task = await ctx.client.tasks.get(task_id)
        return _ok(
            {
                "task_id": task_id,
                "status": task.status.value,
                "review_approved": getattr(task, "review_approved", False),
            }
        )

    @mcp.custom_route("/api/tasks/{task_id}/review/decide", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def review_decide(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Review decisions", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        task_id = cast("str", request.path_params["task_id"])
        body = await parse_body(request, ReviewDecideRequest)
        action = body.action.lower()

        if action in {"approve", "merge"}:
            task = await ctx.client.tasks.get(task_id)
            criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
            if not criteria:
                return _manual_review_required(task_id)

        if action == "approve":
            task = await ctx.client.reviews.approve(task_id)
            return _ok({"task": task_to_wire_dict(task), "action": action})
        if action == "reject":
            feedback = body.feedback
            if not feedback:
                raise ValueError("feedback is required for reject action")
            task = await ctx.client.reviews.reject(task_id, feedback=feedback)
            return _ok({"task": task_to_wire_dict(task), "action": action})
        if action == "merge":
            task = await ctx.client.reviews.merge(task_id)
            return _ok({"task": task_to_wire_dict(task), "action": action})
        if action == "rebase":
            await ctx.client.reviews.rebase(task_id)
            return _ok({"task_id": task_id, "action": action})

        raise ValueError("action must be one of: approve, reject, merge, rebase")

    @mcp.custom_route("/api/tasks/{task_id}/review/conflicts", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def review_conflicts(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        conflicts = await ctx.client.reviews.conflicts(task_id)
        return _ok(conflicts)

    @mcp.custom_route("/api/tasks/{task_id}/diff", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_task_diff(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        stats = await ctx.client.worktrees.diff_stats(task_id)
        return _ok(stats)

    @mcp.custom_route("/api/tasks/{task_id}/diff/raw", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_task_diff_raw(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        diff_text = await ctx.client.worktrees.diff(task_id)
        return _ok({"task_id": task_id, "diff": diff_text})

    @mcp.custom_route("/api/tasks/{task_id}/diff/files", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_task_diff_files(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        diff_text = await ctx.client.worktrees.diff(task_id)
        files: list[dict[str, Any]] = []
        if diff_text:
            current: dict[str, Any] | None = None
            for line in diff_text.splitlines():
                if line.startswith("diff --git"):
                    parts = line.split(" b/")
                    path = parts[-1] if len(parts) > 1 else "unknown"
                    current = {
                        "path": path,
                        "status": "modified",
                        "insertions": 0,
                        "deletions": 0,
                    }
                    files.append(current)
                elif current is not None:
                    if line.startswith("+") and not line.startswith("+++"):
                        current["insertions"] += 1
                    elif line.startswith("-") and not line.startswith("---"):
                        current["deletions"] += 1
        return _ok({"task_id": task_id, "files": files})

    @mcp.custom_route("/api/tasks/{task_id}/worktree", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_task_worktree(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        ws = await ctx.client.worktrees.get(task_id)
        if ws is None:
            return _ok({"task_id": task_id, "worktree": None})
        return _ok(
            {
                "task_id": task_id,
                "worktree": {
                    "path": ws.worktree_path,
                    "branch": ws.branch_name,
                },
            }
        )

    @mcp.custom_route("/api/tasks/{task_id}/commits", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_task_commits(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        task = await ctx.client.tasks.get(task_id)
        base_branch = (cast("str | None", getattr(task, "base_branch", None)) or "main").strip()
        if not base_branch:
            base_branch = "main"

        ws = await ctx.client.worktrees.get(task_id)
        if ws is None:
            return _ok(
                {
                    "task_id": task_id,
                    "branch": None,
                    "base_branch": base_branch,
                    "commits": [],
                }
            )

        commits = await _load_task_branch_commits(ws.worktree_path, base_branch)
        return _ok(
            {
                "task_id": task_id,
                "branch": ws.branch_name,
                "base_branch": base_branch,
                "commits": commits,
            }
        )

    @mcp.custom_route("/api/tasks/{task_id}/follow-up", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def task_follow_up(request: Request, *, ctx: Any) -> JSONResponse:
        """Cancel the current run and restart with follow-up text appended."""
        forbidden = _require_access(
            ctx, operation="Task follow-up messages", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        task_id = cast("str", request.path_params["task_id"])
        body = await parse_body(request, FollowUpRequest)

        # Best-effort cancel current run
        try:
            await ctx.client.tasks.cancel(task_id)
        except Exception as exc:
            logger.debug("Failed to cancel current run for task {}: {}", task_id, exc)

        task = await ctx.client.tasks.get(task_id)
        current_desc = (getattr(task, "description", "") or "").strip()
        follow_up = f"User follow-up:\n{body.text}"
        updated_desc = f"{current_desc}\n\n{follow_up}" if current_desc else follow_up
        task = await ctx.client.tasks.update(task_id, description=updated_desc)

        # Select backend intelligently (with updated description)
        agent_backend, selection_metadata = await _select_backend_intelligently(
            ctx,
            task_id,
            getattr(task, "agent_backend", None),
            task.title,
            updated_desc,
        )

        await ctx.client.tasks.run(task_id, agent_backend=agent_backend)

        runtime = await ctx.client.tasks.runtime_summary(task_id)
        task = await ctx.client.tasks.get(task_id)

        wire_dict = task_to_wire_dict(task, runtime=runtime)
        wire_dict["backend_selection"] = {
            "selected_backend": selection_metadata.get("backend"),
            "backend_confidence": selection_metadata.get("confidence"),
            "backend_reason": selection_metadata.get("reason"),
            "alternatives": selection_metadata.get("alternatives", []),
        }

        return _ok(wire_dict)
