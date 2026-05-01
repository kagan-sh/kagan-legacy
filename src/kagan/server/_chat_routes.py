"""kagan.server._chat_routes — REST + SSE endpoints for chat session management."""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from starlette.responses import JSONResponse, StreamingResponse

from kagan.cli.chat.sessions import (
    append_chat_message,
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    get_messages_after,
    list_chat_sessions,
    save_chat_session,
)
from kagan.core import resolve_default_agent_backend
from kagan.core.errors import KaganError
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
# In-process pub/sub state
# ---------------------------------------------------------------------------

# Track running chat turn tasks for interrupt support.
# Values may be asyncio.Task (active turn) or asyncio.Future (sentinel while
# the route handler awaits before the task is created — prevents a concurrent
# POST from slipping past the 409 guard during those suspension points).
_chat_turn_tasks: dict[str, asyncio.Future[Any]] = {}

# Per-session subscriber queues — broadcast to all connected /watch clients
_chat_subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = defaultdict(list)

# Accumulated partial response chunks for the in-flight turn
_chat_partial_buffers: dict[str, list[str]] = defaultdict(list)

# When each in-flight turn started
_chat_turn_started_at: dict[str, datetime] = {}


def _broadcast(session_id: str, event: dict[str, Any]) -> None:
    """Fan out an event to all /watch subscribers; silently drop on overflow."""
    for q in list(_chat_subscribers[session_id]):
        with contextlib.suppress(asyncio.QueueFull):
            q.put_nowait(event)


async def _claim_turn_slot(
    client: Any,
    session_id: str,
    agent_backend: str | None,
) -> tuple[dict[str, Any], str] | JSONResponse:
    """Atomically claim a turn slot and return (session, backend) or an error response.

    Registers a sentinel Future into ``_chat_turn_tasks`` *before* the first
    ``await`` so that a concurrent POST cannot slip past the 409 guard while
    this coroutine is suspended.  The sentinel is replaced by the real Task
    when ``_run_chat_stream`` starts; error paths pop it explicitly.
    """
    running = _chat_turn_tasks.get(session_id)
    if running is not None and not running.done():
        partial_chars = sum(len(c) for c in _chat_partial_buffers.get(session_id, []))
        started_at = _chat_turn_started_at.get(session_id)
        return JSONResponse(
            TurnInProgressResponse(
                running_since=started_at.isoformat() if started_at else None,
                partial_chars=partial_chars,
            ).model_dump(mode="json"),
            status_code=409,
        )

    sentinel: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
    _chat_turn_tasks[session_id] = sentinel
    try:
        session = await get_chat_session(client, session_id)
        if session is None:
            _chat_turn_tasks.pop(session_id, None)
            return _err("Session not found", status=404)
        settings = await client.settings.get()
        backend = (
            agent_backend or session.get("agent_backend") or resolve_default_agent_backend(settings)
        )
        return (session, backend)
    except BaseException:
        _chat_turn_tasks.pop(session_id, None)
        raise


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


async def _bridge_acp_update(
    update: Any,
    chunk_queue: asyncio.Queue[dict[str, Any] | None],
    session_id: str,
) -> None:
    """Bridge a single ACP session_update callback into the SSE queue and broadcast."""
    from acp.schema import AgentMessageChunk, AgentThoughtChunk, ToolCallProgress, ToolCallStart

    event: dict[str, Any] | None = None

    if isinstance(update, AgentMessageChunk):
        content = getattr(update, "content", None)
        if content and getattr(content, "type", None) == "text":
            chunk_text = getattr(content, "text", "") or ""
            if chunk_text:
                event = {"t": "CHAT_CHUNK", "content": chunk_text}
    elif isinstance(update, AgentThoughtChunk):
        content = getattr(update, "content", None)
        if content and getattr(content, "type", None) == "text":
            chunk_text = getattr(content, "text", "") or ""
            if chunk_text:
                event = {"t": "CHAT_CHUNK", "content": chunk_text, "thought": True}
    elif isinstance(update, ToolCallStart):
        title = getattr(update, "title", None) or getattr(update, "name", None) or "tool"
        event = {"t": "CHAT_TOOL_START", "tool": title}
    elif isinstance(update, ToolCallProgress):
        status = getattr(update, "status", None)
        title = getattr(update, "title", None) or "tool"
        event = {
            "t": "CHAT_TOOL_PROGRESS",
            "tool": title,
            "status": str(status) if status else None,
        }

    if event is not None:
        # Accumulate text chunks into the partial buffer
        if event.get("t") == "CHAT_CHUNK" and not event.get("thought"):
            _chat_partial_buffers[session_id].append(event.get("content", ""))
        await chunk_queue.put(event)
        _broadcast(session_id, event)


