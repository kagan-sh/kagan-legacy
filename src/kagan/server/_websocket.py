"""WebSocket event streaming transport."""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from starlette.routing import WebSocketRoute
from starlette.websockets import WebSocket, WebSocketDisconnect

from kagan.core import resolve_default_agent_backend
from kagan.core.enums import WsMessageType
from kagan.core.errors import KaganError
from kagan.mcp.server import get_server_context
from kagan.server._access import AccessTier, is_access_allowed, websocket_forbidden
from kagan.server._helpers import task_to_wire_dict
from kagan.server.responses import EventResponse

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable, Mapping
    from pathlib import Path

    from mcp.server.fastmcp import FastMCP

    from kagan.core.models import SessionEvent


async def _send_error(
    ws: WebSocket, event_type: str | WsMessageType, exc: Exception, **extra: object
) -> None:
    """Send a typed error response over WebSocket."""
    payload: dict[str, object] = {"t": str(event_type), "error": str(exc), **extra}
    error_code = getattr(exc, "code", None)
    if isinstance(error_code, str):
        payload["error_code"] = error_code
    await ws.send_json(payload)


# Throttle CHAT_CHUNK messages to avoid flooding.
_CHAT_CHUNK_THROTTLE_SECONDS = 0.05


_WS_HEARTBEAT_INTERVAL_SECONDS = 30.0
_WS_HEARTBEAT_TIMEOUT_SECONDS = 10.0
_WS_QUEUE_MAXSIZE = 1000
_ws_connections: set[asyncio.Queue[dict[str, object]]] = set()
_chat_turn_tasks: dict[str, asyncio.Task[None]] = {}


class ChatChunkThrottler:
    def __init__(
        self,
        *,
        websocket: WebSocket,
        session_id: str,
        min_interval: float = _CHAT_CHUNK_THROTTLE_SECONDS,
    ) -> None:
        self._websocket = websocket
        self._session_id = session_id
        self._min_interval = min_interval
        self._send_lock = asyncio.Lock()
        self._last_send_time = 0.0
        self._pending_content = ""
        self._pending_thought = False

    async def flush(self) -> None:
        async with self._send_lock:
            if not self._pending_content:
                return
            content = self._pending_content
            thought = self._pending_thought
            self._pending_content = ""
            self._pending_thought = False
            self._last_send_time = asyncio.get_running_loop().time()
            payload: dict[str, object] = {
                "t": "CHAT_CHUNK",
                "session_id": self._session_id,
                "content": content,
            }
            if thought:
                payload["thought"] = True
            try:
                await self._websocket.send_json(payload)
            except (ConnectionError, RuntimeError, WebSocketDisconnect):
                logger.debug("Failed to send chat chunk update", exc_info=True)

    async def on_update(self, update: Any) -> None:
        from acp.schema import AgentMessageChunk, AgentThoughtChunk, ToolCallProgress, ToolCallStart

        if isinstance(update, AgentMessageChunk):
            content = getattr(update, "content", None)
            if content and getattr(content, "type", None) == "text":
                chunk_text = getattr(content, "text", "") or ""
                if chunk_text:
                    if self._pending_thought and self._pending_content:
                        await self.flush()
                    self._pending_thought = False
                    self._pending_content += chunk_text
                    now = asyncio.get_running_loop().time()
                    if now - self._last_send_time >= self._min_interval:
                        await self.flush()
                    return
        elif isinstance(update, AgentThoughtChunk):
            content = getattr(update, "content", None)
            if content and getattr(content, "type", None) == "text":
                chunk_text = getattr(content, "text", "") or ""
                if chunk_text:
                    if not self._pending_thought and self._pending_content:
                        await self.flush()
                    self._pending_thought = True
                    self._pending_content += chunk_text
                    now = asyncio.get_running_loop().time()
                    if now - self._last_send_time >= self._min_interval:
                        await self.flush()
                    return
        elif isinstance(update, ToolCallStart):
            await self.flush()
            title = getattr(update, "title", None) or getattr(update, "name", None) or "tool"
            try:
                await self._websocket.send_json(
                    {
                        "t": "CHAT_TOOL_START",
                        "session_id": self._session_id,
                        "tool": title,
                    }
                )
            except (ConnectionError, RuntimeError, WebSocketDisconnect):
                logger.debug("Failed to send tool start update", exc_info=True)
        elif isinstance(update, ToolCallProgress):
            await self.flush()
            status = getattr(update, "status", None)
            title = getattr(update, "title", None) or "tool"
            try:
                await self._websocket.send_json(
                    {
                        "t": "CHAT_TOOL_PROGRESS",
                        "session_id": self._session_id,
                        "tool": title,
                        "status": str(status) if status else None,
                    }
                )
            except (ConnectionError, RuntimeError, WebSocketDisconnect):
                logger.debug("Failed to send tool progress update", exc_info=True)


