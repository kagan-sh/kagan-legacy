"""Pure query helpers for session/agent listing.

Kept separate from ``_sessions.py`` to avoid exceeding the 2500-line LOC
budget and to keep the orchestration class (Sessions) free from query-only
concerns.

Public surface:
- ``resolve_active_session`` — pure, total; returns the "most relevant" session
- ``session_event_created_at`` — cursor timestamp for replay pagination
"""

from __future__ import annotations

from datetime import datetime  # noqa: TC003 — runtime-required by frozen dataclass slots
from typing import TYPE_CHECKING

from sqlmodel import select

from kagan.core._db_helpers import _db_async, _sa_col
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, SessionEvent

if TYPE_CHECKING:
    from sqlalchemy import Engine

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Statuses that indicate the agent is still "live" (can receive input / is running).
_ACTIVE_STATUSES: frozenset[SessionStatus] = frozenset(
    [SessionStatus.PENDING, SessionStatus.RUNNING]
)


# ---------------------------------------------------------------------------
# resolve_active_session
# ---------------------------------------------------------------------------


def _session_active(session: Session) -> bool:
    return session.status in _ACTIVE_STATUSES


def _agent_role_lower(session: Session) -> str:
    return (session.agent_role or "").lower()


def resolve_active_session(sessions: list[Session]) -> Session | None:
    """Return the single "most relevant" session from an already-loaded list.

    Priority order (mirrors Claude Code's foreground-job selection):
    1. Worker session with status in {PENDING, RUNNING}
    2. Reviewer session with status in {PENDING, RUNNING}
    3. Most-recent reviewer session (any status)
    4. Most-recent worker session (any status)
    5. None

    ``sessions`` must be the full history for a single task, in any order.
    The function is pure and total — it never raises.
    """
    if not sessions:
        return None

    workers_active = [
        s for s in sessions if _session_active(s) and _agent_role_lower(s) == "worker"
    ]
    if workers_active:
        return max(workers_active, key=lambda s: s.started_at)

    reviewers_active = [
        s for s in sessions if _session_active(s) and _agent_role_lower(s) == "reviewer"
    ]
    if reviewers_active:
        return max(reviewers_active, key=lambda s: s.started_at)

    reviewers_any = [s for s in sessions if _agent_role_lower(s) == "reviewer"]
    if reviewers_any:
        return max(reviewers_any, key=lambda s: s.started_at)

    workers_any = [s for s in sessions if _agent_role_lower(s) == "worker"]
    if workers_any:
        return max(workers_any, key=lambda s: s.started_at)

    # Fallback: most-recent session regardless of role
    return max(sessions, key=lambda s: s.started_at)


# ---------------------------------------------------------------------------
# session_event_created_at
# ---------------------------------------------------------------------------


async def session_event_created_at(
    engine: Engine,
    *,
    session_id: str,
    event_id: str,
) -> datetime | None:
    """Return the cursor timestamp for an event in a session, if it exists."""

    def _query(s) -> datetime | None:
        stmt = select(SessionEvent).where(
            _sa_col(SessionEvent.session_id) == session_id,
            _sa_col(SessionEvent.id) == event_id,
        )
        event = s.exec(stmt).first()
        return event.created_at if event is not None else None

    return await _db_async(engine, _query)


__all__ = [
    "resolve_active_session",
    "session_event_created_at",
]
