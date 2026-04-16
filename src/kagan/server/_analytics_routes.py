"""Analytics API routes — backend stats, session timeline, multi-dimensional analytics."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core._backend_selector import BackendSelector
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

    @mcp.custom_route("/api/analytics/timeline-summary", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_timeline_summary(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})
        days = int(request.query_params.get("days", "30"))
        summary = await ctx.client.analytics.timeline_summary(project_id, days=days)
        return _ok(summary)

    @mcp.custom_route("/api/analytics/recommended-backend", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_recommended_backend(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})
        recommendation = await ctx.client.analytics.recommended_backend(project_id)
        return _ok(recommendation)

    @mcp.custom_route("/api/analytics/export", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def export_analytics(request: Request, *, ctx: Any) -> JSONResponse:
        project_id = ctx.client.active_project_id
        days = int(request.query_params.get("days", "30"))
        if not project_id:
            # Return same structure as successful export, just empty
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
    async def get_analytics_by_role(request: Request, *, ctx: Any) -> JSONResponse:
        """Returns backend stats grouped by agent role.

        Response: { agent_role → [backend stats] }
        """
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})

        raw_stats = await ctx.client.analytics.backend_by_role_stats(project_id)

        # Group by agent_role
        grouped: dict[str, list[dict[str, Any]]] = {}
        for stat in raw_stats:
            role = stat.get("agent_role", "unknown")
            if role not in grouped:
                grouped[role] = []
            grouped[role].append(stat)

        return _ok(grouped)

    @mcp.custom_route("/api/analytics/by-task-type", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_analytics_by_task_type(request: Request, *, ctx: Any) -> JSONResponse:
        """Returns backend stats grouped by task type.

        Response: { task_type → [backend stats] }
        """
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})

        raw_stats = await ctx.client.analytics.backend_by_task_type_stats(project_id)

        # Group by task_type
        grouped: dict[str, list[dict[str, Any]]] = {}
        for stat in raw_stats:
            task_type = stat.get("task_type", "unknown")
            if task_type not in grouped:
                grouped[task_type] = []
            grouped[task_type].append(stat)

        return _ok(grouped)

    @mcp.custom_route("/api/analytics/by-role-and-task-type", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_analytics_by_role_and_task_type(
        request: Request, *, ctx: Any
    ) -> JSONResponse:
        """Returns backend stats filtered by role and/or task type.

        Query params: role=<role>, task_type=<task_type>
        Response: [backend stats matching filters]
        """
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok([])

        filter_role = request.query_params.get("role")
        filter_task_type = request.query_params.get("task_type")

        raw_stats = await ctx.client.analytics.backend_role_task_stats(project_id)

        # Filter by role and/or task_type
        filtered = []
        for stat in raw_stats:
            if filter_role and stat.get("agent_role") != filter_role:
                continue
            if filter_task_type and stat.get("task_type") != filter_task_type:
                continue
            filtered.append(stat)

        return _ok(filtered)

    @mcp.custom_route("/api/analytics/recommend-for-task", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def recommend_backend_for_task(request: Request, *, ctx: Any) -> JSONResponse:
        """Get intelligent backend recommendation for a task.

        Query params:
        - title: task title (required)
        - description: task description (optional)
        - role: agent role (optional, e.g. 'worker')

        Response: { backend, reason, confidence, alternatives }
        """
        project_id = ctx.client.active_project_id
        if not project_id:
            return _ok({})

        title = request.query_params.get("title", "")
        description = request.query_params.get("description", "")
        role = request.query_params.get("role")

        if not title:
            return _ok(
                {
                    "backend": "claude-code",
                    "reason": "title required for recommendation",
                    "confidence": 0,
                    "alternatives": [],
                }
            )

        selector = BackendSelector(ctx.client.analytics, project_id)
        recommendation = await selector.select_backend(
            title=title,
            description=description,
            agent_role=role,
        )

        return _ok(recommendation)
