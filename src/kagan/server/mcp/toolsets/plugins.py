"""kagan.server.mcp.toolsets.plugins — Plugin sync and preflight MCP tools."""

from collections.abc import Callable
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from kagan.core.errors import ValidationError
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary

_OFFICIAL_PLUGIN_ALLOWLIST = frozenset({"github"})


def _public_plugins(available: list[str]) -> list[str]:
    return sorted(name for name in available if name in _OFFICIAL_PLUGIN_ALLOWLIST)


@mcp_error_boundary
async def _plugins_sync(
    ctx: Context,
    plugin: str,
    repo: str,
    state: str = "open",
    import_label: str | None = None,
) -> dict[str, Any]:
    """Sync external items from a plugin source into the active project.

    Imports issues from the specified repository as kagan tasks.
    Labels like ``priority:high`` and ``kagan:auto`` on GitHub issues
    auto-map to task properties. Operation is idempotent — previously
    synced issues are skipped.

    Args:
        plugin: Plugin to sync (e.g. "github"). Use plugins_preflight to list available.
        repo: Repository in owner/repo format (e.g. "octocat/hello-world").
        state: Issue state filter — "open", "closed", or "all".
        import_label: Only sync issues with this label.
    """
    app = get_context(ctx)
    project_id = app.bound_project_id or app.client.active_project_id
    if project_id is None:
        raise ValidationError("", "No active project. Create or open a project first.")

    if "/" not in repo:
        raise ValidationError("", "repo must be in owner/repo format (e.g. 'octocat/hello-world')")

    # Lazy import — plugins module never loaded unless tool is called
    from kagan.core.plugins import PluginManager

    manager = PluginManager(app.client)
    await manager.load()

    available_public = _public_plugins(manager.available)

    if plugin not in available_public:
        available = ", ".join(available_public) or "(none)"
        raise ValidationError("Unknown plugin", f"{plugin!r}. Installed: {available}")

    # Configure and sync via the generic ImporterPlugin interface
    owner, repo_name = repo.split("/", 1)
    import_plugin = manager.get_import(plugin)

    from kagan.core.plugins._github import GitHubImportConfig

    import_plugin.configure(
        GitHubImportConfig(
            owner=owner,
            repo=repo_name,
            state=state,
            import_label=import_label,
        )
    )
    result = await import_plugin.sync(project_id)

    response: dict[str, Any] = {
        "plugin": plugin,
        "repo": repo,
        "project_id": project_id,
        "created": result.created,
        "updated": result.updated,
        "skipped": result.skipped,
        "errors": result.errors,
    }

    # Include community warnings if any
    warnings = manager.community_warnings
    if warnings:
        response["community_warnings"] = warnings

    return response


@mcp_error_boundary
async def _plugins_preflight(ctx: Context, plugin: str | None = None) -> dict[str, Any]:
    """Check if a plugin's external dependencies are satisfied.

    Returns pass/warn/fail checks for the requested plugin (or all plugins).
    For github: verifies gh CLI is installed and authenticated.

    Args:
        plugin: Plugin to check. If omitted, checks all installed plugins.
    """
    app = get_context(ctx)

    from kagan.core.plugins import PluginManager

    manager = PluginManager(app.client)
    await manager.load()

    available_public = _public_plugins(manager.available)

    if plugin is not None and plugin not in available_public:
        available = ", ".join(available_public) or "(none)"
        raise ValidationError("Unknown plugin", f"{plugin!r}. Installed: {available}")

    if plugin is not None:
        target = manager.get(plugin)
        checks = target.preflight()
    else:
        checks = []
        for plugin_name in available_public:
            checks.extend(manager.get(plugin_name).preflight())

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

    response: dict[str, Any] = {
        "available_plugins": available_public,
        "official_plugins": available_public,
        "checks": check_dicts,
        "ready": ready,
    }

    return response


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register plugin domain tools on mcp, filtered by opts."""
    _tools: list[tuple[str, Callable[..., Any]]] = [
        ("plugins_sync", _plugins_sync),
        ("plugins_preflight", _plugins_preflight),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