def _track_chat_turn_task(session_id: str, task: asyncio.Task[None]) -> None:
    _chat_turn_tasks[session_id] = task

    def _cleanup(done_task: asyncio.Task[None]) -> None:
        if _chat_turn_tasks.get(session_id) is done_task:
            _chat_turn_tasks.pop(session_id, None)

    task.add_done_callback(_cleanup)


def _enqueue_with_backpressure(
    queue: asyncio.Queue[dict[str, object]],
    event: dict[str, object],
) -> None:
    try:
        queue.put_nowait(event)
        return
    except asyncio.QueueFull:
        pass

    try:
        queue.get_nowait()
    except asyncio.QueueEmpty:
        return

    try:
        queue.put_nowait(event)
    except asyncio.QueueFull:
        return


def broadcast(event: Mapping[str, object]) -> None:
    payload = dict(event)
    for queue in tuple(_ws_connections):
        _enqueue_with_backpressure(queue, payload)


# Board-change sync: push task mutations to WebSocket clients.
# Two loops: _board_event_bridge (in-process) and _cross_process_sync (DB poll).

_CROSS_PROCESS_POLL_SECONDS = 0.75
_board_sync_started = False


async def _board_event_bridge(mcp: FastMCP) -> None:
    while True:
        ctx = get_server_context(mcp)
        while ctx is None:
            await asyncio.sleep(0.5)
            ctx = get_server_context(mcp)
        try:
            async for event in ctx.client.tasks.events.stream_board():
                broadcast({"t": "TASK_UPDATED", "task_id": event.task_id})
        except asyncio.CancelledError:
            raise
        except (ConnectionError, RuntimeError, OSError, KaganError):
            logger.debug("Board event bridge stream failed; retrying", exc_info=True)
            await asyncio.sleep(1.0)
        except Exception:
            logger.exception("Board event bridge unexpected error; retrying")
            await asyncio.sleep(1.0)


async def _cross_process_sync(mcp: FastMCP) -> None:
    ctx = get_server_context(mcp)
    while ctx is None:
        await asyncio.sleep(0.5)
        ctx = get_server_context(mcp)

    snapshot: frozenset[tuple[str, str, str | None]] = frozenset()
    last_project: str | None = ctx.client.active_project_id

    while True:
        await asyncio.sleep(_CROSS_PROCESS_POLL_SECONDS)
        try:
            current_project = ctx.client.active_project_id
            if current_project != last_project:
                last_project = current_project
                snapshot = frozenset()
                broadcast({"t": "TASK_UPDATED"})
                continue

            if not current_project:
                continue

            tasks = await ctx.client.tasks.list()
            current = frozenset(
                (
                    t.id,
                    t.status.value,
                    t.updated_at.isoformat() if getattr(t, "updated_at", None) else None,
                )
                for t in tasks
            )
            if current == snapshot:
                continue

            old_ids = {k[0] for k in snapshot}
            for key in current - snapshot:
                broadcast({"t": "TASK_UPDATED", "task_id": key[0]})
            for tid in old_ids - {k[0] for k in current}:
                broadcast({"t": "TASK_UPDATED", "task_id": tid})
            snapshot = current
        except (ConnectionError, RuntimeError, OSError, KaganError):
            logger.debug("Cross-process sync poll failed; continuing", exc_info=True)
            continue
        except Exception:
            logger.exception("Cross-process sync unexpected error; continuing")
            continue


