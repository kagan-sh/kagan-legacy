from __future__ import annotations

import asyncio
import contextlib
import json
import os
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from kagan.core import (
    TaskStatus,
    detect_dotfile_overrides,
    parse_priority,
    resolve_launcher,
)
from kagan.core._utils import utc_iso
from kagan.runtime_env import build_sanitized_subprocess_environment
from kagan.server._access import AccessTier
from kagan.server._helpers import (
    _err,
    _ok,
    _require_access,
    handle_errors,
    require_context,
    task_to_wire_dict,
)
from kagan.server._sse import _sse_event_generator, sse_response
from kagan.server.responses import EventResponse, ProjectResponse, RepositoryResponse

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

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


def _project_dict(project: Any, *, active: bool = True) -> dict[str, Any]:
    resp = ProjectResponse.model_validate(project)
    resp.active = active
    return resp.model_dump(mode="json")


def _repo_dict(repo: Any, *, selected: bool = False) -> dict[str, Any]:
    resp = RepositoryResponse.model_validate(repo)
    resp.selected = selected
    return resp.model_dump(mode="json")


def _event_dict(event: Any) -> dict[str, Any]:
    return EventResponse.model_validate(event).model_dump(mode="json")


async def _body(request: Request) -> dict[str, Any]:
    payload = await request.json()
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return cast("dict[str, Any]", payload)


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
        return _ok([task_to_wire_dict(task, runtime=runtime.get(task.id)) for task in tasks])

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
            priority=parse_priority(cast("str | int | None", payload.get("priority"))),
            base_branch=cast("str | None", payload.get("base_branch")),
            acceptance_criteria=cast("list[str] | None", acceptance_criteria),
            agent_backend=cast("str | None", payload.get("agent_backend")),
            launcher=cast("str | None", payload.get("launcher")),
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
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        payload = await _body(request)

        update_args: dict[str, Any] = {}
        if "title" in payload:
            update_args["title"] = payload["title"]
        if "description" in payload:
            update_args["description"] = payload["description"]
        if "priority" in payload:
            update_args["priority"] = parse_priority(
                cast("str | int | None", payload.get("priority"))
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
        return _ok(task_to_wire_dict(task, runtime=runtime))

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
        return _ok(task_to_wire_dict(task, runtime=runtime))

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
        settings = await ctx.client.settings.get()
        if not agent_backend:
            agent_backend = settings.get("default_agent_backend", "claude-code")
        persona = cast("str | None", payload.get("persona"))
        launcher = None
        ide = None
        payload_launcher = cast("str | None", payload.get("launcher"))
        if isinstance(payload_launcher, str) and payload_launcher.strip():
            launcher_input = payload_launcher.strip().lower()
            launcher, ide = resolve_launcher(launcher_input)
        await ctx.client.tasks.run(
            task_id,
            agent_backend=agent_backend,
            launcher=launcher,
            ide=ide,
            persona=persona,
        )
        runtime = await ctx.client.tasks.runtime_summary(task_id)
        task = await ctx.client.tasks.get(task_id)
        return _ok(task_to_wire_dict(task, runtime=runtime))

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
        return _ok(task_to_wire_dict(task, runtime=runtime))

    @mcp.custom_route("/api/tasks/{task_id}/detach", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def detach_task(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Attached session detach", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        result = await ctx.client.tasks.detach(task_id)
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

    @mcp.custom_route("/api/projects", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_projects(_request: Request, *, ctx: Any) -> JSONResponse:
        projects = await ctx.client.projects.list()
        active_project_id = ctx.client.active_project_id
        return _ok(
            [_project_dict(project, active=project.id == active_project_id) for project in projects]
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
        return _ok(_project_dict(project, active=project.id == ctx.client.active_project_id))

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
        return _ok([_repo_dict(repo, selected=repo.id == selected_repo_id) for repo in repos])

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
        return _ok(_repo_dict(repo))

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
            return _ok({"task": task_to_wire_dict(task), "action": action})
        if action == "reject":
            feedback = cast("str | None", payload.get("feedback"))
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

    @mcp.custom_route("/api/events/stream", methods=["GET"])
    @require_context(mcp)
    async def event_stream(_request: Request, *, ctx: Any) -> Response:
        """SSE endpoint — streams board + session events to the client."""
        return sse_response(_sse_event_generator(mcp))

    @mcp.custom_route("/api/tasks/{task_id}/follow-up", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def task_follow_up(request: Request, *, ctx: Any) -> JSONResponse:
        """Cancel the current run and restart with follow-up text appended."""
        forbidden = _require_access(
            ctx, operation="Task follow-up messages", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        task_id = cast("str", request.path_params["task_id"])
        payload = await _body(request)
        text = cast("str", payload.get("text", "")).strip()
        if not text:
            raise ValueError("text is required")

        from kagan.core import resolve_default_agent_backend

        # Best-effort cancel current run
        with contextlib.suppress(Exception):
            await ctx.client.tasks.cancel(task_id)

        task = await ctx.client.tasks.get(task_id)
        current_desc = (getattr(task, "description", "") or "").strip()
        follow_up = f"User follow-up:\n{text}"
        updated_desc = f"{current_desc}\n\n{follow_up}" if current_desc else follow_up
        task = await ctx.client.tasks.update(task_id, description=updated_desc)

        settings = await ctx.client.settings.get()
        backend = getattr(task, "agent_backend", None) or resolve_default_agent_backend(settings)
        await ctx.client.tasks.run(task_id, agent_backend=backend)

        runtime = await ctx.client.tasks.runtime_summary(task_id)
        task = await ctx.client.tasks.get(task_id)
        return _ok(task_to_wire_dict(task, runtime=runtime))
