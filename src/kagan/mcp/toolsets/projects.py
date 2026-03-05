"""kagan.mcp.toolsets.projects — Project and repo domain MCP tools."""

import asyncio

from mcp.server.fastmcp import Context, FastMCP
from sqlmodel import Session, select

from kagan.mcp._policy import is_tool_allowed
from kagan.mcp.server import ServerOptions, get_context
from kagan.mcp.toolsets import mcp_error_boundary


@mcp_error_boundary
async def _project_list(ctx: Context) -> dict:
    """List all projects."""
    app = get_context(ctx)
    projects = await app.client.projects.list()
    return {"projects": [{"id": p.id, "name": p.name} for p in projects]}


@mcp_error_boundary
async def _project_set_active(project_id: str, ctx: Context) -> dict:
    """Open (activate) a project."""
    app = get_context(ctx)
    await app.client.projects.set_active(project_id)
    return {"project_id": project_id}


@mcp_error_boundary
async def _project_add_repo(project_id: str, repo_path: str, ctx: Context) -> dict:
    """Add a repo to a project."""
    app = get_context(ctx)
    await app.client.projects.add_repo(project_id, repo_path)
    return {"project_id": project_id, "repo_path": repo_path}


@mcp_error_boundary
async def _project_set_repo_default_branch(
    project_id: str, repo_id: str, branch: str, ctx: Context
) -> dict:
    """Update a repo's default branch."""
    app = get_context(ctx)
    await app.client.projects.get(project_id)

    def _update_repo() -> bool:
        from kagan.core.models import Repository

        with Session(app.client.engine) as session:
            stmt = select(Repository).where(
                Repository.id == repo_id, Repository.project_id == project_id
            )
            repo = session.exec(stmt).first()
            if repo is None:
                return False
            repo.default_branch = branch
            session.add(repo)
            session.commit()
            return True

    updated = await asyncio.to_thread(_update_repo)
    if not updated:
        raise ValueError(f"Repo not found: {repo_id}")
    return {"project_id": project_id, "repo_id": repo_id, "branch": branch}


@mcp_error_boundary
async def _repo_list(project_id: str, ctx: Context) -> dict:
    """List repos in a project."""
    app = get_context(ctx)
    repos = await app.client.projects.repos(project_id)
    return {"repos": [{"id": r.id, "path": r.path} for r in repos]}


@mcp_error_boundary
async def _project_create(name: str, ctx: Context) -> dict:
    """Create a project (admin only)."""
    app = get_context(ctx)
    project = await app.client.projects.create(name)
    return {"id": project.id, "name": project.name}


@mcp_error_boundary
async def _project_delete(project_id: str, ctx: Context) -> dict:
    """Delete a project (admin only)."""
    app = get_context(ctx)
    await app.client.projects.delete(project_id)
    return {"project_id": project_id, "deleted": True}


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register project and repo domain tools on mcp, filtered by opts."""
    _tools = [
        ("project_list", _project_list),
        ("project_set_active", _project_set_active),
        ("project_add_repo", _project_add_repo),
        ("project_set_repo_default_branch", _project_set_repo_default_branch),
        ("repo_list", _repo_list),
        ("project_create", _project_create),
        ("project_delete", _project_delete),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
