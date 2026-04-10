"""kagan.server.mcp.toolsets.personas — Persona preset domain MCP tools.

4 tools: persona_inspect, persona_import, persona_export, persona_trust.
"""

from mcp.server.fastmcp import Context, FastMCP

from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary


@mcp_error_boundary
async def _persona_inspect(
    ctx: Context,
    repo: str,
    path: str = ".kagan/personas.json",
    ref: str | None = None,
) -> dict:
    """Audit and preview a persona preset repository before import.

    Returns trust assessment including:
    - trust_tier: low_risk, medium_risk, or high_risk
    - trust_score: 0.0-1.0 reputation score
    - findings: security audit results
    - personas: preview of available personas
    """
    app = get_context(ctx)
    return await app.client.persona_presets.audit_repo(repo=repo, path=path, ref=ref)


@mcp_error_boundary
async def _persona_import(
    ctx: Context,
    repo: str,
    path: str = ".kagan/personas.json",
    ref: str | None = None,
    acknowledge_risk: bool = False,
    merge_mode: str = "merge",
    auto_confirm: bool = False,
) -> dict:
    """Import persona presets from GitHub into Kagan.

    Progressive trust behavior:
    - Low risk: Auto-imported (with auto_confirm=True)
    - Medium risk: Imported; trust assessment returned for review
    - High risk: Requires acknowledge_risk=True flag
    """
    app = get_context(ctx)
    return await app.client.persona_presets.import_from_github(
        repo=repo,
        path=path,
        ref=ref,
        acknowledge_risk=acknowledge_risk,
        merge_mode=merge_mode,
        auto_confirm=auto_confirm,
    )


@mcp_error_boundary
async def _persona_export(
    ctx: Context,
    repo: str,
    path: str = ".kagan/personas.json",
    branch: str | None = None,
    commit_message: str = "chore: publish kagan persona presets",
) -> dict:
    """Export local persona presets to GitHub."""
    app = get_context(ctx)
    return await app.client.persona_presets.export_to_github(
        repo=repo,
        path=path,
        branch=branch,
        commit_message=commit_message,
    )


@mcp_error_boundary
async def _persona_trust(
    ctx: Context,
    action: str,
    repo: str | None = None,
) -> dict:
    """Manage trusted persona preset repositories.

    Args:
        action: One of "list", "add", "remove".
        repo: Repository identifier (required for "add" and "remove").
    """
    app = get_context(ctx)

    if action not in ("list", "add", "remove"):
        raise ValueError(f"Invalid action '{action}': must be 'list', 'add', or 'remove'")

    if action == "list":
        return await app.client.persona_presets.whitelist_list()

    if repo is None:
        raise ValueError(f"repo is required for action '{action}'")

    if action == "add":
        return await app.client.persona_presets.whitelist_add(repo)

    return await app.client.persona_presets.whitelist_remove(repo)


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register persona preset domain tools on mcp, filtered by opts."""
    _tools = [
        ("persona_inspect", _persona_inspect),
        ("persona_import", _persona_import),
        ("persona_export", _persona_export),
        ("persona_trust", _persona_trust),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