def _ensure_board_sync(mcp: FastMCP) -> None:
    global _board_sync_started
    if _board_sync_started:
        return
    _board_sync_started = True
    asyncio.create_task(_board_event_bridge(mcp), name="ws-board-event-bridge")
    asyncio.create_task(_cross_process_sync(mcp), name="ws-cross-process-sync")


async def _close_safely(websocket: WebSocket, code: int, reason: str) -> None:
    try:
        await websocket.close(code=code, reason=reason)
    except (ConnectionError, RuntimeError, WebSocketDisconnect, OSError):
        logger.debug("WebSocket close failed", exc_info=True)
        return


async def _sender_loop(
    websocket: WebSocket,
    queue: asyncio.Queue[dict[str, object]],
    pong_event: asyncio.Event,
) -> None:
    while True:
        try:
            event = await asyncio.wait_for(queue.get(), timeout=_WS_HEARTBEAT_INTERVAL_SECONDS)
            await websocket.send_json(event)
            continue
        except TimeoutError:
            pass

        pong_event.clear()
        await websocket.send_json({"t": "PING"})
        try:
            await asyncio.wait_for(pong_event.wait(), timeout=_WS_HEARTBEAT_TIMEOUT_SECONDS)
        except TimeoutError as exc:
            raise WebSocketDisconnect(code=1001) from exc


async def _resolve_project_cwd(client: Any) -> Path | None:
    settings = await client.settings.get()
    return await client.projects.resolve_repo_path(settings=settings)


def _event_to_wire_dict(event: SessionEvent) -> dict[str, Any]:
    return EventResponse.model_validate(event).model_dump(mode="json")


async def _forward_live_session_events(
    *,
    websocket: WebSocket,
    mcp: FastMCP,
) -> None:
    ctx = get_server_context(mcp)
    while ctx is None:
        await asyncio.sleep(0.5)
        ctx = get_server_context(mcp)

    try:
        async for event in ctx.client.tasks.events.stream_all(replay=False):
            try:
                await websocket.send_json(
                    {
                        "t": "SESSION_EVENT",
                        "task_id": str(event.task_id),
                        "event": _event_to_wire_dict(event),
                    }
                )
            except (ConnectionError, RuntimeError, WebSocketDisconnect):
                logger.debug("Failed to forward live session event to websocket", exc_info=True)
    except asyncio.CancelledError:
        raise
    except (ConnectionError, RuntimeError, OSError, KaganError):
        logger.debug("Live session event forward loop failed", exc_info=True)
        return
    except Exception:
        logger.exception("Live session event forward loop unexpected error")
        return


async def _receiver_loop(
    websocket: WebSocket,
    mcp: FastMCP,
    pong_event: asyncio.Event,
) -> None:
    handlers: dict[
        str,
        Callable[[WebSocket, FastMCP, dict[str, object]], Awaitable[None]],
    ] = {
        "BOARD_SUBSCRIBE": _handle_board_subscribe,
        "RUN_START": _handle_run_start,
        "RUN_CANCEL": _handle_run_cancel,
        "CHAT_SUBSCRIBE": _handle_chat_subscribe,
        "CHAT_SEND": _handle_chat_send_message,
        "CHAT_INTERRUPT": _handle_chat_interrupt,
        "TASK_FOLLOW_UP": _handle_task_follow_up,
    }

    while True:
        try:
            raw = await websocket.receive_json()
        except json.JSONDecodeError:
            continue
        if not isinstance(raw, dict):
            continue

        msg_type = raw.get("t")

        if msg_type == "PING":
            await websocket.send_json({"t": "PONG"})
            continue

        if msg_type == "PONG":
            pong_event.set()
            continue

        handler = handlers.get(msg_type) if isinstance(msg_type, str) else None
        if handler is not None:
            await handler(websocket, mcp, raw)


async def _handle_board_subscribe(
    websocket: WebSocket,
    mcp: FastMCP,
    raw: dict[str, object],
) -> None:
    del raw
    ctx = get_server_context(mcp)
    if ctx is None:
        await websocket.send_json({"t": "BOARD_SYNC", "tasks": []})
        return

    tasks = await ctx.client.tasks.list()
    runtime = await ctx.client.tasks.runtime_summaries([task.id for task in tasks])
    await websocket.send_json(
        {
            "t": "BOARD_SYNC",
            "tasks": [task_to_wire_dict(task, runtime=runtime.get(task.id)) for task in tasks],
        }
    )


