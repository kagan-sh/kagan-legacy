"""SSE streaming helpers for kagan.server."""

from __future__ import annotations

import asyncio
import contextlib
import json
from typing import TYPE_CHECKING, Any

from loguru import logger
from starlette.responses import StreamingResponse

from kagan.core._event_bus import BusEvent, BusMessage
from kagan.core.errors import KaganError
from kagan.mcp.server import get_server_context
from kagan.server.responses import EventResponse

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.fastmcp import FastMCP

    from kagan.core._tasks import Tasks
    from kagan.core.models import SessionEvent

_SSE_KEEPALIVE_SECONDS = 25.0
# Safety-net fallback interval — the event bus delivers most mutations
# instantly; this poll only catches cross-process writes the bus cannot see.
_DB_POLL_SECONDS = 10.0


def _event_to_wire(event: SessionEvent) -> dict[str, Any]:
    return EventResponse.model_validate(event).model_dump(mode="json")


def _queue_put_lossy(queue: asyncio.Queue[dict[str, Any]], data: dict[str, Any]) -> None:
    try:
        queue.put_nowait(data)
    except asyncio.QueueFull:
        with contextlib.suppress(asyncio.QueueEmpty):
            queue.get_nowait()
        with contextlib.suppress(asyncio.QueueFull):
            queue.put_nowait(data)


def _queue_put_best_effort(queue: asyncio.Queue[dict[str, Any]], data: dict[str, Any]) -> None:
    with contextlib.suppress(asyncio.QueueFull):
        queue.put_nowait(data)


async def _wait_for_server_ctx(mcp: FastMCP) -> Any | None:
    ctx = get_server_context(mcp)
    for _ in range(60):
        if ctx is not None:
            return ctx
        await asyncio.sleep(0.5)
        ctx = get_server_context(mcp)
    return None


async def _forward_session_events(ctx: Any, queue: asyncio.Queue[dict[str, Any]]) -> None:
    try:
        async for event in ctx.client.tasks.events.stream_all(replay=False):
            _queue_put_lossy(
                queue,
                {
                    "type": "SESSION_EVENT",
                    "task_id": str(event.task_id),
                    "event": _event_to_wire(event),
                },
            )
    except asyncio.CancelledError:
        raise
    except (ConnectionError, RuntimeError, OSError, KaganError):
        logger.debug("SSE session event stream failed", exc_info=True)


async def _forward_board_events(ctx: Any, queue: asyncio.Queue[dict[str, Any]]) -> None:
    try:
        async for event in ctx.client.tasks.events.stream_board():
            _queue_put_best_effort(queue, {"type": "TASK_UPDATED", "task_id": event.task_id})
    except asyncio.CancelledError:
        raise
    except (ConnectionError, RuntimeError, OSError, KaganError):
        logger.debug("SSE board event stream failed", exc_info=True)


def _bus_message_to_sse_data(msg: BusMessage) -> dict[str, Any] | None:
    if msg.event == BusEvent.SETTINGS_CHANGED:
        return {"type": "SETTINGS_CHANGED", "keys": msg.payload.get("keys", [])}
    if msg.event == BusEvent.TASK_DELETED:
        return {"type": "TASK_DELETED", "task_id": msg.entity_id}
    if msg.event in (BusEvent.TASK_CREATED, BusEvent.TASK_UPDATED):
        return {"type": "TASK_UPDATED", "task_id": msg.entity_id}
    return None


async def _forward_bus_events(ctx: Any, queue: asyncio.Queue[dict[str, Any]]) -> None:
    bus_queue = await ctx.client.event_bus.subscribe()
    try:
        while True:
            msg: BusMessage = await bus_queue.get()
            data = _bus_message_to_sse_data(msg)
            if data is not None:
                _queue_put_best_effort(queue, data)
    except asyncio.CancelledError:
        raise
    except (ConnectionError, RuntimeError, OSError, KaganError):
        logger.debug("SSE bus event forwarder failed", exc_info=True)
    finally:
        await ctx.client.event_bus.unsubscribe(bus_queue)


async def _yield_sse_payloads(queue: asyncio.Queue[dict[str, Any]]) -> AsyncIterator[str]:
    while True:
        try:
            data = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_SECONDS)
            yield f"data: {json.dumps(data)}\n\n"
        except TimeoutError:
            yield ": keepalive\n\n"


async def _poll_db_for_external_changes(ctx: Any, queue: asyncio.Queue[dict[str, Any]]) -> None:
    await _poll_db_changes(ctx.client.tasks, queue)


async def _poll_db_changes(
    tasks: Tasks,
    queue: asyncio.Queue[dict[str, Any]],
) -> None:
    """Detect task mutations from external processes (MCP agents, CLI).

    Board events are in-memory per-process — when an agent running in a
    separate process creates or updates a task, the in-memory queues on
    *this* server never see it. Periodic DB polling bridges the gap.
    """
    known: dict[str, str] = {}

    try:
        snapshot = await tasks.list()
        known = {t.id: t.updated_at.isoformat() for t in snapshot}
    except Exception:
        logger.warning("SSE poll: initial snapshot failed", exc_info=True)

    try:
        while True:
            await asyncio.sleep(_DB_POLL_SECONDS)
            try:
                snapshot = await tasks.list()
            except Exception:
                logger.warning("SSE poll: failed to list tasks", exc_info=True)
                continue

            current = {t.id: t.updated_at.isoformat() for t in snapshot}
            changed = {tid for tid, ts in current.items() if known.get(tid) != ts}
            deleted = known.keys() - current.keys()

            for task_id in changed:
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait({"type": "TASK_UPDATED", "task_id": task_id})
            for task_id in deleted:
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait({"type": "TASK_DELETED", "task_id": task_id})

            known = current
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.warning("SSE DB poll stopped due to error", exc_info=True)


async def _sse_event_generator(mcp: FastMCP) -> AsyncIterator[str]:
    """Yield SSE-formatted events from the global event stream + board changes."""
    ctx = await _wait_for_server_ctx(mcp)
    if ctx is None:
        return

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
    tasks = (
        asyncio.create_task(_forward_session_events(ctx, queue)),
        asyncio.create_task(_forward_board_events(ctx, queue)),
        asyncio.create_task(_forward_bus_events(ctx, queue)),
        asyncio.create_task(_poll_db_for_external_changes(ctx, queue)),
    )

    try:
        async for payload in _yield_sse_payloads(queue):
            yield payload
    except asyncio.CancelledError:
        pass
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)


def sse_response(generator: AsyncIterator[str]) -> StreamingResponse:
    """Create a Starlette StreamingResponse for SSE."""
    return StreamingResponse(
        generator,
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
