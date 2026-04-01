from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from kagan.core.integrations.github import (
    canonical_repo_slug,
    detect_github_repo_slug_from_origin,
    normalize_github_state,
)
from kagan.core.plugins import PluginManager
from kagan.core.plugins._github import GitHubImportConfig
from kagan.server._access import AccessTier
from kagan.server._helpers import (
    _err,
    _ok,
    _require_access,
    handle_errors,
    require_context,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse


async def _resolve_selected_repo_path(ctx: Any) -> Path | None:
    settings = await ctx.client.settings.get()
    return await ctx.client.projects.resolve_repo_path(settings=settings)


def register_plugin_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/api/plugins", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_plugins(_request: Request, *, ctx: Any) -> JSONResponse:
        manager = PluginManager(ctx.client)
        await manager.load()
        plugins = []
        for name in manager.available:
            meta = manager.get_meta(name)
            plugins.append(
                {
                    "name": name,
                    "builtin": meta.builtin if meta else False,
                    "package": meta.package if meta else None,
                    "version": meta.version if meta else None,
                }
            )
        return _ok({"plugins": plugins})

    @mcp.custom_route("/api/plugins/{name}/preflight", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def plugin_preflight(request: Request, *, ctx: Any) -> JSONResponse:
        name = cast("str", request.path_params["name"])
        manager = PluginManager(ctx.client)
        await manager.load()
        plugin = manager.get(name)
        checks = plugin.preflight()
        serialized_checks = [
            {
                "ok": check.status.value == "pass",
                "message": check.message,
                "fix_hint": check.fix_hint,
            }
            for check in checks
        ]
        return _ok(
            {
                "plugin": name,
                "checks": serialized_checks,
                "ready": all(check["ok"] for check in serialized_checks),
            }
        )

    @mcp.custom_route("/api/plugins/{name}/detect-repo", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def plugin_detect_repo(request: Request, *, ctx: Any) -> JSONResponse:
        name = cast("str", request.path_params["name"])
        manager = PluginManager(ctx.client)
        await manager.load()
        manager.get(name)

        if name != "github":
            return _err(f"Plugin {name!r} does not support repo detection", status=400)

        repo_path_param = request.query_params.get("repo_path")
        if repo_path_param:
            repo_path = Path(repo_path_param).resolve()
            if not repo_path.is_relative_to(Path.home()):
                return _err("Path outside allowed boundaries", status=403)
        else:
            repo_path = await _resolve_selected_repo_path(ctx)
        if repo_path is None:
            return _ok({"plugin": name, "repo_slug": None})

        repo_slug = await detect_github_repo_slug_from_origin(repo_path)
        return _ok(
            {
                "plugin": name,
                "repo_path": str(repo_path),
                "repo_slug": repo_slug,
            }
        )

    @mcp.custom_route("/api/plugins/{name}/import", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def plugin_import(request: Request, *, ctx: Any) -> JSONResponse:
        name = cast("str", request.path_params["name"])
        forbidden = _require_access(ctx, operation="Plugin imports", minimum_tier=AccessTier.ADMIN)
        if forbidden is not None:
            return forbidden
        payload = await request.json()
        body = payload if isinstance(payload, dict) else {}

        project_id = ctx.client.active_project_id
        if not project_id:
            return _err("No active project", status=400)

        manager = PluginManager(ctx.client)
        await manager.load()
        import_plugin = manager.get_import(name)

        if name == "github":
            repo_slug = canonical_repo_slug(str(body.get("repo_slug", "")))
            state = normalize_github_state(str(body.get("state", "open")))
            import_label_raw = body.get("import_label")
            import_label = (
                str(import_label_raw).strip() if import_label_raw is not None else None
            ) or None

            owner, repo = repo_slug.split("/", 1)
            import_plugin.configure(
                GitHubImportConfig(
                    owner=owner,
                    repo=repo,
                    state=state,
                    import_label=import_label,
                )
            )
        else:
            import_plugin.configure(body.get("config", body))

        result = await manager.sync(name, project_id=project_id)
        return _ok(
            {
                "plugin": name,
                "created": result.created,
                "updated": result.updated,
                "skipped": result.skipped,
                "errors": list(result.errors),
            }
        )