async def _run_chat_stream(
    ctx: Any,
    session_id: str,
    session: dict[str, Any],
    text: str,
    backend: str,
    attachments: list[dict[str, str]] | None,
) -> AsyncIterator[str]:
    """Core SSE generator for a single chat turn.

    The turn task runs independently of the SSE delivery — if the client
    disconnects mid-stream the agent keeps working, persists its response,
    and the frontend can poll ``/turn-status`` to reconnect.
    Chunks are also broadcast to all /watch subscribers in real time.
    """
    from kagan.cli.chat.acp import run_orchestrator_turn
    from kagan.cli.chat.prompt import build_orchestrator_prompt

    try:
        prior_history: list[tuple[str, str]] = [
            (str(item[0]), str(item[1]))
            for item in (session.get("orchestrator_history") or [])
            if isinstance(item, list | tuple) and len(item) == 2
        ]

        is_first_message = len(prior_history) == 0

        prompt = build_orchestrator_prompt(prior_history, text)
        current_settings = await ctx.client.settings.get()
        project_cwd = await ctx.client.projects.resolve_repo_path(settings=current_settings)

        chunk_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        # Persist user message and broadcast
        user_msg = await append_chat_message(ctx.client, session_id, "user", text)
        user_msg_id = getattr(user_msg, "id", None)
        session["agent_backend"] = backend
        await save_chat_session(ctx.client, session)

        _broadcast(
            session_id,
            {"t": "CHAT_USER_MESSAGE", "message_id": user_msg_id, "content": text},
        )

        started_at = datetime.now(UTC)
        _chat_turn_started_at[session_id] = started_at
        _broadcast(
            session_id,
            {
                "t": "CHAT_TURN_STARTED",
                "at": started_at.isoformat(),
                "by_source": session.get("source"),
            },
        )

        async def _run_turn_and_persist() -> str:
            """Execute the orchestrator turn and persist the result.

            Persistence happens here (not in the SSE generator) so that the
            assistant response is saved even when the client disconnects.
            On CancelledError: persist the partial buffer with terminated=True.
            """
            full_response = ""
            try:
                result = await run_orchestrator_turn(
                    ctx.client,
                    prompt=prompt,
                    agent_backend=backend,
                    on_update=lambda u: _bridge_acp_update(u, chunk_queue, session_id),
                    attachments=attachments,
                    cwd=project_cwd,
                )
                full_response = result or ""
            except asyncio.CancelledError:
                # Persist partial buffer if non-empty, then re-raise
                partial = "".join(_chat_partial_buffers.get(session_id, []))
                if partial:
                    try:
                        assistant_msg = await append_chat_message(
                            ctx.client,
                            session_id,
                            "assistant",
                            partial,
                            terminated=True,
                        )
                        assistant_msg_id = getattr(assistant_msg, "id", None)
                        _broadcast(
                            session_id,
                            {
                                "t": "CHAT_ASSISTANT_MESSAGE",
                                "message_id": assistant_msg_id,
                                "content": partial,
                                "terminated": True,
                            },
                        )
                    except Exception:
                        logger.debug("Failed to persist partial for session {}", session_id)
                raise
            except Exception:
                logger.exception("Chat turn failed for session {}", session_id)
                raise
            finally:
                await chunk_queue.put(None)  # Signal stream end
                _chat_turn_tasks.pop(session_id, None)
                _chat_turn_started_at.pop(session_id, None)
                _chat_partial_buffers.pop(session_id, None)

            # Persist completed assistant response
            if full_response:
                assistant_msg = await append_chat_message(
                    ctx.client, session_id, "assistant", full_response
                )
                assistant_msg_id = getattr(assistant_msg, "id", None)
                _broadcast(
                    session_id,
                    {
                        "t": "CHAT_ASSISTANT_MESSAGE",
                        "message_id": assistant_msg_id,
                        "content": full_response,
                        "terminated": False,
                    },
                )

            # Generate title if first message
            if is_first_message and full_response:
                await _maybe_generate_title(ctx, session, session_id, text, full_response, backend)

            # Broadcast session updated
            updated_session = await get_chat_session(ctx.client, session_id)
            if updated_session is not None:
                _broadcast(
                    session_id,
                    {"t": "CHAT_SESSION_UPDATED", "session": _session_summary(updated_session)},
                )

            return full_response

        turn_task = asyncio.create_task(_run_turn_and_persist())
        _chat_turn_tasks[session_id] = turn_task

        try:
            while True:
                item = await chunk_queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"

            # Stream completed normally — await result for CHAT_DONE
            full_response = await turn_task
            done_event = {"t": "CHAT_DONE", "full_response": full_response}
            _broadcast(session_id, done_event)
            yield f"data: {json.dumps(done_event)}\n\n"

        except (asyncio.CancelledError, GeneratorExit, ConnectionError):
            logger.debug("Client disconnected during chat stream for session {}", session_id)
            return

    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.exception("Chat stream failed for session {}", session_id)
        yield f"data: {json.dumps({'t': 'CHAT_ERROR', 'error': str(exc)})}\n\n"


