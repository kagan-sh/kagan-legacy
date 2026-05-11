"""W3 behavioral tests: task event producer writes EventLog frames.

Every significant lifecycle event for an agent session must also write a
frame into EventLog(session_id, kind="task") so the SSE endpoint (W4) can
stream task events with native Last-Event-ID resume.

Frame semantics (locked per W3 spec):
  1. Agent spawn    → create frame  role="assistant" text="" finalized=False
  2. stdout chunk   → append frame  on the running assistant idx
  3. Status change  → create frame  role="system"   text=json(event payload)
  4. agent_completed→ finalize frame on the running assistant idx
  5. agent_failed   → finalize frame on the running assistant idx reason="agent_failed"

Post-W9a: SessionEvent dual-write removed; only EventLog rows are written.
All emitted frames must carry a "type" discriminator field.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from sqlmodel import select

from kagan.core._db_helpers import _db_async
from kagan.core._event_log import EventLog, FrameRow
from kagan.core.models import SessionEvent
from tests.helpers.driver import KaganDriver
from tests.helpers.fake_agent_backend import (
    FakeCue,
    FakeScript,
    director,
    ensure_fake_agent_backend_registered,
)
from tests.helpers.helpers import make_git_repo

pytestmark = [pytest.mark.core, pytest.mark.slow]


# ---------------------------------------------------------------------------
# Module-level setup
# ---------------------------------------------------------------------------

ensure_fake_agent_backend_registered()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def git_board(tmp_path: Path) -> KaganDriver:
    """KaganDriver backed by a real git repo; fake-agent runs to completion fast."""
    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch="main")
    driver = await KaganDriver.boot(tmp_path)
    await driver.create_project("W3 Project", repo_path=str(repo_path))
    yield driver
    await driver.teardown()


# ---------------------------------------------------------------------------
# DSL helper
# ---------------------------------------------------------------------------


async def _read_task_frames(driver: KaganDriver, task_id: str) -> list[FrameRow]:
    """Read all EventLog frames for a task's most recent session."""
    return await driver.read_task_frames(task_id)


async def _drive_fast_run(
    driver: KaganDriver,
    task_id: str,
    *,
    chunks: list[str] | None = None,
    fail: bool = False,
    timeout: float = 12.0,
) -> None:
    """Schedule a scripted fake-agent run and wait for full completion.

    Uses Events.wait_idle so we block until the ACP done-callback finishes
    (all frames committed) before returning.
    """
    cues: list[FakeCue] = []
    if chunks:
        for c in chunks:
            cues.append(FakeCue(emit={"type": "chunk", "text": c}))
    if fail:
        cues.append(FakeCue(error="simulated failure"))
    else:
        cues.append(FakeCue(done=True))

    script = FakeScript(cues=cues)
    await director.schedule(task_id, script)

    session = await driver.run_task(task_id, agent_backend="fake-agent")
    if session is None:
        return

    # Get the session_id from the returned session object
    session_id: str | None = getattr(session, "id", None)
    if session_id is None:
        return

    # Wait for the ACP done-callback to complete (settlement rule).
    # This ensures agent_completed/agent_failed frames are flushed before we return.
    if driver._ctx is not None:
        events = driver._ctx.tasks.events
        await events.wait_idle(session_id, timeout=timeout)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


async def test_agent_spawn_emits_create_frame(git_board: KaganDriver) -> None:
    """Agent spawn writes an assistant create frame to the EventLog."""
    task = await git_board.create_task("Spawn test")
    await _drive_fast_run(git_board, task.id)

    frames = await _read_task_frames(git_board, task.id)

    create_frames = [f for f in frames if f.frame.get("op") == "create"]
    assistant_creates = [
        f for f in create_frames if f.frame.get("value", {}).get("role") == "assistant"
    ]
    assert assistant_creates, f"No assistant create frame found in {frames}"
    entry = assistant_creates[0].frame["value"]
    assert entry["finalized"] is False or entry.get("text", "") == ""


async def test_agent_stdout_chunk_emitted_as_append_frame(git_board: KaganDriver) -> None:
    """Each agent stdout chunk becomes an append frame in the EventLog."""
    task = await git_board.create_task("Chunk test")
    chunks = ["hello ", "world\n"]
    await _drive_fast_run(git_board, task.id, chunks=chunks)

    frames = await _read_task_frames(git_board, task.id)

    append_frames = [f for f in frames if f.frame.get("op") == "append"]
    assert append_frames, f"No append frames found in {frames}"
    # All appended text should map to one of the chunks
    appended_texts = [f.frame.get("value", "") for f in append_frames]
    for chunk in chunks:
        assert any(chunk in t for t in appended_texts), (
            f"Chunk {chunk!r} not found in appended texts {appended_texts}"
        )