async def _handle_run_start(
    websocket: WebSocket,
    mcp: FastMCP,
    raw: dict[str, object],
) -> None:
    ctx = get_server_context(mcp)
    if ctx is None:
        await websocket.send_json({"t": "RUN_ERROR", "error": "Server not ready"})
        return
    if not is_access_allowed(ctx, AccessTier.STANDARD):
        await websocket.send_json(
            websocket_forbidden(
                event_type="RUN_ERROR",
                operation="Task execution",
                minimum_tier=AccessTier.STANDARD,
            )
        )
        return

    task_id = raw.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        await websocket.send_json({"t": "RUN_ERROR", "error": "task_id is required"})
        return

    mode = raw.get("mode", "AUTO")
    if mode != "AUTO":
        await websocket.send_json(
            {
                "t": "RUN_ERROR",
                "error": "Only AUTO mode is supported",
            }
        )
        return

    try:
        task = await ctx.client.tasks.get(task_id)
        settings = await ctx.client.settings.get()
        backend = task.agent_backend or resolve_default_agent_backend(settings)
        session = await ctx.client.tasks.run(task_id, agent_backend=backend)
        await websocket.send_json(
            {
                "t": "RUN_STARTED",
                "session_id": session.id,
                "task_id": task_id,
            }
        )
        broadcast({"t": "TASK_UPDATED", "task_id": task_id})
    except KaganError as exc:
        await _send_error(websocket, WsMessageType.RUN_ERROR, exc, task_id=task_id)
    except Exception as exc:
        logger.exception("Unexpected error starting run for task {}", task_id)
        await _send_error(websocket, WsMessageType.RUN_ERROR, exc, task_id=task_id)


async def _handle_run_cancel(
    websocket: WebSocket,
    mcp: FastMCP,
    raw: dict[str, object],
) -> None:
    ctx = get_server_context(mcp)
    if ctx is None:
        await websocket.send_json({"t": "RUN_ERROR", "error": "Server not ready"})
        return
    if not is_access_allowed(ctx, AccessTier.STANDARD):
        await websocket.send_json(
            websocket_forbidden(
                event_type="RUN_ERROR",
                operation="Task cancellation",
                minimum_tier=AccessTier.STANDARD,
            )
        )
        return

    task_id = raw.get("task_id")
    if not isinstance(task_id, str) or not task_id:
        await websocket.send_json({"t": "RUN_ERROR", "error": "task_id is required"})
        return

    try:
        await ctx.client.tasks.cancel(task_id)
        await websocket.send_json({"t": "RUN_CANCELLED", "task_id": task_id})
        broadcast({"t": "TASK_UPDATED", "task_id": task_id})
    except KaganError as exc:
        await _send_error(websocket, WsMessageType.RUN_ERROR, exc)
    except Exception as exc:
        logger.exception("Unexpected error cancelling run for task {}", task_id)
        await _send_error(websocket, WsMessageType.RUN_ERROR, exc)


