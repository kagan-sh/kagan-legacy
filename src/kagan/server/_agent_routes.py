"""Routes for the global orchestrator-chat overlay.

Surfaces:
- GET /api/v1/agents/running?project_id=<optional>
    → RunningAgentsResponse
- GET /api/v1/sessions/{session_id}/replay?cursor=<event_id>&limit=200&direction=forward
    → SessionReplayPage
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from starlette.responses import JSONResponse

from kagan.core._sessions_query import list_running_agents, session_event_created_at
from kagan.server._access import AccessTier
from kagan.server._helpers import (
    _err,
    _ok,
    _require_access,
    handle_errors,
    require_context,
)
from kagan.server.responses import (
    ActiveAgentRowResponse,
    RunningAgentsResponse,
    SessionReplayEvent,
    SessionReplayPage,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request

    from kagan.core.models import SessionEvent
    from kagan.server.mcp.server import ServerContext

_MAX_REPLAY_LIMIT = 1000
_DEFAULT_REPLAY_LIMIT = 200


@dataclass(frozen=True)
class _ReplayCursor:
    created_at: datetime | None
    event_id: str | None


@dataclass(frozen=True)
class _ReplayQuery:
    session_id: str
    cursor: _ReplayCursor
    direction: str
    limit: int


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _fetch_agents_response(
    ctx: ServerContext, project_id: str | None
) -> RunningAgentsResponse:
    engine = ctx.client.engine
    rows = await list_running_agents(engine, project_id=project_id)
    agents = [
        ActiveAgentRowResponse(
            task_id=r.task_id,
            task_title=r.task_title,
            task_status=r.task_status,
            session_id=r.session_id,
            agent_role=r.agent_role,
            agent_backend=r.agent_backend,
            session_status=r.session_status,
            started_at=r.started_at,
            last_event_at=r.last_event_at,
            input_tokens=r.input_tokens,
            output_tokens=r.output_tokens,
        )
        for r in rows
    ]
    return RunningAgentsResponse(agents=agents)


def _parse_replay_cursor(cursor: str | None) -> _ReplayCursor:
    if cursor is None:
        return _ReplayCursor(created_at=None, event_id=None)
    if "|" not in cursor:
        return _ReplayCursor(created_at=None, event_id=cursor)

    ts_part, id_part = cursor.split("|", 1)
    try:
        return _ReplayCursor(created_at=datetime.fromisoformat(ts_part), event_id=id_part)
    except ValueError:
        return _ReplayCursor(created_at=None, event_id=cursor)


def _parse_replay_limit(raw_limit: str | None) -> int:
    try:
        limit = int(raw_limit or _DEFAULT_REPLAY_LIMIT)
    except (ValueError, TypeError):
        return _DEFAULT_REPLAY_LIMIT
    return max(1, min(limit, _MAX_REPLAY_LIMIT))


def _parse_replay_query(request: Request) -> _ReplayQuery:
    params = request.query_params
    return _ReplayQuery(
        session_id=request.path_params.get("session_id", ""),
        cursor=_parse_replay_cursor(params.get("cursor") or None),
        direction=params.get("direction", "forward"),
        limit=_parse_replay_limit(params.get("limit")),
    )


async def _query_session_replay_events(
    ctx: ServerContext, query: _ReplayQuery
) -> tuple[list[SessionEvent], bool]:
    task_id, project_id = await ctx.client.tasks.sessions.resolve_binding(query.session_id)
    bound_project_id = getattr(ctx, "bound_project_id", None)
    if task_id is None or (bound_project_id is not None and project_id != bound_project_id):
        return [], False

    page_limit = query.limit + 1
    if query.direction == "backward":
        rows = await _query_backward_events(ctx, task_id, query, page_limit)
    else:
        rows = await _query_forward_events(ctx, task_id, query, page_limit)
    return rows[: query.limit], len(rows) > query.limit


async def _query_forward_events(
    ctx: ServerContext, task_id: str, query: _ReplayQuery, page_limit: int
) -> list[SessionEvent]:
    cursor = await _resolve_replay_cursor(ctx, query)
    if cursor.created_at is not None and cursor.event_id is not None:
        return await ctx.client.tasks.events.list_after(
            task_id,
            after_ts=cursor.created_at.isoformat(),
            after_id=cursor.event_id,
            limit=page_limit,
            session_id=query.session_id,
        )
    return await ctx.client.tasks.events.list(
        task_id,
        limit=page_limit,
        session_id=query.session_id,
    )


async def _query_backward_events(
    ctx: ServerContext, task_id: str, query: _ReplayQuery, page_limit: int
) -> list[SessionEvent]:
    cursor = await _resolve_replay_cursor(ctx, query)
    if cursor.created_at is not None and cursor.event_id is not None:
        rows = await ctx.client.tasks.events.list_before(
            task_id,
            before=cursor.created_at.isoformat(),
            before_id=cursor.event_id,
            limit=page_limit,
            session_id=query.session_id,
        )
    else:
        rows = await ctx.client.tasks.events.list_recent(
            task_id,
            limit=page_limit,
            session_id=query.session_id,
        )
    rows.reverse()
    return rows


async def _resolve_replay_cursor(ctx: ServerContext, query: _ReplayQuery) -> _ReplayCursor:
    cursor = query.cursor
    if cursor.created_at is not None or cursor.event_id is None:
        return cursor

    created_at = await session_event_created_at(
        ctx.client.engine,
        session_id=query.session_id,
        event_id=cursor.event_id,
    )
    if created_at is None:
        return _ReplayCursor(created_at=None, event_id=None)
    return _ReplayCursor(created_at=created_at, event_id=cursor.event_id)


def _to_replay_event(row: SessionEvent) -> SessionReplayEvent:
    return SessionReplayEvent(
        id=row.id,
        session_id=row.session_id,
        event_type=row.event_type,
        payload=row.payload or {},
        created_at=row.created_at,
    )


def _next_replay_cursor(events: list[SessionReplayEvent], has_more: bool) -> str | None:
    if not has_more or not events:
        return None
    last = events[-1]
    return f"{last.created_at.replace('+00:00', 'Z')}|{last.id}"


async def _session_replay_response(request: Request, ctx: ServerContext) -> JSONResponse:
    query = _parse_replay_query(request)
    task_id, project_id = await ctx.client.tasks.sessions.resolve_binding(query.session_id)
    bound_project_id = getattr(ctx, "bound_project_id", None)
    if task_id is None or (bound_project_id is not None and project_id != bound_project_id):
        return _err(f"Session {query.session_id!r} not found", status=404)

    rows, has_more = await _query_session_replay_events(ctx, query)
    events = [_to_replay_event(row) for row in rows]
    page = SessionReplayPage(
        events=events,
        next_cursor=_next_replay_cursor(events, has_more),
        has_more=has_more,
    )
    return _ok(page.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_agent_routes(mcp: FastMCP) -> None:
    """Register all agent / session overlay routes on *mcp*."""

    @mcp.custom_route("/api/v1/agents/running", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def running_agents(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, minimum_tier=AccessTier.READONLY, operation="List running agents"
        )
        if forbidden is not None:
            return forbidden
        project_id = _running_agents_project_id(request, ctx)
        if isinstance(project_id, JSONResponse):
            return project_id
        resp = await _fetch_agents_response(ctx, project_id)
        return _ok(resp.model_dump(mode="json"))

    @mcp.custom_route("/api/v1/sessions/{session_id}/replay", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def session_replay(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, minimum_tier=AccessTier.READONLY, operation="Replay session events"
        )
        if forbidden is not None:
            return forbidden
        return await _session_replay_response(request, ctx)


def _running_agents_project_id(request: Request, ctx: ServerContext) -> str | None | JSONResponse:
    requested = request.query_params.get("project_id") or None
    bound = getattr(ctx, "bound_project_id", None)
    if bound is None:
        return requested
    if requested is not None and requested != bound:
        return _err("Project is outside the current server binding", status=403)
    return bound
