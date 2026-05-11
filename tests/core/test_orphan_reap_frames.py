"""Behavioral tests: orphan reap boot-time scan emits resume / finalize frames.

W5 — orphan reap must emit EventLog frames so reconnecting SSE clients can
distinguish "agent still running" from "session reaped".

PID-alive is the one process seam we stub per testing.md: ``_pid_alive``
is an OS-signal probe, not a domain rule. Fixtures ``fake_pid_alive`` and
``fake_pid_dead`` monkeypatch it to return a deterministic value so the
tests are OS-independent and do not kill real processes.

DSL surface used: ``KaganDriver.simulate_boot_reap()`` and
``KaganDriver.read_frames(session_id, kind="task")``.
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Any

import pytest

from kagan.core._event_log import EventLog
from kagan.core.enums import SessionStatus, TaskStatus
from tests.helpers.driver import KaganDriver
from tests.helpers.fixtures import board  # noqa: F401 — pytest fixture re-export

pytestmark = [pytest.mark.core]

# ---------------------------------------------------------------------------
# PID-alive monkeypatch fixtures (explicit seam per testing.md)
# ---------------------------------------------------------------------------

_ORPHAN_REAP_MODULE = "kagan.core._orphan_reap._pid_alive"


@pytest.fixture
def fake_pid_dead(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub _pid_alive to always return False (process is dead)."""
    monkeypatch.setattr(_ORPHAN_REAP_MODULE, lambda _pid: False)


