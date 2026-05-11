"""kagan.tui._frame_reducer — Pure TUI-side frame → Entry state reducer.

Mirrors the server-side ``reduce_frames`` pure function but operates on
:class:`Frame` union values (not raw ``FrameRow`` objects) and maintains
state as a ``dict[int, Entry]`` keyed on entry idx.

Usage::

    from kagan.tui._frame_reducer import Entry, apply_frame

    state: dict[int, Entry] = {}
    for frame in frames:
        state = apply_frame(state, frame)

Design notes
------------
- ``apply_frame`` is a **pure** function — it never mutates *state* in-place;
  it returns a new dict (or the same dict if no change is needed).
- ``FrameSnapshot`` replaces the entire state from the snapshot's
  ``entries`` list.
- ``FramePatch`` with ``op="create"`` inserts or replaces an entry.
- ``FramePatch`` with ``op="append"`` extends the text of an existing entry
  (creates a stub if the entry is missing — out-of-order tolerance).
- ``FramePatch`` with ``op="finalize"`` sets ``finalized=True`` (creates a
  stub if missing).
- Unknown ops log a warning and return state unchanged.
- ``FrameReady`` and ``FrameResume`` are meta-frames; they do not touch
  entry state.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Literal

from loguru import logger

if TYPE_CHECKING:
    from kagan.server.responses import Frame

# Matches /entries/N  or  /entries/N/text (same regex as server-side reducer)
_PATH_RE = re.compile(r"^/entries/(\d+)")


def _parse_entry_idx(path: str) -> int | None:
    """Extract the entry idx from a path string.  Returns None if not parseable."""
    m = _PATH_RE.match(path)
    if m is None:
        return None
    return int(m.group(1))


# ---------------------------------------------------------------------------
# Entry dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Entry:
    """Immutable snapshot of a single conversation/log entry.

    Corresponds to ``FrameEntry`` on the wire but is keyed by ``idx`` and
    stored in the TUI's local ``dict[int, Entry]`` state.
    """

    idx: int
    role: Literal["user", "assistant", "system", "tool"]
    text: str
    finalized: bool


# ---------------------------------------------------------------------------
# EntrySnapshot — result of snapshot()
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EntrySnapshot:
    """Result of an EventSource.snapshot() call."""

    entries: list[Entry]
    max_seq: int


# ---------------------------------------------------------------------------
# apply_frame — pure state transition
# ---------------------------------------------------------------------------


def apply_frame(state: dict[int, Entry], frame: Frame) -> dict[int, Entry]:
    """Apply one SSE frame to the TUI-local entry state.

    Parameters
    ----------
    state:
        Current ``{entry_idx: Entry}`` mapping.  The function never mutates
        this dict — it always returns a new dict (or the input dict when
        no change is warranted, e.g. for ``ready`` / ``resume`` frames).
    frame:
        A parsed ``Frame`` union value (``FrameSnapshot | FrameReady |
        FramePatch | FrameResume``) as defined in
        ``kagan.server.responses``.

    Returns
    -------
    dict[int, Entry]
        Updated state.
    """
    frame_type: str = getattr(frame, "type", "")

    if frame_type == "snapshot":
        return _apply_snapshot(frame)

    if frame_type == "patch":
        return _apply_patch(state, frame)

    # "ready" and "resume" are meta-frames — no entry mutations.
    if frame_type in ("ready", "resume"):
        return state

    logger.warning("apply_frame: unrecognised frame type {!r}, skipping", frame_type)
    return state


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _apply_snapshot(frame: Any) -> dict[int, Entry]:
    """Replace state entirely from FrameSnapshot.entries."""
    new_state: dict[int, Entry] = {}
    for fe in frame.entries:
        entry = Entry(
            idx=fe.idx,
            role=fe.role,
            text=fe.text,
            finalized=fe.finalized,
        )
        new_state[fe.idx] = entry
    return new_state


def _apply_patch(state: dict[int, Entry], frame: Any) -> dict[int, Entry]:
    """Dispatch create / append / finalize patch ops."""
    op: str = getattr(frame, "op", "")
    path: str = getattr(frame, "path", "")
    value: Any = getattr(frame, "value", None)

    entry_idx = _parse_entry_idx(path)
    if entry_idx is None:
        logger.warning("apply_frame: unparseable path {!r} in patch frame, skipping", path)
        return state

    new_state = dict(state)  # shallow copy so we don't mutate caller's dict

    if op == "create":
        if isinstance(value, dict):
            new_state[entry_idx] = Entry(
                idx=entry_idx,
                role=value.get("role", "assistant"),
                text=value.get("text", ""),
                finalized=bool(value.get("finalized", False)),
            )
        else:
            new_state[entry_idx] = Entry(
                idx=entry_idx,
                role="assistant",
                text="",
                finalized=False,
            )

    elif op == "append":
        existing = new_state.get(entry_idx)
        if existing is None:
            # Out-of-order append — create stub
            existing = Entry(idx=entry_idx, role="assistant", text="", finalized=False)
        delta = value if isinstance(value, str) else ""
        new_state[entry_idx] = Entry(
            idx=existing.idx,
            role=existing.role,
            text=existing.text + delta,
            finalized=existing.finalized,
        )

    elif op == "finalize":
        existing = new_state.get(entry_idx)
        if existing is None:
            new_state[entry_idx] = Entry(idx=entry_idx, role="assistant", text="", finalized=True)
        else:
            new_state[entry_idx] = Entry(
                idx=existing.idx,
                role=existing.role,
                text=existing.text,
                finalized=True,
            )

    else:
        logger.warning("apply_frame: unknown op {!r} for entry_idx={}, skipping", op, entry_idx)
        return state

    return new_state


__all__ = ["Entry", "EntrySnapshot", "apply_frame"]
