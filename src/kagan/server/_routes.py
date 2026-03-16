from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from kagan.core import Priority, TaskStatus, WorkMode, detect_dotfile_overrides
from kagan.mcp._policy import AccessTier
from kagan.runtime_env import build_sanitized_subprocess_environment
from kagan.server._helpers import (
    _err,
    _ok,
    _require_access,
    handle_errors,
    require_context,
    task_to_wire,
)
from kagan.wire.models import (
    WireEvent,
    WireProject,
    WireRepository,
    utc_iso,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse

_DEFAULT_WIP_LIMITS = {
    TaskStatus.BACKLOG.value: 0,
    TaskStatus.IN_PROGRESS.value: 4,
    TaskStatus.REVIEW.value: 2,
    TaskStatus.DONE.value: 0,
}


def _parse_wip_limits(raw: str | None) -> dict[str, int]:
    if not raw:
        return dict(_DEFAULT_WIP_LIMITS)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return dict(_DEFAULT_WIP_LIMITS)
    if not isinstance(parsed, dict):
        return dict(_DEFAULT_WIP_LIMITS)

    limits = dict(_DEFAULT_WIP_LIMITS)
    for key, value in parsed.items():
        if key not in limits:
            continue
        try:
            parsed_value = int(value)
        except (TypeError, ValueError):
            continue
        limits[key] = max(0, parsed_value)
    return limits


def _project_to_wire(project: Any, *, active: bool = True) -> WireProject:
    return WireProject(id=project.id, name=project.name, active=active)


def _repo_to_wire(repo: Any, *, selected: bool = False) -> WireRepository:
    return WireRepository(
        id=repo.id,
        project_id=repo.project_id or "",
        name=repo.name,
        path=repo.path,
        default_branch=repo.default_branch,
        selected=selected,
    )


def _event_to_wire(event: Any) -> WireEvent:
    return WireEvent(
        id=event.id,
        session_id=event.session_id,
        type=event.event_type.value,
        payload=cast("dict[str, object]", event.payload),
        created_at=utc_iso(event.created_at) or "",
    )


async def _body(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return cast("dict[str, Any]", payload)


def _parse_priority(value: str | int | None) -> Priority:
    if value is None:
        return Priority.MEDIUM
    if isinstance(value, int):
        return Priority(value)
    if value.isdigit():
        return Priority(int(value))
    return Priority[value]


def _parse_work_mode(value: str | None) -> WorkMode:
    return WorkMode(value) if value else WorkMode.AUTO


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


async def _resolve_project_repo_path(client: Any, settings: dict[str, str]) -> Path | None:
    return await client.projects.resolve_repo_path(settings=settings)


def register_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/api/tasks", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_tasks(request: Request, *, ctx: Any) -> JSONResponse:
        status_value = request.query_params.get("status")
        status_enum = TaskStatus(status_value) if status_value else None
        tasks = await ctx.client.tasks.list(status=status_enum)
        runtime = await ctx.client.tasks.runtime_summaries([task.id for task in tasks])
        return _ok(
            [task_to_wire(task, runtime=runtime.get(task.id)).model_dump() for task in tasks]
        )

    @mcp.custom_route("/api/tasks", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def create_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Task creation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        payload = await _body(request)
        acceptance_criteria = payload.get("acceptance_criteria")
        if acceptance_criteria is not None and not isinstance(acceptance_criteria, list):
            raise ValueError("acceptance_criteria must be a list of strings")

        task = await ctx.client.tasks.create(
            cast("str", payload["title"]),
            description=cast("str", payload.get("description", "")),
            execution_mode=_parse_work_mode(cast("str | None", payload.get("execution_mode"))),
            priority=_parse_priority(cast("str | int | None", payload.get("priority"))),
            base_branch=cast("str | None", payload.get("base_branch")),
            acceptance_criteria=cast("list[str] | None", acceptance_criteria),
            agent_backend=cast("str | None", payload.get("agent_backend")),
            launcher=cast("str | None", payload.get("launcher")),
        )
        runtime = await ctx.client.tasks.runtime_summary(task.id)
        return _ok(task_to_wire(task, runtime=runtime).model_dump())

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
        return _ok(task_to_wire(task, runtime=runtime).model_dump())

    @mcp.custom_route("/api/tasks/{task_id}", methods=["PATCH"])
    @require_context(mcp)
    @handle_errors
    async def update_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(ctx, operation="Task updates", minimum_tier=AccessTier.STANDARD)
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        payload = await _body(request)

        update_args: dict[str, Any] = {}
        if "title" in payload:
            update_args["title"] = payload["title"]
        if "description" in payload:
            update_args["description"] = payload["description"]
        if "priority" in payload:
            update_args["priority"] = _parse_priority(
                cast("str | int | None", payload.get("priority"))
            )
        if "execution_mode" in payload:
            update_args["execution_mode"] = _parse_work_mode(
                cast("str | None", payload.get("execution_mode"))
            )
        if "base_branch" in payload:
            update_args["base_branch"] = payload["base_branch"]
        if "acceptance_criteria" in payload:
            criteria = payload["acceptance_criteria"]
            if criteria is not None and not isinstance(criteria, list):
                raise ValueError("acceptance_criteria must be a list of strings")
            update_args["acceptance_criteria"] = criteria
        if "agent_backend" in payload:
            update_args["agent_backend"] = payload["agent_backend"]
        if "launcher" in payload:
            update_args["launcher"] = payload["launcher"]

        task = await ctx.client.tasks.update(task_id, **update_args)
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        return _ok(task_to_wire(task, runtime=runtime).model_dump())

    @mcp.custom_route("/api/tasks/{task_id}", methods=["DELETE"])
    @require_context(mcp)
    @handle_errors
    async def delete_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(ctx, operation="Task deletion", minimum_tier=AccessTier.ADMIN)
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
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
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        payload = await _body(request)
        status_value = cast("str", payload["status"])
        task = await ctx.client.tasks.set_status(task_id, TaskStatus(status_value))
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        return _ok(task_to_wire(task, runtime=runtime).model_dump())

    @mcp.custom_route("/api/tasks/{task_id}/run", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def run_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Task execution", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        payload = await _body(request)
        agent_backend = cast("str", payload.get("agent_backend", ""))
        if not agent_backend:
            settings = await ctx.client.settings.get()
            agent_backend = settings.get("default_agent_backend", "claude-code")
        persona = cast("str | None", payload.get("persona"))
        await ctx.client.tasks.run(task_id, agent_backend=agent_backend, persona=persona)
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        task = await ctx.client.tasks.get(task_id)
        return _ok(task_to_wire(task, runtime=runtime).model_dump())

    @mcp.custom_route("/api/tasks/{task_id}/pair", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def pair_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="PAIR sessions", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        payload = await _body(request)
        agent_backend = cast("str", payload.get("agent_backend", ""))
        if not agent_backend:
            settings = await ctx.client.settings.get()
            agent_backend = settings.get("default_agent_backend", "claude-code")
        settings = await ctx.client.settings.get()
        pair_launcher = str(settings.get("pair_launcher", "tmux")).strip().lower()
        from kagan.core._launchers import resolve_launcher

        launcher, ide = resolve_launcher(pair_launcher)
        persona = cast("str | None", payload.get("persona"))
        await ctx.client.tasks.pair(
            task_id,
            agent_backend=agent_backend,
            launcher=launcher,
            ide=ide,
            persona=persona,
        )
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        task = await ctx.client.tasks.get(task_id)
        return _ok(task_to_wire(task, runtime=runtime).model_dump())

    @mcp.custom_route("/api/tasks/{task_id}/cancel", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def cancel_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Task cancellation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        await ctx.client.tasks.cancel(task_id)
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        task = await ctx.client.tasks.get(task_id)
        return _ok(task_to_wire(task, runtime=runtime).model_dump())

    @mcp.custom_route("/api/tasks/{task_id}/end-pairing", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def end_pairing(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="PAIR session shutdown", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        result = await ctx.client.tasks.end_pairing(task_id)
        return _ok(result)

    @mcp.custom_route("/api/tasks/{task_id}/events", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def task_events(request: Request, *, ctx: Any) -> JSONResponse:
        task_id = cast("str", request.path_params["task_id"])
        limit = int(request.query_params.get("limit", "20"))
        offset = int(request.query_params.get("offset", "0"))
        tail = request.query_params.get("tail", "0") in {"1", "true", "yes"}
        before = request.query_params.get("before") or None
        session_id = request.query_params.get("session_id") or None
        if before:
            events = await ctx.client.tasks.events.list_before(
                task_id,
                before=before,
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
        return _ok([_event_to_wire(event).model_dump() for event in events])

    @mcp.custom_route("/api/projects", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_projects(_request: Request, *, ctx: Any) -> JSONResponse:
        projects = await ctx.client.projects.list()
        active_project_id = ctx.client.active_project_id
        return _ok(
            [
                _project_to_wire(project, active=project.id == active_project_id).model_dump()
                for project in projects
            ]
        )

    @mcp.custom_route("/api/projects", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def create_project(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Project creation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        payload = await _body(request)
        project = await ctx.client.projects.create(cast("str", payload["name"]))
        return _ok(
            _project_to_wire(
                project, active=project.id == ctx.client.active_project_id
            ).model_dump()
        )

    @mcp.custom_route("/api/projects/{project_id}/activate", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def activate_project(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Project activation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        project_id = cast("str", request.path_params["project_id"])
        await ctx.client.projects.set_active(project_id)
        return _ok({"project_id": project_id, "active": True})

    @mcp.custom_route("/api/projects/{project_id}", methods=["DELETE"])
    @require_context(mcp)
    @handle_errors
    async def delete_project(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Project deletion", minimum_tier=AccessTier.ADMIN
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        project_id = cast("str", request.path_params["project_id"])
        await ctx.client.projects.delete(project_id)
        return _ok({"project_id": project_id, "deleted": True})

    @mcp.custom_route("/api/projects/{project_id}/repos", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_project_repos(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = cast("str", request.path_params["project_id"])
        repos = await ctx.client.projects.repos(project_id)
        settings = await ctx.client.settings.get()
        selected_repo_id = settings.get(f"ui.selected_repo.{project_id}")
        return _ok(
            [
                _repo_to_wire(repo, selected=repo.id == selected_repo_id).model_dump()
                for repo in repos
            ]
        )

    @mcp.custom_route("/api/projects/{project_id}/repos", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def add_project_repo(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Repository linking", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        project_id = cast("str", request.path_params["project_id"])
        payload = await _body(request)
        path = cast("str", payload["path"])
        repo = await ctx.client.projects.add_repo(project_id, path)
        return _ok(_repo_to_wire(repo).model_dump())

    @mcp.custom_route("/api/projects/{project_id}/repos/{repo_id}/select", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def select_project_repo(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Repository selection", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        project_id = cast("str", request.path_params["project_id"])
        repo_id = cast("str", request.path_params["repo_id"])
        await ctx.client.settings.set({f"ui.selected_repo.{project_id}": repo_id})
        return _ok({"repo_id": repo_id, "selected": True})

    @mcp.custom_route("/api/projects/{project_id}/repos/{repo_id}", methods=["DELETE"])
    async def delete_project_repo(_request: Request) -> JSONResponse:
        return _err("Not implemented", status=501)

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
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        payload = await _body(request)
        action = cast("str", payload["action"]).lower()

        if action in {"approve", "merge"}:
            task = await ctx.client.tasks.get(task_id)
            criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
            if not criteria:
                return _manual_review_required(task_id)

        if action == "approve":
            task = await ctx.client.reviews.approve(task_id)
            return _ok({"task": task_to_wire(task).model_dump(), "action": action})
        if action == "reject":
            feedback = cast("str | None", payload.get("feedback"))
            if not feedback:
                raise ValueError("feedback is required for reject action")
            task = await ctx.client.reviews.reject(task_id, feedback=feedback)
            return _ok({"task": task_to_wire(task).model_dump(), "action": action})
        if action == "merge":
            task = await ctx.client.reviews.merge(task_id)
            return _ok({"task": task_to_wire(task).model_dump(), "action": action})
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

    @mcp.custom_route("/api/settings", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_settings(_request: Request, *, ctx: Any) -> JSONResponse:
        settings = await ctx.client.settings.get()
        return _ok(settings)

    @mcp.custom_route("/api/settings", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def set_settings(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Settings changes", minimum_tier=AccessTier.ADMIN
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        payload = await _body(request)
        updates = {str(key): "" if value is None else str(value) for key, value in payload.items()}
        await ctx.client.settings.set(updates)
        return _ok(await ctx.client.settings.get())

    @mcp.custom_route("/api/settings/resolved", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_resolved_settings(_request: Request, *, ctx: Any) -> JSONResponse:
        settings = await ctx.client.settings.get()

        from kagan.core.git import get_git_user_identity

        git_name, git_email = await get_git_user_identity(settings)

        project_path = await _resolve_project_repo_path(ctx.client, settings)
        overrides = detect_dotfile_overrides(project_path)

        return _ok(
            {
                "git_user_name": git_name,
                "git_user_email": git_email,
                "dotfile_overrides": {
                    "orchestrator": (
                        str(overrides["orchestrator"]) if "orchestrator" in overrides else None
                    ),
                    "execution": (
                        str(overrides["execution"]) if "execution" in overrides else None
                    ),
                    "review": str(overrides["review"]) if "review" in overrides else None,
                },
                "workflow": {"wip_limits": _parse_wip_limits(settings.get("workflow.wip_limits"))},
            }
        )

    @mcp.custom_route("/api/fs/browse", methods=["GET"])
    @handle_errors
    async def browse_filesystem(request: Request) -> JSONResponse:
        """List directories at *path* (defaults to user home).

        Returns entries sorted: directories first, then alphabetically.
        Each entry reports whether it is a git repository so the UI can
        highlight selectable repos.
        """
        import asyncio

        raw_path = request.query_params.get("path", "~")

        def _list_dir(raw: str) -> dict[str, Any]:
            target = Path(raw).expanduser().resolve()
            if not target.is_dir():
                raise ValueError(f"Not a directory: {target}")

            entries: list[dict[str, Any]] = []
            try:
                with os.scandir(target) as it:
                    for entry in it:
                        if entry.name.startswith("."):
                            continue
                        try:
                            is_dir = entry.is_dir(follow_symlinks=False)
                        except OSError:
                            continue
                        if not is_dir:
                            continue
                        full_path = str(Path(entry.path).resolve())
                        is_git = (Path(entry.path) / ".git").exists()
                        entries.append(
                            {
                                "name": entry.name,
                                "path": full_path,
                                "is_dir": True,
                                "is_git_repo": is_git,
                            }
                        )
            except PermissionError:
                pass

            entries.sort(key=lambda e: (not e["is_git_repo"], e["name"].lower()))
            return {"path": str(target), "entries": entries}

        result = await asyncio.to_thread(_list_dir, raw_path)
        return _ok(result)

    @mcp.custom_route("/api/preflight", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_preflight(request: Request, *, ctx: Any) -> JSONResponse:
        agent_backend = request.query_params.get("agent_backend")
        checks = await ctx.client.preflight(agent_backend=agent_backend)
        serialized = [
            {
                "name": check.name,
                "status": check.status.value,
                "message": check.message,
                "fix_hint": check.fix_hint,
                "is_blocking": check.is_blocking,
            }
            for check in checks
        ]
        return _ok({"checks": serialized, "ok": all(not check.is_blocking for check in checks)})

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
