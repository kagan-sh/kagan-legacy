"""kagan.tui._event_source — EventSource interface for TUI chat/task subscriptions.

Two implementations:

``InProcEventSource``
    Talks directly to ``kagan.core._event_log.EventLog`` (the instance owned
    by ``KaganCore._event_log``).  Used for the default local-TUI mode.

``HttpEventSource``
    Talks to the server's SSE endpoints over HTTP using an injected
    ``httpx.AsyncClient``.  Used when the TUI is run in remote mode
    (``--connect``).  Carries ``Last-Event-ID`` on reconnect and implements
    automatic retry on connection loss.

Both expose the same two coroutines:

``snapshot(session_id, kind, from_seq) -> EntrySnapshot``
    Return a point-in-time snapshot of all entries from ``from_seq`` onward,
    plus the highest seq seen.  Suitable for pre-filling a chat panel on
    (re-)open.

``subscribe(session_id, kind, from_seq) -> AsyncIterator[Frame]``
    Yield a live stream of parsed :class:`~kagan.server.responses.Frame`
    objects.  For ``InProcEventSource`` this is a thin wrapper around
    ``EventLog.subscribe``.  For ``HttpEventSource`` it reconnects on
    transient errors with ``_HTTP_RETRY_DELAY`` back-off.
"""

from __future__ import annotations

import asyncio
import json
from typing import TYPE_CHECKING, Any

from loguru import logger

from kagan.server._frame_reduce import reduce_frames
from kagan.server.responses import (
    FramePatch,
    FrameReady,
    FrameResume,
    FrameSnapshot,
)
from kagan.tui._frame_reducer import Entry, EntrySnapshot

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    import httpx

    from kagan.core._event_log import EventLog, FrameRow
    from kagan.server.responses import Frame

_HTTP_RETRY_DELAY = 5.0


def _parse_frame(raw: dict[str, Any]) -> Frame | None:
    """Parse a raw dict into a typed Frame union.

    Returns ``None`` if the dict cannot be mapped to a known frame type.
    Handles all four variants: snapshot, ready, patch, resume.

    The ``"type"`` discriminator field is required.  Frames without it are
    dropped with a debug log — the W9a producer fix ensures all newly written
    frames carry ``"type"``.
    """
    frame_type = raw.get("type")
    if frame_type is None:
        logger.debug("_parse_frame: frame missing 'type' discriminator, dropping: {!r}", raw)
        return None

    try:
        if frame_type == "snapshot":
            return FrameSnapshot.model_validate(raw)
        if frame_type == "ready":
            return FrameReady.model_validate(raw)
        if frame_type == "patch":
            return FramePatch.model_validate(raw)
        if frame_type == "resume":
            return FrameResume.model_validate(raw)
    except Exception as exc:
        logger.debug("_parse_frame: failed to validate frame type={!r}: {}", frame_type, exc)
        return None

    logger.debug("_parse_frame: unknown frame type {!r}", frame_type)
    return None


def _frame_row_to_frame(row: FrameRow) -> Frame | None:
    """Convert a FrameRow from EventLog into a typed Frame."""
    return _parse_frame(row.frame)


def _reduce_rows_to_snapshot(rows: list[FrameRow], from_seq: int) -> EntrySnapshot:
    """Replay FrameRows through reduce_frames and convert to Entry objects."""
    entry_dicts, max_seq = reduce_frames(rows)
    entries = [
        Entry(
            idx=e["idx"],
            role=e["role"],
            text=e["text"],
            finalized=bool(e.get("finalized", False)),
        )
        for e in entry_dicts
    ]
    return EntrySnapshot(entries=entries, max_seq=max_seq)


# ---------------------------------------------------------------------------
# InProcEventSource
# ---------------------------------------------------------------------------


class InProcEventSource:
    """EventSource backed by the in-process EventLog instance.

    Parameters
    ----------
    event_log:
        The ``EventLog`` instance from ``KaganCore._event_log``.  Must be
        the **same** instance — using a fresh ``EventLog(engine)`` would not
        receive live-tail notifications.
    """

    def __init__(self, event_log: EventLog) -> None:
        self._event_log = event_log

    async def snapshot(
        self,
        session_id: str,
        kind: str,
        from_seq: int = 0,
    ) -> EntrySnapshot:
        """Return a snapshot of all entries from ``from_seq`` onward."""
        rows = await self._event_log.history(session_id, kind, from_seq=from_seq)
        return _reduce_rows_to_snapshot(rows, from_seq)

    async def subscribe(
        self,
        session_id: str,
        kind: str,
        from_seq: int = 0,
    ) -> AsyncIterator[Frame]:
        """Yield all frames from ``from_seq`` then tail live frames.

        Wraps ``EventLog.subscribe`` and converts each ``FrameRow`` to a
        typed ``Frame`` object.  Rows whose ``frame`` dict cannot be parsed
        are silently dropped.
        """
        async for row in self._event_log.subscribe(session_id, kind, from_seq):
            frame = _frame_row_to_frame(row)
            if frame is not None:
                yield frame  # type: ignore[misc]


# ---------------------------------------------------------------------------
# HttpEventSource
# ---------------------------------------------------------------------------


