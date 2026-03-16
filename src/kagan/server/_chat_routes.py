"""kagan.server._chat_routes — REST endpoints for chat session management."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, cast

from starlette.responses import JSONResponse

from kagan.chat.sessions import (
    create_chat_session,
    delete_chat_session,
    get_chat_session,
    list_chat_sessions,
)
from kagan.mcp._policy import AccessTier
from kagan.mcp.server import get_server_context
from kagan.server._access import http_forbidden, is_access_allowed
from kagan.wire.envelopes import WireEnvelope

if TYPE_CHECKING:
    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request


def _ok(data: Any) -> JSONResponse:
    return JSONResponse(WireEnvelope(ok=True, data=data).model_dump())


def _err(msg: str, status: int = 400) -> JSONResponse:
    return JSONResponse(WireEnvelope(ok=False, error=msg).model_dump(), status_code=status)


def _require_access(
    ctx: Any,
    *,
    operation: str,
    minimum_tier: AccessTier,
) -> JSONResponse | None:
    if is_access_allowed(ctx, minimum_tier):
        return None
    return http_forbidden(operation=operation, minimum_tier=minimum_tier)


def _session_to_wire(session: dict[str, Any]) -> dict[str, Any]:
    """Convert a chat session record to a wire-safe dict."""
    history = session.get("orchestrator_history") or []
    messages: list[dict[str, str]] = []
    for item in history:
        if isinstance(item, list | tuple) and len(item) == 2:
            messages.append({"role": str(item[0]), "content": str(item[1])})

    return {
        "id": session.get("id", ""),
        "label": session.get("label", ""),
        "source": session.get("source", "repl"),
        "agent_backend": session.get("agent_backend"),
        "updated_at": session.get("updated_at", ""),
        "message_count": len(messages),
        "messages": messages,
    }


def _session_summary(session: dict[str, Any]) -> dict[str, Any]:
    """Lightweight summary without full message history."""
    history = session.get("orchestrator_history") or []
    msg_count = sum(1 for item in history if isinstance(item, list | tuple) and len(item) == 2)
    return {
        "id": session.get("id", ""),
        "label": session.get("label", ""),
        "source": session.get("source", "repl"),
        "agent_backend": session.get("agent_backend"),
        "updated_at": session.get("updated_at", ""),
        "message_count": msg_count,
    }


def register_chat_routes(mcp: FastMCP) -> None:
    """Register chat session CRUD endpoints."""

    @mcp.custom_route("/api/chat/sessions", methods=["GET"])
    async def list_sessions(_request: Request) -> JSONResponse:
        ctx = get_server_context(mcp)
        if ctx is None:
            return _err("Server not ready", status=503)
        try:
            source = _request.query_params.get("source")
            sessions = await list_chat_sessions(ctx.client, source=source)
            return _ok([_session_summary(s) for s in sessions])
        except Exception as exc:
            return _err(str(exc), status=500)

    @mcp.custom_route("/api/chat/sessions", methods=["POST"])
    async def create_session(request: Request) -> JSONResponse:
        ctx = get_server_context(mcp)
        if ctx is None:
            return _err("Server not ready", status=503)
        forbidden = _require_access(
            ctx, operation="Chat session creation", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        try:
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
        except Exception as exc:
            return _err(str(exc), status=500)

    @mcp.custom_route("/api/chat/sessions/{session_id}", methods=["GET"])
    async def get_session(request: Request) -> JSONResponse:
        ctx = get_server_context(mcp)
        if ctx is None:
            return _err("Server not ready", status=503)
        try:
            session_id = cast("str", request.path_params["session_id"])
            session = await get_chat_session(ctx.client, session_id)
            if session is None:
                return _err("Session not found", status=404)
            return _ok(_session_to_wire(session))
        except Exception as exc:
            return _err(str(exc), status=500)

    @mcp.custom_route("/api/chat/sessions/{session_id}", methods=["DELETE"])
    async def delete_session(request: Request) -> JSONResponse:
        ctx = get_server_context(mcp)
        if ctx is None:
            return _err("Server not ready", status=503)
        forbidden = _require_access(
            ctx, operation="Chat session deletion", minimum_tier=AccessTier.STANDARD
        )
        if forbidden is not None:
            return forbidden
        try:
            session_id = cast("str", request.path_params["session_id"])
            deleted = await delete_chat_session(ctx.client, session_id)
            if not deleted:
                return _err("Session not found", status=404)
            return _ok({"session_id": session_id, "deleted": True})
        except Exception as exc:
            return _err(str(exc), status=500)

    @mcp.custom_route("/api/chat/agents", methods=["GET"])
    async def list_agents(_request: Request) -> JSONResponse:
        """List available agent backends."""
        ctx = get_server_context(mcp)
        if ctx is None:
            return _err("Server not ready", status=503)
        try:
            from kagan.chat.agents import list_registered_agent_backends

            backends = list_registered_agent_backends()
            settings = await ctx.client.settings.get()
            default = (
                settings.get("default_agent_backend")
                or settings.get("default_agent")
                or "claude-code"
            )
            return _ok(
                {
                    "backends": backends,
                    "default": default,
                }
            )
        except Exception as exc:
            return _err(str(exc), status=500)
