"""kagan.mcp.toolsets.settings — Settings and audit domain MCP tools."""

from mcp.server.fastmcp import Context, FastMCP

from kagan.mcp._policy import is_tool_allowed
from kagan.mcp.server import ServerOptions, get_context
from kagan.mcp.toolsets import mcp_error_boundary


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register settings and audit domain tools on mcp, filtered by opts."""
    if is_tool_allowed("settings_get", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def settings_get(ctx: Context) -> dict:
            """Read allowlisted runtime settings."""
            app = get_context(ctx)
            return await app.client.settings.get()

    if is_tool_allowed("audit_list", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def audit_list(ctx: Context, limit: int | None = None) -> dict:
            """List recent audit log entries."""
            app = get_context(ctx)
            entries = await app.client.audit_log.list(limit=limit)
            return {
                "entries": [
                    {
                        "id": e.id,
                        "action": e.action,
                        "entity_type": e.entity_type,
                        "entity_id": e.entity_id,
                    }
                    for e in entries
                ]
            }

    if is_tool_allowed("settings_set", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def settings_set(section: str, key: str, value: str, ctx: Context) -> dict:
            """Update one allowlisted setting value."""
            app = get_context(ctx)
            await app.client.settings.set({key: value})
            return {"section": section, "key": key, "value": value}

    if is_tool_allowed("persona_preset_audit", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def persona_preset_audit(
            ctx: Context,
            repo: str,
            path: str = ".kagan/personas.json",
            ref: str | None = None,
        ) -> dict:
            """Audit a persona preset repository before import."""
            app = get_context(ctx)
            return await app.client.persona_presets.audit_repo(repo=repo, path=path, ref=ref)

    if is_tool_allowed("persona_preset_import", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def persona_preset_import(
            ctx: Context,
            repo: str,
            path: str = ".kagan/personas.json",
            ref: str | None = None,
            allow_untrusted: bool = False,
            acknowledge_risk: bool = False,
            merge_mode: str = "merge",
        ) -> dict:
            """Import persona presets from GitHub into Kagan."""
            app = get_context(ctx)
            return await app.client.persona_presets.import_from_github(
                repo=repo,
                path=path,
                ref=ref,
                allow_untrusted=allow_untrusted,
                acknowledge_risk=acknowledge_risk,
                merge_mode=merge_mode,
            )

    if is_tool_allowed("persona_preset_export", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def persona_preset_export(
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

    if is_tool_allowed("persona_preset_whitelist_list", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def persona_preset_whitelist_list(ctx: Context) -> dict:
            """List trusted persona preset repositories."""
            app = get_context(ctx)
            return await app.client.persona_presets.whitelist_list()

    if is_tool_allowed("persona_preset_whitelist_add", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def persona_preset_whitelist_add(ctx: Context, repo: str) -> dict:
            """Trust a persona preset repository for future imports."""
            app = get_context(ctx)
            return await app.client.persona_presets.whitelist_add(repo)

    if is_tool_allowed("persona_preset_whitelist_remove", opts):

        @mcp.tool()
        @mcp_error_boundary
        async def persona_preset_whitelist_remove(ctx: Context, repo: str) -> dict:
            """Remove a repository from the persona preset trust list."""
            app = get_context(ctx)
            return await app.client.persona_presets.whitelist_remove(repo)
