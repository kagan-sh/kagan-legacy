from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

from starlette.responses import JSONResponse

from kagan.core.errors import KaganError
from kagan.integrations.github import (
    canonical_repo_slug,
    detect_github_repo_slug_from_origin,
    normalize_github_state,
)
from kagan.mcp._policy import AccessTier
from kagan.mcp.server import get_server_context
from kagan.plugins import PluginManager
from kagan.plugins._github import GitHubImportConfig
from kagan.server._access import http_forbidden, is_access_allowed
from kagan.wire.envelopes import WireEnvelope

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request


def _ok(data: Any) -> JSONResponse:
    return JSONResponse(WireEnvelope(ok=True, data=data).model_dump())


def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse(WireEnvelope(ok=False, error=msg).model_dump(), status_code=status)


def _error_response(exc: Exception) -> JSONResponse:
    if isinstance(exc, KaganError | ValueError | KeyError | TypeError):
        if isinstance(exc, KeyError):
            field = exc.args[0] if exc.args else "unknown"
            return _err(f"Missing field: {field}", status=400)
        return _err(str(exc), status=400)
    return _err("Internal server error", status=500)


def _require_access(
    ctx: Any,
    *,
    operation: str,
    minimum_tier: AccessTier,
) -> JSONResponse | None:
    if is_access_allowed(ctx, minimum_tier):
        return None
    return http_forbidden(operation=operation, minimum_tier=minimum_tier)


async def _resolve_selected_repo_path(ctx: Any) -> Path | None:
    settings = await ctx.client.settings.get()
    return await ctx.client.projects.resolve_repo_path(settings=settings)


def register_plugin_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/api/plugins", methods=["GET"])
    async def list_plugins(_request: Request) -> JSONResponse:
        ctx = get_server_context(mcp)
        if ctx is None:
            return _err("Server not ready", status=503)
        try:
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
        except Exception as exc:
            return _error_response(exc)

    @mcp.custom_route("/api/plugins/{name}/preflight", methods=["GET"])
    async def plugin_preflight(request: Request) -> JSONResponse:
        name = cast("str", request.path_params["name"])
        ctx = get_server_context(mcp)
        if ctx is None:
            return _err("Server not ready", status=503)
        try:
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
        except Exception as exc:
            return _error_response(exc)

    @mcp.custom_route("/api/plugins/{name}/detect-repo", methods=["GET"])
    async def plugin_detect_repo(request: Request) -> JSONResponse:
        name = cast("str", request.path_params["name"])
        ctx = get_server_context(mcp)
        if ctx is None:
            return _err("Server not ready", status=503)
        try:
            manager = PluginManager(ctx.client)
            await manager.load()
            manager.get(name)

            if name != "github":
                return _err(f"Plugin {name!r} does not support repo detection", status=400)

            repo_path_param = request.query_params.get("repo_path")
            repo_path = (
                Path(repo_path_param) if repo_path_param else await _resolve_selected_repo_path(ctx)
            )
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
        except Exception as exc:
            return _error_response(exc)

    @mcp.custom_route("/api/plugins/{name}/import", methods=["POST"])
    async def plugin_import(request: Request) -> JSONResponse:
        name = cast("str", request.path_params["name"])
        ctx = get_server_context(mcp)
        if ctx is None:
            return _err("Server not ready", status=503)
        forbidden = _require_access(ctx, operation="Plugin imports", minimum_tier=AccessTier.ADMIN)
        if forbidden is not None:
            return forbidden
        try:
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
        except Exception as exc:
            return _error_response(exc)