async def _maybe_generate_title(
    ctx: Any,
    session: dict[str, Any],
    session_id: str,
    text: str,
    full_response: str,
    backend: str,
) -> None:
    """Best-effort title generation for first-message sessions."""
    from kagan.cli.chat._title import ensure_session_title

    try:
        await ensure_session_title(
            ctx.client,
            session,
            user_message=text,
            assistant_reply=full_response,
            agent_backend=backend,
        )
    except Exception:
        logger.debug("Chat title generation failed for session {}", session_id)


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def _teardown_session_state(session_id: str) -> None:
    """Cancel any in-flight turn and remove all in-process state for a session."""
    running_turn = _chat_turn_tasks.pop(session_id, None)
    if running_turn is not None and not running_turn.done():
        running_turn.cancel()
    _chat_subscribers.pop(session_id, None)
    _chat_partial_buffers.pop(session_id, None)
    _chat_turn_started_at.pop(session_id, None)


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
            session["agent_backend"] = agent_backend
        await save_chat_session(ctx.client, session)
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
        _teardown_session_state(session_id)
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


def _idle_interrupt_response(session_id: str) -> JSONResponse:
    return _ok(
        {
            "session_id": session_id,
            "interrupted": False,
            "partial_persisted": False,
            "partial_chars": 0,
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


async def _interrupt_running_turn(
    session_id: str,
    running_task: asyncio.Future[Any],
    *,
    reason: str,
) -> JSONResponse:
    partial_chars = sum(len(c) for c in _chat_partial_buffers.get(session_id, []))

    running_task.cancel()
    interrupt_errors = (
        asyncio.CancelledError,
        TimeoutError,
        KaganError,
        RuntimeError,
        ConnectionError,
    )
    with contextlib.suppress(*interrupt_errors):
        await asyncio.wait_for(running_task, timeout=5.0)

    _broadcast(session_id, {"t": "CHAT_TURN_TERMINATED", "reason": reason})
    return _ok(
        {
            "session_id": session_id,
            "interrupted": True,
            "partial_persisted": partial_chars > 0,
            "partial_chars": partial_chars,
        }
    )


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

        claimed = await _claim_turn_slot(ctx.client, session_id, agent_backend)
        if isinstance(claimed, JSONResponse):
            return claimed
        session, backend = claimed

        return StreamingResponse(
            _run_chat_stream(ctx, session_id, session, text, backend, attachments),
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
        task = _chat_turn_tasks.get(session_id)
        partial_chars = sum(len(c) for c in _chat_partial_buffers.get(session_id, []))
        started_at = _chat_turn_started_at.get(session_id)
        return _ok(
            {
                "active": task is not None and not task.done(),
                "partial_chars": partial_chars,
                "running_since": started_at.isoformat() if started_at else None,
            }
        )

    @mcp.custom_route("/api/chat/{session_id}/interrupt", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def chat_interrupt(request: Request, *, ctx: Any) -> JSONResponse:
        """Interrupt a running chat turn.

        Request body: {"reason": "user" | "takeover"} (default "user").
        Returns: {interrupted, partial_persisted, partial_chars}.
        The partial buffer is persisted as a terminated assistant message if non-empty;
        CHAT_TURN_TERMINATED is broadcast to /watch subscribers.
        """
        session_id = cast("str", request.path_params["session_id"])
        running_task = _chat_turn_tasks.get(session_id)
        if running_task is None or running_task.done():
            return _idle_interrupt_response(session_id)
        return await _interrupt_running_turn(
            session_id,
            running_task,
            reason=await _interrupt_reason(request),
        )


def register_chat_routes(mcp: FastMCP) -> None:
    """Register all chat session endpoints."""
    _register_crud_routes(mcp)
    _register_stream_routes(mcp)
