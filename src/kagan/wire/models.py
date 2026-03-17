"""Wire-format models for Kagan remote clients.

Pure Pydantic v2 models — no SQLModel dependencies.
Field names and types match ``_task_to_dict()`` exactly.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from kagan.core._utils import utc_iso


class WireTaskActiveSession(BaseModel):
    id: str
    status: str
    mode: str
    agent_backend: str
    started_at: str
    context_window_used: int | None = None
    context_window_size: int | None = None
    cost_amount: float | None = None
    cost_currency: str | None = None


class WireReviewVerdict(BaseModel):
    criterion_index: int
    verdict: Literal["PASS", "FAIL"]
    reason: str


class WireTask(BaseModel):
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
    id: str
    name: str
    active: bool = True


class WireRepository(BaseModel):
    id: str
    project_id: str
    name: str
    path: str
    default_branch: str = "main"
    selected: bool = False


class WireSession(BaseModel):
    id: str
    task_id: str
    status: str
    mode: str
    agent_backend: str | None = None
    started_at: str
    created_at: str | None = None
    context_window_used: int | None = None
    context_window_size: int | None = None
    cost_amount: float | None = None
    cost_currency: str | None = None


class WireEvent(BaseModel):
    id: str
    session_id: str | None = None
    type: str
    payload: dict[str, object] = Field(default_factory=dict)
    created_at: str


__all__ = [
    "WireEvent",
    "WireProject",
    "WireRepository",
    "WireReviewVerdict",
    "WireSession",
    "WireTask",
    "WireTaskActiveSession",
    "utc_iso",
]
