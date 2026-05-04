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

from kagan.core import (
    Attachment,
    AttachmentBody,
    ChatSessionCreateRequest,
    ChatSessionPatchRequest,
    resolve_default_agent_backend,
)
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
    chat_session_to_legacy_dict,
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


async def _load_session_dict(client: Any, session_id: str) -> dict[str, Any] | None:
    """Fetch a session + its messages and return the legacy dict shape.

    Wraps ``client.chat_sessions.get_with_history`` for transport-layer code
    that consumes the dict-shaped wire mappers (``_session_to_wire`` /
    ``_session_summary``). Returns ``None`` if the session is missing.
    """
    pair = await client.chat_sessions.get_with_history(session_id)
    if pair is None:
        return None
    return chat_session_to_legacy_dict(*pair)


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


def _parse_attachments(body: dict[str, Any]) -> list[Attachment] | None:
    """Extract and validate attachments from the request body.

    Validates against :class:`kagan.core._io.sessions._AttachmentBody` so
    callers receive typed :class:`Attachment` instances instead of hand-rolled
    dicts. Entries without a ``data`` field are filtered out by the model
    (``data`` is required; model_validate will raise for missing required fields
    and they are skipped via the list comprehension guard).

    Returns ``None`` when the validated list is empty.
    """
    # Pre-filter entries with no data before model_validate to avoid
    # raising ValidationError for structurally invalid items. Only
    # well-formed dicts with a truthy 'data' key are forwarded.
    raw = body.get("attachments")
    if not isinstance(raw, list):
        return None
    candidates = [a for a in raw if isinstance(a, dict) and a.get("data")]
    if not candidates:
        return None
    parsed = AttachmentBody.model_validate({"attachments": candidates}).attachments
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
    attachments: list[Attachment] | None,
) -> AsyncIterator[str]:
    """Drive a single chat turn through ``ChatEngine`` and yield SSE frames.

    Caller (``chat_stream``) has already verified the session exists and that
    no turn is in flight (the latter via ``ChatEngine.stream_assistant``'s
    own claim, surfaced as ``TurnInProgressError`` on first iteration).
    """
    engine = ctx.client.chat

    # Claim the engine slot BEFORE any side effects (push_user, broadcast,
    # session metadata update). The claim is synchronous so it is atomic
    # w.r.t. the asyncio scheduler; without it, a concurrent /stream request
    # on the same session could slip past the pre-flight ``turn_status``
    # check, persist a user row, broadcast CHAT_USER_MESSAGE +
    # CHAT_TURN_STARTED, then trip TurnInProgressError inside
    # ``stream_assistant`` — leaving an orphan user row in DB and /watch
    # subscribers stuck without a recovery frame. (Greptile P1.)
    try:
        engine.try_claim_turn(session_id)
    except TurnInProgressError:
        err = {"t": "CHAT_ERROR", "error": "Turn already in progress for this session"}
        _broadcast(session_id, err)
        yield _emit(err)
        return

    # Update session metadata BEFORE persisting the user message. The legacy
    # ``save_chat_session`` shim used ``upsert_with_history`` which DELETEs every
    # ``ChatMessage`` row for the session and re-inserts only the snapshot —
    # calling it after ``push_user`` would wipe the just-persisted user row.
    # Use the metadata-only ``cs.update`` path instead. (Greptile P1 fix.)
    session["agent_backend"] = backend
    # The claimed slot must be released if ANYTHING between the claim and
    # entering ``stream_assistant`` fails — including settings/cwd resolution,
    # client disconnect at a yield, or push_user. Once ``stream_assistant``
    # is entered it owns teardown via its own try/finally; ``detach`` is
    # idempotent so double-teardown is safe.
    stream_entered = False
    turn_done = False
    try:
        await ctx.client.chat_sessions.update(session_id, agent_backend=backend)

        # Serialise typed Attachment models back to dicts for the downstream
        # functions (SpawnPerTurnACPFactory, engine.push_user) which still
        # consume list[dict[str, str]]. The boundary-typed list is used for
        # internal clarity; the wire shape is unchanged.
        attachment_dicts: list[dict[str, str]] | None = (
            [a.model_dump() for a in attachments] if attachments else None
        )

        # Persist user message and broadcast (transport owns user-row emission;
        # see the note above ``UserMessagePersisted`` in core.chat.events).
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
            attachments=attachment_dicts,
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

        stream_entered = True
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
            if frame.get("t") == "CHAT_DONE":
                turn_done = True
    except TurnInProgressError:
        # Surfaced to the route caller via the wrapper below — no body here.
        raise
    except (asyncio.CancelledError, GeneratorExit, ConnectionError):
        logger.debug("Client disconnected during chat stream for session {}", session_id)
        # Starlette throws CancelledError at the active yield when the client
        # drops; the inner stream_assistant generator is abandoned and its
        # ``finally: _teardown`` only fires when Python's async-gen finalizer
        # eventually calls aclose(). Until then the sentinel stays in
        # engine._states and every subsequent /stream 409s. detach() is
        # idempotent so this is safe even when stream_assistant cleaned up
        # itself (Greptile P1).
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

    # Post-turn metadata refresh OUTSIDE the error handler. A DB hiccup here
    # must not emit a spurious CHAT_ERROR after the successful CHAT_DONE that
    # already shipped — clients toggling spinners / turn counts would see
    # success-then-error for the same turn (Greptile P1).
    if turn_done:
        try:
            refreshed_pair = await ctx.client.chat_sessions.get_with_history(session_id)
        except Exception:
            logger.exception("Post-turn session refresh failed for {}", session_id)
        else:
            if refreshed_pair is not None:
                refreshed = chat_session_to_legacy_dict(*refreshed_pair)
                _broadcast(
                    session_id,
                    {"t": "CHAT_SESSION_UPDATED", "session": _session_summary(refreshed)},
                )


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


