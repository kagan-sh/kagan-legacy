"""Analytics API routes — backend stats, session timeline, multi-dimensional analytics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core import BackendSelector
from kagan.server._helpers import _ok, handle_errors, require_context

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse


def _group_by_key(stats: list[dict[str, Any]], key: str) -> dict[str, list[dict[str, Any]]]:
    """Group stats list by a key field."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for stat in stats:
        group_key = stat.get(key, "unknown")
        if group_key not in grouped:
            grouped[group_key] = []
        grouped[group_key].append(stat)
    return grouped


def _filter_by_params(
    stats: list[dict[str, Any]], role: str | None, task_type: str | None
) -> list[dict[str, Any]]:
    """Filter stats by role and/or task type."""
    return [
        stat
        for stat in stats
        if (not role or stat.get("agent_role") == role)
        and (not task_type or stat.get("task_type") == task_type)
    ]


def _optional_days(request: Request) -> int | None:
    days = request.query_params.get("days")
    return int(days) if days else None


def register_analytics_routes(mcp: FastMCP) -> None:
    @mcp.custom_route("/api/analytics/backend-stats", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def _backend_stats(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok([])
        stats = await ctx.client.analytics.backend_stats(project_id, days=_optional_days(request))
        return _ok(stats)

    @mcp.custom_route("/api/analytics/session-timeline", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def _session_timeline(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok([])
        days = int(request.query_params.get("days", "30"))
        timeline = await ctx.client.analytics.session_timeline(project_id, days=days)
        return _ok(timeline)

    @mcp.custom_route("/api/analytics/timeline-summary", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def _timeline_summary(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})
        days = int(request.query_params.get("days", "30"))
        summary = await ctx.client.analytics.timeline_summary(project_id, days=days)
        return _ok(summary)

    @mcp.custom_route("/api/analytics/recommended-backend", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def _recommended_backend(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})
        recommendation = await ctx.client.analytics.recommended_backend(project_id)
        return _ok(recommendation)

    @mcp.custom_route("/api/analytics/export", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def _export(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        days = int(request.query_params.get("days", "30"))
        if not project_id:
            return _ok(
                {
                    "exported_at": None,
                    "period_days": days,
                    "backend_stats": [],
                    "session_timeline": [],
                }
            )
        data = await ctx.client.analytics.export(project_id, days=days)
        return _ok(data)

    @mcp.custom_route("/api/analytics/by-role", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def _by_role(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})
        raw_stats = await ctx.client.analytics.backend_by_role_stats(
            project_id, days=_optional_days(request)
        )
        grouped = _group_by_key(raw_stats, "agent_role")
        return _ok(grouped)

    @mcp.custom_route("/api/analytics/by-task-type", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def _by_task_type(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})
        raw_stats = await ctx.client.analytics.backend_by_task_type_stats(
            project_id, days=_optional_days(request)
        )
        grouped = _group_by_key(raw_stats, "task_type")
        return _ok(grouped)

    @mcp.custom_route("/api/analytics/by-role-and-task-type", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def _by_role_and_task_type(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok([])
        filter_role = request.query_params.get("role")
        filter_task_type = request.query_params.get("task_type")
        raw_stats = await ctx.client.analytics.backend_role_task_stats(
            project_id, days=_optional_days(request)
        )
        filtered = _filter_by_params(raw_stats, filter_role, filter_task_type)
        return _ok(filtered)

    @mcp.custom_route("/api/analytics/recommend-for-task", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def _recommend_for_task(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})
        title = request.query_params.get("title", "")
        if not title:
            return _ok(
                {
                    "backend": "claude-code",
                    "reason": "title required for recommendation",
                    "confidence": 0,
                    "alternatives": [],
                }
            )
        description = request.query_params.get("description", "")
        role = request.query_params.get("role")
        selector = BackendSelector(ctx.client.analytics, project_id)
        recommendation = await selector.select_backend(
            title=title,
            description=description,
            agent_role=role,
        )
        return _ok(recommendation)