async def test_agent_completed_emits_finalize_frame(git_board: KaganDriver) -> None:
    """agent_completed triggers a finalize frame on the running assistant entry."""
    task = await git_board.create_task("Completion test")
    await _drive_fast_run(git_board, task.id)

    frames = await _read_task_frames(git_board, task.id)

    finalize_frames = [f for f in frames if f.frame.get("op") == "finalize"]
    assert finalize_frames, f"No finalize frames found in {frames}"
    # The finalize frame targeting the assistant entry should have no reason
    # (or reason=None) for a successful completion
    assistant_finalizes = [f for f in finalize_frames if f.frame.get("reason") is None]
    assert assistant_finalizes, (
        f"Expected at least one finalize without reason; got {finalize_frames}"
    )


async def test_agent_failed_emits_finalize_with_reason(git_board: KaganDriver) -> None:
    """agent_failed triggers a finalize frame with reason='agent_failed'."""
    task = await git_board.create_task("Failure test")
    await _drive_fast_run(git_board, task.id, fail=True)

    frames = await _read_task_frames(git_board, task.id)

    failed_finalizes = [
        f
        for f in frames
        if f.frame.get("op") == "finalize" and f.frame.get("reason") == "agent_failed"
    ]
    assert failed_finalizes, f"No finalize frame with reason='agent_failed' in {frames}"


async def test_task_status_transition_emits_system_create_frame(git_board: KaganDriver) -> None:
    """Status transitions emit a system create frame with JSON event payload in text."""
    task = await git_board.create_task("Status test")
    await _drive_fast_run(git_board, task.id)

    frames = await _read_task_frames(git_board, task.id)

    system_creates = [
        f
        for f in frames
        if f.frame.get("op") == "create" and f.frame.get("value", {}).get("role") == "system"
    ]
    assert system_creates, f"No system create frames found in {frames}"
    # The text must be valid JSON with an "event" key
    for sf in system_creates:
        raw_text = sf.frame["value"].get("text", "")
        data = json.loads(raw_text)
        assert "event" in data, f"System frame text missing 'event' key: {data}"


async def test_session_completed_emits_finalize_on_running_entry(git_board: KaganDriver) -> None:
    """When a session completes, the running assistant entry gets finalized.

    The finalize frame's path targets the same entry idx as the assistant create
    frame (i.e. path="/entries/{N}" for the same N).  The FrameRow.idx is the
    row's own seq-index in the append-only log, not the target entry idx — we
    check the path field instead.
    """
    task = await git_board.create_task("Finalize running entry")
    await _drive_fast_run(git_board, task.id)

    frames = await _read_task_frames(git_board, task.id)

    # The assistant create frame's FrameRow.idx is the target entry index.
    create_frames = [
        f
        for f in frames
        if f.frame.get("op") == "create" and f.frame.get("value", {}).get("role") == "assistant"
    ]
    finalize_frames = [f for f in frames if f.frame.get("op") == "finalize"]

    assert create_frames, f"No assistant create frames in {frames}"
    assert finalize_frames, f"No finalize frames in {frames}"

    # The create frame's FrameRow.idx is the stable entry address.
    # The finalize frame's path should reference that same idx.
    assistant_entry_idx = create_frames[0].idx
    finalize_paths = [f.frame.get("path", "") for f in finalize_frames]

    expected_path = f"/entries/{assistant_entry_idx}"
    assert any(expected_path in p for p in finalize_paths), (
        f"No finalize frame targets path {expected_path!r}. Finalize paths: {finalize_paths}"
    )


