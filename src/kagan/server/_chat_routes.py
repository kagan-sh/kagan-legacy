"""kagan.server._chat_routes — REST endpoints for chat session management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from kagan.chat.sessions import (
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    list_chat_sessions,
)
from kagan.server._access import AccessTier
from kagan.server._helpers import _err, _ok, _require_access, handle_errors, require_context
from kagan.server.responses import (
    ChatMessageResponse,
    ChatSessionResponse,
    ChatSessionSummaryResponse,
)

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request
    from starlette.responses import JSONResponse


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


def register_chat_routes(mcp: FastMCP) -> None:
    """Register chat session CRUD endpoints."""

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
        return _ok(
            {
                "backends": backends,
                "default": default,
            }
        )