async def _handle_task_follow_up(
    websocket: WebSocket,
    mcp: FastMCP,
    raw: dict[str, object],
) -> None:
    task_id = raw.get("task_id")
    text = raw.get("text")
    if not isinstance(task_id, str) or not task_id or not isinstance(text, str) or not text.strip():
        await websocket.send_json(
            {"t": "TASK_FOLLOW_UP_ERROR", "error": "task_id and text are required"}
        )
        return

    ctx = get_server_context(mcp)
    if ctx is None:
        await websocket.send_json(
            {"t": "TASK_FOLLOW_UP_ERROR", "task_id": task_id, "error": "Server not ready"}
        )
        return
    if not is_access_allowed(ctx, AccessTier.STANDARD):
        await websocket.send_json(
            websocket_forbidden(
                event_type="TASK_FOLLOW_UP_ERROR",
                operation="Task follow-up messages",
                minimum_tier=AccessTier.STANDARD,
                extra={"task_id": task_id},
            )
        )
        return

    text = text.strip()

    try:
        try:
            await ctx.client.tasks.cancel(task_id)
        except (KaganError, ConnectionError, RuntimeError):
            logger.debug("Task follow-up cancel best-effort failed", exc_info=True)

        task = await ctx.client.tasks.get(task_id)
        current_desc = (getattr(task, "description", "") or "").strip()
        follow_up = f"User follow-up:\n{text}"
        updated_desc = f"{current_desc}\n\n{follow_up}" if current_desc else follow_up

        task = await ctx.client.tasks.update(task_id, description=updated_desc)

        settings = await ctx.client.settings.get()
        backend = getattr(task, "agent_backend", None) or resolve_default_agent_backend(settings)
        session = await ctx.client.tasks.run(task_id, agent_backend=backend)

        await websocket.send_json(
            {
                "t": "TASK_FOLLOW_UP_ACK",
                "task_id": task_id,
                "session_id": session.id,
            }
        )
        broadcast({"t": "TASK_UPDATED", "task_id": task_id})
    except KaganError as exc:
        logger.exception("Task follow-up failed for task {}", task_id)
        await _send_error(websocket, WsMessageType.TASK_FOLLOW_UP_ERROR, exc, task_id=task_id)
    except Exception as exc:
        logger.exception("Task follow-up unexpected error for task {}", task_id)
        await _send_error(websocket, WsMessageType.TASK_FOLLOW_UP_ERROR, exc, task_id=task_id)


async def _handle_chat_subscribe(
    websocket: WebSocket,
    mcp: FastMCP,
    raw: dict[str, object],
) -> None:
    session_id = raw.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        await websocket.send_json({"t": "CHAT_ERROR", "error": "session_id is required"})
        return

    ctx = get_server_context(mcp)
    if ctx is None:
        await websocket.send_json(
            {
                "t": "CHAT_ERROR",
                "session_id": session_id,
                "error": "Server not ready",
            }
        )
        return
    if not is_access_allowed(ctx, AccessTier.STANDARD):
        await websocket.send_json(
            websocket_forbidden(
                event_type="CHAT_ERROR",
                operation="Chat messages",
                minimum_tier=AccessTier.STANDARD,
                extra={"session_id": session_id},
            )
        )
        return

    from kagan.chat.sessions import get_chat_session

    session = await get_chat_session(ctx.client, session_id)
    if session is None:
        await websocket.send_json(
            {
                "t": "CHAT_ERROR",
                "session_id": session_id,
                "error": "Session not found",
            }
        )
        return

    history = session.get("orchestrator_history") or []
    messages: list[dict[str, str]] = []
    for item in history:
        if isinstance(item, list | tuple) and len(item) == 2:
            messages.append({"role": str(item[0]), "content": str(item[1])})

    running_task = _chat_turn_tasks.get(session_id)
    busy = running_task is not None and not running_task.done()

    await websocket.send_json(
        {
            "t": "CHAT_SUBSCRIBED",
            "session_id": session_id,
            "label": session.get("label", ""),
            "agent_backend": session.get("agent_backend"),
            "messages": messages,
            "busy": busy,
        }
    )


async def _handle_chat_send_message(
    websocket: WebSocket,
    mcp: FastMCP,
    raw: dict[str, object],
) -> None:
    session_id = raw.get("session_id")
    text = raw.get("text")
    if (
        not isinstance(session_id, str)
        or not session_id
        or not isinstance(text, str)
        or not text.strip()
    ):
        await websocket.send_json(
            {
                "t": "CHAT_ERROR",
                "error": "session_id and text are required",
            }
        )
        return

    ctx = get_server_context(mcp)
    if ctx is None:
        await websocket.send_json(
            {
                "t": "CHAT_ERROR",
                "session_id": session_id,
                "error": "Server not ready",
            }
        )
        return
    if not is_access_allowed(ctx, AccessTier.STANDARD):
        await websocket.send_json(
            websocket_forbidden(
                event_type="CHAT_ERROR",
                operation="Chat messages",
                minimum_tier=AccessTier.STANDARD,
                extra={"session_id": session_id},
            )
        )
        return

    running_task = _chat_turn_tasks.get(session_id)
    if running_task is not None and not running_task.done():
        await websocket.send_json(
            {
                "t": "CHAT_BUSY",
                "session_id": session_id,
                "error": "Chat turn already running",
            }
        )
        return

    raw_attachments = raw.get("attachments")
    attachments: list[dict[str, str]] | None = None
    if isinstance(raw_attachments, list):
        attachments = [
            {
                "type": str(a.get("type", "")),
                "name": str(a.get("name", "")),
                "mime_type": str(a.get("mime_type", "")),
                "data": str(a.get("data", "")),
            }
            for a in raw_attachments
            if isinstance(a, dict) and a.get("data")
        ]
        if not attachments:
            attachments = None

    turn_task = asyncio.create_task(
        _handle_chat_send(
            websocket=websocket,
            mcp=mcp,
            session_id=session_id,
            text=text.strip(),
            agent_backend=cast("str | None", raw.get("agent_backend")),
            attachments=attachments,
        ),
        name=f"chat-turn:{session_id}",
    )
    _track_chat_turn_task(session_id, turn_task)


