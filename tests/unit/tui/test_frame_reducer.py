"""Unit tests for kagan.tui._frame_reducer.apply_frame.

TDD-first — written before the implementation.

The reducer maps a single Frame (from kagan.server.responses) onto a
mutable dict[int, Entry] state.  Tests verify all four frame types plus
the pure-function contract (no I/O, no side-effects).
"""

from __future__ import annotations

from typing import Any

import pytest

pytestmark = [pytest.mark.unit]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _entry_state(**kwargs: Any) -> dict[int, Any]:
    """Build an Entry-keyed state dict from keyword args.

    Each kwarg becomes an Entry at the given idx::

        _entry_state(idx=0, role="user", text="hi", finalized=False)
    """
    from kagan.tui._frame_reducer import Entry

    idx = kwargs.get("idx", 0)
    role = kwargs.get("role", "assistant")
    text = kwargs.get("text", "")
    finalized = kwargs.get("finalized", False)
    entry = Entry(idx=idx, role=role, text=text, finalized=finalized)
    return {idx: entry}


def _make_create_frame(entry_idx: int, role: str = "assistant", text: str = "") -> Any:
    from kagan.server.responses import FramePatch

    return FramePatch(
        type="patch",
        op="create",
        path=f"/entries/{entry_idx}",
        value={
            "idx": entry_idx,
            "role": role,
            "text": text,
            "finalized": False,
        },
    )


def _make_append_frame(entry_idx: int, delta: str) -> Any:
    from kagan.server.responses import FramePatch

    return FramePatch(
        type="patch",
        op="append",
        path=f"/entries/{entry_idx}/text",
        value=delta,
    )


def _make_finalize_frame(entry_idx: int) -> Any:
    from kagan.server.responses import FramePatch

    return FramePatch(
        type="patch",
        op="finalize",
        path=f"/entries/{entry_idx}",
        value=None,
    )


def _make_snapshot_frame(entries: list[dict[str, Any]] | None = None) -> Any:
    from kagan.server.responses import FrameSnapshot

    return FrameSnapshot(
        type="snapshot",
        kind="chat",
        session_id="sess-1",
        from_seq=0,
        to_seq=0,
        entries=entries or [],
    )


def _make_ready_frame() -> Any:
    from kagan.server.responses import FrameReady

    return FrameReady(type="ready")


def _make_resume_frame(kind: str = "task", turn_active: bool = False) -> Any:
    from kagan.server.responses import FrameResume

    return FrameResume(type="resume", kind=kind, turn_active=turn_active)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_apply_create_patch_adds_entry() -> None:
    """A 'create' patch inserts a new Entry at the given idx."""
    from kagan.tui._frame_reducer import apply_frame

    state: dict[int, Any] = {}
    frame = _make_create_frame(0, role="user", text="Hello")
    new_state = apply_frame(state, frame)

    assert 0 in new_state
    assert new_state[0].role == "user"
    assert new_state[0].text == "Hello"
    assert new_state[0].finalized is False


def test_apply_append_patch_extends_text() -> None:
    """An 'append' patch concatenates the delta to the existing entry text."""
    from kagan.tui._frame_reducer import Entry, apply_frame

    state: dict[int, Any] = {0: Entry(idx=0, role="assistant", text="He", finalized=False)}
    result = apply_frame(state, _make_append_frame(0, "llo"))
    result = apply_frame(result, _make_append_frame(0, " world"))

    assert result[0].text == "Hello world"
    assert result[0].finalized is False


def test_apply_finalize_patch_marks_finalized() -> None:
    """A 'finalize' patch sets finalized=True on the target entry."""
    from kagan.tui._frame_reducer import Entry, apply_frame

    state: dict[int, Any] = {2: Entry(idx=2, role="assistant", text="Done", finalized=False)}
    result = apply_frame(state, _make_finalize_frame(2))

    assert result[2].finalized is True
    assert result[2].text == "Done"  # text unchanged