class HttpEventSource:
    """EventSource backed by the server's SSE endpoints over HTTP.

    Parameters
    ----------
    http_client:
        An ``httpx.AsyncClient`` pre-configured with auth and base URL.
    base_url:
        The server base URL (e.g. ``http://localhost:9999``).  Only used for
        constructing SSE URLs; the client itself may already have a
        ``base_url`` set.
    """

    def __init__(self, http_client: httpx.AsyncClient, base_url: str = "") -> None:
        self._client = http_client
        self._base_url = base_url.rstrip("/")

    def _chat_url(self, session_id: str) -> str:
        return f"{self._base_url}/api/sessions/{session_id}/events"

    def _task_url(self, task_id: str) -> str:
        return f"{self._base_url}/api/tasks/{task_id}/sse"

    def _url_for(self, session_id: str, kind: str) -> str:
        if kind == "task":
            return self._task_url(session_id)
        return self._chat_url(session_id)

    async def snapshot(
        self,
        session_id: str,
        kind: str,
        from_seq: int = 0,
    ) -> EntrySnapshot:
        """Fetch a snapshot by opening the SSE stream, consuming until 'ready',
        then closing.

        The server sends ``snapshot → ready`` immediately on connect;  we
        consume up to and including the ``ready`` frame, then return the
        materialised ``EntrySnapshot``.
        """
        url = self._url_for(session_id, kind)
        headers: dict[str, str] = {}
        if from_seq > 0:
            headers["Last-Event-ID"] = str(from_seq)

        entries: list[Entry] = []
        max_seq = from_seq - 1

        try:
            async with self._client.stream("GET", url, headers=headers) as response:
                if response.status_code == 404:
                    logger.debug(
                        "HttpEventSource.snapshot: 404 for session={} kind={}",
                        session_id,
                        kind,
                    )
                    return EntrySnapshot(entries=[], max_seq=-1)
                response.raise_for_status()

                async for line in response.aiter_lines():
                    line = line.strip()
                    if not line or line.startswith(":"):
                        continue
                    if line.startswith("data: "):
                        raw_str = line[6:]
                        try:
                            raw = json.loads(raw_str)
                        except json.JSONDecodeError:
                            continue
                        if not isinstance(raw, dict):
                            continue

                        # Update max_seq from the SSE id field carried in the
                        # previous "id:" line — we approximate from "to_seq"
                        frame_type = raw.get("type")
                        if frame_type == "snapshot":
                            max_seq = raw.get("to_seq", max_seq)
                            for fe in raw.get("entries", []):
                                if isinstance(fe, dict):
                                    entries.append(
                                        Entry(
                                            idx=fe.get("idx", 0),
                                            role=fe.get("role", "assistant"),
                                            text=fe.get("text", ""),
                                            finalized=bool(fe.get("finalized", False)),
                                        )
                                    )
                        elif frame_type == "ready":
                            # Stop consuming; snapshot is complete.
                            break
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.debug(
                "HttpEventSource.snapshot: error for session={} kind={}: {}",
                session_id,
                kind,
                exc,
            )
            return EntrySnapshot(entries=entries, max_seq=max_seq)

        return EntrySnapshot(entries=entries, max_seq=max_seq)

    async def subscribe(
        self,
        session_id: str,
        kind: str,
        from_seq: int = 0,
    ) -> AsyncIterator[Frame]:
        """Open an SSE stream and yield parsed Frame objects with auto-reconnect.

        Follows the ``Last-Event-ID`` resume pattern.  On any connection
        error, waits ``_HTTP_RETRY_DELAY`` seconds then reconnects from the
        last seen seq.
        """
        url = self._url_for(session_id, kind)
        last_seq = from_seq

        while True:
            headers: dict[str, str] = {}
            if last_seq > 0:
                headers["Last-Event-ID"] = str(last_seq)

            try:
                async with self._client.stream("GET", url, headers=headers) as response:
                    if response.status_code == 404:
                        logger.debug(
                            "HttpEventSource.subscribe: 404 for {} kind={}; stopping",
                            session_id,
                            kind,
                        )
                        return

                    response.raise_for_status()

                    current_id: int | None = None
                    async for line in response.aiter_lines():
                        line = line.strip()
                        if not line:
                            current_id = None
                            continue
                        if line.startswith(":"):
                            continue
                        if line.startswith("id: "):
                            import contextlib

                            with contextlib.suppress(ValueError):
                                current_id = int(line[4:])
                            continue
                        if line.startswith("data: "):
                            raw_str = line[6:]
                            try:
                                raw = json.loads(raw_str)
                            except json.JSONDecodeError:
                                continue
                            if not isinstance(raw, dict):
                                continue

                            frame = _parse_frame(raw)
                            if frame is not None:
                                if current_id is not None:
                                    last_seq = current_id
                                yield frame  # type: ignore[misc]

            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.debug(
                    "HttpEventSource.subscribe: connection lost for {} kind={}: {}",
                    session_id,
                    kind,
                    exc,
                )

            try:
                await asyncio.sleep(_HTTP_RETRY_DELAY)
            except asyncio.CancelledError:
                raise


__all__ = [
    "EntrySnapshot",
    "HttpEventSource",
    "InProcEventSource",
]
