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
    ctx = get_server_context(mcp)
    _wait_iters = 0
    while ctx is None:
        if _wait_iters >= 60:
            return
        await asyncio.sleep(0.5)
        _wait_iters += 1
        ctx = get_server_context(mcp)

    # Create a merged stream: session events + board task updates
    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)

    async def _forward_session_events() -> None:
        try:
            async for event in ctx.client.tasks.events.stream_all(replay=False):
                data = {
                    "type": "SESSION_EVENT",
                    "task_id": str(event.task_id),
                    "event": _event_to_wire(event),
                }
                try:
                    queue.put_nowait(data)
                except asyncio.QueueFull:
                    # Drop oldest non-critical event
                    with contextlib.suppress(asyncio.QueueEmpty):
                        queue.get_nowait()
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(data)
        except asyncio.CancelledError:
            raise
        except (ConnectionError, RuntimeError, OSError, KaganError):
            logger.debug("SSE session event stream failed", exc_info=True)

    async def _forward_board_events() -> None:
        try:
            async for event in ctx.client.tasks.events.stream_board():
                data = {"type": "TASK_UPDATED", "task_id": event.task_id}
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait(data)
        except asyncio.CancelledError:
            raise
        except (ConnectionError, RuntimeError, OSError, KaganError):
            logger.debug("SSE board event stream failed", exc_info=True)

    async def _forward_bus_events() -> None:
        bus_queue = await ctx.client.event_bus.subscribe()
        try:
            while True:
                msg: BusMessage = await bus_queue.get()
                if msg.event in (
                    BusEvent.TASK_CREATED,
                    BusEvent.TASK_UPDATED,
                    BusEvent.TASK_DELETED,
                ):
                    wire_type = {
                        BusEvent.TASK_CREATED: "TASK_UPDATED",
                        BusEvent.TASK_UPDATED: "TASK_UPDATED",
                        BusEvent.TASK_DELETED: "TASK_DELETED",
                    }[msg.event]
                    data = {"type": wire_type, "task_id": msg.entity_id}
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(data)
                elif msg.event == BusEvent.SETTINGS_CHANGED:
                    data = {"type": "SETTINGS_CHANGED", "keys": msg.payload.get("keys", [])}
                    with contextlib.suppress(asyncio.QueueFull):
                        queue.put_nowait(data)
        except asyncio.CancelledError:
            raise
        except (ConnectionError, RuntimeError, OSError, KaganError):
            logger.debug("SSE bus event forwarder failed", exc_info=True)
        finally:
            await ctx.client.event_bus.unsubscribe(bus_queue)

    # Safety-net fallback: polls the DB for cross-process mutations
    # that the in-memory event bus cannot observe.
    async def _poll_db_for_external_changes() -> None:
        await _poll_db_changes(ctx.client.tasks, queue)

    session_task = asyncio.create_task(_forward_session_events())
    board_task = asyncio.create_task(_forward_board_events())
    bus_task = asyncio.create_task(_forward_bus_events())
    poll_task = asyncio.create_task(_poll_db_for_external_changes())

    try:
        while True:
            try:
                data = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_SECONDS)
                yield f"data: {json.dumps(data)}\n\n"
            except TimeoutError:
                # Send keepalive comment to prevent proxy/browser timeouts
                yield ": keepalive\n\n"
    except asyncio.CancelledError:
        pass
    finally:
        session_task.cancel()
        board_task.cancel()
        bus_task.cancel()
        poll_task.cancel()
        await asyncio.gather(session_task, board_task, bus_task, poll_task, return_exceptions=True)


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