async def _handle_chat_interrupt(
    websocket: WebSocket,
    mcp: FastMCP,
    raw: dict[str, object],
) -> None:
    session_id = raw.get("session_id")
    if not isinstance(session_id, str) or not session_id:
        await websocket.send_json({"t": "CHAT_ERROR", "error": "session_id is required"})
        return
    ctx = get_server_context(mcp)
    if not is_access_allowed(ctx, AccessTier.STANDARD):
        await websocket.send_json(
            websocket_forbidden(
                event_type="CHAT_ERROR",
                operation="Chat interruption",
                minimum_tier=AccessTier.STANDARD,
                extra={"session_id": session_id},
            )
        )
        return

    running_task = _chat_turn_tasks.get(session_id)
    if running_task is None or running_task.done():
        await websocket.send_json(
            {
                "t": "CHAT_INTERRUPTED",
                "session_id": session_id,
                "interrupted": False,
            }
        )
        return

    running_task.cancel()
    try:
        await asyncio.wait_for(running_task, timeout=5.0)
    except asyncio.CancelledError:
        logger.debug("Chat interrupt wait cancelled", exc_info=True)
    except TimeoutError:
        logger.debug("Chat interrupt wait timed out", exc_info=True)
    except (KaganError, RuntimeError, ConnectionError):
        logger.debug("Chat interrupt wait failed", exc_info=True)

    await websocket.send_json(
        {
            "t": "CHAT_INTERRUPTED",
            "session_id": session_id,
            "interrupted": True,
        }
    )


