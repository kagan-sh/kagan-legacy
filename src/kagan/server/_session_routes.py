"""Canonical unified session routes (Agent C — Wave 3).

GET  /api/v1/sessions                    → list all sessions
POST /api/v1/sessions                    → create a new session
GET  /api/v1/sessions/:id/replay         → replay session events
POST /api/v1/sessions/:id/message        → send a message
POST /api/v1/sessions/:id/stop           → stop a running session
POST /api/v1/sessions/:id/close          → close a session
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import acp
from loguru import logger
from starlette.responses import JSONResponse, Response, StreamingResponse

from kagan.core.chat import TurnInProgressError, make_spawn_per_turn_acp_factory
from kagan.server._access import AccessTier, is_access_allowed
from kagan.server._chat_routes import (
    _broadcast,
    _chat_event_to_sse_frame,
    _emit,
    _load_session_view,
    _parse_attachments,
    _teardown_session_state,
)
from kagan.server._helpers import (
    _err,
    _ok,
    _require_access,
    handle_errors,
    parse_body,
    require_context,
)
from kagan.server.responses import (
    CreateSessionRequest,
    SessionCapabilitiesResponse,
    SessionItemResponse,
    SessionReplayEvent,
    SessionReplayPage,
    SessionsResponse,
    TurnInProgressResponse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request

    from kagan.core.models import SessionEvent
    from kagan.server.mcp.server import ServerContext

_MAX_REPLAY_LIMIT = 1000
_DEFAULT_REPLAY_LIMIT = 200


# ---------------------------------------------------------------------------
# Unified session ID helpers
# ---------------------------------------------------------------------------


def _parse_unified_session_id(session_id: str) -> tuple[str, str]:
    """Parse a unified session ID into (kind, raw_id).

    Kind is one of: ``orch``, ``gen``, ``task``.
    """
    if session_id.startswith("orch:"):
        return "orch", session_id[5:]
    if session_id.startswith("gen:"):
        return "gen", session_id[4:]
    if session_id.startswith("task:"):
        return "task", session_id[5:]
    raise ValueError(f"Invalid session ID format: {session_id!r}")


# ---------------------------------------------------------------------------
# Replay helpers (reused from _agent_routes)
# ---------------------------------------------------------------------------


class _ReplayCursor:
    def __init__(self, created_at: datetime | None, event_id: str | None) -> None:
        self.created_at = created_at
        self.event_id = event_id


class _ReplayQuery:
    def __init__(
        self,
        session_id: str,
        cursor: _ReplayCursor,
        direction: str,
        limit: int,
    ) -> None:
        self.session_id = session_id
        self.cursor = cursor
        self.direction = direction
        self.limit = limit


def _parse_replay_cursor(cursor: str | None) -> _ReplayCursor:
    if cursor is None:
        return _ReplayCursor(created_at=None, event_id=None)
    if "|" not in cursor:
        return _ReplayCursor(created_at=None, event_id=cursor)
    ts_part, id_part = cursor.split("|", 1)
    try:
        return _ReplayCursor(
            created_at=_normalize_replay_timestamp(datetime.fromisoformat(ts_part)),
            event_id=id_part,
        )
    except ValueError:
        return _ReplayCursor(created_at=None, event_id=cursor)


def _normalize_replay_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value
    return value.astimezone(UTC).replace(tzinfo=None)


def _format_replay_timestamp(value: datetime | str) -> str:
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        normalized = _normalize_replay_timestamp(parsed)
    else:
        normalized = _normalize_replay_timestamp(value)
    return f"{normalized.isoformat()}Z"


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


async def _resolve_replay_cursor(ctx: ServerContext, query: _ReplayQuery) -> _ReplayCursor:
    cursor = query.cursor
    if cursor.created_at is not None or cursor.event_id is None:
        return cursor
    created_at = await _session_event_created_at(
        ctx.client.engine,
        session_id=query.session_id,
        event_id=cursor.event_id,
    )
    if created_at is None:
        return _ReplayCursor(created_at=None, event_id=None)
    return _ReplayCursor(
        created_at=_normalize_replay_timestamp(created_at),
        event_id=cursor.event_id,
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
            after_ts=_format_replay_timestamp(cursor.created_at),
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
            before=_format_replay_timestamp(cursor.created_at),
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


async def _session_event_created_at(
    engine: Any, *, session_id: str, event_id: str
) -> datetime | None:
    from sqlmodel import select

    from kagan.core._db_helpers import _db_async, _sa_col
    from kagan.core.models import SessionEvent

    def _query(s) -> datetime | None:
        stmt = select(SessionEvent).where(
            _sa_col(SessionEvent.session_id) == session_id,
            _sa_col(SessionEvent.id) == event_id,
        )
        event = s.exec(stmt).first()
        return event.created_at if event is not None else None

    return await _db_async(engine, _query)


def _to_replay_event(row: SessionEvent) -> SessionReplayEvent:
    return SessionReplayEvent(
        id=row.id,
        session_id=row.session_id,
        event_type=row.event_type,
        payload=row.payload,
        created_at=row.created_at.isoformat() if row.created_at else "",
    )


def _next_replay_cursor(events: list[SessionReplayEvent], has_more: bool) -> str | None:
    if not has_more or not events:
        return None
    last = events[-1]
    return f"{last.created_at}|{last.id}"


async def _query_chat_replay(
    ctx: ServerContext, session_id: str, query: _ReplayQuery
) -> tuple[list[SessionReplayEvent], bool]:
    messages = await ctx.client.chat_sessions.history(session_id)
    events: list[SessionReplayEvent] = []
    for msg in messages:
        events.append(
            SessionReplayEvent(
                id=str(msg.id) if msg.id is not None else "",
                session_id=session_id,
                event_type="chat_message",
                payload={
                    "role": msg.role,
                    "content": msg.content,
                    "terminated_at_user_request": msg.terminated_at_user_request,
                },
                created_at=msg.created_at.isoformat() if msg.created_at else "",
            )
        )
    return events, False


# ---------------------------------------------------------------------------
# Message streaming helpers
# ---------------------------------------------------------------------------


async def _resolve_message_request(
    request: Request, ctx: ServerContext, session_id: str
) -> Response | tuple[Any, str, str, list[Any] | None]:
    if not is_access_allowed(ctx, AccessTier.STANDARD):
        return _err("Insufficient access tier for chat", status=403)
    body = await request.json()
    if not isinstance(body, dict):
        return _err("Request body must be a JSON object", status=400)
    text = cast("str", body.get("text", "")).strip()
    if not text:
        return _err("text is required", status=400)
    agent_backend = cast("str | None", body.get("agent_backend"))
    attachments = _parse_attachments(body)

    session = await _load_session_view(ctx.client, session_id)
    if session is None:
        return _err("Session not found", status=404)
    settings = await ctx.client.settings.get()
    if agent_backend or session.agent_backend:
        backend = agent_backend or session.agent_backend
    else:
        from kagan.cli.chat.agents import resolve_available_chat_backend

        backend = resolve_available_chat_backend(settings)

    status = ctx.client.chat.turn_status(session_id)
    if status.active:
        return JSONResponse(
            TurnInProgressResponse(
                running_since=(
                    status.started_at.isoformat() if status.started_at is not None else None
                ),
                partial_chars=status.partial_chars,
            ).model_dump(mode="json"),
            status_code=409,
        )

    return session, text, cast("str", backend), attachments


async def _message_sse_stream(
    ctx: ServerContext,
    session_id: str,
    session: Any,
    text: str,
    backend: str,
    attachments: list[Any] | None,
    *,
    is_orchestrator: bool,
) -> AsyncIterator[str]:
    engine = ctx.client.chat
    try:
        engine.try_claim_turn(session_id)
    except TurnInProgressError:
        err = {"t": "CHAT_ERROR", "error": "Turn already in progress for this session"}
        _broadcast(session_id, err)
        yield _emit(err)
        return

    stream_entered = False
    turn_done = False
    try:
        await ctx.client.chat_sessions.update(session_id, agent_backend=backend)

        attachment_dicts: list[dict[str, str]] | None = (
            [a.model_dump() for a in attachments] if attachments else None
        )

        user_msg = await engine.push_user(session_id, text, attachments=attachment_dicts)
        user_msg_id = getattr(user_msg, "id", None)

        user_event = {
            "t": "CHAT_USER_MESSAGE",
            "message_id": user_msg_id,
            "content": text,
        }
        _broadcast(session_id, user_event)
        yield _emit(user_event)

        started_event = {
            "t": "CHAT_TURN_STARTED",
            "at": datetime.now(UTC).isoformat(),
            "by_source": session.source,
        }
        _broadcast(session_id, started_event)
        yield _emit(started_event)

        settings = await ctx.client.settings.get()
        project_cwd = await ctx.client.projects.resolve_repo_path(settings=settings)
        factory = make_spawn_per_turn_acp_factory(
            client=ctx.client,
            default_agent_backend=backend,
            cwd=project_cwd,
            attachments=attachment_dicts,
        )

        if is_orchestrator:
            from kagan.cli.chat.prompt import build_orchestrator_prompt

            prior_history: list[tuple[str, str]] = [
                (str(item[0]), str(item[1]))
                for item in session.orchestrator_history
                if isinstance(item, list | tuple) and len(item) == 2
            ]
            prompt_text = build_orchestrator_prompt(prior_history, text)
            prompt_blocks = [acp.text_block(prompt_text)]
        else:
            prompt_blocks = [acp.text_block(text)]

        stream_entered = True
        async for event in engine.stream_assistant(
            session_id,
            prompt_blocks=prompt_blocks,
            agent_backend=backend,
            acp_factory=factory,
        ):
            frame = _chat_event_to_sse_frame(event)
            if frame is None:
                continue
            _broadcast(session_id, frame)
            yield _emit(frame)
            if frame.get("t") == "CHAT_DONE":
                turn_done = True
    except TurnInProgressError:
        raise
    except (asyncio.CancelledError, GeneratorExit, ConnectionError):
        logger.debug("Client disconnected during chat stream for session {}", session_id)
        await engine.detach(session_id)
        return
    except Exception as exc:
        logger.exception("Chat stream failed for session {}", session_id)
        err = {"t": "CHAT_ERROR", "error": str(exc)}
        _broadcast(session_id, err)
        yield _emit(err)
    finally:
        if not stream_entered:
            await engine.detach(session_id)

    if turn_done:
        try:
            refreshed_pair = await ctx.client.chat_sessions.get_with_history(session_id)
        except Exception:
            logger.exception("Post-turn session refresh failed for {}", session_id)
        else:
            if refreshed_pair is not None:
                from kagan.core.chat.sessions import chat_session_to_view

                refreshed = chat_session_to_view(*refreshed_pair)
                _broadcast(
                    session_id,
                    {
                        "t": "CHAT_SESSION_UPDATED",
                        "session": {
                            "id": refreshed.id,
                            "label": refreshed.label,
                            "source": refreshed.source,
                            "agent_backend": refreshed.agent_backend,
                            "project_id": refreshed.project_id,
                            "updated_at": refreshed.updated_at,
                            "message_count": len(refreshed.orchestrator_history),
                        },
                    },
                )


# ---------------------------------------------------------------------------
# Route body helpers (extracted to keep register_session_routes simple)
# ---------------------------------------------------------------------------


async def _do_list_sessions(ctx: ServerContext) -> JSONResponse:
    forbidden = _require_access(ctx, minimum_tier=AccessTier.READONLY, operation="List sessions")
    if forbidden is not None:
        return forbidden

    bound_project_id = getattr(ctx, "bound_project_id", None)
    items = await ctx.client.list_session_items(project_id=bound_project_id)
    sessions = [SessionItemResponse.model_validate(item).model_dump(mode="json") for item in items]
    return _ok(SessionsResponse(sessions=sessions).model_dump(mode="json"))


async def _do_create_session(request: Request, ctx: ServerContext) -> JSONResponse:
    forbidden = _require_access(ctx, minimum_tier=AccessTier.STANDARD, operation="Create session")
    if forbidden is not None:
        return forbidden

    body = await parse_body(request, CreateSessionRequest)
    bound_project_id = getattr(ctx, "bound_project_id", None)

    if body.type == "orchestrator":
        row = await ctx.client.chat_sessions.create(
            source="web",
            session_type="orchestrator",
            label=body.title,
            agent_backend=body.backend,
            project_id=bound_project_id,
        )
        prefix = "orch"
    elif body.type == "general":
        backend = body.backend
        if backend is None:
            from kagan.cli.chat.agents import resolve_available_chat_backend

            settings = await ctx.client.settings.get()
            backend = resolve_available_chat_backend(settings)
        row = await ctx.client.chat_sessions.create_general(
            backend=backend,
            label=body.title,
            project_id=bound_project_id,
        )
        prefix = "gen"
    else:
        return _err(f"Unknown session type: {body.type}", status=400)

    capabilities = SessionCapabilitiesResponse(
        can_chat=True,
        can_stream=True,
        can_replay=False,
        can_stop=True,
        can_close=True,
        has_kagan_tools=(body.type == "orchestrator"),
    )

    updated_at = ""
    if row.updated_at is not None:
        updated_at = (
            row.updated_at.isoformat()
            if isinstance(row.updated_at, datetime)
            else str(row.updated_at)
        )

    item = SessionItemResponse(
        id=f"{prefix}:{row.id}",
        type=body.type,
        role=None,
        status="idle",
        title=row.label,
        backend=row.agent_backend,
        project_id=row.project_id,
        task_id=None,
        session_id=None,
        chat_session_id=row.id,
        updated_at=updated_at,
        capabilities=capabilities,
    )
    return _ok(item.model_dump(mode="json"))


async def _do_session_replay(request: Request, ctx: ServerContext) -> JSONResponse:
    forbidden = _require_access(
        ctx, minimum_tier=AccessTier.READONLY, operation="Replay session events"
    )
    if forbidden is not None:
        return forbidden

    session_id = cast("str", request.path_params["session_id"])
    try:
        kind, raw_id = _parse_unified_session_id(session_id)
    except ValueError as exc:
        return _err(str(exc), status=400)

    if kind == "task":
        query = _parse_replay_query(request)
        query = _ReplayQuery(
            session_id=raw_id,
            cursor=query.cursor,
            direction=query.direction,
            limit=query.limit,
        )
        task_id, project_id = await ctx.client.tasks.sessions.resolve_binding(raw_id)
        bound_project_id = getattr(ctx, "bound_project_id", None)
        if task_id is None or (bound_project_id is not None and project_id != bound_project_id):
            return _err(f"Session {session_id!r} not found", status=404)

        rows, has_more = await _query_session_replay_events(ctx, query)
        events = [_to_replay_event(row) for row in rows]
        page = SessionReplayPage(
            events=events,
            next_cursor=_next_replay_cursor(events, has_more),
            has_more=has_more,
        )
        return _ok(page.model_dump(mode="json"))

    query = _parse_replay_query(request)
    session = await _load_session_view(ctx.client, raw_id)
    if session is None:
        return _err("Session not found", status=404)

    events, has_more = await _query_chat_replay(ctx, raw_id, query)
    page = SessionReplayPage(
        events=events,
        next_cursor=_next_replay_cursor(events, has_more),
        has_more=has_more,
    )
    return _ok(page.model_dump(mode="json"))


async def _do_session_stop(request: Request, ctx: ServerContext) -> Response:
    forbidden = _require_access(ctx, minimum_tier=AccessTier.STANDARD, operation="Stop session")
    if forbidden is not None:
        return forbidden

    session_id = cast("str", request.path_params["session_id"])
    try:
        kind, raw_id = _parse_unified_session_id(session_id)
    except ValueError as exc:
        return _err(str(exc), status=400)

    if kind == "task":
        task_id, project_id = await ctx.client.tasks.sessions.resolve_binding(raw_id)
        bound_project_id = getattr(ctx, "bound_project_id", None)
        if task_id is None or (bound_project_id is not None and project_id != bound_project_id):
            return _err(f"Session {session_id!r} not found", status=404)
        await ctx.client.tasks.cancel(task_id)
    else:
        await ctx.client.chat.cancel(raw_id)

    return Response(status_code=204)


async def _do_session_close(request: Request, ctx: ServerContext) -> Response:
    forbidden = _require_access(ctx, minimum_tier=AccessTier.STANDARD, operation="Close session")
    if forbidden is not None:
        return forbidden

    session_id = cast("str", request.path_params["session_id"])
    try:
        kind, raw_id = _parse_unified_session_id(session_id)
    except ValueError as exc:
        return _err(str(exc), status=400)

    if kind == "task":
        return _err("Task sessions cannot be closed, only stopped", status=400)

    deleted = await ctx.client.chat_sessions.delete(raw_id)
    if not deleted:
        return _err("Session not found", status=404)

    _teardown_session_state(ctx, raw_id)
    return Response(status_code=204)


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_session_routes(mcp: FastMCP) -> None:
    """Register all canonical unified session endpoints on *mcp*."""

    @mcp.custom_route("/api/v1/sessions", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_sessions(_request: Request, *, ctx: ServerContext) -> JSONResponse:
        return await _do_list_sessions(ctx)

    @mcp.custom_route("/api/v1/sessions", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def create_session(request: Request, *, ctx: ServerContext) -> JSONResponse:
        return await _do_create_session(request, ctx)

    @mcp.custom_route("/api/v1/sessions/{session_id}/replay", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def session_replay(request: Request, *, ctx: ServerContext) -> JSONResponse:
        return await _do_session_replay(request, ctx)

    @mcp.custom_route("/api/v1/sessions/{session_id}/message", methods=["POST"])
    @require_context(mcp)
    async def session_message(request: Request, *, ctx: ServerContext) -> Response:
        forbidden = _require_access(
            ctx, minimum_tier=AccessTier.STANDARD, operation="Send session message"
        )
        if forbidden is not None:
            return forbidden

        session_id = cast("str", request.path_params["session_id"])
        try:
            kind, raw_id = _parse_unified_session_id(session_id)
        except ValueError as exc:
            return _err(str(exc), status=400)

        if kind == "task":
            return _err("Task sessions do not support direct messaging", status=400)

        resolved = await _resolve_message_request(request, ctx, raw_id)
        if isinstance(resolved, Response):
            return resolved
        session, text, backend, attachments = resolved

        return StreamingResponse(
            _message_sse_stream(
                ctx, raw_id, session, text, backend, attachments, is_orchestrator=(kind == "orch")
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @mcp.custom_route("/api/v1/sessions/{session_id}/stop", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def session_stop(request: Request, *, ctx: ServerContext) -> Response:
        return await _do_session_stop(request, ctx)

    @mcp.custom_route("/api/v1/sessions/{session_id}/close", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def session_close(request: Request, *, ctx: ServerContext) -> Response:
        return await _do_session_close(request, ctx)
