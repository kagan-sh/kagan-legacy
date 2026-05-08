"""Routes for the global orchestrator-chat overlay.

Surfaces:
- GET /api/v1/agents/running?project_id=<optional>
    → RunningAgentsResponse
- GET /api/v1/agents/running/events
    → SSE: live diff of running-agents list (joined/started/finished/status_change)
- GET /api/v1/sessions/{session_id}/replay?cursor=<event_id>&limit=200&direction=forward
    → SessionReplayPage
- GET /api/v1/sessions/{session_id}/events?since=<event_id>
    → SSE: live tail of SessionEvents for one session
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlmodel import asc, desc, or_, select

from kagan.core import db_async as _db_async
from kagan.core import list_running_agents
from kagan.core import sa_col as _sa_col
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, SessionEvent
from kagan.server._access import AccessTier
from kagan.server._helpers import (
    _err,
    _ok,
    _require_access,
    handle_errors,
    require_context,
)
from kagan.server._sse import sse_response
from kagan.server.responses import (
    ActiveAgentRowResponse,
    RunningAgentsResponse,
    SessionReplayEvent,
    SessionReplayPage,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse, StreamingResponse

    from kagan.server.mcp.server import ServerContext

_MAX_REPLAY_LIMIT = 1000
_DEFAULT_REPLAY_LIMIT = 200
_SSE_KEEPALIVE_SECONDS = 25.0
_AGENT_POLL_SECONDS = 3.0
_SESSION_EVENTS_POLL_SECONDS = 1.0


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


def _row_key(row: dict[str, Any]) -> str:
    """Stable dict key from a running-agent row for diff comparison."""
    return f"{row['task_id']}:{row['session_id']}:{row['session_status']}"


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


def _query_param_or_none(request: Request, name: str) -> str | None:
    return request.query_params.get(name) or None


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


def _apply_replay_cursor(stmt: Any, query: _ReplayQuery) -> Any:
    cursor = query.cursor
    if cursor.created_at is not None and cursor.event_id is not None:
        created_at_col = _sa_col(SessionEvent.created_at)
        id_col = _sa_col(SessionEvent.id)
        if query.direction == "backward":
            return stmt.where(
                or_(
                    created_at_col < cursor.created_at,
                    (created_at_col == cursor.created_at) & (id_col < cursor.event_id),
                )
            )
        return stmt.where(
            or_(
                created_at_col > cursor.created_at,
                (created_at_col == cursor.created_at) & (id_col > cursor.event_id),
            )
        )

    if cursor.event_id is None:
        return stmt
    if query.direction == "backward":
        return stmt.where(_sa_col(SessionEvent.id) < cursor.event_id)
    return stmt.where(_sa_col(SessionEvent.id) > cursor.event_id)


def _order_replay_stmt(stmt: Any, direction: str) -> Any:
    if direction == "backward":
        return stmt.order_by(desc(_sa_col(SessionEvent.created_at)), desc(_sa_col(SessionEvent.id)))
    return stmt.order_by(asc(_sa_col(SessionEvent.created_at)), asc(_sa_col(SessionEvent.id)))


async def _session_exists(ctx: ServerContext, session_id: str) -> bool:
    return await _db_async(ctx.client.engine, lambda s: s.get(Session, session_id) is not None)


async def _query_session_replay_events(
    ctx: ServerContext, query: _ReplayQuery
) -> tuple[list[SessionEvent], bool]:
    def _query(s) -> tuple[list[SessionEvent], bool]:
        stmt = select(SessionEvent).where(_sa_col(SessionEvent.session_id) == query.session_id)
        stmt = _apply_replay_cursor(stmt, query)
        stmt = _order_replay_stmt(stmt, query.direction)
        rows = list(s.exec(stmt.limit(query.limit + 1)).all())
        return rows[: query.limit], len(rows) > query.limit

    return await _db_async(ctx.client.engine, _query)


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
    return f"{last.created_at}|{last.id}"


async def _session_replay_response(request: Request, ctx: ServerContext) -> JSONResponse:
    query = _parse_replay_query(request)
    if not await _session_exists(ctx, query.session_id):
        return _err(f"Session {query.session_id!r} not found", status=404)

    rows, has_more = await _query_session_replay_events(ctx, query)
    events = [_to_replay_event(row) for row in rows]
    page = SessionReplayPage(
        events=events,
        next_cursor=_next_replay_cursor(events, has_more),
        has_more=has_more,
    )
    return _ok(page.model_dump(mode="json"))


def _running_agents_sse_response(request: Request, ctx: ServerContext) -> StreamingResponse:
    project_id = _query_param_or_none(request, "project_id")
    return sse_response(_running_agents_events_generator(ctx, project_id=project_id))


def _session_events_sse_response(request: Request, ctx: ServerContext) -> StreamingResponse:
    session_id = request.path_params.get("session_id", "")
    since = _query_param_or_none(request, "since")
    return sse_response(_session_events_sse_generator(ctx, session_id, since=since))


# ---------------------------------------------------------------------------
# SSE generators
# ---------------------------------------------------------------------------


async def _session_events_sse_generator(
    ctx: ServerContext,
    session_id: str,
    *,
    since: str | None,
) -> AsyncIterator[str]:
    """Yield SSE-formatted events for a single session, with heartbeat."""
    engine = ctx.client.engine
    last_id = since
    last_keepalive = time.monotonic()

    while True:
        # Capture last_id in a local default to avoid B023 loop-variable capture.
        def _fetch_new(s, _last_id: str | None = last_id) -> list[SessionEvent]:
            stmt = select(SessionEvent).where(_sa_col(SessionEvent.session_id) == session_id)
            if _last_id is not None:
                stmt = stmt.where(_sa_col(SessionEvent.id) > _last_id)
            stmt = stmt.order_by(asc(_sa_col(SessionEvent.id))).limit(100)
            return list(s.exec(stmt).all())

        try:
            new_events = await _db_async(engine, _fetch_new)
        except Exception:
            logger.debug("session_events SSE: DB poll failed", exc_info=True)
            new_events = []

        for event in new_events:
            last_id = event.id
            data = {
                "type": "SESSION_EVENT",
                "session_id": session_id,
                "event": SessionReplayEvent(
                    id=event.id,
                    session_id=event.session_id,
                    event_type=event.event_type,
                    payload=event.payload or {},
                    created_at=event.created_at,
                ).model_dump(mode="json"),
            }
            yield f"data: {json.dumps(data)}\n\n"

        # Heartbeat
        now = time.monotonic()
        if not new_events and now - last_keepalive >= _SSE_KEEPALIVE_SECONDS:
            last_keepalive = now
            yield ": keepalive\n\n"

        # Stop tailing once the session has ended (drain then exit)
        def _session_done(s) -> bool:
            row = s.get(Session, session_id)
            if row is None:
                return True
            return row.status not in {SessionStatus.PENDING, SessionStatus.RUNNING}

        try:
            done = await _db_async(engine, _session_done)
            if done and not new_events:
                break
        except Exception:
            logger.debug("session_events SSE: session status check failed", exc_info=True)

        await asyncio.sleep(_SESSION_EVENTS_POLL_SECONDS)


async def _running_agents_events_generator(
    ctx: ServerContext,
    *,
    project_id: str | None,
) -> AsyncIterator[str]:
    """Yield SSE diffs for the running-agents list on channel ``agents.running``."""
    known: dict[str, dict[str, Any]] = {}
    last_keepalive = time.monotonic()

    # Initial snapshot
    try:
        resp = await _fetch_agents_response(ctx, project_id)
        for agent in resp.agents:
            d = agent.model_dump(mode="json")
            known[_row_key(d)] = d
    except Exception:
        logger.debug("running_agents SSE: initial snapshot failed", exc_info=True)

    while True:
        await asyncio.sleep(_AGENT_POLL_SECONDS)
        try:
            resp = await _fetch_agents_response(ctx, project_id)
        except Exception:
            logger.debug("running_agents SSE: poll failed", exc_info=True)
            now = time.monotonic()
            if now - last_keepalive >= _SSE_KEEPALIVE_SECONDS:
                last_keepalive = now
                yield ": keepalive\n\n"
            continue

        current: dict[str, dict[str, Any]] = {}
        for agent in resp.agents:
            d = agent.model_dump(mode="json")
            current[_row_key(d)] = d

        joined = set(current) - set(known)
        finished = set(known) - set(current)
        changed: set[str] = set()
        for key in set(current) & set(known):
            if current[key] != known[key]:
                changed.add(key)

        for key in joined:
            data = {"type": "AGENT_JOINED", "channel": "agents.running", "agent": current[key]}
            yield f"data: {json.dumps(data)}\n\n"

        for key in finished:
            data = {"type": "AGENT_FINISHED", "channel": "agents.running", "agent": known[key]}
            yield f"data: {json.dumps(data)}\n\n"

        for key in changed:
            data = {
                "type": "AGENT_STATUS_CHANGE",
                "channel": "agents.running",
                "agent": current[key],
            }
            yield f"data: {json.dumps(data)}\n\n"

        has_changes = bool(joined or finished or changed)
        now = time.monotonic()
        if not has_changes and now - last_keepalive >= _SSE_KEEPALIVE_SECONDS:
            last_keepalive = now
            yield ": keepalive\n\n"

        known = current


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
        project_id = request.query_params.get("project_id") or None
        resp = await _fetch_agents_response(ctx, project_id)
        return _ok(resp.model_dump(mode="json"))

    @mcp.custom_route("/api/v1/agents/running/events", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def running_agents_events(request: Request, *, ctx: ServerContext) -> StreamingResponse:
        forbidden = _require_access(
            ctx, minimum_tier=AccessTier.READONLY, operation="Stream running agents"
        )
        if forbidden is not None:
            return forbidden  # type: ignore[return-value]
        return _running_agents_sse_response(request, ctx)

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

    @mcp.custom_route("/api/v1/sessions/{session_id}/events", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def session_events_sse(request: Request, *, ctx: ServerContext) -> StreamingResponse:
        forbidden = _require_access(
            ctx, minimum_tier=AccessTier.READONLY, operation="Stream session events"
        )
        if forbidden is not None:
            return forbidden  # type: ignore[return-value]
        return _session_events_sse_response(request, ctx)
