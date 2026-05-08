"""kagan.server._chat_routes — REST + SSE endpoints for chat session management.

Phase 3 of refactor R1: the SSE turn lifecycle, partial-buffering, 409-guard,
and assistant persistence all live on ``ChatEngine`` (``ctx.client.chat``).
This module is now a thin transport that handles the request/response shape
for ``/stream``, ``/watch``, ``/turn-status`` and ``/interrupt``.

SSE fanout, wire-frame helpers, and parameter resolution live in ``_sse_fanout.py``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from starlette.responses import JSONResponse, Response, StreamingResponse

from kagan.core import Attachment, ChatSessionCreateRequest, ChatSessionPatchRequest
from kagan.core.chat import ChatSessionView, chat_session_to_view
from kagan.server._access import AccessTier, is_access_allowed
from kagan.server._helpers import _err, _ok, _require_access, handle_errors, require_context
from kagan.server._sse_fanout import (
    _broadcast,
    _chat_event_to_sse_frame,
    _chat_subscribers,
    _emit,
    _load_session_view,
    _session_summary,
    _teardown_session_state,
    resolve_sse_parameters,
)
from kagan.server.responses import (
    AgentBackendResponse,
    ChatAgentsResponse,
    ChatMessageDetailResponse,
    ChatMessageResponse,
    ChatSessionResponse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request

    from kagan.server.mcp.server import ServerContext


# ---------------------------------------------------------------------------
# Chat session REST wire helper (private to this module)
# ---------------------------------------------------------------------------


def _session_to_wire(session: ChatSessionView) -> dict[str, Any]:
    """Serialize a typed session view to the REST wire shape."""
    messages: list[ChatMessageResponse] = [
        ChatMessageResponse(role=str(item[0]), content=str(item[1]))
        for item in session.orchestrator_history
        if isinstance(item, list | tuple) and len(item) == 2
    ]

    return ChatSessionResponse(
        id=session.id,
        label=session.label,
        source=session.source,
        agent_backend=session.agent_backend,
        project_id=session.project_id,
        updated_at=session.updated_at,
        message_count=len(messages),
        messages=messages,
    ).model_dump(mode="json")


async def _patch_session(request: Request, *, ctx: ServerContext) -> JSONResponse:
    """PATCH handler — metadata-only update for a chat session."""
    forbidden = _require_access(
        ctx, operation="Chat session update", minimum_tier=AccessTier.STANDARD
    )
    if forbidden is not None:
        return forbidden
    session_id = cast("str", request.path_params["session_id"])
    session = await _load_session_view(ctx.client, session_id)
    if session is None:
        return _err("Session not found", status=404)
    raw = await request.json()
    if not isinstance(raw, dict):
        return _err("Request body must be a JSON object", status=400)
    body = ChatSessionPatchRequest.model_validate(raw)
    if body.agent_backend is not None:
        # Metadata-only patch — never round-trip through ``upsert_with_history``,
        # which DELETEs every ``ChatMessage`` for the session. (Greptile P1 fix.)
        await ctx.client.chat_sessions.update(session_id, agent_backend=body.agent_backend)
        # Re-fetch so the response carries the new ``updated_at`` rather than
        # the pre-update snapshot. (Greptile P2 fix.)
        refreshed = await _load_session_view(ctx.client, session_id)
        if refreshed is not None:
            session = refreshed
    return _ok(_session_to_wire(session))


def _register_crud_routes(mcp: FastMCP) -> None:
    """Register chat session CRUD endpoints (list, create, get, delete, agents)."""

    @mcp.custom_route("/api/chat/sessions", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_sessions(_request: Request, *, ctx: ServerContext) -> JSONResponse:
        source = _request.query_params.get("source")
        project_id = _request.query_params.get("project_id")
        pairs = await ctx.client.chat_sessions.list_with_history(
            source=source, project_id=project_id
        )
        sessions = [chat_session_to_view(row, msgs) for row, msgs in pairs]
        return _ok([_session_summary(s) for s in sessions])

    @mcp.custom_route("/api/chat/sessions", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def create_session(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Chat session creation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        raw = await request.json()
        body = ChatSessionCreateRequest.model_validate(raw if isinstance(raw, dict) else {})
        project_id = body.project_id or ctx.client.active_project_id
        row = await ctx.client.chat_sessions.create(
            source=body.source,
            label=body.label,
            agent_backend=body.agent_backend,
            project_id=project_id,
        )
        session = chat_session_to_view(row, [])
        return _ok(_session_to_wire(session))

    @mcp.custom_route("/api/chat/sessions/{session_id}", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_session(request: Request, *, ctx: ServerContext) -> Response:
        session_id = cast("str", request.path_params["session_id"])
        session = await _load_session_view(ctx.client, session_id)
        if session is None:
            return _err("Session not found", status=404)
        etag = f'"{session.updated_at}"'
        if request.headers.get("If-None-Match") == etag:
            return Response(status_code=304, headers={"ETag": etag, "Cache-Control": "no-cache"})
        resp = _ok(_session_to_wire(session))
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @mcp.custom_route("/api/chat/sessions/{session_id}/messages", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_session_messages(request: Request, *, ctx: ServerContext) -> JSONResponse:
        """Cursor-tail endpoint for reconnecting /watch clients.

        Returns messages with id > after_id so clients can catch up on messages
        missed during a /watch disconnect. Defaults to after_id=0 (all messages).
        """
        session_id = cast("str", request.path_params["session_id"])
        try:
            after_id = int(request.query_params.get("after_id", "0"))
        except (ValueError, TypeError):
            return _err("after_id must be an integer", status=400)

        # Existence check only — messages are fetched separately below.
        session_exists = await _load_session_view(ctx.client, session_id)
        if session_exists is None:
            return _err("Session not found", status=404)

        messages = await ctx.client.chat_sessions.messages_after(session_id, after_id=after_id)
        wire = [
            ChatMessageDetailResponse(
                id=m.id or 0,
                session_id=m.session_id,
                role=m.role,
                content=m.content,
                terminated_at_user_request=m.terminated_at_user_request,
                created_at=m.created_at.isoformat() if m.created_at else "",
            ).model_dump(mode="json")
            for m in messages
        ]
        return _ok(wire)

    @mcp.custom_route("/api/chat/sessions/{session_id}", methods=["PATCH"])
    @require_context(mcp)
    @handle_errors
    async def update_session(request: Request, *, ctx: ServerContext) -> JSONResponse:
        return await _patch_session(request, ctx=ctx)

    @mcp.custom_route("/api/chat/sessions/{session_id}", methods=["DELETE"])
    @require_context(mcp)
    @handle_errors
    async def delete_session(request: Request, *, ctx: ServerContext) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Chat session deletion", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        session_id = cast("str", request.path_params["session_id"])
        deleted = await ctx.client.chat_sessions.delete(session_id)
        if not deleted:
            return _err("Session not found", status=404)
        _teardown_session_state(ctx, session_id)
        return _ok({"session_id": session_id, "deleted": True})

    @mcp.custom_route("/api/chat/agents", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_agents(_request: Request, *, ctx: ServerContext) -> JSONResponse:
        """List available agent backends."""
        from kagan.cli.chat.agents import (
            list_backends_with_availability,
            resolve_available_chat_backend,
        )

        backend_availability = list_backends_with_availability()
        backends = [
            AgentBackendResponse.model_validate(backend) for backend in backend_availability
        ]
        settings = await ctx.client.settings.get()
        default = resolve_available_chat_backend(settings, backends=backend_availability)
        return _ok(ChatAgentsResponse(backends=backends, default=default).model_dump(mode="json"))


async def _sse_stream(
    ctx: ServerContext,
    session_id: str,
    session: ChatSessionView,
    text: str,
    backend: str,
    attachments: list[Attachment] | None,
) -> AsyncIterator[str]:
    """Drive a single orchestrator chat turn and yield SSE frames.

    Thin wrapper around :func:`_unified_sse_stream` with ``is_orchestrator=True``.
    Caller (``chat_stream``) has already verified the session exists and that
    no turn is in flight.
    """
    from kagan.server._sse_stream import _unified_sse_stream

    async for chunk in _unified_sse_stream(
        ctx,
        session_id,
        session,
        text,
        backend,
        attachments,
        is_orchestrator=True,
        broadcast=_broadcast,
        emit=_emit,
        chat_event_to_sse_frame=_chat_event_to_sse_frame,
        session_summary=_session_summary,
    ):
        yield chunk


def _register_stream_routes(mcp: FastMCP) -> None:
    """Register chat streaming, watch, and interrupt endpoints."""

    @mcp.custom_route("/api/chat/{session_id}/stream", methods=["POST"])
    @require_context(mcp)
    async def chat_stream(request: Request, *, ctx: ServerContext) -> Response:
        """SSE endpoint — runs one chat turn and streams chunks back.

        Returns 409 if a turn is already in progress for this session.
        Chunks are simultaneously broadcast to all /watch subscribers.
        """
        session_id = cast("str", request.path_params["session_id"])
        resolved = await resolve_sse_parameters(request, ctx, session_id)
        if isinstance(resolved, JSONResponse):
            return resolved
        session, text, backend, attachments = resolved
        return StreamingResponse(
            _sse_stream(ctx, session_id, session, text, backend, attachments),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @mcp.custom_route("/api/chat/sessions/{session_id}/watch", methods=["GET"])
    @require_context(mcp)
    async def chat_watch(request: Request, *, ctx: ServerContext) -> Response:
        """SSE endpoint — subscribe to all events for a session (broadcast channel).

        Multiple clients can connect simultaneously. Each gets every event in
        lockstep. On disconnect the subscriber is removed from the registry.
        """
        session_id = cast("str", request.path_params["session_id"])
        if not is_access_allowed(ctx, AccessTier.STANDARD):
            return _err("Insufficient access tier for chat", status=403)

        session_view = await _load_session_view(ctx.client, session_id)
        if session_view is None:
            return _err("Session not found", status=404)

        async def _event_stream() -> AsyncIterator[str]:
            q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=128)
            shutdown_event = getattr(ctx, "shutdown_event", None)
            last_keepalive = datetime.now(UTC)
            _chat_subscribers[session_id].append(q)
            try:
                while shutdown_event is None or not shutdown_event.is_set():
                    timeout = 0.5 if shutdown_event is not None else 25.0
                    try:
                        event = await asyncio.wait_for(q.get(), timeout=timeout)
                        yield f"data: {json.dumps(event)}\n\n"
                    except TimeoutError:
                        if shutdown_event is not None and shutdown_event.is_set():
                            break
                        now = datetime.now(UTC)
                        if (now - last_keepalive).total_seconds() >= 25.0:
                            last_keepalive = now
                            yield ": keepalive\n\n"
            except (GeneratorExit, asyncio.CancelledError, ConnectionError):
                pass
            finally:
                with contextlib.suppress(ValueError):
                    _chat_subscribers[session_id].remove(q)

        return StreamingResponse(
            _event_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @mcp.custom_route("/api/chat/{session_id}/turn-status", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def turn_status(request: Request, *, ctx: ServerContext) -> JSONResponse:
        """Check whether a chat turn is still running for the given session."""
        session_id = cast("str", request.path_params["session_id"])
        status = ctx.client.chat.turn_status(session_id)
        return _ok(
            {
                "active": status.active,
                "partial_chars": status.partial_chars,
                "running_since": (
                    status.started_at.isoformat() if status.started_at is not None else None
                ),
            }
        )

    @mcp.custom_route("/api/chat/sessions/{session_id}/permission/{future_id}", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def chat_resolve_permission(request: Request, *, ctx: ServerContext) -> Response:
        """Resolve a pending permission request from the agent.

        Body: ``{"outcome": "allow_once"|...|"deny", "feedback": str|null}``
        """
        session_id = cast("str", request.path_params["session_id"])
        future_id = cast("str", request.path_params["future_id"])
        if not is_access_allowed(ctx, AccessTier.STANDARD):
            return _err("Insufficient access tier", status=403)
        try:
            body = await request.json()
        except json.JSONDecodeError:
            return _err("Request body must be valid JSON", status=400)
        if not isinstance(body, dict):
            return _err("Request body must be a JSON object", status=400)
        outcome = str(body.get("outcome", "deny"))
        feedback = body.get("feedback") or None
        await ctx.client.chat.resolve_permission(
            session_id, future_id, outcome=outcome, feedback=feedback
        )
        return Response(status_code=204)

    @mcp.custom_route("/api/chat/{session_id}/interrupt", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def chat_interrupt(request: Request, *, ctx: ServerContext) -> JSONResponse:
        """Interrupt a running chat turn.

        Request body: {"reason": "user" | "takeover"} (default "user").
        Returns: {interrupted, partial_persisted, partial_chars}.
        The partial buffer is persisted as a terminated assistant message if non-empty
        (handled inside ``ChatEngine``); CHAT_TURN_TERMINATED is broadcast to /watch.
        """
        session_id = cast("str", request.path_params["session_id"])
        reason = await _interrupt_reason(request)
        result = await ctx.client.chat.cancel(session_id, reason=reason)
        if not result.was_running:
            # No active /stream consumer to relay the engine's TurnCancelled
            # event, so emit a transport-level CHAT_TURN_TERMINATED here so
            # any /watch-only subscribers still see the cancel. When a turn
            # *is* running, the engine emits TurnCancelled which
            # ``_sse_stream`` already broadcasts — broadcasting again here
            # would deliver the same frame twice. (Greptile P2.)
            _broadcast(session_id, {"t": "CHAT_TURN_TERMINATED", "reason": reason})
            return _ok(
                {
                    "session_id": session_id,
                    "interrupted": False,
                    "partial_persisted": False,
                    "partial_chars": 0,
                }
            )
        return _ok(
            {
                "session_id": session_id,
                "interrupted": True,
                "partial_persisted": result.partial_chars > 0,
                "partial_chars": result.partial_chars,
            }
        )


async def _interrupt_reason(request: Request) -> str:
    try:
        body = await request.json()
    except Exception:
        return "user"
    if not isinstance(body, dict):
        return "user"
    reason = body.get("reason", "user")
    return str(reason) if reason in {"user", "takeover"} else "user"


def register_chat_routes(mcp: FastMCP) -> None:
    """Register all chat session endpoints."""
    _register_crud_routes(mcp)
    _register_stream_routes(mcp)
