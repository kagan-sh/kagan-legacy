"""kagan.server._integration_routes — REST routes for native integrations.

Endpoints:

    GET  /api/integrations
    GET  /api/integrations/{id}/preflight
    GET  /api/integrations/{id}/detect-repo
    GET  /api/integrations/{id}/preview
    POST /api/integrations/{id}/sync
    GET  /api/mentions/search
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, cast

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

    from kagan.server.mcp.server import ServerContext


async def _resolve_selected_repo_path(ctx: ServerContext) -> Path | None:
    settings = await ctx.client.settings.get()
    return await ctx.client.projects.resolve_repo_path(settings=settings)


async def _handle_mentions_search(request: Request, ctx: ServerContext) -> JSONResponse:
    """Search kagan tasks + GitHub issues for #-mention autocomplete.

    Query params: ``project_id`` (defaults to active project), ``q`` (required),
    ``limit`` (default 10, max 50).
    """
    from kagan.core.integrations.mentions import search_mentions

    q = request.query_params.get("q", "").strip()
    if not q:
        return _err("'q' query parameter is required", status=400)

    project_id = request.query_params.get("project_id") or ctx.client.active_project_id
    if not project_id:
        return _err("No active project and no project_id provided", status=400)

    try:
        limit = min(max(int(request.query_params.get("limit", "10")), 1), 50)
    except ValueError:
        limit = 10

    mentions = await search_mentions(ctx.client, project_id, q, limit=limit)
    return _ok(
        {
            "mentions": [
                {"source": m.source, "id": m.id, "title": m.title, "state": m.state}
                for m in mentions
            ],
            "total": len(mentions),
        }
    )


def register_integration_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/api/integrations", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_integrations(_request: Request, *, ctx: ServerContext) -> JSONResponse:
        from kagan.core.integrations import all_enabled

        integrations = all_enabled()
        return _ok({"integrations": [{"id": i.id, "name": i.id} for i in integrations]})

    @mcp.custom_route("/api/integrations/{id}/preflight", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def integration_preflight(request: Request, *, ctx: ServerContext) -> JSONResponse:
        from kagan.core.integrations import all_enabled

        integration_id = cast("str", request.path_params["id"])
        integrations = all_enabled()
        target = next((i for i in integrations if i.id == integration_id), None)
        if target is None:
            return _err(f"Integration {integration_id!r} not found", status=404)

        checks = target.preflight()
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
                "id": integration_id,
                "checks": serialized_checks,
                "ready": all(check["ok"] for check in serialized_checks),
            }
        )

    @mcp.custom_route("/api/integrations/{id}/detect-repo", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def integration_detect_repo(request: Request, *, ctx: ServerContext) -> JSONResponse:
        from kagan.core.integrations import all_enabled

        integration_id = cast("str", request.path_params["id"])
        integrations = all_enabled()
        if not any(i.id == integration_id for i in integrations):
            return _err(f"Integration {integration_id!r} not found", status=404)

        if integration_id != "github":
            return _err(
                f"Integration {integration_id!r} does not support repo detection", status=400
            )

        from kagan.core.integrations.github import detect_github_repo_slug_from_origin

        repo_path_param = request.query_params.get("repo_path")
        if repo_path_param:
            repo_path = Path(repo_path_param).resolve()
        else:
            repo_path = await _resolve_selected_repo_path(ctx)
        if repo_path is None:
            return _ok({"id": integration_id, "repo_slug": None})

        repo_slug = await detect_github_repo_slug_from_origin(repo_path)
        return _ok(
            {
                "id": integration_id,
                "repo_path": str(repo_path),
                "repo_slug": repo_slug,
            }
        )

    @mcp.custom_route("/api/integrations/{id}/preview", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def integration_preview(request: Request, *, ctx: ServerContext) -> JSONResponse:
        from kagan.core.integrations import all_enabled
        from kagan.core.integrations.github import (
            canonical_repo_slug,
            normalize_github_state,
            preview_github_issues,
        )

        integration_id = cast("str", request.path_params["id"])
        integrations = all_enabled()
        if not any(i.id == integration_id for i in integrations):
            return _err(f"Integration {integration_id!r} not found", status=404)

        if integration_id != "github":
            return _err(f"Integration {integration_id!r} does not support preview", status=400)

        project_id = ctx.client.active_project_id
        if not project_id:
            return _err("No active project", status=400)

        repo_slug = canonical_repo_slug(request.query_params.get("repo_slug", ""))
        state = normalize_github_state(request.query_params.get("state", "open"))
        labels_raw = request.query_params.get("labels", "")
        labels = [s.strip() for s in labels_raw.split(",") if s.strip()] if labels_raw else []
        limit_raw = request.query_params.get("limit", "100")
        limit = min(max(int(limit_raw), 1), 500)

        items = await preview_github_issues(
            ctx.client,
            project_id=project_id,
            repo_slug=repo_slug,
            state=state,
            labels=labels,
            limit=limit,
        )
        # Serialize ExternalItem to dict for wire transport
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
        return _ok({"id": integration_id, "issues": serialized, "total": len(serialized)})

    @mcp.custom_route("/api/integrations/{id}/sync", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def integration_sync(request: Request, *, ctx: ServerContext) -> JSONResponse:
        from kagan.core.integrations import all_enabled
        from kagan.core.integrations.github import (
            GitHubConfig,
            canonical_repo_slug,
            github,
            normalize_github_state,
        )

        integration_id = cast("str", request.path_params["id"])
        forbidden = _require_access(
            ctx, operation="Integration sync", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden

        integrations = all_enabled()
        if not any(i.id == integration_id for i in integrations):
            return _err(f"Integration {integration_id!r} not found", status=404)

        payload = await request.json()
        body = payload if isinstance(payload, dict) else {}

        project_id = ctx.client.active_project_id
        if not project_id:
            return _err("No active project", status=400)

        if integration_id == "github":
            repo_slug = canonical_repo_slug(str(body.get("repo_slug", "")))
            state = normalize_github_state(str(body.get("state", "open")))
            labels_raw = body.get("labels")
            labels = (
                tuple(str(s).strip() for s in labels_raw) if isinstance(labels_raw, list) else ()
            )
            limit = min(max(int(body.get("limit", 100)), 1), 500)
            issue_numbers_raw = body.get("issue_numbers")
            issue_numbers = (
                tuple(int(n) for n in issue_numbers_raw)
                if isinstance(issue_numbers_raw, list)
                else ()
            )
            owner, repo = repo_slug.split("/", 1)
            config = GitHubConfig(
                owner=owner,
                repo=repo,
                state=state,
                labels=labels,
                limit=limit,
                issue_numbers=issue_numbers,
            )
            result = await github.sync(ctx.client, config, project_id)
        else:
            return _err(f"Integration {integration_id!r} does not support sync", status=400)

        return _ok(
            {
                "id": integration_id,
                "created": result.created,
                "updated": result.updated,
                "skipped": result.skipped,
                "errors": list(result.errors),
            }
        )

    @mcp.custom_route("/api/mentions/search", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def mentions_search(request: Request, *, ctx: ServerContext) -> JSONResponse:
        return await _handle_mentions_search(request, ctx)