async def _handle_chat_send(
    *,
    websocket: WebSocket,
    mcp: FastMCP,
    session_id: str,
    text: str,
    agent_backend: str | None,
    attachments: list[dict[str, str]] | None = None,
) -> None:
    from kagan.chat.acp import run_orchestrator_turn
    from kagan.chat.prompt import build_orchestrator_prompt
    from kagan.chat.sessions import get_chat_session, save_chat_session

    ctx = get_server_context(mcp)
    if ctx is None:
        await websocket.send_json(
            {"t": "CHAT_ERROR", "session_id": session_id, "error": "Server not ready"}
        )
        return

    session = await get_chat_session(ctx.client, session_id)
    if session is None:
        await websocket.send_json(
            {"t": "CHAT_ERROR", "session_id": session_id, "error": "Session not found"}
        )
        return

    settings = await ctx.client.settings.get()
    backend = (
        agent_backend or session.get("agent_backend") or resolve_default_agent_backend(settings)
    )
    throttler = ChatChunkThrottler(websocket=websocket, session_id=session_id)

    try:
        prior_history: list[tuple[str, str]] = [
            (str(item[0]), str(item[1]))
            for item in (session.get("orchestrator_history") or [])
            if isinstance(item, list | tuple) and len(item) == 2
        ]

        # Persist the user message BEFORE starting the turn so it survives
        # component unmount/remount (the client fetches history via REST).
        history = list(session.get("orchestrator_history") or [])
        is_first_message = len(history) == 0
        history.append(["user", text])
        session["orchestrator_history"] = history
        session["agent_backend"] = backend
        await save_chat_session(ctx.client, session)

        prompt = build_orchestrator_prompt(prior_history, text)
        project_cwd = await _resolve_project_cwd(ctx.client)
        full_response = await run_orchestrator_turn(
            ctx.client,
            prompt=prompt,
            agent_backend=backend,
            on_update=throttler.on_update,
            attachments=attachments,
            cwd=project_cwd,
        )
        await throttler.flush()

        if full_response:
            history.append(["assistant", full_response])
            session["orchestrator_history"] = history
            await save_chat_session(ctx.client, session)

        await websocket.send_json(
            {
                "t": "CHAT_DONE",
                "session_id": session_id,
                "full_response": full_response,
            }
        )

        # Orchestrator chat may have mutated tasks via MCP tools (start, cancel,
        # update status, etc.).  Broadcast a generic TASK_UPDATED so every
        # connected client — including the kanban board — refreshes.
        broadcast({"t": "TASK_UPDATED"})

        if is_first_message:
            asyncio.create_task(
                _generate_chat_session_title(
                    websocket=websocket,
                    client=ctx.client,
                    session=session,
                    user_message=text,
                    assistant_reply=full_response or "",
                    agent_backend=backend,
                ),
                name=f"chat-title-gen:{session_id}",
            )
    except asyncio.CancelledError:
        await throttler.flush()
        return
    except Exception as exc:
        await throttler.flush()
        logger.exception("Chat orchestrator turn failed for session {}", session_id)
        try:
            await _send_error(websocket, WsMessageType.CHAT_ERROR, exc, session_id=session_id)
        except (ConnectionError, RuntimeError, WebSocketDisconnect):
            logger.debug("Failed to send chat error event", exc_info=True)


async def _generate_chat_session_title(
    *,
    websocket: WebSocket,
    client: Any,
    session: dict[str, Any],
    user_message: str,
    assistant_reply: str,
    agent_backend: str,
) -> None:
    from kagan.chat._title import ensure_session_title

    try:
        title = await ensure_session_title(
            client,
            session,
            user_message=user_message,
            assistant_reply=assistant_reply,
            agent_backend=agent_backend,
        )
        if title:
            try:
                await websocket.send_json(
                    {
                        "t": "CHAT_SESSION_UPDATED",
                        "session_id": (
                            str(session.get("id")) if session.get("id") is not None else None
                        ),
                        "label": title,
                    }
                )
            except (ConnectionError, RuntimeError, WebSocketDisconnect):
                logger.debug("Failed to send generated chat session title", exc_info=True)
    except (KaganError, ConnectionError, RuntimeError):
        logger.debug("Chat session title generation failed", exc_info=True)
    except Exception:
        logger.exception("Chat session title generation unexpected error")


def register_websocket(mcp: FastMCP) -> None:
    async def ws_handler(websocket: WebSocket) -> None:
        await websocket.accept()

        _ = get_server_context(mcp)
        _ensure_board_sync(mcp)

        queue: asyncio.Queue[dict[str, object]] = asyncio.Queue(maxsize=_WS_QUEUE_MAXSIZE)
        _ws_connections.add(queue)
        pong_event = asyncio.Event()

        sender_task = asyncio.create_task(_sender_loop(websocket, queue, pong_event))
        receiver_task = asyncio.create_task(_receiver_loop(websocket, mcp, pong_event))
        session_events_task = asyncio.create_task(
            _forward_live_session_events(websocket=websocket, mcp=mcp)
        )
        try:
            try:
                done, pending = await asyncio.wait(
                    {sender_task, receiver_task, session_events_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )

                for task in pending:
                    task.cancel()
                await asyncio.gather(*pending, return_exceptions=True)

                for task in done:
                    exc = task.exception()
                    if isinstance(exc, WebSocketDisconnect):
                        continue
                    if exc is not None:
                        await _close_safely(websocket, code=1011, reason="WebSocket error")
                        break
            except WebSocketDisconnect:
                pass
        finally:
            _ws_connections.discard(queue)
            await _close_safely(websocket, code=1000, reason="Disconnected")

    route = WebSocketRoute("/ws", ws_handler)
    routes = cast("list[Any]", mcp._custom_starlette_routes)
    routes.append(route)
