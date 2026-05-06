from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from kagan.core import ProjectCreateRequest, RepoAddRequest
from kagan.server._access import AccessTier
from kagan.server._helpers import (
    _err,
    _ok,
    _require_access,
    handle_errors,
    parse_body,
    require_context,
)
from kagan.server.responses import (
    ProjectFolderResolutionResponse,
    ProjectResponse,
    RepositoryResponse,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse

    from kagan.server.mcp.server import ServerContext


def _project_dict(project: Any, *, active: bool = True) -> dict[str, Any]:
    resp = ProjectResponse.model_validate(project)
    resp.active = active
    return resp.model_dump(mode="json")


def _repo_dict(repo: Any, *, selected: bool = False) -> dict[str, Any]:
    resp = RepositoryResponse.model_validate(repo)
    resp.selected = selected
    return resp.model_dump(mode="json")


def register_project_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/api/projects", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_projects(_request: Request, *, ctx: ServerContext) -> JSONResponse:
        projects = await ctx.client.projects.list()
        active_project_id = ctx.client.active_project_id
        return _ok(
            [_project_dict(project, active=project.id == active_project_id) for project in projects]
        )

    @mcp.custom_route("/api/projects/resolve-folder", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def resolve_project_folder(request: Request, *, ctx: ServerContext) -> JSONResponse:
        raw_path = request.query_params.get("path")
        target = Path(raw_path).expanduser() if raw_path else Path.cwd()
        resolution = await ctx.client.projects.inspect_folder(target)
        return _ok(
            ProjectFolderResolutionResponse.model_validate(
                resolution, from_attributes=True
            ).model_dump()
        )

    @mcp.custom_route("/api/projects", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def create_project(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Project creation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        body = await parse_body(request, ProjectCreateRequest)
        project = await ctx.client.projects.create(body.name)
        return _ok(_project_dict(project, active=project.id == ctx.client.active_project_id))

    @mcp.custom_route("/api/projects/{project_id}/activate", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def activate_project(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Project activation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        project_id = cast("str", request.path_params["project_id"])
        await ctx.client.projects.set_active(project_id)
        return _ok({"project_id": project_id, "active": True})

    @mcp.custom_route("/api/projects/{project_id}", methods=["DELETE"])
    @require_context(mcp)
    @handle_errors
    async def delete_project(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Project deletion", minimum_tier=AccessTier.ADMIN
        )
        if forbidden is not None:
            return forbidden
        project_id = cast("str", request.path_params["project_id"])
        await ctx.client.projects.delete(project_id)
        return _ok({"project_id": project_id, "deleted": True})

    @mcp.custom_route("/api/projects/{project_id}/repos", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_project_repos(request: Request, *, ctx: ServerContext) -> JSONResponse:
        project_id = cast("str", request.path_params["project_id"])
        repos = await ctx.client.projects.repos(project_id)
        settings = await ctx.client.settings.get()
        selected_repo_id = settings.get(f"ui.selected_repo.{project_id}")
        return _ok([_repo_dict(repo, selected=repo.id == selected_repo_id) for repo in repos])

    @mcp.custom_route("/api/projects/{project_id}/repos", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def add_project_repo(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Repository linking", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        project_id = cast("str", request.path_params["project_id"])
        body = await parse_body(request, RepoAddRequest)
        repo = await ctx.client.projects.add_repo(project_id, body.path)
        return _ok(_repo_dict(repo))

    @mcp.custom_route("/api/projects/{project_id}/repos/{repo_id}/select", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def select_project_repo(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Repository selection", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        project_id = cast("str", request.path_params["project_id"])
        repo_id = cast("str", request.path_params["repo_id"])
        await ctx.client.settings.set({f"ui.selected_repo.{project_id}": repo_id})
        return _ok({"repo_id": repo_id, "selected": True})

    @mcp.custom_route("/api/projects/{project_id}/repos/{repo_id}", methods=["DELETE"])
    async def delete_project_repo(_request: Request) -> JSONResponse:
        return _err("Not implemented", status=501)
