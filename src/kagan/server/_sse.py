"""SSE streaming helpers for kagan.server."""

from __future__ import annotations

import asyncio
import contextlib
import json
import time
from typing import TYPE_CHECKING, Any

from loguru import logger
from starlette.responses import StreamingResponse

from kagan.core.errors import KaganError
from kagan.server._helpers import event_to_wire, task_wire_dict
from kagan.server.mcp.server import get_server_context

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.fastmcp import FastMCP

    from kagan.core._tasks import Tasks

_SSE_KEEPALIVE_SECONDS = 25.0
# Safety-net fallback interval — the event bus delivers most mutations
# instantly; this poll only catches cross-process writes the bus cannot see.
_DB_POLL_SECONDS = 10.0
_TASK_UPDATE_MIN_INTERVAL_SECONDS = 0.2


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


async def _build_project_task_ids(ctx: Any) -> set[str] | None:
    """Return the set of task IDs belonging to the bound project, or None if unscoped."""
    project_id = getattr(ctx, "bound_project_id", None)
    if project_id is None:
        return None
    try:
        tasks = await ctx.client.tasks.list()
        return {t.id for t in tasks if t.project_id == project_id}
    except (KaganError, OSError, RuntimeError):
        logger.debug("SSE: failed to build project task set for filtering")
        return None


async def _forward_session_events(ctx: Any, queue: asyncio.Queue[dict[str, Any]]) -> None:
    # Scope events to the bound project context so that SSE clients only
    # receive events for tasks they are authorized to see.  The task set is
    # rebuilt periodically to pick up newly-created tasks.
    allowed_task_ids = await _build_project_task_ids(ctx)

    events_since_refresh = 0
    _REFRESH_INTERVAL = 50  # rebuild the allowed set every N events

    try:
        async for event in ctx.client.tasks.events.stream_all(replay=False):
            task_id = str(event.task_id)

            # Refresh the allowed set periodically to capture new tasks
            events_since_refresh += 1
            if events_since_refresh >= _REFRESH_INTERVAL:
                allowed_task_ids = await _build_project_task_ids(ctx)
                events_since_refresh = 0

            # Filter: skip events for tasks outside the bound project
            if allowed_task_ids is not None and task_id not in allowed_task_ids:
                # Task may have been created after last refresh — do one
                # immediate refresh before dropping the event.
                allowed_task_ids = await _build_project_task_ids(ctx)
                if allowed_task_ids is not None and task_id not in allowed_task_ids:
                    continue

            _queue_put_lossy(
                queue,
                {
                    "type": "SESSION_EVENT",
                    "task_id": task_id,
                    "event": event_to_wire(event),
                },
            )
    except asyncio.CancelledError:
        raise
    except (ConnectionError, RuntimeError, OSError, KaganError):
        logger.debug("SSE session event stream failed", exc_info=True)


async def _forward_board_events(ctx: Any, queue: asyncio.Queue[dict[str, Any]]) -> None:
    # Board events are also scoped to the bound project context.
    allowed_task_ids = await _build_project_task_ids(ctx)
    events_since_refresh = 0
    _REFRESH_INTERVAL = 50
    last_sent_at: dict[str, float] = {}

    try:
        async for event in ctx.client.tasks.events.stream_board():
            task_id = event.task_id

            events_since_refresh += 1
            if events_since_refresh >= _REFRESH_INTERVAL:
                allowed_task_ids = await _build_project_task_ids(ctx)
                events_since_refresh = 0

            if allowed_task_ids is not None and task_id not in allowed_task_ids:
                allowed_task_ids = await _build_project_task_ids(ctx)
                if allowed_task_ids is not None and task_id not in allowed_task_ids:
                    continue

            now = time.monotonic()
            if now - last_sent_at.get(task_id, 0.0) < _TASK_UPDATE_MIN_INTERVAL_SECONDS:
                continue
            last_sent_at[task_id] = now

            _queue_put_best_effort(queue, await _task_update_message(ctx, task_id))
    except asyncio.CancelledError:
        raise
    except (ConnectionError, RuntimeError, OSError, KaganError):
        logger.debug("SSE board event stream failed", exc_info=True)


async def _task_update_message(ctx: Any, task_id: str) -> dict[str, Any]:
    try:
        task = await task_wire_dict(ctx, task_id)
        return {"type": "TASK_UPDATED", "task_id": task_id, "task": task}
    except (KaganError, OSError, RuntimeError, AttributeError):
        logger.debug("SSE: failed to build task payload for {}", task_id, exc_info=True)
        return {"type": "TASK_UPDATED", "task_id": task_id}