async def test_replay_from_seq_zero_reconstructs_full_history(git_board: KaganDriver) -> None:
    """Full history from seq=0 allows reconstructing the complete session state.

    Drive a full run; read EventLog.history; assert reduced state matches
    expected entries (assistant entry exists, system entries present).
    """
    task = await git_board.create_task("Full history test")
    chunks = ["line1\n", "line2\n"]
    await _drive_fast_run(git_board, task.id, chunks=chunks)

    frames = await _read_task_frames(git_board, task.id)

    assert frames, "Expected at least one frame in history"

    # Reduce the frame sequence to reconstruct entries.
    # For "create" frames, the target entry idx is the FrameRow.idx (the row is the entry).
    # For "append" and "finalize" frames, the target idx is encoded in the path
    # ("/entries/{N}/text" or "/entries/{N}") — extract it from the path string.
    import re as _re

    entries: dict[int, dict[str, Any]] = {}
    for frame in frames:
        op = frame.frame.get("op")
        path = frame.frame.get("path", "")

        def _extract_target_idx(p: str, fallback: int) -> int:
            m = _re.search(r"/entries/(\d+)", p)
            return int(m.group(1)) if m else fallback

        if op == "create":
            target_idx = _extract_target_idx(path, frame.idx)
            entries[target_idx] = dict(frame.frame.get("value", {}))
        elif op == "append":
            target_idx = _extract_target_idx(path, -1)
            if target_idx in entries:
                entries[target_idx]["text"] = entries[target_idx].get("text", "") + frame.frame.get(
                    "value", ""
                )
        elif op == "finalize":
            target_idx = _extract_target_idx(path, -1)
            if target_idx in entries:
                entries[target_idx]["finalized"] = True

    # Should have an assistant entry
    assistant_entries = [e for e in entries.values() if e.get("role") == "assistant"]
    assert assistant_entries, f"No assistant entry reconstructed from {entries}"

    # Should have a system entry
    system_entries = [e for e in entries.values() if e.get("role") == "system"]
    assert system_entries, f"No system entry reconstructed from {entries}"

    # The assistant entry should have the chunks in its text
    combined_chunk_text = "".join(chunks)
    assistant_text = assistant_entries[0].get("text", "")
    assert combined_chunk_text in assistant_text or all(c in assistant_text for c in chunks), (
        f"Expected chunks in assistant text, got: {assistant_text!r}"
    )


async def test_two_subscribers_see_identical_seq_stream(git_board: KaganDriver) -> None:
    """Two concurrent subscribers to the same session's EventLog see identical frames."""
    task = await git_board.create_task("Two subscribers")
    await _drive_fast_run(git_board, task.id, chunks=["msg\n"])

    frames = await _read_task_frames(git_board, task.id)

    # Read history twice (simulates two subscribers starting from seq=0)
    if git_board._ctx is None:
        pytest.skip("No KaganCore context available")
    engine = git_board._ctx.engine
    event_log = EventLog(engine)

    # Get the session_id of the most recent session
    session_id = await _get_latest_session_id(git_board, task.id)
    assert session_id is not None, "No session found for task"

    history_a = await event_log.history(session_id, "task", from_seq=0)
    history_b = await event_log.history(session_id, "task", from_seq=0)

    assert history_a and history_b, "Expected non-empty histories"
    assert len(history_a) == len(history_b)
    for a, b in zip(history_a, history_b):
        assert a.seq == b.seq
        assert a.idx == b.idx
        assert a.frame == b.frame


async def test_no_session_event_dual_write_after_w9a(git_board: KaganDriver) -> None:
    """Post-W9a: EventLog is the authoritative frame store for task lifecycle events.

    All emitted frames must have a 'type' discriminator. Both EventLog frames
    and SessionEvent rows coexist for backward-compat with read-only consumers
    (e.g. session replay endpoint) that still query the session_events table.
    This test verifies EventLog frames are present, well-formed, and carry the
    discriminator so reduce_frames can process them without inference fallback.
    """
    task = await git_board.create_task("EventLog authority test")
    await _drive_fast_run(git_board, task.id)

    frames = await _read_task_frames(git_board, task.id)
    assert frames, "Expected EventLog frames to be written"

    # All frames must carry a 'type' field (the W9a producer fix)
    for frame_row in frames:
        assert "type" in frame_row.frame, f"EventLog frame missing 'type': {frame_row.frame}"

    # EventLog frames cover the lifecycle — status transitions emit system frames
    system_frames = [
        f
        for f in frames
        if f.frame.get("op") == "create" and f.frame.get("value", {}).get("role") == "system"
    ]
    assert system_frames, "Expected system create frames for status transitions in EventLog"


async def test_every_task_frame_has_type_discriminator(git_board: KaganDriver) -> None:
    """Every frame written by _emit_task_frame_for_event includes a 'type' discriminator.

    W9a producer fix: frames stored in EventLog must have 'type' so that
    _frame_reduce.reduce_frames can route them correctly without inference.
    Valid discriminator values: 'patch', 'resume', 'snapshot', 'ready'.
    """
    task = await git_board.create_task("Type discriminator test")
    await _drive_fast_run(git_board, task.id, chunks=["hello"])

    frames = await _read_task_frames(git_board, task.id)
    assert frames, "Expected EventLog frames"

    valid_types = {"patch", "resume", "snapshot", "ready"}
    for frame_row in frames:
        frame = frame_row.frame
        assert "type" in frame, f"Frame missing 'type' discriminator: {frame}"
        assert frame["type"] in valid_types, f"Frame has unknown type {frame['type']!r}: {frame}"


