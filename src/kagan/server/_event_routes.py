"""kagan.server._event_routes — Unified SSE endpoints with Last-Event-ID resume.

Implements the ``snapshot → ready → live`` pattern:

    GET /api/sessions/{session_id}/events   chat-session SSE  (kind="chat")
    GET /api/tasks/{task_id}/sse            task SSE          (kind="task")

Note: the task SSE endpoint uses ``/sse`` suffix instead of ``/events`` to
avoid path collision with the existing paginated task-events endpoint at
``GET /api/tasks/{task_id}/events`` (which returns raw SessionEvent rows).

Both endpoints follow identical framing:

    retry: 1000

    id: 0
    event: snapshot
    data: {"type":"snapshot","kind":"chat","session_id":"...","from_seq":0,"to_seq":N,"entries":[]}

    id: N
    event: ready
    data: {"type":"ready"}

    id: N+1
    event: patch
    data: {"type":"patch","op":"append","path":"/entries/8/text","value":"Hello"}

    : keepalive (comment line, every 15 s)

Last-Event-ID handling
----------------------
- No header → fresh connect from seq 0.
- Header present → parse as int; invalid → 400.
- ``N < max_seq``  → catchup snapshot (from_seq=N+1..max_seq) then ready then live.
- ``N == max_seq`` → ready then live (empty snapshot omitted).
- ``N > max_seq``  → ready then live (treat as fresh; do not error).

Snapshot strategy
-----------------
A single ``snapshot`` frame is emitted by replaying all frames via
:func:`~kagan.server._frame_reduce.reduce_frames` into a ``FrameSnapshot``.
The ``id:`` of the snapshot frame carries ``max_seq`` so reconnect from that
point skips the snapshot entirely.

Auth
----
Reuses the existing server-context middleware (cookie-based).  ``EventSource``
clients that cannot set headers should use the same cookie as all other API
callers.  No ``?token=`` query param is required.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any, Literal, cast

from loguru import logger
from starlette.responses import JSONResponse, StreamingResponse

from kagan.core.errors import NotFoundError
from kagan.server._frame_reduce import reduce_frames
from kagan.server._helpers import _err, handle_errors, require_context
from kagan.server.responses import FrameEntry, FrameReady, FrameSnapshot

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from mcp.server.fastmcp import FastMCP
    from starlette.requests import Request

    from kagan.server.mcp.server import ServerContext

_KEEPALIVE_INTERVAL: float = 15.0
_RETRY_MS: int = 1000


# ---------------------------------------------------------------------------
# SSE wire helpers
# ---------------------------------------------------------------------------


def _sse_event(event_id: int, event_type: str, data: str) -> str:
    """Format a single SSE event block."""
    return f"id: {event_id}\nevent: {event_type}\ndata: {data}\n\n"


def _sse_comment(text: str = "keepalive") -> str:
    """Format an SSE comment line (not an event; no ``id:`` line)."""
    return f": {text}\n\n"


def _sse_retry(ms: int) -> str:
    return f"retry: {ms}\n\n"


# ---------------------------------------------------------------------------
# Snapshot builder
# ---------------------------------------------------------------------------


def _build_snapshot_frame(
    session_id: str,
    kind: Literal["chat", "task"],
    from_seq: int,
    frames: list,
) -> tuple[FrameSnapshot, int, int]:
    """Reduce *frames* into a FrameSnapshot.

    Returns ``(snapshot, max_seq_floored, raw_max_seq)``.

    ``raw_max_seq`` is -1 when there are no frames; used by the live tail to
    correctly set the subscribe start point (``raw_max_seq + 1``).
    ``max_seq_floored`` is ``max(raw_max_seq, 0)``; used for ``id:`` lines.
    """
    entries_raw, raw_max_seq = reduce_frames(frames)
    max_seq_floored = max(raw_max_seq, 0)

    entries: list[FrameEntry] = []
    for raw in entries_raw:
        ts_raw = raw.get("ts")
        if isinstance(ts_raw, str):
            try:
                ts = datetime.fromisoformat(ts_raw)
            except ValueError:
                ts = datetime.now(tz=UTC)
        elif isinstance(ts_raw, datetime):
            ts = ts_raw
        else:
            ts = datetime.now(tz=UTC)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=UTC)
        entries.append(
            FrameEntry(
                idx=raw["idx"],
                role=raw["role"],  # type: ignore[arg-type]
                text=raw["text"],
                finalized=raw["finalized"],
                ts=ts,
            )
        )

    snapshot = FrameSnapshot(
        kind=kind,
        session_id=session_id,
        from_seq=from_seq,
        to_seq=max_seq_floored,
        entries=entries,
    )
    return snapshot, max_seq_floored, raw_max_seq


# ---------------------------------------------------------------------------
# Last-Event-ID parsing
# ---------------------------------------------------------------------------


def _parse_last_event_id(raw: str | None) -> int | None | JSONResponse:
    """Parse the Last-Event-ID header.

    Returns:
        - ``None``  — header absent; fresh connect.
        - ``int``   — parsed seq value.
        - ``JSONResponse`` — invalid (non-integer) header; 400 response.
    """
    if raw is None:
        return None
    try:
        return int(raw)
    except (ValueError, TypeError):
        return _err("Last-Event-ID must be an integer", status=400)


# ---------------------------------------------------------------------------
# Core SSE generator
# ---------------------------------------------------------------------------


async def _sse_generator(
    ctx: ServerContext,
    session_id: str,
    kind: Literal["chat", "task"],
    from_seq: int,
) -> AsyncIterator[str]:
    """Drive the snapshot → ready → live SSE frame sequence.

    Subscribes to ``ctx.client._event_log`` (the shared instance) so that
    live-tail queues are populated by producers writing to the same instance.

    Parameters
    ----------
    ctx:
        Server context — carries ``ctx.client._event_log``.
    session_id:
        Raw session ID (no ``orch:`` / ``task:`` prefix).
    kind:
        ``"chat"`` or ``"task"``.
    from_seq:
        First seq to include in history.  ``0`` = fresh connect.
        ``N+1`` = resume after Last-Event-ID N.
    """
    event_log = ctx.client._event_log
    shutdown_event = getattr(ctx, "shutdown_event", None)

    # --- Phase 1: build snapshot from history ---------------------------------
    history = await event_log.history(session_id, kind, from_seq=from_seq)
    snapshot, max_seq_floored, raw_max_seq = _build_snapshot_frame(
        session_id, kind, from_seq, history
    )

    # Only emit a snapshot frame when there is history to summarise OR it is a
    # fresh connect (from_seq == 0).  When the client reconnects at exactly
    # max_seq we skip the snapshot entirely (nothing new to replay).
    emit_snapshot = from_seq == 0 or len(history) > 0

    if emit_snapshot:
        yield _sse_event(
            max_seq_floored,
            "snapshot",
            snapshot.model_dump_json(),
        )

    # --- Phase 2: ready sentinel ----------------------------------------------
    # When we skip the snapshot (reconnect at head: from_seq > 0, empty history),
    # max_seq_floored is 0 while the client sent Last-Event-ID = from_seq - 1.
    # Emit ready with that id so the browser does not treat id:0 as a rewind.
    ready_event_id = max_seq_floored if emit_snapshot else max(from_seq - 1, 0)
    ready = FrameReady()
    yield _sse_event(ready_event_id, "ready", ready.model_dump_json())

    # --- Phase 3: live tail ---------------------------------------------------
    # After replaying *history* into the snapshot, new rows start at
    # ``raw_max_seq + 1``.  When *history* is empty and ``from_seq > 0`` the
    # client is already caught up at Last-Event-ID — subscribing at 0 would
    # replay the entire log (duplicate frames).  Use ``from_seq`` instead.
    live_from = raw_max_seq + 1 if history else from_seq
    last_keepalive = datetime.now(UTC)

    async def _drain_live() -> AsyncIterator[str]:
        nonlocal last_keepalive
        live_iter = event_log.subscribe(session_id, kind, from_seq=live_from)
        queue: asyncio.Queue[tuple[str, Any]] = asyncio.Queue()

        async def _pump() -> None:
            try:
                async for row in live_iter:
                    await queue.put(("row", row))
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception(
                    "EventLog subscribe pump failed session={} kind={}",
                    session_id,
                    kind,
                )
            finally:
                with contextlib.suppress(Exception):
                    await live_iter.aclose()
                with contextlib.suppress(Exception):
                    await queue.put(("end", None))

        pump = asyncio.create_task(_pump())
        try:
            while True:
                if shutdown_event is not None and shutdown_event.is_set():
                    return

                now = datetime.now(UTC)
                elapsed = (now - last_keepalive).total_seconds()
                remaining_keepalive = max(0.0, _KEEPALIVE_INTERVAL - elapsed)

                try:
                    kind_msg, payload = await asyncio.wait_for(
                        queue.get(),
                        timeout=remaining_keepalive + 0.1,
                    )
                except TimeoutError:
                    now = datetime.now(UTC)
                    if (now - last_keepalive).total_seconds() >= _KEEPALIVE_INTERVAL:
                        last_keepalive = now
                        yield _sse_comment()
                else:
                    if kind_msg == "end":
                        return
                    row = payload
                    frame_dict = row.frame if isinstance(row.frame, dict) else dict(row.frame)
                    sse_kind = frame_dict.get("type")
                    if sse_kind not in ("patch", "resume"):
                        logger.warning(
                            "Live SSE tail: unexpected frame type "
                            "session={} kind={} seq={} type={}",
                            session_id,
                            kind,
                            row.seq,
                            sse_kind,
                        )
                        sse_kind = "patch"
                    frame_data = json.dumps(frame_dict)
                    yield _sse_event(row.seq, sse_kind, frame_data)
        except (GeneratorExit, asyncio.CancelledError, ConnectionError):
            return
        finally:
            pump.cancel()
            with contextlib.suppress(asyncio.CancelledError, TimeoutError):
                await asyncio.wait_for(pump, timeout=5.0)

    async for chunk in _drain_live():
        yield chunk


# ---------------------------------------------------------------------------
# Route: GET /api/sessions/{session_id}/events
# ---------------------------------------------------------------------------


async def _chat_session_events(
    request: Request, *, ctx: ServerContext
) -> StreamingResponse | JSONResponse:
    """SSE for a chat session (kind='chat').

    Resolves ``session_id`` against ChatSessions (chat-oriented EventLog).
    Returns 404 when the session does not exist.
    """
    session_id = cast("str", request.path_params["session_id"])

    # Verify session exists.
    pair = await ctx.client.chat_sessions.get_with_history(session_id)
    if pair is None:
        return _err("Session not found", status=404)

    raw_lei = request.headers.get("last-event-id")
    result = _parse_last_event_id(raw_lei)
    if isinstance(result, JSONResponse):
        return result

    from_seq = (result + 1) if result is not None else 0

    async def _stream() -> AsyncIterator[str]:
        yield _sse_retry(_RETRY_MS)
        try:
            async for chunk in _sse_generator(ctx, session_id, "chat", from_seq):
                yield chunk
        except (GeneratorExit, asyncio.CancelledError, ConnectionError):
            logger.debug("SSE client disconnected from session {}", session_id)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Route: GET /api/tasks/{task_id}/events
# ---------------------------------------------------------------------------


async def _task_events(request: Request, *, ctx: ServerContext) -> StreamingResponse | JSONResponse:
    """SSE for a task's agent session (kind='task').

    Resolves ``task_id`` → active session (PENDING/RUNNING) → fallback to
    last completed session.  Returns 404 if the task doesn't exist or has no
    sessions at all.
    """
    task_id = cast("str", request.path_params["task_id"])

    # Verify task exists (narrow catch — DB/client errors must not become 404).
    try:
        await ctx.client.tasks.get(task_id)
    except NotFoundError:
        return _err("Task not found", status=404)

    # Resolve session: prefer active, fall back to latest.
    from kagan.core.enums import SessionStatus

    all_sessions = await ctx.client.tasks.sessions.list_for_task(task_id)
    if not all_sessions:
        return _err("Task has no sessions", status=404)

    active_statuses = {SessionStatus.PENDING, SessionStatus.RUNNING}
    active = next(
        (s for s in reversed(all_sessions) if s.status in active_statuses),
        None,
    )
    session = active if active is not None else all_sessions[-1]
    session_id = session.id

    raw_lei = request.headers.get("last-event-id")
    result = _parse_last_event_id(raw_lei)
    if isinstance(result, JSONResponse):
        return result

    from_seq = (result + 1) if result is not None else 0

    async def _stream() -> AsyncIterator[str]:
        yield _sse_retry(_RETRY_MS)
        try:
            async for chunk in _sse_generator(ctx, session_id, "task", from_seq):
                yield chunk
        except (GeneratorExit, asyncio.CancelledError, ConnectionError):
            logger.debug("SSE client disconnected from task {}", task_id)

    return StreamingResponse(
        _stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------


def register_event_routes(mcp: FastMCP) -> None:
    """Register the unified SSE event endpoints."""

    @mcp.custom_route("/api/sessions/{session_id}/events", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def chat_session_events(
        request: Request, *, ctx: ServerContext
    ) -> StreamingResponse | JSONResponse:
        return await _chat_session_events(request, ctx=ctx)

    @mcp.custom_route("/api/tasks/{task_id}/sse", methods=["GET"])
    @require_context(mcp)
    @handle_errors
    async def task_events(
        request: Request, *, ctx: ServerContext
    ) -> StreamingResponse | JSONResponse:
        return await _task_events(request, ctx=ctx)
