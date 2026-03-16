"""Wire-format models for Kagan remote clients.

Pure Pydantic v2 models — no SQLModel, no kagan.core imports.
Field names and types match ``_task_to_dict()`` exactly.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from pydantic import BaseModel, Field


def utc_iso(dt: datetime | None) -> str | None:
    """Format a datetime as an ISO 8601 UTC string with trailing 'Z'.

    SQLite returns naive datetimes (no tzinfo) even though they are stored as
    UTC.  This helper normalises both naive and aware datetimes to a consistent
    ``YYYY-MM-DDTHH:MM:SS.ffffffZ`` representation so every consumer (web,
    TUI, MCP, chat) can unambiguously interpret them as UTC.
    """
    if dt is None:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(UTC).replace(tzinfo=None)
    return dt.isoformat() + "Z"


class WireTaskActiveSession(BaseModel):
    """Live session metadata associated with a task."""

    id: str
    status: str
    mode: str
    agent_backend: str
    started_at: str


class WireReviewVerdict(BaseModel):
    criterion_index: int
    verdict: Literal["PASS", "FAIL"]
    reason: str


class WireTask(BaseModel):
    """Serialisable representation of a Kagan task."""

    id: str
    title: str
    description: str = ""
    status: str = Field(
        description="Value of TaskStatus enum, e.g. 'BACKLOG'.",
    )
    priority: str = Field(
        description="Name of Priority enum, e.g. 'HIGH'.",
    )
    execution_mode: str = Field(
        description="Value of WorkMode enum, e.g. 'AUTO'.",
    )
    base_branch: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    agent_backend: str | None = None
    launcher: str | None = None
    review_approved: bool = False
    review_verdicts: list[WireReviewVerdict] = Field(default_factory=list)
    updated_at: str | None = None
    last_event_at: str | None = None
    has_workspace: bool = False
    review_running: bool = False
    active_session: WireTaskActiveSession | None = None


class WireProject(BaseModel):
    """Serialisable representation of a Kagan project."""

    id: str
    name: str
    active: bool = True


class WireRepository(BaseModel):
    """Serialisable representation of a Kagan repository."""

    id: str
    project_id: str
    name: str
    path: str
    default_branch: str = "main"
    selected: bool = False


class WireSession(BaseModel):
    """Serialisable representation of a Kagan session."""

    id: str
    task_id: str
    status: str
    mode: str
    created_at: str


class WireEvent(BaseModel):
    """Serialisable representation of a Kagan event."""

    id: str
    session_id: str
    type: str
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: str
