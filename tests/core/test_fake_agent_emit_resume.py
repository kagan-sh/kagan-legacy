"""Behavioral tests: FakeAgent.emit_resume_frame injects a FrameResume into the EventLog.

These tests exercise the explicit test knob that lets Playwright and behavioral
specs trigger the resume-notice UX path without orchestrating a real orphan reap.

DSL surface used:
    ``KaganDriver.emit_resume_frame(session_id, kind, turn_active)``
    ``KaganDriver.read_frames(session_id, kind)``

The tests assert observable outcomes — frame presence and field values — without
importing from ``kagan.core._fake_agent`` directly.
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
# Helpers
# ---------------------------------------------------------------------------


async def _create_chat_session(driver: KaganDriver) -> str:
    """Create a bare chat session and return its id."""
    session = await driver.chat_create_session(source="test", label="resume-test")
    return session["id"]


async def _seed_running_task_session(
    driver: KaganDriver,
    *,
    pid: int = 99999,
) -> tuple[str, str]:
    """Create a task + RUNNING agent session; return (task_id, session_id)."""
    task = await driver.create_task("Emit-Resume Task")
    await driver.move_task(task.id, TaskStatus.IN_PROGRESS)

    session_id = uuid.uuid4().hex[:16]

    from kagan.core._db_helpers import _db_async
    from kagan.core.models import Session as AgentSession

    def _create(s: Any) -> None:
        row = AgentSession(
            id=session_id,
            task_id=task.id,
            agent_backend="fake-agent",
            status=SessionStatus.RUNNING,
            pid=pid,
        )
        s.add(row)
        s.commit()

    assert driver._ctx is not None
    await _db_async(driver._ctx.engine, _create)
    return task.id, session_id


# ---------------------------------------------------------------------------
# Task-kind resume frame tests
# ---------------------------------------------------------------------------


async def test_emit_resume_frame_appends_resume_frame(board: KaganDriver) -> None:
    """emit_resume_frame writes a FrameResume to the EventLog for kind='task'."""
    _task_id, session_id = await _seed_running_task_session(board)

    seq = await board.emit_resume_frame(session_id, kind="task", turn_active=True)

    assert seq >= 0, f"Expected a non-negative seq; got {seq}"
    frames = await board.read_frames(session_id, kind="task")
    resume_frames = [f for f in frames if f.frame.get("type") == "resume"]
    assert resume_frames, f"Expected at least one 'resume' frame; got {frames}"


async def test_emit_resume_frame_turn_active_true(board: KaganDriver) -> None:
    """FrameResume carries turn_active=True when requested."""
    _task_id, session_id = await _seed_running_task_session(board)

    await board.emit_resume_frame(session_id, kind="task", turn_active=True)

    frames = await board.read_frames(session_id, kind="task")
    resume_frames = [f for f in frames if f.frame.get("type") == "resume"]
    assert resume_frames, f"No resume frame found; got {frames}"
    assert resume_frames[-1].frame.get("turn_active") is True, (
        f"Expected turn_active=True; got {resume_frames[-1].frame}"
    )


async def test_emit_resume_frame_turn_active_false(board: KaganDriver) -> None:
    """FrameResume carries turn_active=False when turn is idle."""
    _task_id, session_id = await _seed_running_task_session(board)

    await board.emit_resume_frame(session_id, kind="task", turn_active=False)

    frames = await board.read_frames(session_id, kind="task")
    resume_frames = [f for f in frames if f.frame.get("type") == "resume"]
    assert resume_frames, f"No resume frame found; got {frames}"
    assert resume_frames[-1].frame.get("turn_active") is False, (
        f"Expected turn_active=False; got {resume_frames[-1].frame}"
    )


async def test_emit_resume_frame_kind_field_is_task(board: KaganDriver) -> None:
    """The persisted frame has kind='task' matching the requested kind."""
    _task_id, session_id = await _seed_running_task_session(board)

    await board.emit_resume_frame(session_id, kind="task", turn_active=True)

    frames = await board.read_frames(session_id, kind="task")
    resume_frames = [f for f in frames if f.frame.get("type") == "resume"]
    assert resume_frames, f"No resume frame found; got {frames}"
    assert resume_frames[-1].frame.get("kind") == "task", (
        f"Expected kind='task'; got {resume_frames[-1].frame}"
    )


# ---------------------------------------------------------------------------
# Chat-kind resume frame tests
# ---------------------------------------------------------------------------


async def test_emit_resume_frame_chat_kind(board: KaganDriver) -> None:
    """emit_resume_frame works for kind='chat' sessions."""
    session_id = await _create_chat_session(board)

    seq = await board.emit_resume_frame(session_id, kind="chat", turn_active=True)

    assert seq >= 0, f"Expected a non-negative seq; got {seq}"

    # Read frames from the chat kind bucket.
    assert board._ctx is not None
    event_log = EventLog(board._ctx.engine)
    rows = await event_log.history(session_id, "chat")
    resume_frames = [r for r in rows if r.frame.get("type") == "resume"]
    assert resume_frames, f"Expected a 'resume' frame in chat kind; got {rows}"
    assert resume_frames[-1].frame.get("kind") == "chat", (
        f"Expected kind='chat'; got {resume_frames[-1].frame}"
    )


# ---------------------------------------------------------------------------
# Returns seq
# ---------------------------------------------------------------------------


async def test_emit_resume_frame_returns_seq(board: KaganDriver) -> None:
    """emit_resume_frame returns the monotonically-increasing seq."""
    _task_id, session_id = await _seed_running_task_session(board)

    seq0 = await board.emit_resume_frame(session_id, kind="task", turn_active=True)
    seq1 = await board.emit_resume_frame(session_id, kind="task", turn_active=False)

    assert seq1 > seq0, f"seq must increase monotonically; got seq0={seq0} seq1={seq1}"


# ---------------------------------------------------------------------------
# Subscriber sees the injected frame
# ---------------------------------------------------------------------------


async def test_emit_resume_frame_subscriber_sees_frame(board: KaganDriver) -> None:
    """A subscriber replaying EventLog history sees the resume frame after emission.

    Emits a resume frame and then subscribes from seq=0 so the frame is
    served from the backlog phase.  This confirms that the frame is durably
    persisted and visible to any reconnecting SSE client — the same code path
    used by the ``useEntryStream`` hook on page reload.
    """
    _task_id, session_id = await _seed_running_task_session(board)

    assert board._ctx is not None
    event_log = EventLog(board._ctx.engine)

    # Emit first so the frame is in the DB.
    await board.emit_resume_frame(session_id, kind="task", turn_active=True)

    collected: list[dict[str, Any]] = []

    async def _collect() -> None:
        async for row in event_log.subscribe(session_id, "task", from_seq=0):
            collected.append(row.frame)
            if collected and collected[-1].get("type") == "resume":
                break

    # The subscriber drains the backlog then waits for live frames.
    # Since we already emitted, the frame is in the backlog → no live wait needed.
    await asyncio.wait_for(_collect(), timeout=5.0)

    resume_frames = [f for f in collected if f.get("type") == "resume"]
    assert resume_frames, f"Subscriber never received a resume frame; got {collected}"
    assert resume_frames[-1].get("turn_active") is True, (
        f"Expected turn_active=True in subscriber frame; got {resume_frames[-1]}"
    )


__all__: list[str] = []