async def _patch_session(request: Request, *, ctx: Any) -> JSONResponse:
    """PATCH handler — metadata-only update for a chat session."""
    forbidden = _require_access(
        ctx, operation="Chat session update", minimum_tier=AccessTier.STANDARD
    )
    if forbidden is not None:
        return forbidden
    session_id = cast("str", request.path_params["session_id"])
    session = await _load_session_dict(ctx.client, session_id)
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
        refreshed = await _load_session_dict(ctx.client, session_id)
        if refreshed is not None:
            session = refreshed
    return _ok(_session_to_wire(session))


def _register_crud_routes(mcp: FastMCP) -> None:
    """Register chat session CRUD endpoints (list, create, get, delete, agents)."""

    @mcp.custom_route("/api/chat/sessions", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_sessions(_request: Request, *, ctx: Any) -> JSONResponse:
        source = _request.query_params.get("source")
        project_id = _request.query_params.get("project_id")
        pairs = await ctx.client.chat_sessions.list_with_history(
            source=source, project_id=project_id
        )
        sessions = [chat_session_to_legacy_dict(row, msgs) for row, msgs in pairs]
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
        raw = await request.json()
        body = ChatSessionCreateRequest.model_validate(raw if isinstance(raw, dict) else {})
        project_id = body.project_id or ctx.client.active_project_id
        row = await ctx.client.chat_sessions.create(
            source=body.source,
            label=body.label,
            agent_backend=body.agent_backend,
            project_id=project_id,
        )
        session = chat_session_to_legacy_dict(row, [])
        return _ok(_session_to_wire(session))

    @mcp.custom_route("/api/chat/sessions/{session_id}", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def get_session(request: Request, *, ctx: Any) -> JSONResponse:
        session_id = cast("str", request.path_params["session_id"])
        session = await _load_session_dict(ctx.client, session_id)
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

        session = await _load_session_dict(ctx.client, session_id)
        if session is None:
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
    async def update_session(request: Request, *, ctx: Any) -> JSONResponse:
        return await _patch_session(request, ctx=ctx)

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
        deleted = await ctx.client.chat_sessions.delete(session_id)
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
        session = await _load_session_dict(ctx.client, session_id)
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

        session = await _load_session_dict(ctx.client, session_id)
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
