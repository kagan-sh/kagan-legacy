"""kagan.server._sse_fanout — Shared SSE infrastructure for chat/session routes.

Provides the /watch fanout, wire-frame helpers, parameter resolution,
and session teardown used by both ``_chat_routes`` and ``_session_routes``.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from collections import defaultdict
from typing import TYPE_CHECKING, Any, cast

from starlette.responses import JSONResponse

from kagan.core import Attachment, AttachmentBody
from kagan.core.chat import ChatSessionView, chat_session_to_view
from kagan.core.events import Event, event_to_dict
from kagan.core.permission import PermissionRequest
from kagan.server._access import AccessTier, is_access_allowed
from kagan.server._helpers import _err
from kagan.server.responses import (
    ChatSessionSummaryResponse,
    TurnInProgressResponse,
)

if TYPE_CHECKING:
    from starlette.requests import Request

    from kagan.server.mcp.server import ServerContext

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


def _emit(frame: dict[str, Any]) -> str:
    return f"data: {json.dumps(frame)}\n\n"


def _chat_event_to_sse_frame(event: Event | PermissionRequest) -> dict[str, Any] | None:
    """Serialize one event to an SSE frame dict.

    Event variants are serialized directly via ``event_to_dict``.
    ``PermissionRequest`` (sidechannel) produces a ``CHAT_PERMISSION_REQUEST``
    frame so web consumers can display the approval UI.
    ``TurnStart`` is suppressed here because the SSE producer already emits a
    ``CHAT_TURN_STARTED`` frame with ``by_source`` before streaming begins.

    Returns ``None`` for events that have no SSE wire analogue.
    """
    if isinstance(event, PermissionRequest):
        tc = event.tool_call
        if isinstance(tc, dict):
            raw_title = tc.get("title") or tc.get("name") or ""
        else:
            raw_title = getattr(tc, "title", None) or getattr(tc, "name", None) or ""
        tool_name = str(raw_title).split(":")[0].split("{")[0].strip()
        return {
            "t": "CHAT_PERMISSION_REQUEST",
            "future_id": event.future_id,
            "tool_name": tool_name,
        }
    match event.type:
        case "turn_start":
            # Suppressed: producer emits CHAT_TURN_STARTED with by_source before streaming.
            return None
        case "assistant_chunk":
            return event_to_dict(event)
        case "thinking_chunk":
            return event_to_dict(event)
        case "tool_call":
            return event_to_dict(event)
        case "tool_call_update":
            return event_to_dict(event)
        case "tool_call_result":
            return event_to_dict(event)
        case "usage_update":
            return event_to_dict(event)
        case "error":
            return event_to_dict(event)
        case "agent_lifecycle":
            return event_to_dict(event)
        case "assistant_message":
            return event_to_dict(event)
        case "user_message":
            return event_to_dict(event)
        case "turn_end":
            return event_to_dict(event)
        case _:
            return None


def _session_summary(session: ChatSessionView) -> dict[str, Any]:
    """Serialize a typed session view to the lightweight summary wire shape."""
    msg_count = sum(
        1
        for item in session.orchestrator_history
        if isinstance(item, list | tuple) and len(item) == 2
    )
    return ChatSessionSummaryResponse(
        id=session.id,
        label=session.label,
        source=session.source,
        agent_backend=session.agent_backend,
        project_id=session.project_id,
        updated_at=session.updated_at,
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


async def _load_session_view(client: Any, session_id: str) -> ChatSessionView | None:
    """Fetch a session + its messages and return a typed view.

    Wraps ``client.chat_sessions.get_with_history`` for transport-layer code
    that needs the session view for wire serialization. Returns ``None`` if
    the session is missing.
    """
    pair = await client.chat_sessions.get_with_history(session_id)
    if pair is None:
        return None
    return chat_session_to_view(*pair)


def _teardown_session_state(ctx: ServerContext, session_id: str) -> None:
    """Clear per-session transport state and ask the engine to detach."""
    _chat_subscribers.pop(session_id, None)
    engine = getattr(ctx.client, "chat", None)
    if engine is not None:
        # Fire-and-forget — detach is best-effort cleanup at delete time.
        with contextlib.suppress(RuntimeError):
            asyncio.get_running_loop().create_task(engine.detach(session_id))


# ---------------------------------------------------------------------------
# Stream request resolution (unified)
# ---------------------------------------------------------------------------


async def resolve_sse_parameters(
    request: Request, ctx: ServerContext, session_id: str
) -> JSONResponse | tuple[ChatSessionView, str, str, list[Attachment] | None]:
    """Validate + resolve a stream/message request. Returns an early Response on
    failure, or the (session, text, backend, attachments) tuple to stream."""
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

    # Pre-flight 409: cheap turn_status read keeps the early-error path fast
    # (no need to start the SSE response just to tear it down).
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
