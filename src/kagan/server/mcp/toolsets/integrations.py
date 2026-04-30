"""kagan.server.mcp.toolsets.integrations — integration sync and preflight MCP tools."""

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from kagan.core.errors import ValidationError
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary


@mcp_error_boundary
async def _integration_preflight(ctx: Context, integration: str | None = None) -> dict[str, Any]:
    """Check whether an integration's external dependencies are satisfied.

    Returns pass/warn/fail checks for the requested integration (or all
    integrations). For github: verifies gh CLI is installed and authenticated.

    Args:
        integration: Integration to check. If omitted, checks all enabled integrations.
    """
    from kagan.core.integrations import all_enabled

    integrations = all_enabled()
    available = [i.id for i in integrations]

    if integration is not None and integration not in available:
        avail_str = ", ".join(available) or "(none)"
        raise ValidationError("Unknown integration", f"{integration!r}. Available: {avail_str}")

    if integration is not None:
        target = next(i for i in integrations if i.id == integration)
        checks = target.preflight()
    else:
        checks = []
        for i in integrations:
            checks.extend(i.preflight())

    check_dicts = [
        {
            "name": c.name,
            "status": str(c.status),
            "message": c.message,
            "fix_hint": c.fix_hint,
        }
        for c in checks
    ]
    ready = all(c.status.value != "fail" for c in checks)

    return {
        "available_integrations": available,
        "checks": check_dicts,
        "ready": ready,
    }


@mcp_error_boundary
async def _integration_preview(
    ctx: Context,
    integration: str,
    repo: str,
    state: str = "open",
    labels: list[str] | None = None,
    limit: int = 100,
) -> dict[str, Any]:
    """Preview issues from a GitHub repository without importing.

    Returns a list of issues matching the filters so the user can select
    which ones to import via integration_sync with issue_numbers.

    Args:
        integration: Integration name (e.g. "github").
        repo: Repository in owner/repo format.
        state: Issue state filter — "open", "closed", or "all".
        labels: Filter by labels (AND logic).
        limit: Maximum issues to fetch (1-500).
    """
    from kagan.core.integrations import all_enabled
    from kagan.core.integrations.github import preview_github_issues

    app = get_context(ctx)
    project_id = app.bound_project_id or app.client.active_project_id
    if project_id is None:
        raise ValidationError("", "No active project. Create or open a project first.")

    if "/" not in repo:
        raise ValidationError("", "repo must be in owner/repo format (e.g. 'octocat/hello-world')")

    available = [i.id for i in all_enabled()]
    if integration not in available:
        avail_str = ", ".join(available) or "(none)"
        raise ValidationError("Unknown integration", f"{integration!r}. Available: {avail_str}")

    if integration != "github":
        raise ValidationError("", f"Integration {integration!r} does not support preview")

    items = await preview_github_issues(
        app.client,
        project_id=project_id,
        repo_slug=repo,
        state=state,
        labels=labels or [],
        limit=limit,
    )
    serialized = [
        {
            "number": item.extra.get("number", item.id),
            "title": item.title,
            "state": item.state,
            "labels": list(item.labels),
            "url": item.url,
            "already_synced": item.already_synced,
        }
        for item in items
    ]
    return {
        "integration": integration,
        "repo": repo,
        "issues": serialized,
        "total": len(serialized),
    }


@mcp_error_boundary
async def _integration_sync(
    ctx: Context,
    integration: str,
    repo: str,
    state: str = "open",
    labels: list[str] | None = None,
    limit: int = 100,
    issue_numbers: list[int] | None = None,
) -> dict[str, Any]:
    """Sync external items from an integration source into the active project.

    Imports issues from the specified repository as kagan tasks. Labels like
    ``priority:high`` on GitHub issues auto-map to task properties. Operation
    is idempotent — previously synced issues are skipped.

    Args:
        integration: Integration to sync (e.g. "github").
        repo: Repository in owner/repo format.
        state: Issue state filter — "open", "closed", or "all".
        labels: Only sync issues with ALL of these labels.
        limit: Maximum issues to fetch (1-500).
        issue_numbers: Import only these specific issue numbers.
    """
    from kagan.core.integrations import all_enabled
    from kagan.core.integrations.github import sync_github_issues

    app = get_context(ctx)
    project_id = app.bound_project_id or app.client.active_project_id
    if project_id is None:
        raise ValidationError("", "No active project. Create or open a project first.")

    if "/" not in repo:
        raise ValidationError("", "repo must be in owner/repo format (e.g. 'octocat/hello-world')")

    available = [i.id for i in all_enabled()]
    if integration not in available:
        avail_str = ", ".join(available) or "(none)"
        raise ValidationError("Unknown integration", f"{integration!r}. Available: {avail_str}")

    if integration != "github":
        raise ValidationError("", f"Integration {integration!r} does not support sync")

    result = await sync_github_issues(
        app.client,
        project_id=project_id,
        repo_slug=repo,
        state=state,
        labels=labels or [],
        limit=limit,
        issue_numbers=issue_numbers,
    )

    return {
        "integration": integration,
        "repo": repo,
        "project_id": project_id,
        "created": result.created,
        "updated": result.updated,
        "skipped": result.skipped,
        "errors": result.errors,
    }


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register integration domain tools on mcp, filtered by opts."""
    _tools: list[tuple[str, Callable[..., Any]]] = [
        ("integration_preview", _integration_preview),
        ("integration_sync", _integration_sync),
        ("integration_preflight", _integration_preflight),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
