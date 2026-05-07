"""Pure query helpers for session/agent listing.

Kept separate from ``_sessions.py`` to avoid exceeding the 2500-line LOC
budget and to keep the orchestration class (Sessions) free from query-only
concerns.

Public surface:
- ``ActiveAgentRow`` — typed dataclass returned by ``list_running_agents``
- ``resolve_active_session`` — pure, total; returns the "most relevant" session
- ``list_running_agents`` — cross-task joined query, optionally scoped to project
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 — runtime-required by frozen dataclass slots
from typing import TYPE_CHECKING

from sqlmodel import desc, select

from kagan.core._db_helpers import _db_async, _sa_col
from kagan.core.enums import SessionStatus
from kagan.core.models import Session, Task

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
# Typed row for running-agents query
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ActiveAgentRow:
    """Joined projection of Task + Session for a live or recent agent session.

    Returned by ``list_running_agents``.  All fields are plain Python types so
    the dataclass is JSON-safe after serialisation.
    """

    task_id: str
    task_title: str
    task_status: str
    session_id: str
    agent_role: str | None
    agent_backend: str
    session_status: str
    started_at: datetime
    last_event_at: datetime | None
    input_tokens: int | None
    output_tokens: int | None


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
# list_running_agents (DB query)
# ---------------------------------------------------------------------------


async def list_running_agents(
    engine: Engine,
    *,
    project_id: str | None = None,
) -> list[ActiveAgentRow]:
    """Return all sessions currently in an active status, joined with their task.

    The join is performed inside a single DB transaction for consistency.
    Results are sorted by ``started_at DESC``.

    When *project_id* is provided, only sessions belonging to tasks in that
    project are included.
    """

    def _query(s) -> list[ActiveAgentRow]:
        # Build the base statement: join Session → Task on active sessions only.
        stmt = (
            select(Session, Task)
            .join(Task, _sa_col(Session.task_id) == _sa_col(Task.id))
            .where(_sa_col(Session.status).in_(list(_ACTIVE_STATUSES)))
            .order_by(desc(_sa_col(Session.started_at)))
        )
        if project_id is not None:
            stmt = stmt.where(_sa_col(Task.project_id) == project_id)

        rows = s.exec(stmt).all()
        result: list[ActiveAgentRow] = []
        for session, task in rows:
            result.append(
                ActiveAgentRow(
                    task_id=task.id,
                    task_title=task.title,
                    task_status=(
                        task.status.value if hasattr(task.status, "value") else str(task.status)
                    ),
                    session_id=session.id,
                    agent_role=session.agent_role,
                    agent_backend=session.agent_backend,
                    session_status=(
                        session.status.value
                        if hasattr(session.status, "value")
                        else str(session.status)
                    ),
                    started_at=session.started_at,
                    last_event_at=session.ended_at,
                    input_tokens=session.input_tokens,
                    output_tokens=session.output_tokens,
                )
            )
        return result

    return await _db_async(engine, _query)


__all__ = [
    "ActiveAgentRow",
    "list_running_agents",
    "resolve_active_session",
]