@pytest.fixture
def fake_pid_alive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Stub _pid_alive to always return True (process is alive)."""
    monkeypatch.setattr(_ORPHAN_REAP_MODULE, lambda _pid: True)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_running_session(
    driver: KaganDriver,
    *,
    pid: int = 12345,
) -> tuple[str, str]:
    """Create a task + RUNNING session and return (task_id, session_id).

    Directly inserts the Session row with status=RUNNING and an assigned
    pid so orphan reap sees it on the next boot scan.
    """
    task = await driver.create_task("Orphan Test Task")
    await driver.move_task(task.id, TaskStatus.IN_PROGRESS)

    # Generate the session id so we can reference it immediately.
    # Passing id=None to the SQLModel constructor skips the factory, so
    # we generate the ID ourselves.
    session_id = uuid.uuid4().hex[:16]

    from kagan.core._db_helpers import _db_async
    from kagan.core.models import Session as AgentSession

    def _create_session(s: Any) -> None:
        row = AgentSession(
            id=session_id,
            task_id=task.id,
            agent_backend="test",
            status=SessionStatus.RUNNING,
            pid=pid,
        )
        s.add(row)
        s.commit()

    assert driver._ctx is not None
    await _db_async(driver._ctx.engine, _create_session)
    return task.id, session_id


# ---------------------------------------------------------------------------
# Dead-PID tests
# ---------------------------------------------------------------------------


async def test_dead_pid_session_emits_finalize_frame(
    board: KaganDriver,
    fake_pid_dead: None,
) -> None:
    """A session whose PID is dead AND has an open assistant entry gets a finalize frame."""
    _task_id, session_id = await _seed_running_session(board)

    # Seed an open (non-finalized) assistant entry in the EventLog.
    event_log = EventLog(board._ctx.engine)  # type: ignore[union-attr]
    await event_log.append(
        session_id,
        "task",
        {
            "type": "patch",
            "op": "create",
            "path": "/entries/0",
            "role": "assistant",
            "finalized": False,
        },
    )

    reaped = await board.simulate_boot_reap()
    assert reaped == 1

    frames = await board.read_frames(session_id)
    frame_types = [f.frame.get("type") for f in frames]
    assert "patch" in frame_types, f"Expected a 'patch' finalize frame; got {frames}"
    finalize_frames = [
        f for f in frames if f.frame.get("type") == "patch" and f.frame.get("op") == "finalize"
    ]
    assert finalize_frames, f"Expected op=finalize frame; got {frames}"


async def test_dead_pid_finalize_carries_orphan_reap_reason(
    board: KaganDriver,
    fake_pid_dead: None,
) -> None:
    """The finalize frame must carry reason='orphan_reap'."""
    _task_id, session_id = await _seed_running_session(board)

    event_log = EventLog(board._ctx.engine)  # type: ignore[union-attr]
    await event_log.append(
        session_id,
        "task",
        {
            "type": "patch",
            "op": "create",
            "path": "/entries/0",
            "role": "assistant",
            "finalized": False,
        },
    )

    await board.simulate_boot_reap()

    frames = await board.read_frames(session_id)
    finalize_frames = [f for f in frames if f.frame.get("op") == "finalize"]
    assert finalize_frames, f"No finalize frame found in {frames}"
    assert finalize_frames[-1].frame.get("reason") == "orphan_reap", (
        f"Expected reason='orphan_reap'; got {finalize_frames[-1].frame}"
    )


async def test_dead_pid_session_marked_failed_via_funnel(
    board: KaganDriver,
    fake_pid_dead: None,
) -> None:
    """Status RUNNING → FAILED via transition funnel; frame is supplementary.

    The reap call returns the count of reaped sessions, and the session
    status in the DB must be FAILED afterwards.
    """
    _task_id, session_id = await _seed_running_session(board)

    reaped = await board.simulate_boot_reap()
    assert reaped == 1

    # Verify session status via the DB.
    from kagan.core._db_helpers import _db_async
    from kagan.core.models import Session as AgentSession

    def _get_status(s: Any) -> SessionStatus:
        row = s.get(AgentSession, session_id)
        assert row is not None
        return row.status

    assert board._ctx is not None
    status = await _db_async(board._ctx.engine, _get_status)
    assert status == SessionStatus.FAILED, f"Expected FAILED, got {status}"


# ---------------------------------------------------------------------------
# Alive-PID tests
# ---------------------------------------------------------------------------


async def test_alive_pid_session_emits_resume_frame(
    board: KaganDriver,
    fake_pid_alive: None,
) -> None:
    """A session whose PID is alive gets a resume frame appended."""
    _task_id, session_id = await _seed_running_session(board)

    await board.simulate_boot_reap()

    frames = await board.read_frames(session_id)
    resume_frames = [f for f in frames if f.frame.get("type") == "resume"]
    assert resume_frames, f"Expected a 'resume' frame; got {frames}"


async def test_alive_pid_session_status_stays_running(
    board: KaganDriver,
    fake_pid_alive: None,
) -> None:
    """An alive PID must NOT change session status — stays RUNNING."""
    _task_id, session_id = await _seed_running_session(board)

    await board.simulate_boot_reap()

    from kagan.core._db_helpers import _db_async
    from kagan.core.models import Session as AgentSession

    def _get_status(s: Any) -> SessionStatus:
        row = s.get(AgentSession, session_id)
        assert row is not None
        return row.status

    assert board._ctx is not None
    status = await _db_async(board._ctx.engine, _get_status)
    assert status == SessionStatus.RUNNING, f"Expected RUNNING, got {status}"


async def test_resume_frame_carries_turn_active_true(
    board: KaganDriver,
    fake_pid_alive: None,
) -> None:
    """The resume frame must carry turn_active=True."""
    _task_id, session_id = await _seed_running_session(board)

    await board.simulate_boot_reap()

    frames = await board.read_frames(session_id)
    resume_frames = [f for f in frames if f.frame.get("type") == "resume"]
    assert resume_frames, f"No resume frame; got {frames}"
    assert resume_frames[-1].frame.get("turn_active") is True, (
        f"Expected turn_active=True; got {resume_frames[-1].frame}"
    )


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------


async def test_finalize_skipped_when_no_open_assistant_entry(
    board: KaganDriver,
    fake_pid_dead: None,
) -> None:
    """Session that died before any assistant entry → no finalize frame, only status flip.

    The EventLog remains empty (no frames) and the session is still FAILED.
    """
    _task_id, session_id = await _seed_running_session(board)
    # Do NOT add any EventLog entries — simulate a session that died immediately.

    reaped = await board.simulate_boot_reap()
    assert reaped == 1

    frames = await board.read_frames(session_id)
    finalize_frames = [f for f in frames if f.frame.get("op") == "finalize"]
    assert not finalize_frames, f"Expected no finalize frame; got {finalize_frames}"

    # Status must still be FAILED.
    from kagan.core._db_helpers import _db_async
    from kagan.core.models import Session as AgentSession

    def _get_status(s: Any) -> SessionStatus:
        row = s.get(AgentSession, session_id)
        assert row is not None
        return row.status

    assert board._ctx is not None
    status = await _db_async(board._ctx.engine, _get_status)
    assert status == SessionStatus.FAILED


# ---------------------------------------------------------------------------
# End-to-end: subscriber sees the reap outcome frame
# ---------------------------------------------------------------------------


async def test_subscriber_after_reap_sees_finalize_or_resume(
    board: KaganDriver,
) -> None:
    """End-to-end: drive a session to RUNNING, simulate boot reap, subscribe → first frame is the reap outcome.

    Tests the dead-PID path via a direct monkeypatch so the test is
    self-contained (no fixture composition needed).
    """
    _task_id, session_id = await _seed_running_session(board)

    # Seed an open assistant entry so finalize has something to latch onto.
    event_log = EventLog(board._ctx.engine)  # type: ignore[union-attr]
    await event_log.append(
        session_id,
        "task",
        {
            "type": "patch",
            "op": "create",
            "path": "/entries/0",
            "role": "assistant",
            "finalized": False,
        },
    )

    # Simulate dead PID via direct monkeypatch at module level.
    import kagan.core._orphan_reap as _reap_mod

    original = _reap_mod._pid_alive
    _reap_mod._pid_alive = lambda _pid: False
    try:
        await board.simulate_boot_reap()
    finally:
        _reap_mod._pid_alive = original

    # Subscribe from seq=0 and collect the first batch of frames.
    collected: list[dict[str, Any]] = []

    async def _collect() -> None:
        async for row in event_log.subscribe(session_id, "task", from_seq=0):
            collected.append(row.frame)
            if len(collected) >= 2:
                break

    await asyncio.wait_for(_collect(), timeout=5.0)

    # At minimum: the seeded "create" frame + the "finalize" frame from reap.
    assert len(collected) >= 2, f"Expected >=2 frames; got {collected}"
    finalize_frames = [f for f in collected if f.get("op") == "finalize"]
    assert finalize_frames, f"No finalize frame in subscriber stream; got {collected}"


__all__: list[str] = []
