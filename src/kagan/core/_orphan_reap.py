"""kagan.core._orphan_reap — Orphan session reaper.

Walks Session rows with status=RUNNING, checks whether the recorded PID is
still alive, and marks dead sessions as FAILED with a diagnostic reason.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from loguru import logger
from sqlmodel import select

from kagan.core._db_helpers import _utc_now
from kagan.core.enums import SessionStatus
from kagan.core.models import Session

if TYPE_CHECKING:
    from sqlalchemy import Engine


def _pid_alive(pid: int | None) -> bool:
    """Return True if *pid* is still running in this OS."""
    if pid is None:
        # No PID recorded — treat as orphan (session never properly started).
        return False
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        # PID exists but we don't own it — still alive.
        return True


async def reap_orphan_sessions(engine: Engine) -> int:
    """Find RUNNING sessions whose PID is dead and mark them FAILED.

    Returns the count of sessions reaped.
    """
    import asyncio

    def _op(s) -> int:
        running_sessions = list(
            s.exec(select(Session).where(Session.status == SessionStatus.RUNNING)).all()
        )
        reaped = 0
        for session in running_sessions:
            if _pid_alive(session.pid):
                continue
            logger.warning(
                "Reaping orphan session id={} task_id={} pid={}",
                session.id,
                session.task_id,
                session.pid,
            )
            session.status = SessionStatus.FAILED
            session.fail_reason = "orphan (parent process gone)"
            session.ended_at = datetime.now(UTC)
            s.add(session)
            reaped += 1
        if reaped:
            s.commit()
        return reaped

    return await asyncio.to_thread(_sync_reap, engine)


def _sync_reap(engine: Engine) -> int:
    """Synchronous implementation of orphan reap (called via asyncio.to_thread)."""
    from sqlmodel import Session as DBSession

    with DBSession(engine) as s:
        running_sessions = list(
            s.exec(select(Session).where(Session.status == SessionStatus.RUNNING)).all()
        )
        reaped = 0
        for session in running_sessions:
            if _pid_alive(session.pid):
                continue
            logger.warning(
                "Reaping orphan session id={} task_id={} pid={}",
                session.id,
                session.task_id,
                session.pid,
            )
            session.status = SessionStatus.FAILED
            session.fail_reason = "orphan (parent process gone)"
            session.ended_at = _utc_now()
            s.add(session)
            reaped += 1
        if reaped:
            s.commit()
            logger.info("Reaped {} orphan session(s)", reaped)
        return reaped


__all__ = ["reap_orphan_sessions"]
