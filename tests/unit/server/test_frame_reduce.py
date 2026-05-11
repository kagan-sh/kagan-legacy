"""Unit tests for kagan.server._frame_reduce.reduce_frames.

TDD — committed before the implementation.

The reducer replays create/append/finalize ops from a sequence of FrameRow
objects into a list of FrameEntry-shaped dicts.  These tests verify the core
reduction logic in isolation (pure function, no I/O, no DB).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _ts() -> datetime:
    return datetime.now(tz=UTC)


def _make_row(seq: int, idx: int, frame: dict[str, Any]) -> Any:
    """Build a minimal FrameRow-compatible object for testing."""
    from kagan.core._event_log import FrameRow

    return FrameRow(seq=seq, idx=idx, ts=_ts(), frame=frame)


def _create_frame(entry_idx: int, role: str = "assistant", text: str = "") -> dict[str, Any]:
    return {
        "type": "patch",
        "op": "create",
        "path": f"/entries/{entry_idx}",
        "value": {
            "idx": entry_idx,
            "role": role,
            "text": text,
            "finalized": False,
            "ts": _ts().isoformat(),
        },
    }


def _append_frame(entry_idx: int, delta: str) -> dict[str, Any]:
    return {
        "type": "patch",
        "op": "append",
        "path": f"/entries/{entry_idx}/text",
        "value": delta,
    }


def _finalize_frame(entry_idx: int, reason: str | None = None) -> dict[str, Any]:
    frame: dict[str, Any] = {
        "type": "patch",
        "op": "finalize",
        "path": f"/entries/{entry_idx}",
        "value": None,
    }
    if reason is not None:
        frame["reason"] = reason
    return frame


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_reduce_empty_frames_returns_empty_list() -> None:
    from kagan.server._frame_reduce import reduce_frames

    entries, max_seq = reduce_frames([])
    assert entries == []
    assert max_seq == -1


def test_reduce_single_create_yields_one_entry() -> None:
    from kagan.server._frame_reduce import reduce_frames

    rows = [_make_row(0, 0, _create_frame(0, role="user", text="hello"))]
    entries, max_seq = reduce_frames(rows)

    assert len(entries) == 1
    assert entries[0]["idx"] == 0
    assert entries[0]["role"] == "user"
    assert entries[0]["text"] == "hello"
    assert entries[0]["finalized"] is False
    assert max_seq == 0


def test_reduce_append_extends_entry_text() -> None:
    from kagan.server._frame_reduce import reduce_frames

    rows = [
        _make_row(0, 0, _create_frame(0, role="assistant", text="He")),
        _make_row(1, 1, _append_frame(0, "llo")),
        _make_row(2, 2, _append_frame(0, " world")),
    ]
    entries, max_seq = reduce_frames(rows)

    assert len(entries) == 1
    assert entries[0]["text"] == "Hello world"
    assert max_seq == 2


def test_reduce_finalize_sets_finalized_true() -> None:
    from kagan.server._frame_reduce import reduce_frames

    rows = [
        _make_row(0, 0, _create_frame(0, role="assistant", text="Done")),
        _make_row(1, 1, _finalize_frame(0, reason="turn_end")),
    ]
    entries, max_seq = reduce_frames(rows)

    assert len(entries) == 1
    assert entries[0]["finalized"] is True
    assert max_seq == 1


def test_reduce_out_of_order_create_uses_path_idx() -> None:
    """Path-based idx extraction must be used, not FrameRow.idx."""
    from kagan.server._frame_reduce import reduce_frames

    # FrameRow.idx is the log row's own counter (not the entry idx).
    # Both rows have FrameRow.idx=99 but different path-based entry indices.
    rows = [
        _make_row(5, 99, _create_frame(3, role="user", text="first")),
        _make_row(6, 99, _create_frame(7, role="assistant", text="second")),
    ]
    entries, max_seq = reduce_frames(rows)

    assert len(entries) == 2
    idxs = {e["idx"] for e in entries}
    assert idxs == {3, 7}
    assert max_seq == 6


def test_reduce_ignores_unknown_op_warning_logged(caplog: pytest.LogCaptureFixture) -> None:
    import logging

    from kagan.server._frame_reduce import reduce_frames

    rows = [
        _make_row(0, 0, _create_frame(0, role="user", text="hi")),
        _make_row(1, 1, {"type": "patch", "op": "delete", "path": "/entries/0"}),
    ]
    with caplog.at_level(logging.WARNING):
        entries, max_seq = reduce_frames(rows)

    # Unrecognized op is silently ignored for entries but max_seq still advances.
    assert len(entries) == 1
    assert max_seq == 1


def test_reduce_returns_max_seq_correctly() -> None:
    from kagan.server._frame_reduce import reduce_frames

    rows = [
        _make_row(10, 0, _create_frame(0)),
        _make_row(20, 1, _append_frame(0, " more")),
        _make_row(30, 2, _finalize_frame(0)),
    ]
    _, max_seq = reduce_frames(rows)
    assert max_seq == 30


def test_reduce_multiple_entries_sorted_by_idx() -> None:
    from kagan.server._frame_reduce import reduce_frames

    rows = [
        _make_row(0, 0, _create_frame(2, role="assistant", text="second")),
        _make_row(1, 1, _create_frame(0, role="user", text="first")),
        _make_row(2, 2, _create_frame(4, role="system", text="third")),
    ]
    entries, max_seq = reduce_frames(rows)

    assert [e["idx"] for e in entries] == [0, 2, 4]
    assert max_seq == 2


def test_reduce_append_before_create_is_tolerated() -> None:
    """Append arriving before create (from seq ordering) creates a stub entry."""
    from kagan.server._frame_reduce import reduce_frames

    rows = [
        _make_row(0, 0, _append_frame(5, "text")),
    ]
    # Should not raise; entry idx=5 is created implicitly.
    entries, max_seq = reduce_frames(rows)
    # The append text must be incorporated.
    assert any(e["idx"] == 5 for e in entries)
    assert max_seq == 0


def test_reduce_snapshot_frames_are_skipped() -> None:
    """Frames of type 'snapshot' or 'ready' have no op to reduce."""
    from kagan.server._frame_reduce import reduce_frames

    rows = [
        _make_row(0, 0, {"type": "snapshot", "kind": "chat", "entries": []}),
        _make_row(1, 1, _create_frame(0, role="user", text="real")),
        _make_row(2, 2, {"type": "ready"}),
    ]
    entries, max_seq = reduce_frames(rows)

    assert len(entries) == 1
    assert entries[0]["text"] == "real"
    assert max_seq == 2
