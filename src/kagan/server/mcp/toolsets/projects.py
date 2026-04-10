"""kagan.server.mcp.toolsets.projects — Project and repo domain MCP tools.

3 tools: project_list, project_setup, project_update.
"""

from mcp.server.fastmcp import Context, FastMCP

from kagan.core.errors import NotFoundError
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary


@mcp_error_boundary
async def _project_list(ctx: Context) -> dict:
    """List all projects with repos inlined and active status.

    Returns each project with its attached repositories and whether
    it is the currently active project.
    """
    app = get_context(ctx)
    projects = await app.client.projects.list()

    active_id = app.client.active_project_id

    result = []
    for p in projects:
        repos = await app.client.projects.repos(p.id)
        result.append(
            {
                "id": p.id,
                "name": p.name,
                "is_active": p.id == active_id,
                "repos": [{"id": r.id, "path": r.path} for r in repos],
            }
        )
    return {"projects": result}


@mcp_error_boundary
async def _project_setup(
    name: str,
    ctx: Context,
    repo_paths: list[str] | None = None,
    set_active: bool = True,
) -> dict:
    """Create a new project, optionally attach repos and set it active.

    Args:
        name: Project name (required).
        repo_paths: Optional list of repository paths to attach.
        set_active: Whether to set this project as active (default True).
    """
    app = get_context(ctx)
    project = await app.client.projects.create(name)

    if repo_paths:
        for path in repo_paths:
            await app.client.projects.add_repo(project.id, path)

    if set_active:
        await app.client.projects.set_active(project.id)

    repos = await app.client.projects.repos(project.id)
    return {
        "id": project.id,
        "name": project.name,
        "is_active": set_active,
        "repos": [{"id": r.id, "path": r.path} for r in repos],
    }


@mcp_error_boundary
async def _project_update(
    project_id: str,
    ctx: Context,
    set_active: bool | None = None,
    add_repo_path: str | None = None,
    repo_id: str | None = None,
    default_branch: str | None = None,
    delete: bool = False,
) -> dict:
    """Update an existing project: set active, add repo, set default branch, or delete.

    Args:
        project_id: The project to update (required).
        set_active: If True, set this project as the active project.
        add_repo_path: Path of a repository to attach.
        repo_id: Repository ID (required when setting default_branch).
        default_branch: New default branch for the repo identified by repo_id.
        delete: If True, delete the project and return early.
    """
    app = get_context(ctx)

    if delete:
        await app.client.projects.delete(project_id)
        return {"project_id": project_id, "deleted": True}

    # Validate project exists
    await app.client.projects.get(project_id)

    if set_active is True:
        await app.client.projects.set_active(project_id)

    if add_repo_path is not None:
        await app.client.projects.add_repo(project_id, add_repo_path)

    if default_branch is not None:
        if repo_id is None:
            raise ValueError("repo_id is required when setting default_branch")
        repos = await app.client.projects.repos(project_id)
        if not any(r.id == repo_id for r in repos):
            raise NotFoundError("repo", repo_id)
        await app.client.projects.set_repo_default_branch(project_id, repo_id, default_branch)

    # Return updated state
    repos = await app.client.projects.repos(project_id)

    return {
        "id": project_id,
        "is_active": app.client.active_project_id == project_id,
        "repos": [{"id": r.id, "path": r.path} for r in repos],
    }


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register project and repo domain tools on mcp, filtered by opts."""
    _tools = [
        ("project_list", _project_list),
        ("project_setup", _project_setup),
        ("project_update", _project_update),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
