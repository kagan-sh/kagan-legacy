"""kagan.server._frame_reduce — Replay create/append/finalize ops into entries.

Pure helper used by the SSE endpoint to build a snapshot frame from EventLog
history.  No I/O — takes an iterable of FrameRow objects and returns the
reconstructed entry list plus the highest seq seen.

Design notes
------------
- ``FrameRow.idx`` is the *log row's own* idx counter, NOT the entry idx.
  Entry idx is always extracted from the ``path`` field: ``/entries/{N}`` or
  ``/entries/{N}/text``.
- For ``create`` ops the entry's initial text and role come from ``value``.
- For ``append`` ops the delta is appended to the existing text.
- For ``finalize`` ops the entry's ``finalized`` flag is set to ``True``.
- Unknown ops emit a warning and are otherwise ignored (max_seq still advances).
- ``snapshot`` / ``ready`` frames (no ``op`` field) are silently skipped.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

from loguru import logger

if TYPE_CHECKING:
    from collections.abc import Iterable

    from kagan.core._event_log import FrameRow

# Matches /entries/N  or  /entries/N/text
_PATH_RE = re.compile(r"^/entries/(\d+)")


def _parse_entry_idx(path: str) -> int | None:
    """Extract the entry idx from a path string.  Returns None if not parseable."""
    m = _PATH_RE.match(path)
    if m is None:
        return None
    return int(m.group(1))


def _utcnow() -> datetime:
    return datetime.now(tz=UTC)


def reduce_frames(
    frames: Iterable[FrameRow],
) -> tuple[list[dict[str, Any]], int]:
    """Replay create/append/finalize ops into entries.

    Parameters
    ----------
    frames:
        Iterable of :class:`~kagan.core._event_log.FrameRow` objects in
        ascending ``seq`` order (as returned by
        :meth:`~kagan.core._event_log.EventLog.history`).

    Returns
    -------
    tuple[list[dict[str, Any]], int]
        ``(entries_sorted_by_idx, max_seq_seen)``.  When *frames* is empty the
        returned entries list is empty and max_seq is ``-1``.
    """
    # idx → mutable entry dict
    entry_map: dict[int, dict[str, Any]] = {}
    max_seq: int = -1

    for row in frames:
        max_seq = max(max_seq, row.seq)
        frame = row.frame
        if not isinstance(frame, dict):
            continue

        frame_type = frame.get("type")
        # Skip non-patch frames (snapshot, ready, resume, etc.)
        if frame_type != "patch":
            continue

        op = frame.get("op")
        path = frame.get("path", "")
        value = frame.get("value")
        entry_idx = _parse_entry_idx(path)

        if entry_idx is None:
            logger.warning("reduce_frames: unparseable path {!r} in frame, skipping", path)
            continue

        if op == "create":
            # value is a FrameEntry-shaped dict
            if isinstance(value, dict):
                entry = {
                    "idx": entry_idx,
                    "role": value.get("role", "assistant"),
                    "text": value.get("text", ""),
                    "finalized": bool(value.get("finalized", False)),
                    "ts": value.get("ts", _utcnow().isoformat()),
                }
            else:
                entry = {
                    "idx": entry_idx,
                    "role": "assistant",
                    "text": "",
                    "finalized": False,
                    "ts": _utcnow().isoformat(),
                }
            entry_map[entry_idx] = entry

        elif op == "append":
            if entry_idx not in entry_map:
                # Append arriving before create — create a stub.
                entry_map[entry_idx] = {
                    "idx": entry_idx,
                    "role": "assistant",
                    "text": "",
                    "finalized": False,
                    "ts": _utcnow().isoformat(),
                }
            delta = value if isinstance(value, str) else ""
            entry_map[entry_idx]["text"] = entry_map[entry_idx]["text"] + delta

        elif op == "finalize":
            if entry_idx not in entry_map:
                entry_map[entry_idx] = {
                    "idx": entry_idx,
                    "role": "assistant",
                    "text": "",
                    "finalized": True,
                    "ts": _utcnow().isoformat(),
                }
            else:
                entry_map[entry_idx]["finalized"] = True

        else:
            logger.warning(
                "reduce_frames: unknown op {!r} for entry_idx={}, skipping",
                op,
                entry_idx,
            )

    entries = sorted(entry_map.values(), key=lambda e: e["idx"])
    return entries, max_seq


__all__ = ["reduce_frames"]
