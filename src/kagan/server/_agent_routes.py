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
from datetime import datetime
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlmodel import asc, desc, or_, select

from kagan.core._db_helpers import _db_async, _sa_col
from kagan.core._sessions_query import list_running_agents
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, SessionEvent
from kagan.server._access import AccessTier
from kagan.server._helpers import (
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
        project_id = request.query_params.get("project_id") or None
        return sse_response(_running_agents_events_generator(ctx, project_id=project_id))

    @mcp.custom_route("/api/v1/sessions/{session_id}/replay", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def session_replay(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, minimum_tier=AccessTier.READONLY, operation="Replay session events"
        )
        if forbidden is not None:
            return forbidden

        session_id = request.path_params.get("session_id", "")
        params = request.query_params
        cursor = params.get("cursor") or None
        direction = params.get("direction", "forward")

        try:
            limit = int(params.get("limit", _DEFAULT_REPLAY_LIMIT))
            limit = max(1, min(limit, _MAX_REPLAY_LIMIT))
        except (ValueError, TypeError):
            limit = _DEFAULT_REPLAY_LIMIT

        engine = ctx.client.engine

        session_exists = await _db_async(engine, lambda s: s.get(Session, session_id) is not None)
        if not session_exists:
            from kagan.server._helpers import _err

            return _err(f"Session {session_id!r} not found", status=404)

        # Parse composite cursor: "<created_at_iso>|<id>" or legacy bare "<id>".
        # The "|" separator avoids ambiguity with colons in ISO timestamps.
        # Using (created_at, id) guarantees stable pagination even when random
        # hex IDs don't sort in insertion order.
        cursor_ts: datetime | None = None
        cursor_id: str | None = None
        if cursor is not None:
            if "|" in cursor:
                ts_part, id_part = cursor.split("|", 1)
                try:
                    cursor_ts = datetime.fromisoformat(ts_part)
                    cursor_id = id_part
                except ValueError:
                    cursor_id = cursor  # fallback: treat as bare id
            else:
                cursor_id = cursor

        def _query(s) -> tuple[list[SessionEvent], bool]:
            stmt = select(SessionEvent).where(_sa_col(SessionEvent.session_id) == session_id)
            if direction == "backward":
                if cursor_ts is not None and cursor_id is not None:
                    stmt = stmt.where(
                        or_(
                            _sa_col(SessionEvent.created_at) < cursor_ts,
                            (
                                (_sa_col(SessionEvent.created_at) == cursor_ts)
                                & (_sa_col(SessionEvent.id) < cursor_id)
                            ),
                        )
                    )
                elif cursor_id is not None:
                    stmt = stmt.where(_sa_col(SessionEvent.id) < cursor_id)
                stmt = stmt.order_by(
                    desc(_sa_col(SessionEvent.created_at)), desc(_sa_col(SessionEvent.id))
                )
            else:
                if cursor_ts is not None and cursor_id is not None:
                    stmt = stmt.where(
                        or_(
                            _sa_col(SessionEvent.created_at) > cursor_ts,
                            (
                                (_sa_col(SessionEvent.created_at) == cursor_ts)
                                & (_sa_col(SessionEvent.id) > cursor_id)
                            ),
                        )
                    )
                elif cursor_id is not None:
                    stmt = stmt.where(_sa_col(SessionEvent.id) > cursor_id)
                stmt = stmt.order_by(
                    asc(_sa_col(SessionEvent.created_at)), asc(_sa_col(SessionEvent.id))
                )

            rows = list(s.exec(stmt.limit(limit + 1)).all())
            has_more = len(rows) > limit
            return rows[:limit], has_more

        rows, has_more = await _db_async(engine, _query)

        events = [
            SessionReplayEvent(
                id=row.id,
                session_id=row.session_id,
                event_type=row.event_type,
                payload=row.payload or {},
                created_at=row.created_at,
            )
            for row in rows
        ]

        next_cursor: str | None = None
        if has_more and events:
            last = events[-1]
            # Composite cursor: "<created_at_iso>|<id>" — isoformat already a str in response model.
            # "|" avoids ambiguity with colons in ISO timestamps.
            next_cursor = f"{last.created_at}|{last.id}"
        page = SessionReplayPage(events=events, next_cursor=next_cursor, has_more=has_more)
        return _ok(page.model_dump(mode="json"))

    @mcp.custom_route("/api/v1/sessions/{session_id}/events", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def session_events_sse(request: Request, *, ctx: ServerContext) -> StreamingResponse:
        forbidden = _require_access(
            ctx, minimum_tier=AccessTier.READONLY, operation="Stream session events"
        )
        if forbidden is not None:
            return forbidden  # type: ignore[return-value]
        session_id = request.path_params.get("session_id", "")
        since = request.query_params.get("since") or None
        return sse_response(_session_events_sse_generator(ctx, session_id, since=since))