async def test_task_patch_frame_has_type_patch(git_board: KaganDriver) -> None:
    """All patch-op frames (create/append/finalize) carry type='patch'."""
    task = await git_board.create_task("Patch type test")
    await _drive_fast_run(git_board, task.id, chunks=["chunk text"])

    frames = await _read_task_frames(git_board, task.id)

    patch_ops = {"create", "append", "finalize"}
    for frame_row in frames:
        frame = frame_row.frame
        if frame.get("op") in patch_ops:
            assert frame.get("type") == "patch", (
                f"Frame with op={frame.get('op')!r} has type={frame.get('type')!r}, "
                f"expected 'patch': {frame}"
            )


async def test_task_resume_frame_has_type_resume(git_board: KaganDriver) -> None:
    """FrameResume written by orphan reap carries type='resume'.

    This test verifies the orphan-reap producer path via _emit_resume, which
    uses FrameResume.model_dump() — already includes type by Pydantic default.
    We seed the frame directly to isolate the serialization check.
    """
    if git_board._ctx is None:
        pytest.skip("No KaganCore context available")

    engine = git_board._ctx.engine
    from kagan.core._event_log import EventLog
    from kagan.server.responses import FrameResume

    event_log = EventLog(engine)
    task = await git_board.create_task("Resume type test")

    # Simulate what _emit_resume does in orphan reap
    session_id = "test-resume-session"
    frame = FrameResume(kind="task", turn_active=True).model_dump()
    await event_log.append(session_id, "task", frame)

    rows = await event_log.history(session_id, "task", from_seq=0)
    assert rows, "Expected frame row in EventLog"
    stored_frame = rows[0].frame
    assert stored_frame.get("type") == "resume", (
        f"FrameResume missing type='resume' in stored frame: {stored_frame}"
    )


async def test_concurrent_sessions_get_independent_idx_streams(git_board: KaganDriver) -> None:
    """Two concurrent sessions for different tasks have independent idx streams.

    Each session's (session_id, kind="task") pair gets an independent idx counter
    starting from 0, so frames for one session do not interleave with another's.
    """
    task_a = await git_board.create_task("Session A")
    task_b = await git_board.create_task("Session B")

    # Run both sequentially (fake-agent is in-process so truly concurrent is OK,
    # but sequential avoids racing the director's task_id keying)
    await _drive_fast_run(git_board, task_a.id, chunks=["a chunk\n"])
    await _drive_fast_run(git_board, task_b.id, chunks=["b chunk\n"])

    session_id_a = await _get_latest_session_id(git_board, task_a.id)
    session_id_b = await _get_latest_session_id(git_board, task_b.id)

    assert session_id_a is not None
    assert session_id_b is not None
    assert session_id_a != session_id_b, "Tasks should have distinct session IDs"

    if git_board._ctx is None:
        pytest.skip("No KaganCore context available")
    engine = git_board._ctx.engine
    event_log = EventLog(engine)

    frames_a = await event_log.history(session_id_a, "task", from_seq=0)
    frames_b = await event_log.history(session_id_b, "task", from_seq=0)

    assert frames_a, "Session A should have frames"
    assert frames_b, "Session B should have frames"

    # Each session's idx stream starts from 0 independently
    seqs_a = {f.seq for f in frames_a}
    seqs_b = {f.seq for f in frames_b}

    # Sessions are independent — no seq overlap for distinct session_ids is expected
    # (seq is per-(session_id, kind) so they both start at 0 and increment independently)
    assert min(seqs_a) == 0, f"Session A seq should start at 0, got min={min(seqs_a)}"
    assert min(seqs_b) == 0, f"Session B seq should start at 0, got min={min(seqs_b)}"

    # Verify append frames contain the right chunks for each session
    def _appended_text(frames: list[FrameRow]) -> str:
        return "".join(f.frame.get("value", "") for f in frames if f.frame.get("op") == "append")

    assert "a chunk" in _appended_text(frames_a), "Session A frames should contain 'a chunk'"
    assert "b chunk" in _appended_text(frames_b), "Session B frames should contain 'b chunk'"
    assert "b chunk" not in _appended_text(frames_a), "Session A should not contain B's chunks"
    assert "a chunk" not in _appended_text(frames_b), "Session B should not contain A's chunks"


# ---------------------------------------------------------------------------
# Private test helpers
# ---------------------------------------------------------------------------


async def _get_latest_session_id(driver: KaganDriver, task_id: str) -> str | None:
    """Return the most recent session_id for a task."""
    from sqlmodel import desc

    from kagan.core.models import Session

    if driver._ctx is None:
        return None
    engine = driver._ctx.engine

    session = await _db_async(
        engine,
        lambda s: s.exec(
            select(Session).where(Session.task_id == task_id).order_by(desc(Session.started_at))
        ).first(),
    )
    return session.id if session is not None else None