async def _yield_sse_payloads(queue: asyncio.Queue[dict[str, Any]]) -> AsyncIterator[str]:
    while True:
        try:
            data = await asyncio.wait_for(queue.get(), timeout=_SSE_KEEPALIVE_SECONDS)
            yield f"data: {json.dumps(data)}\n\n"
        except TimeoutError:
            yield ": keepalive\n\n"


async def _poll_db_changes(
    ctx_or_tasks: Any,
    queue: asyncio.Queue[dict[str, Any]],
    *,
    project_id: str | None = None,
) -> None:
    """Detect task mutations from external processes (MCP agents, CLI).

    Board events are in-memory per-process — when an agent running in a
    separate process creates or updates a task, the in-memory queues on
    *this* server never see it. Periodic DB polling bridges the gap.

    When *project_id* is provided, only tasks belonging to that project are
    tracked — events for other projects are never emitted.

    Accepts either a server `ctx` (production) or a bare `Tasks`-like object
    (unit tests). When called without a ctx the emitted update message omits
    the inline task payload — that mode is *only* for tests; production code
    must pass a ctx so SSE clients receive the full board update.
    """
    ctx = ctx_or_tasks if hasattr(ctx_or_tasks, "client") else None
    tasks: Tasks = ctx.client.tasks if ctx is not None else ctx_or_tasks
    known: dict[str, str] = {}

    def _scoped(snapshot: list[Any]) -> list[Any]:
        if project_id is None:
            return snapshot
        return [t for t in snapshot if t.project_id == project_id]

    try:
        snapshot = _scoped(await tasks.list())
        known = {t.id: t.updated_at.isoformat() for t in snapshot}
    except (KaganError, OSError, RuntimeError):
        logger.warning("SSE poll: initial snapshot failed", exc_info=True)

    try:
        while True:
            await asyncio.sleep(_DB_POLL_SECONDS)
            try:
                snapshot = _scoped(await tasks.list())
            except (KaganError, OSError, RuntimeError):
                logger.warning("SSE poll: failed to list tasks", exc_info=True)
                continue

            current = {t.id: t.updated_at.isoformat() for t in snapshot}
            changed = {tid for tid, ts in current.items() if known.get(tid) != ts}
            deleted = known.keys() - current.keys()

            for task_id in changed:
                with contextlib.suppress(asyncio.QueueFull):
                    message = (
                        await _task_update_message(ctx, task_id)
                        if ctx is not None
                        else {"type": "TASK_UPDATED", "task_id": task_id}
                    )
                    queue.put_nowait(message)
            for task_id in deleted:
                with contextlib.suppress(asyncio.QueueFull):
                    queue.put_nowait({"type": "TASK_DELETED", "task_id": task_id})

            known = current
    except asyncio.CancelledError:
        raise
    except (KaganError, OSError, RuntimeError):
        logger.warning("SSE DB poll stopped due to error", exc_info=True)


async def _sse_event_generator(
    mcp: FastMCP,
    client_type: str = "web",
    client_id: str | None = None,
) -> AsyncIterator[str]:
    """Yield SSE-formatted events from the global event stream + board changes."""
    ctx = await _wait_for_server_ctx(mcp)
    if ctx is None:
        return

    # Auto-register presence for this SSE client
    import uuid as _uuid

    connection_token = _uuid.uuid4().hex
    sse_client_id = client_id or _uuid.uuid4().hex[:16]
    tracker = getattr(ctx, "presence", None)
    if tracker is not None:
        tracker.register(sse_client_id, client_type, connection_token=connection_token)

    queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=500)
    tasks = (
        asyncio.create_task(_forward_session_events(ctx, queue)),
        asyncio.create_task(_forward_board_events(ctx, queue)),
        asyncio.create_task(
            _poll_db_changes(ctx, queue, project_id=getattr(ctx, "bound_project_id", None))
        ),
    )

    try:
        async for payload in _yield_sse_payloads(queue):
            if tracker is not None:
                tracker.heartbeat(sse_client_id, connection_token=connection_token)
            yield payload
    except asyncio.CancelledError:
        pass
    finally:
        if tracker is not None:
            tracker.unregister(sse_client_id, connection_token=connection_token)
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
