"""Analytics API routes — backend stats, session timeline."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.server._helpers import _ok, handle_errors, require_context

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse


def register_analytics_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/api/analytics/backend-stats", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_backend_stats(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok([])
        stats = await ctx.client.analytics.backend_stats(project_id)
        return _ok(stats)

    @mcp.custom_route("/api/analytics/session-timeline", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_session_timeline(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok([])
        days = int(request.query_params.get("days", "30"))
        timeline = await ctx.client.analytics.session_timeline(project_id, days=days)
        return _ok(timeline)

    @mcp.custom_route("/api/analytics/export", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def export_analytics(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            empty: dict = {
                "exported_at": None,
                "period_days": 30,
                "backend_stats": [],
                "session_timeline": [],
            }
            return _ok(empty)
        days = int(request.query_params.get("days", "30"))
        data = await ctx.client.analytics.export(project_id, days=days)
        return _ok(data)
