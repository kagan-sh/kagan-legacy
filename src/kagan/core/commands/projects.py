from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

from kagan.core.policy import command

from ._parsing import str_list
from ._serialization import project_to_dict
from ._transport_truncation import (
    DEFAULT_AUDIT_FIELD_CHAR_LIMIT as _DEFAULT_AUDIT_FIELD_CHAR_LIMIT,
)
from ._transport_truncation import (
    truncate_for_transport as _truncate_for_transport,
)

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


@command(
    "projects",
    "create",
    profile="maintainer",
    mutating=True,
    description="Create a new project with optional repositories.",
)
async def create_project(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    name = str(params.get("name", ""))
    description = str(params.get("description", "")).strip()
    repo_paths = str_list(params.get("repo_paths"))

    project_id = await ctx.project_service.create_project(
        name=name.strip(),
        repo_paths=[Path(path) for path in repo_paths] if repo_paths else None,
        description=description,
    )
    return {
        "success": True,
        "project_id": project_id,
        "name": name.strip(),
        "description": description,
        "repo_count": len(repo_paths),
    }


@command(
    "projects",
    "open",
    profile="maintainer",
    mutating=True,
    description="Open/switch to a project.",
)
async def open_project(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    project_id = params["project_id"]
    project = await ctx.project_service.open_project(project_id)
    return {"success": True, "project_id": project.id, "name": project.name}


@command(
    "projects",
    "add_repo",
    profile="maintainer",
    mutating=True,
    description="Add a repository to a project.",
)
async def add_repo(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    project_id = str(params.get("project_id", ""))
    repo_path = str(params.get("repo_path", ""))
    is_primary = bool(params.get("is_primary", False))
    repo_id = await ctx.project_service.add_repo_to_project(
        project_id=project_id.strip(),
        repo_path=repo_path.strip(),
        is_primary=is_primary,
    )
    return {
        "success": True,
        "project_id": project_id.strip(),
        "repo_id": repo_id,
        "repo_path": repo_path.strip(),
    }


@command("projects", "get", description="Get a project by ID.")
async def get_project(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    project_id = params["project_id"]
    project = await ctx.project_service.get_project(project_id)
    if project is None:
        return {"found": False, "project": None}
    return {"found": True, "project": project_to_dict(project)}


@command("projects", "list", description="List recent projects.")
async def list_projects(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    limit = params.get("limit", 10)
    projects = await ctx.project_service.list_recent_projects(limit=limit)
    return {"projects": [project_to_dict(project) for project in projects], "count": len(projects)}


@command("projects", "repos", description="Get all repos for a project.")
async def get_project_repos(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    project_id = params["project_id"]
    repos = await ctx.project_service.get_project_repos(project_id)
    return {
        "repos": [
            {
                "id": repo.id,
                "name": repo.name,
                "display_name": repo.display_name,
                "path": str(repo.path),
                "default_branch": repo.default_branch,
            }
            for repo in repos
        ],
        "count": len(repos),
    }


@command(
    "projects",
    "find_by_repo_path",
    description="Find a project containing the given repository path.",
)
async def find_project_by_repo_path(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    repo_path = params["repo_path"]
    project = await ctx.project_service.find_project_by_repo_path(repo_path)
    if project is None:
        return {"found": False, "project": None}
    return {"found": True, "project": project_to_dict(project)}


@command("audit", "list", description="List recent audit events.")
async def list_audit_events(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    capability = params.get("capability")
    limit = params.get("limit", 50)
    cursor = params.get("cursor")
    events = await ctx.audit_repository.list_events(
        capability=capability,
        limit=limit,
        cursor=cursor,
    )

    result_events: list[dict[str, Any]] = []
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

    return {"events": result_events, "count": len(result_events), "truncated": truncated}


@command(
    "projects",
    "update_repo_default_branch",
    profile="maintainer",
    mutating=True,
    description="Update a repository's default branch.",
)
async def update_repo_default_branch(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    repo_id = params["repo_id"]
    branch = params["branch"]
    mark_configured = bool(params.get("mark_configured", False))
    repo = await ctx.api.update_repo_default_branch(
        repo_id, branch, mark_configured=mark_configured
    )
    if repo is None:
        return {"success": False, "repo_id": repo_id, "message": f"Repo {repo_id} not found."}
    return {
        "success": True,
        "repo_id": repo.id,
        "default_branch": repo.default_branch,
    }


__all__ = [
    "add_repo",
    "create_project",
    "find_project_by_repo_path",
    "get_project",
    "get_project_repos",
    "list_audit_events",
    "list_projects",
    "open_project",
    "update_repo_default_branch",
]
