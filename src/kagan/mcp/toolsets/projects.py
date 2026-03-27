"""kagan.mcp.toolsets.projects — Project and repo domain MCP tools."""

from mcp.server.fastmcp import Context, FastMCP

from kagan.core.errors import NotFoundError
from kagan.mcp._policy import is_tool_allowed
from kagan.mcp.server import ServerOptions, get_context
from kagan.mcp.toolsets import mcp_error_boundary


@mcp_error_boundary
async def _project_list(ctx: Context) -> dict:
    """List projects available to the current workspace."""
    app = get_context(ctx)
    projects = await app.client.projects.list()
    return {"projects": [{"id": p.id, "name": p.name} for p in projects]}


@mcp_error_boundary
async def _project_set_active(project_id: str, ctx: Context) -> dict:
    """Set the active project for subsequent project-scoped operations."""
    app = get_context(ctx)
    await app.client.projects.set_active(project_id)
    return {"project_id": project_id}


@mcp_error_boundary
async def _project_add_repo(project_id: str, repo_path: str, ctx: Context) -> dict:
    """Attach a repository path to a project."""
    app = get_context(ctx)
    await app.client.projects.add_repo(project_id, repo_path)
    return {"project_id": project_id, "repo_path": repo_path}


@mcp_error_boundary
async def _project_set_repo_default_branch(
    project_id: str, repo_id: str, branch: str, ctx: Context
) -> dict:
    """Set the default base branch for a project repository."""
    app = get_context(ctx)
    await app.client.projects.get(project_id)

    repos = await app.client.projects.repos(project_id)
    if not any(repo.id == repo_id for repo in repos):
        raise NotFoundError("repo", repo_id)

    await app.client.projects.set_repo_default_branch(project_id, repo_id, branch)
    return {"project_id": project_id, "repo_id": repo_id, "branch": branch}


@mcp_error_boundary
async def _repo_list(project_id: str, ctx: Context) -> dict:
    """List repositories attached to a project."""
    app = get_context(ctx)
    repos = await app.client.projects.repos(project_id)
    return {"repos": [{"id": r.id, "path": r.path} for r in repos]}


@mcp_error_boundary
async def _project_create(name: str, ctx: Context) -> dict:
    """Create a project by name."""
    app = get_context(ctx)
    project = await app.client.projects.create(name)
    return {"id": project.id, "name": project.name}


@mcp_error_boundary
async def _project_delete(project_id: str, ctx: Context) -> dict:
    """Delete a project permanently."""
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
