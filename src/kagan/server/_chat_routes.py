"""kagan.server._chat_routes — REST + SSE endpoints for chat session management.

Phase 3 of refactor R1: the SSE turn lifecycle, partial-buffering, 409-guard,
and assistant persistence all live on ``ChatEngine`` (``ctx.client.chat``).
This module is now a thin transport that:

* maps each :class:`ChatEvent` from the engine to its existing SSE wire frame
  (the web/VSCode clients depend on the exact ``"t": "CHAT_..."`` shapes —
  see ``packages/web/src/lib/api/types.ts``);
* keeps a per-server ``_chat_subscribers`` fanout so multiple ``/watch``
  clients can observe the same session in lockstep;
* handles the request/response shape for ``/stream``, ``/watch``,
  ``/turn-status`` and ``/interrupt``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

import acp
from loguru import logger
from starlette.responses import JSONResponse, StreamingResponse

from kagan.cli.chat.sessions import (
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    get_messages_after,
    list_chat_sessions,
)
from kagan.core import resolve_default_agent_backend
from kagan.core.chat import (
    AssistantChunk,
    AssistantMessagePersisted,
    ChatEvent,
    SpawnPerTurnACPFactory,
    ToolCallProgress,
    ToolCallStart,
    TurnCancelled,
    TurnDone,
    TurnError,
    TurnInProgressError,
    TurnStarted,
)
from kagan.server._access import AccessTier, is_access_allowed
from kagan.server._helpers import _err, _ok, _require_access, handle_errors, require_context
from kagan.server.responses import (
    AgentBackendResponse,
    ChatAgentsResponse,
    ChatMessageDetailResponse,
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionSummaryResponse,
    TurnInProgressResponse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import Response

# ---------------------------------------------------------------------------
# /watch fanout
# ---------------------------------------------------------------------------
# The engine produces ChatEvents on a single iterator consumed by the SSE
# producer. ``/watch`` subscribers tap that producer via this fanout — kept at
# transport level (not in the engine) because it is a server-only concern.

_chat_subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)


def _broadcast(session_id: str, event: dict[str, Any]) -> None:
    """Fan out an event to all /watch subscribers; silently drop on overflow."""
    for q in list(_chat_subscribers[session_id]):
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(event)


# ---------------------------------------------------------------------------
# Wire helpers
# ---------------------------------------------------------------------------


def _session_to_wire(session: dict[str, Any]) -> dict[str, Any]:
    """Convert a chat session record to a wire-safe dict."""
    history = session.get("orchestrator_history") or []
    messages: list[ChatMessageResponse] = []
    for item in history:
        if isinstance(item, list | tuple) and len(item) == 2:
            messages.append(ChatMessageResponse(role=str(item[0]), content=str(item[1])))

    return ChatSessionResponse(
        id=session.get("id", ""),
        label=session.get("label", ""),
        source=session.get("source", "repl"),
        agent_backend=session.get("agent_backend"),
        project_id=session.get("project_id"),
        updated_at=session.get("updated_at", ""),
        message_count=len(messages),
        messages=messages,
    ).model_dump(mode="json")


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    """Lightweight summary without full message history."""
    history = session.get("orchestrator_history") or []
    msg_count = sum(1 for item in history if isinstance(item, list | tuple) and len(item) == 2)
    return ChatSessionSummaryResponse(
        id=session.get("id", ""),
        label=session.get("label", ""),
        source=session.get("source", "repl"),
        agent_backend=session.get("agent_backend"),
        project_id=session.get("project_id"),
        updated_at=session.get("updated_at", ""),
        message_count=msg_count,
    ).model_dump(mode="json")


def _parse_attachments(body: dict[str, Any]) -> list[dict[str, str]] | None:
    """Extract and validate attachments from request body."""
    raw = body.get("attachments")
    if not isinstance(raw, list):
        return None
    parsed = [
        {
            "type": str(a.get("type", "")),
            "name": str(a.get("name", "")),
            "mime_type": str(a.get("mime_type", "")),
            "data": str(a.get("data", "")),
        }
        for a in raw
        if isinstance(a, dict) and a.get("data")
    ]
    return parsed or None


# ---------------------------------------------------------------------------
# ChatEvent -> SSE frame mapping
# ---------------------------------------------------------------------------


def _chat_event_to_sse_frame(event: ChatEvent) -> dict[str, Any] | None:
    """Translate one ``ChatEvent`` to its existing SSE wire shape.

    The web client (``packages/web/src/lib/api/types.ts``) and VS Code
    extension consume these by string type tag. DO NOT change the shapes here
    without coordinating a wire-drift bump.

    Returns ``None`` for events that have no SSE analogue today — e.g.
    ``UsageUpdate``, ``PermissionRequest`` (handled by ACP-level routes).
    """
    if isinstance(event, AssistantChunk):
        frame: dict[str, Any] = {"t": "CHAT_CHUNK", "content": event.text}
        if event.thought:
            frame["thought"] = True
        return frame
    if isinstance(event, ToolCallStart):
        return {"t": "CHAT_TOOL_START", "tool": event.title}
    if isinstance(event, ToolCallProgress):
        return {"t": "CHAT_TOOL_PROGRESS", "tool": event.tool_id, "status": event.status}
    if isinstance(event, AssistantMessagePersisted):
        return {
            "t": "CHAT_ASSISTANT_MESSAGE",
            "message_id": event.message_id,
            "content": event.content,
            "terminated": event.terminated,
        }
    if isinstance(event, TurnDone):
        return {"t": "CHAT_DONE", "full_response": event.full_response}
    if isinstance(event, TurnError):
        return {"t": "CHAT_ERROR", "error": event.message}
    if isinstance(event, TurnCancelled):
        return {"t": "CHAT_TURN_TERMINATED", "reason": event.reason}
    # TurnStarted is emitted as CHAT_TURN_STARTED at a different point in the
    # producer (it carries by_source from the request), so we ignore it here.
    if isinstance(event, TurnStarted):
        return None
    return None


# ---------------------------------------------------------------------------
# SSE producer
# ---------------------------------------------------------------------------


def _emit(frame: dict[str, Any]) -> str:
    return f"data: {json.dumps(frame)}\n\n"


async def _sse_stream(
    ctx: Any,
    session_id: str,
    session: dict[str, Any],
    text: str,
    backend: str,
    attachments: list[dict[str, str]] | None,
) -> AsyncIterator[str]:
    """Drive a single chat turn through ``ChatEngine`` and yield SSE frames.

    Caller (``chat_stream``) has already verified the session exists and that
    no turn is in flight (the latter via ``ChatEngine.stream_assistant``'s
    own claim, surfaced as ``TurnInProgressError`` on first iteration).
    """
    engine = ctx.client.chat

    # Update session metadata BEFORE persisting the user message. The legacy
    # ``save_chat_session`` shim used ``upsert_with_history`` which DELETEs every
    # ``ChatMessage`` row for the session and re-inserts only the snapshot —
    # calling it after ``push_user`` would wipe the just-persisted user row.
    # Use the metadata-only ``cs.update`` path instead. (Greptile P1 fix.)
    session["agent_backend"] = backend
    await ctx.client.chat_sessions.update(session_id, agent_backend=backend)

    # Persist user message and broadcast (transport owns user-row emission;
    # see the note above ``UserMessagePersisted`` in core.chat.events).
    user_msg = await engine.push_user(session_id, text, attachments=attachments)
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
        "by_source": session.get("source"),
    }
    _broadcast(session_id, started_event)
    yield _emit(started_event)

    # Build a per-request factory that captures cwd + attachments.
    settings = await ctx.client.settings.get()
    project_cwd = await ctx.client.projects.resolve_repo_path(settings=settings)
    factory = SpawnPerTurnACPFactory(
        client=ctx.client,
        default_agent_backend=backend,
        cwd=project_cwd,
        attachments=attachments,
    )

    # Build the prompt blocks. Today the spawn-per-turn factory only honours
    # the user text (it reconstructs system + wrapper internally via
    # ``run_orchestrator_turn``); we forward the prior conversation here so
    # the orchestrator sees full context.
    from kagan.cli.chat.prompt import build_orchestrator_prompt

    prior_history: list[tuple[str, str]] = [
        (str(item[0]), str(item[1]))
        for item in (session.get("orchestrator_history") or [])
        if isinstance(item, list | tuple) and len(item) == 2
    ]
    prompt_text = build_orchestrator_prompt(prior_history, text)

    try:
        async for event in engine.stream_assistant(
            session_id,
            prompt_blocks=[acp.text_block(prompt_text)],
            agent_backend=backend,
            acp_factory=factory,
        ):
            frame = _chat_event_to_sse_frame(event)
            if frame is None:
                continue
            _broadcast(session_id, frame)
            yield _emit(frame)

            # After a successful turn, broadcast a session summary refresh so
            # /watch subscribers can update sidebar metadata.
            if frame.get("t") == "CHAT_DONE":
                refreshed = await get_chat_session(ctx.client, session_id)
                if refreshed is not None:
                    update = {
                        "t": "CHAT_SESSION_UPDATED",
                        "session": _session_summary(refreshed),
                    }
                    _broadcast(session_id, update)
    except TurnInProgressError:
        # Surfaced to the route caller via the wrapper below — no body here.
        raise
    except (asyncio.CancelledError, GeneratorExit, ConnectionError):
        logger.debug("Client disconnected during chat stream for session {}", session_id)
        return
    except Exception as exc:
        logger.exception("Chat stream failed for session {}", session_id)
        err = {"t": "CHAT_ERROR", "error": str(exc)}
        _broadcast(session_id, err)
        yield _emit(err)


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def _teardown_session_state(ctx: Any, session_id: str) -> None:
    """Clear per-session transport state and ask the engine to detach."""
    _chat_subscribers.pop(session_id, None)
    engine = getattr(ctx.client, "chat", None)
    if engine is not None:
        # Fire-and-forget — detach is best-effort cleanup at delete time.
        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(engine.detach(session_id))


def _register_crud_routes(mcp: FastMCP) -> None:
    """Register chat session CRUD endpoints (list, create, get, delete, agents)."""

    @mcp.custom_route("/api/chat/sessions", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_sessions(_request: Request, *, ctx: Any) -> JSONResponse:
        source = _request.query_params.get("source")
        project_id = _request.query_params.get("project_id")
        sessions = await list_chat_sessions(ctx.client, source=source, project_id=project_id)
        return _ok([_session_summary(s) for s in sessions])

    @mcp.custom_route("/api/chat/sessions", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def create_session(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Chat session creation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
        agent_backend = cast("str | None", body.get("agent_backend"))
        label = cast("str | None", body.get("label"))
        source = str(body.get("source") or "web").strip() or "web"
        project_id = cast("str | None", body.get("project_id")) or ctx.client.active_project_id
        session = await create_chat_session(
            ctx.client,
            source=source,
            label=label,
            agent_backend=agent_backend,
            project_id=project_id,
        )
        return _ok(_session_to_wire(session))

    @mcp.custom_route("/api/chat/sessions/{session_id}", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_session(request: Request, *, ctx: Any) -> JSONResponse:
        session_id = cast("str", request.path_params["session_id"])
        session = await get_chat_session(ctx.client, session_id)
        if session is None:
            return _err("Session not found", status=404)
        etag = f'"{session.get("updated_at", "")}"'
        if request.headers.get("If-None-Match") == etag:
            return JSONResponse(None, status_code=304)
        resp = _ok(_session_to_wire(session))
        resp.headers["ETag"] = etag
        resp.headers["Cache-Control"] = "no-cache"
        return resp

    @mcp.custom_route("/api/chat/sessions/{session_id}/messages", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_session_messages(request: Request, *, ctx: Any) -> JSONResponse:
        """Cursor-tail endpoint for reconnecting /watch clients.

        Returns messages with id > after_id so clients can catch up on messages
        missed during a /watch disconnect. Defaults to after_id=0 (all messages).
        """
        session_id = cast("str", request.path_params["session_id"])
        try:
            after_id = int(request.query_params.get("after_id", "0"))
        except (ValueError, TypeError):
            return _err("after_id must be an integer", status=400)

        session = await get_chat_session(ctx.client, session_id)
        if session is None:
            return _err("Session not found", status=404)

        messages = await get_messages_after(ctx.client, session_id, after_id=after_id)
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
    async def update_session(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Chat session update", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        session_id = cast("str", request.path_params["session_id"])
        session = await get_chat_session(ctx.client, session_id)
        if session is None:
            return _err("Session not found", status=404)
        body = await request.json()
        if not isinstance(body, dict):
            return _err("Request body must be a JSON object", status=400)
        agent_backend = body.get("agent_backend")
        if agent_backend is not None:
            # Metadata-only patch — never round-trip through the legacy
            # ``save_chat_session`` shim, which DELETEs every ``ChatMessage``
            # for the session via ``upsert_with_history``. (Greptile P1 fix.)
            await ctx.client.chat_sessions.update(session_id, agent_backend=agent_backend)
            # Re-fetch so the response carries the new ``updated_at`` rather
            # than the pre-update snapshot. (Greptile P2 fix.)
            refreshed = await get_chat_session(ctx.client, session_id)
            if refreshed is not None:
                session = refreshed
        return _ok(_session_to_wire(session))

    @mcp.custom_route("/api/chat/sessions/{session_id}", methods=["DELETE"])
    @require_context(mcp)
    @handle_errors
    async def delete_session(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Chat session deletion", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        session_id = cast("str", request.path_params["session_id"])
        deleted = await delete_chat_session(ctx.client, session_id)
        if not deleted:
            return _err("Session not found", status=404)
        _teardown_session_state(ctx, session_id)
        return _ok({"session_id": session_id, "deleted": True})

    @mcp.custom_route("/api/chat/agents", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_agents(_request: Request, *, ctx: Any) -> JSONResponse:
        """List available agent backends."""
        from kagan.cli.chat.agents import list_backends_with_availability

        backends = [
            AgentBackendResponse.model_validate(backend)
            for backend in list_backends_with_availability()
        ]
        settings = await ctx.client.settings.get()
        default = resolve_default_agent_backend(settings)
        return _ok(ChatAgentsResponse(backends=backends, default=default).model_dump(mode="json"))


def _register_stream_routes(mcp: FastMCP) -> None:
    """Register chat streaming, watch, and interrupt endpoints."""

    @mcp.custom_route("/api/chat/{session_id}/stream", methods=["POST"])
    @require_context(mcp)
    async def chat_stream(request: Request, *, ctx: Any) -> Response:
        """SSE endpoint — runs one chat turn and streams chunks back.

        Returns 409 if a turn is already in progress for this session.
        Chunks are simultaneously broadcast to all /watch subscribers.
        """
        session_id = cast("str", request.path_params["session_id"])
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

        # Resolve session + backend up-front (mirrors the legacy
        # ``_claim_turn_slot`` body).
        session = await get_chat_session(ctx.client, session_id)
        if session is None:
            return _err("Session not found", status=404)
        settings = await ctx.client.settings.get()
        backend = (
            agent_backend or session.get("agent_backend") or resolve_default_agent_backend(settings)
        )

        # Pre-flight 409: cheap turn_status read keeps the early-error path
        # fast (no need to start the SSE response just to tear it down).
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
    async def chat_watch(request: Request, *, ctx: Any) -> Response:
        """SSE endpoint — subscribe to all events for a session (broadcast channel).

        Multiple clients can connect simultaneously. Each gets every event in
        lockstep. On disconnect the subscriber is removed from the registry.
        """
        session_id = cast("str", request.path_params["session_id"])
        if not is_access_allowed(ctx, AccessTier.STANDARD):
            return _err("Insufficient access tier for chat", status=403)

        session = await get_chat_session(ctx.client, session_id)
        if session is None:
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
    async def turn_status(request: Request, *, ctx: Any) -> JSONResponse:
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

    @mcp.custom_route("/api/chat/{session_id}/interrupt", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def chat_interrupt(request: Request, *, ctx: Any) -> JSONResponse:
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
