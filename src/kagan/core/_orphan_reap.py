"""kagan.core._orphan_reap — Orphan session reaper.

Walks Session rows with status=RUNNING, checks whether the recorded PID is
still alive, and:

- Alive PID  → appends a ``FrameResume`` to the EventLog so reconnecting
  clients see "agent still running" and can resume their stream.
- Dead PID   → marks the session FAILED via ``transition_session_in_db``
  (the status funnel), cascades the parent task back to BACKLOG, and
  appends a ``FramePatch(op="finalize")`` to the EventLog if an open
  assistant entry exists.

Frame appends happen AFTER the status transition commits so the frame
ordering reflects the post-transition state.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING, Any

from loguru import logger
from sqlmodel import select

from kagan.core._db_helpers import _db_async, _db_sync, _utc_now
from kagan.core._event_log import EventLog
from kagan.core.enums import SessionStatus, TaskStatus
from kagan.core.models import EventLogEntry, Session, Task

if TYPE_CHECKING:
    from sqlalchemy import Engine

    from kagan.core.client import KaganCore


def _pid_alive(pid: int | None) -> bool:
    """Return True if *pid* is still running in this OS."""
    if pid is None:
        return False
    if os.name == "nt":
        return _pid_alive_windows(pid)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _pid_alive_windows(pid: int) -> bool:
    """Return True if *pid* is running on Windows without signalling it."""
    import ctypes
    from ctypes import wintypes

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.GetExitCodeProcess.argtypes = [
        wintypes.HANDLE,
        ctypes.POINTER(wintypes.DWORD),
    ]
    kernel32.GetExitCodeProcess.restype = wintypes.BOOL
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    kernel32.CloseHandle.restype = wintypes.BOOL

    process_query_limited_information = 0x1000
    still_active = 259

    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        # ERROR_ACCESS_DENIED means the process exists but cannot be queried.
        return ctypes.get_last_error() == 5

    try:
        exit_code = wintypes.DWORD()
        if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
            return ctypes.get_last_error() == 5
        return exit_code.value == still_active
    finally:
        kernel32.CloseHandle(handle)


def _last_open_assistant_idx(engine: Engine, session_id: str) -> int | None:
    """Return idx of the last non-finalized assistant entry for *session_id*.

    Scans the EventLog for ``kind="task"`` frames emitted by the session,
    finds the most recent frame whose payload has ``role="assistant"`` and
    ``finalized`` set to ``False`` (or absent), and returns its ``idx``.
    Returns ``None`` when no such entry exists.
    """

    def _query(s) -> int | None:
        stmt = (
            select(EventLogEntry)
            .where(
                EventLogEntry.session_id == session_id,
                EventLogEntry.kind == "task",
            )
            .order_by(EventLogEntry.idx.desc())  # type: ignore[union-attr]
        )
        rows = list(s.exec(stmt).all())
        for row in rows:
            frame: dict[str, Any] = row.frame or {}
            if frame.get("role") == "assistant" and not frame.get("finalized", True):
                return row.idx
        return None

    return _db_sync(engine, _query)


async def _emit_resume(event_log: EventLog, session_id: str) -> None:
    """Append a FrameResume to signal the agent PID is still alive."""
    from kagan.server.responses import FrameResume

    frame = FrameResume(kind="task", turn_active=True).model_dump()
    await event_log.append(session_id, "task", frame)
    logger.debug("orphan_reap: emitted resume frame for session={}", session_id)


async def _emit_finalize(event_log: EventLog, session_id: str, idx: int) -> None:
    """Append a FramePatch(op=finalize) to close the open assistant entry."""
    from kagan.server.responses import FramePatch

    frame = FramePatch(
        op="finalize",
        path=f"/entries/{idx}",
        reason="orphan_reap",
    ).model_dump()
    await event_log.append(session_id, "task", frame)
    logger.debug(
        "orphan_reap: emitted finalize frame for session={} idx={}",
        session_id,
        idx,
    )


def _mark_session_failed(s: Any, session_id: str) -> None:
    """Transition *session_id* to FAILED inside an open DB session.

    Uses ``transition_session_in_db`` so the (from, to) matrix is enforced.
    Also writes ``fail_reason`` and ``ended_at`` in the same transaction.
    """
    from kagan.core.transitions import transition_session_in_db

    result = transition_session_in_db(s, session_id, SessionStatus.FAILED, strict=False)
    if result is not None:
        row, _ = result
        row.fail_reason = "orphan (parent process gone)"
        row.ended_at = _utc_now()
        s.add(row)
    s.commit()


def _has_other_running(s: Any, task_id: str, exclude_session_id: str) -> bool:
    """Return True if any other RUNNING session exists for *task_id*."""
    other = s.exec(
        select(Session).where(
            Session.task_id == task_id,
            Session.status == SessionStatus.RUNNING,
            Session.id != exclude_session_id,
        )
    ).first()
    return other is not None


def _cascade_task_to_backlog(s: Any, task_id: str) -> None:
    """Move *task_id* from IN_PROGRESS to BACKLOG inside an open DB session."""
    db_task = s.get(Task, task_id)
    if db_task is not None and db_task.status == TaskStatus.IN_PROGRESS:
        db_task.status = TaskStatus.BACKLOG
        s.add(db_task)
        s.commit()
        logger.info(
            "Cascaded orphan reap to task id={}: IN_PROGRESS → BACKLOG",
            task_id,
        )


async def _reap_one(engine: Engine, event_log: EventLog, session: Session) -> None:
    """Reap a single dead-PID session: transition → FAILED, cascade task, emit frame."""
    session_id = session.id
    task_id = session.task_id

    logger.warning(
        "Reaping orphan session id={} task_id={} pid={}",
        session_id,
        task_id,
        session.pid,
    )

    # Capture open assistant idx BEFORE the status transition.
    open_idx = _last_open_assistant_idx(engine, session_id)

    # Transition session → FAILED.
    await _db_async(engine, lambda s: _mark_session_failed(s, session_id))

    # Cascade task → BACKLOG if no other RUNNING sessions remain.
    no_others = not await _db_async(engine, lambda s: _has_other_running(s, task_id, session_id))
    if no_others:
        await _db_async(engine, lambda s: _cascade_task_to_backlog(s, task_id))

    logger.info("Reaped orphan session id={}", session_id)

    # Emit finalize frame AFTER the status transition commits.
    if open_idx is not None:
        await _emit_finalize(event_log, session_id, open_idx)


async def reap_orphan_sessions(client: KaganCore) -> int:
    """Find RUNNING sessions whose PID is dead and mark them FAILED.

    For each RUNNING session:
    - Alive PID  → emit a ``FrameResume`` (type="resume") into the EventLog
      so reconnecting SSE clients know the agent is still running.
    - Dead PID   → transition session → FAILED via the status funnel,
      cascade task → BACKLOG, then emit a ``FramePatch(op="finalize")``
      if an open (non-finalized) assistant entry exists in the EventLog.

    Frame appends happen after the status transition commits.

    Returns the count of sessions reaped (dead-PID only).
    """
    engine = client.engine

    def _list_running(s) -> list[Session]:
        return list(s.exec(select(Session).where(Session.status == SessionStatus.RUNNING)).all())

    running_sessions = await _db_async(engine, _list_running)

    event_log = EventLog(engine)
    reaped = 0

    for session in running_sessions:
        if _pid_alive(session.pid):
            # PID still alive — emit a resume frame; do not touch status.
            logger.info(
                "orphan_reap: session id={} pid={} is alive; emitting resume frame",
                session.id,
                session.pid,
            )
            await _emit_resume(event_log, session.id)
            continue

        await _reap_one(engine, event_log, session)
        reaped += 1

    if reaped:
        logger.info("Reaped {} orphan session(s)", reaped)
    return reaped


__all__ = ["reap_orphan_sessions"]
