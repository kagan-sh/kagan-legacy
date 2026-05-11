"""Wire frame model tests for the SSE resume pattern.

Tests the Pydantic frame models added to src/kagan/server/responses.py:
  FrameEntry, FrameSnapshot, FrameReady, FramePatch, FrameResume, Frame union.

TDD: this file was committed before the implementation in responses.py.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest
from pydantic import TypeAdapter, ValidationError

pytestmark = [pytest.mark.unit]


# ── Helpers ───────────────────────────────────────────────────────────────────


def _utcnow() -> datetime:
    return datetime.now(tz=timezone.utc)


def _make_entry(idx: int = 0) -> dict:
    return {
        "idx": idx,
        "role": "assistant",
        "text": "hello",
        "finalized": False,
        "ts": _utcnow().isoformat(),
    }


# ── FrameEntry ────────────────────────────────────────────────────────────────


def test_frame_entry_valid() -> None:
    from kagan.server.responses import FrameEntry

    entry = FrameEntry(
        idx=0,
        role="assistant",
        text="hello world",
        finalized=True,
        ts=_utcnow(),
    )
    assert entry.idx == 0
    assert entry.role == "assistant"
    assert entry.finalized is True


def test_frame_entry_all_roles() -> None:
    from kagan.server.responses import FrameEntry

    for role in ("user", "assistant", "system", "tool"):
        entry = FrameEntry(idx=0, role=role, text="x", finalized=False, ts=_utcnow())  # type: ignore[arg-type]
        assert entry.role == role


def test_frame_entry_rejects_unknown_role() -> None:
    from kagan.server.responses import FrameEntry

    with pytest.raises(ValidationError):
        FrameEntry(idx=0, role="unknown", text="x", finalized=False, ts=_utcnow())  # type: ignore[arg-type]


# ── FrameSnapshot ─────────────────────────────────────────────────────────────


def test_snapshot_frame_roundtrip_json() -> None:
    from kagan.server.responses import FrameEntry, FrameSnapshot

    entry = FrameEntry(idx=0, role="user", text="hello", finalized=True, ts=_utcnow())
    snap = FrameSnapshot(
        type="snapshot",
        kind="chat",
        session_id="sess-001",
        from_seq=0,
        to_seq=5,
        entries=[entry],
    )
    raw = snap.model_dump_json()
    parsed = json.loads(raw)

    assert parsed["type"] == "snapshot"
    assert parsed["kind"] == "chat"
    assert parsed["session_id"] == "sess-001"
    assert parsed["from_seq"] == 0
    assert parsed["to_seq"] == 5
    assert len(parsed["entries"]) == 1
    assert parsed["entries"][0]["idx"] == 0

    # Roundtrip
    snap2 = FrameSnapshot.model_validate_json(raw)
    assert snap2.kind == "chat"
    assert snap2.entries[0].role == "user"


def test_snapshot_frame_kind_task() -> None:
    from kagan.server.responses import FrameSnapshot

    snap = FrameSnapshot(
        type="snapshot",
        kind="task",
        session_id="sess-002",
        from_seq=1,
        to_seq=3,
        entries=[],
    )
    assert snap.kind == "task"


def test_snapshot_frame_rejects_unknown_kind() -> None:
    from kagan.server.responses import FrameSnapshot

    with pytest.raises(ValidationError):
        FrameSnapshot(
            type="snapshot",
            kind="other",  # type: ignore[arg-type]
            session_id="x",
            from_seq=0,
            to_seq=0,
            entries=[],
        )


# ── FrameReady ────────────────────────────────────────────────────────────────


def test_ready_frame_has_no_payload() -> None:
    from kagan.server.responses import FrameReady

    frame = FrameReady(type="ready")
    dumped = json.loads(frame.model_dump_json())

    assert dumped["type"] == "ready"
    # Only "type" field — no other payload keys
    assert list(dumped.keys()) == ["type"]


# ── FramePatch ────────────────────────────────────────────────────────────────


def test_patch_create_frame_validates() -> None:
    from kagan.server.responses import FramePatch

    patch = FramePatch(
        type="patch",
        op="create",
        path="/entries/0",
        value={"idx": 0, "role": "user", "text": "hi", "finalized": False},
        reason=None,
    )
    assert patch.op == "create"
    assert patch.path == "/entries/0"
    assert patch.value is not None


def test_patch_append_frame_validates() -> None:
    from kagan.server.responses import FramePatch

    patch = FramePatch(
        type="patch",
        op="append",
        path="/entries/0/text",
        value=" more text",
        reason=None,
    )
    assert patch.op == "append"
    assert patch.path == "/entries/0/text"


def test_patch_finalize_frame_validates_with_reason() -> None:
    from kagan.server.responses import FramePatch

    patch = FramePatch(
        type="patch",
        op="finalize",
        path="/entries/2",
        value=None,
        reason="turn_end",
    )
    assert patch.op == "finalize"
    assert patch.reason == "turn_end"
    assert patch.value is None


def test_patch_rejects_unknown_op() -> None:
    from kagan.server.responses import FramePatch

    with pytest.raises(ValidationError):
        FramePatch(
            type="patch",
            op="delete",  # type: ignore[arg-type]
            path="/entries/0",
            value=None,
            reason=None,
        )


# ── FrameResume ───────────────────────────────────────────────────────────────


def test_resume_frame_carries_turn_active_bool() -> None:
    from kagan.server.responses import FrameResume

    frame = FrameResume(type="resume", kind="chat", turn_active=True)
    assert frame.turn_active is True

    frame2 = FrameResume(type="resume", kind="task", turn_active=False)
    assert frame2.turn_active is False


def test_resume_frame_rejects_unknown_kind() -> None:
    from kagan.server.responses import FrameResume

    with pytest.raises(ValidationError):
        FrameResume(type="resume", kind="other", turn_active=False)  # type: ignore[arg-type]


# ── Frame discriminated union ─────────────────────────────────────────────────


def test_discriminator_rejects_unknown_type() -> None:
    from kagan.server.responses import Frame

    adapter: TypeAdapter[Frame] = TypeAdapter(Frame)  # type: ignore[type-arg]
    with pytest.raises(ValidationError):
        adapter.validate_python({"type": "bogus"})


def test_frame_union_parses_each_variant() -> None:
    from kagan.server.responses import Frame, FramePatch, FrameReady, FrameResume, FrameSnapshot

    adapter: TypeAdapter[Frame] = TypeAdapter(Frame)  # type: ignore[type-arg]

    snapshot_raw = {
        "type": "snapshot",
        "kind": "chat",
        "session_id": "s1",
        "from_seq": 0,
        "to_seq": 1,
        "entries": [],
    }
    ready_raw = {"type": "ready"}
    patch_raw = {
        "type": "patch",
        "op": "create",
        "path": "/entries/0",
        "value": {"idx": 0, "role": "user", "text": "x", "finalized": False},
        "reason": None,
    }
    resume_raw = {"type": "resume", "kind": "task", "turn_active": False}

    snap = adapter.validate_python(snapshot_raw)
    assert isinstance(snap, FrameSnapshot)

    ready = adapter.validate_python(ready_raw)
    assert isinstance(ready, FrameReady)

    patch = adapter.validate_python(patch_raw)
    assert isinstance(patch, FramePatch)

    resume = adapter.validate_python(resume_raw)
    assert isinstance(resume, FrameResume)


# ── Path format assertions ────────────────────────────────────────────────────


def test_entry_path_format_create_op() -> None:
    """A create op path must be /entries/{idx}."""
    from kagan.server.responses import FramePatch

    idx = 3
    patch = FramePatch(
        type="patch",
        op="create",
        path=f"/entries/{idx}",
        value=_make_entry(idx),
        reason=None,
    )
    assert patch.path == f"/entries/{idx}"
    assert patch.path.startswith("/entries/")
    suffix = patch.path.removeprefix("/entries/")
    assert suffix.isdigit()


def test_entry_path_format_append_op() -> None:
    """An append op path must be /entries/{idx}/text."""
    from kagan.server.responses import FramePatch

    idx = 7
    patch = FramePatch(
        type="patch",
        op="append",
        path=f"/entries/{idx}/text",
        value=" delta",
        reason=None,
    )
    assert patch.path == f"/entries/{idx}/text"
    assert patch.path.endswith("/text")
    # Verify the idx segment is numeric
    parts = patch.path.split("/")
    assert parts[2].isdigit()


# ── TS codegen drift (Tier C carve-out) ──────────────────────────────────────


def test_generated_ts_matches_python_models() -> None:
    """Check that the checked-in wire.ts matches what generate_wire_types.py would emit.

    This is the Tier C (CI-gate) drift test.  The script already has a --check
    mode used by scripts/check_wire_drift.py; this test exercises the same
    comparison from within pytest so the full test suite catches drift too.
    """
    import subprocess
    import sys
    from pathlib import Path

    repo_root = Path(__file__).resolve().parent.parent.parent
    wire_ts = repo_root / "packages" / "shared" / "api-client" / "src" / "wire.ts"

    result = subprocess.run(
        [
            sys.executable,
            str(repo_root / "scripts" / "generate_wire_types.py"),
            "--check",
            "-o",
            str(wire_ts),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, (
        f"Wire drift detected — regenerate wire.ts:\n"
        f"  uv run python scripts/generate_wire_types.py -o {wire_ts}\n"
        f"stdout: {result.stdout}\nstderr: {result.stderr}"
    )