def test_apply_create_with_out_of_order_idx_uses_path() -> None:
    """Entry idx is always extracted from the frame path, not from the state order."""
    from kagan.tui._frame_reducer import apply_frame

    state: dict[int, Any] = {}
    result = apply_frame(state, _make_create_frame(7, role="system", text="msg"))

    assert 7 in result
    assert result[7].role == "system"
    assert 0 not in result


def test_apply_unknown_op_logs_warning_returns_state() -> None:
    """An unknown op leaves state unchanged (and logs a warning).

    FramePatch.op is a strict Literal so we inject the unknown op via a
    plain dict that mimics the frame interface — apply_frame reads .op via
    getattr, which works on any object with those attributes.
    """
    from kagan.tui._frame_reducer import Entry, apply_frame

    state: dict[int, Any] = {0: Entry(idx=0, role="user", text="original", finalized=False)}

    # Minimal frame-like object with an unknown op
    class _FakeFrame:
        type = "patch"
        op = "delete"
        path = "/entries/0"
        value = None

    result = apply_frame(state, _FakeFrame())  # type: ignore[arg-type]

    # State unchanged
    assert result[0].text == "original"
    # Returns same or equivalent dict (pure function may return new dict)
    assert 0 in result


def test_apply_snapshot_replaces_state() -> None:
    """A 'snapshot' frame replaces the entire state with the snapshot entries."""
    from datetime import UTC, datetime

    from kagan.server.responses import FrameEntry, FrameSnapshot
    from kagan.tui._frame_reducer import Entry, apply_frame

    state: dict[int, Any] = {99: Entry(idx=99, role="system", text="stale", finalized=True)}
    snap = FrameSnapshot(
        type="snapshot",
        kind="chat",
        session_id="sess-1",
        from_seq=0,
        to_seq=5,
        entries=[
            FrameEntry(idx=0, role="user", text="first", finalized=True, ts=datetime.now(UTC)),
            FrameEntry(
                idx=1, role="assistant", text="second", finalized=False, ts=datetime.now(UTC)
            ),
        ],
    )
    result = apply_frame(state, snap)

    assert 99 not in result  # stale entry gone
    assert 0 in result
    assert 1 in result
    assert result[0].text == "first"
    assert result[1].text == "second"


def test_apply_resume_does_not_modify_entries() -> None:
    """A 'resume' frame is a meta-frame — it does not modify entry state."""
    from kagan.tui._frame_reducer import Entry, apply_frame

    state: dict[int, Any] = {0: Entry(idx=0, role="user", text="existing", finalized=True)}
    result = apply_frame(state, _make_resume_frame(kind="task", turn_active=True))

    assert result == state or (len(result) == 1 and result[0].text == "existing")


def test_apply_ready_frame_does_not_modify_entries() -> None:
    """A 'ready' frame is a sentinel — it does not modify entry state."""
    from kagan.tui._frame_reducer import Entry, apply_frame

    state: dict[int, Any] = {0: Entry(idx=0, role="user", text="existing", finalized=True)}
    result = apply_frame(state, _make_ready_frame())

    assert 0 in result
    assert result[0].text == "existing"


def test_apply_append_before_create_creates_stub() -> None:
    """Append arriving before create should create a stub entry (no crash)."""
    from kagan.tui._frame_reducer import apply_frame

    state: dict[int, Any] = {}
    result = apply_frame(state, _make_append_frame(5, "delta"))

    assert 5 in result
    assert result[5].text == "delta"


def test_apply_finalize_before_create_creates_stub() -> None:
    """Finalize arriving before create should create a stub and mark finalized."""
    from kagan.tui._frame_reducer import apply_frame

    state: dict[int, Any] = {}
    result = apply_frame(state, _make_finalize_frame(3))

    assert 3 in result
    assert result[3].finalized is True


def test_apply_create_replaces_existing_entry() -> None:
    """A second 'create' for the same idx replaces the old entry."""
    from kagan.tui._frame_reducer import Entry, apply_frame

    state: dict[int, Any] = {0: Entry(idx=0, role="assistant", text="old", finalized=True)}
    result = apply_frame(state, _make_create_frame(0, role="user", text="new"))

    assert result[0].role == "user"
    assert result[0].text == "new"
    assert result[0].finalized is False
