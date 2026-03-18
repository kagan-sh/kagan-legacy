"""kagan.server._chat_routes — REST + SSE endpoints for chat session management."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from starlette.responses import StreamingResponse

from kagan.chat.sessions import (
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    list_chat_sessions,
    save_chat_session,
)
from kagan.core import resolve_default_agent_backend
from kagan.core.errors import KaganError
from kagan.server._access import AccessTier, is_access_allowed
from kagan.server._helpers import _err, _ok, _require_access, handle_errors, require_context
from kagan.server.responses import (
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionSummaryResponse,
)

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse, Response

# Track running chat turn tasks for interrupt support
_chat_turn_tasks: dict[str, asyncio.Task[Any]] = {}


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
    update: Any, chunk_queue: asyncio.Queue[dict[str, Any] | None]
) -> None:
    """Bridge a single ACP session_update callback into the SSE queue."""
    from acp.schema import AgentMessageChunk, AgentThoughtChunk, ToolCallProgress, ToolCallStart

    if isinstance(update, AgentMessageChunk):
        content = getattr(update, "content", None)
        if content and getattr(content, "type", None) == "text":
            chunk_text = getattr(content, "text", "") or ""
            if chunk_text:
                await chunk_queue.put({"t": "CHAT_CHUNK", "content": chunk_text})
    elif isinstance(update, AgentThoughtChunk):
        content = getattr(update, "content", None)
        if content and getattr(content, "type", None) == "text":
            chunk_text = getattr(content, "text", "") or ""
            if chunk_text:
                await chunk_queue.put(
                    {"t": "CHAT_CHUNK", "content": chunk_text, "thought": True}
                )
    elif isinstance(update, ToolCallStart):
        title = getattr(update, "title", None) or getattr(update, "name", None) or "tool"
        await chunk_queue.put({"t": "CHAT_TOOL_START", "tool": title})
    elif isinstance(update, ToolCallProgress):
        status = getattr(update, "status", None)
        title = getattr(update, "title", None) or "tool"
        await chunk_queue.put(
            {"t": "CHAT_TOOL_PROGRESS", "tool": title, "status": str(status) if status else None}
        )


async def _run_chat_stream(
    ctx: Any,
    session_id: str,
    session: dict[str, Any],
    text: str,
    backend: str,
    attachments: list[dict[str, str]] | None,
) -> AsyncIterator[str]:
    """Core SSE generator for a single chat turn."""
    from kagan.chat.acp import run_orchestrator_turn
    from kagan.chat.prompt import build_orchestrator_prompt

    try:
        prior_history: list[tuple[str, str]] = [
            (str(item[0]), str(item[1]))
            for item in (session.get("orchestrator_history") or [])
            if isinstance(item, list | tuple) and len(item) == 2
        ]

        history = list(session.get("orchestrator_history") or [])
        is_first_message = len(history) == 0
        history.append(["user", text])
        session["orchestrator_history"] = history
        session["agent_backend"] = backend
        await save_chat_session(ctx.client, session)

        prompt = build_orchestrator_prompt(prior_history, text)
        current_settings = await ctx.client.settings.get()
        project_cwd = await ctx.client.projects.resolve_repo_path(settings=current_settings)

        chunk_queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue()

        async def _run_turn() -> str:
            try:
                result = await run_orchestrator_turn(
                    ctx.client,
                    prompt=prompt,
                    agent_backend=backend,
                    on_update=lambda u: _bridge_acp_update(u, chunk_queue),
                    attachments=attachments,
                    cwd=project_cwd,
                )
                return result or ""
            finally:
                await chunk_queue.put(None)

        turn_task = asyncio.create_task(_run_turn())
        _chat_turn_tasks[session_id] = turn_task

        try:
            while True:
                item = await chunk_queue.get()
                if item is None:
                    break
                yield f"data: {json.dumps(item)}\n\n"
        finally:
            _chat_turn_tasks.pop(session_id, None)
            if not turn_task.done():
                turn_task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await turn_task

        full_response = await turn_task

        if full_response:
            history.append(["assistant", full_response])
            session["orchestrator_history"] = history
            await save_chat_session(ctx.client, session)

        yield f"data: {json.dumps({'t': 'CHAT_DONE', 'full_response': full_response})}\n\n"

        if is_first_message and full_response:
            from kagan.chat._title import ensure_session_title

            try:
                title = await ensure_session_title(
                    ctx.client,
                    session,
                    user_message=text,
                    assistant_reply=full_response,
                    agent_backend=backend,
                )
                if title:
                    evt = {"t": "CHAT_SESSION_UPDATED", "session_id": session_id, "label": title}
                    yield f"data: {json.dumps(evt)}\n\n"
            except Exception:
                logger.debug("Chat title generation failed", exc_info=True)

    except asyncio.CancelledError:
        return
    except Exception as exc:
        logger.exception("Chat stream failed for session {}", session_id)
        yield f"data: {json.dumps({'t': 'CHAT_ERROR', 'error': str(exc)})}\n\n"


def _register_crud_routes(mcp: FastMCP) -> None:
    """Register chat session CRUD endpoints (list, create, get, delete, agents)."""

    @mcp.custom_route("/api/chat/sessions", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_sessions(_request: Request, *, ctx: Any) -> JSONResponse:
        source = _request.query_params.get("source")
        sessions = await list_chat_sessions(ctx.client, source=source)
        return _ok([_session_summary(s) for s in sessions])

    @mcp.custom_route("/api/chat/sessions", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def create_session(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Chat session creation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        body = await request.json()
        if not isinstance(body, dict):
            body = {}
        agent_backend = cast("str | None", body.get("agent_backend"))
        label = cast("str | None", body.get("label"))
        session = await create_chat_session(
            ctx.client,
            source="web",
            label=label,
            agent_backend=agent_backend,
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
        return _ok(_session_to_wire(session))

    @mcp.custom_route("/api/chat/sessions/{session_id}", methods=["DELETE"])
    @require_context(mcp)
    @handle_errors
    async def delete_session(request: Request, *, ctx: Any) -> JSONResponse:
        forbidden = _require_access(
            ctx, operation="Chat session deletion", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return cast("JSONResponse", forbidden)
        session_id = cast("str", request.path_params["session_id"])
        deleted = await delete_chat_session(ctx.client, session_id)
        if not deleted:
            return _err("Session not found", status=404)
        return _ok({"session_id": session_id, "deleted": True})

    @mcp.custom_route("/api/chat/agents", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def list_agents(_request: Request, *, ctx: Any) -> JSONResponse:
        """List available agent backends."""
        from kagan.chat.agents import list_registered_agent_backends

        backends = list_registered_agent_backends()
        settings = await ctx.client.settings.get()
        default = settings.get("default_agent_backend") or "claude-code"
        return _ok({"backends": backends, "default": default})


def _register_stream_routes(mcp: FastMCP) -> None:
    """Register chat streaming and interrupt endpoints."""

    @mcp.custom_route("/api/chat/{session_id}/stream", methods=["POST"])
    @require_context(mcp)
    async def chat_stream(request: Request, *, ctx: Any) -> Response:
        """SSE endpoint — runs one chat turn and streams chunks back."""
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

        session = await get_chat_session(ctx.client, session_id)
        if session is None:
            return _err("Session not found", status=404)

        settings = await ctx.client.settings.get()
        backend = (
            agent_backend or session.get("agent_backend") or resolve_default_agent_backend(settings)
        )

        return StreamingResponse(
            _run_chat_stream(ctx, session_id, session, text, backend, attachments),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )

    @mcp.custom_route("/api/chat/{session_id}/interrupt", methods=["POST"])
    @require_context(mcp)
    @handle_errors
    async def chat_interrupt(request: Request, *, ctx: Any) -> JSONResponse:
        """Interrupt a running chat turn."""
        session_id = cast("str", request.path_params["session_id"])
        running_task = _chat_turn_tasks.get(session_id)
        if running_task is None or running_task.done():
            return _ok({"session_id": session_id, "interrupted": False})

        running_task.cancel()
        _interrupt_errors = (
            asyncio.CancelledError,
            TimeoutError,
            KaganError,
            RuntimeError,
            ConnectionError,
        )
        with contextlib.suppress(*_interrupt_errors):
            await asyncio.wait_for(running_task, timeout=5.0)

        return _ok({"session_id": session_id, "interrupted": True})


def register_chat_routes(mcp: FastMCP) -> None:
    """Register all chat session endpoints."""
    _register_crud_routes(mcp)
    _register_stream_routes(mcp)
