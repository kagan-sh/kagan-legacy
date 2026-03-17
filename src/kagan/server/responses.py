"""Pydantic response models — single source of truth for the API wire shape.

Each model declares exactly the fields that appear in JSON responses.
``from_attributes = True`` allows projecting directly from SQLModel ORM instances
via ``Model.model_validate(orm_instance)``.

The web-facing TypeScript types are generated from JSON Schema exported by these
models (see ``scripts/generate_wire_types.py``).
"""

from __future__ import annotations

from datetime import datetime
from enum import IntEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

# ── Tiny helpers ──────────────────────────────────────────────────────────────


def _enum_name(v: Any) -> str:
    """Coerce StrEnum/IntEnum to a wire-safe string."""
    if isinstance(v, IntEnum):
        return v.name
    if hasattr(v, "value"):
        return str(v.value)
    return str(v)


def _dt_iso(v: Any) -> str | None:
    """Coerce datetime to ISO-8601 string (or pass through if already str)."""
    if v is None:
        return None
    if isinstance(v, datetime):
        return v.isoformat()
    return str(v)


class _OrmBase(BaseModel):
    """Shared config: read from ORM attributes, serialize enums by value."""

    model_config = ConfigDict(from_attributes=True)


# ── Active-session sub-shape ──────────────────────────────────────────────────


class ActiveSessionResponse(_OrmBase):
    id: str
    status: str
    mode: str
    agent_backend: str
    started_at: str
    context_window_used: int | None = None
    context_window_size: int | None = None
    cost_amount: float | None = None
    cost_currency: str | None = None

    @field_validator("status", "mode", mode="before")
    @classmethod
    def _coerce_enum(cls, v: Any) -> str:
        return _enum_name(v)

    @field_validator("started_at", mode="before")
    @classmethod
    def _coerce_dt(cls, v: Any) -> str:
        result = _dt_iso(v)
        return result or ""


# ── Task ──────────────────────────────────────────────────────────────────────


class ReviewVerdictResponse(BaseModel):
    criterion_index: int
    verdict: Literal["PASS", "FAIL"]
    reason: str


class TaskResponse(_OrmBase):
    id: str
    title: str
    description: str = ""
    status: str
    priority: str
    execution_mode: str
    base_branch: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    agent_backend: str | None = None
    launcher: str | None = None
    review_approved: bool = False
    review_verdicts: list[ReviewVerdictResponse] = Field(default_factory=list)
    updated_at: str | None = None

    # Runtime-computed (not on ORM — injected after construction)
    last_event_at: str | None = None
    has_workspace: bool = False
    review_running: bool = False
    active_session: ActiveSessionResponse | None = None

    @field_validator("status", "priority", "execution_mode", mode="before")
    @classmethod
    def _coerce_enum(cls, v: Any) -> str:
        return _enum_name(v)

    @field_validator("updated_at", mode="before")
    @classmethod
    def _coerce_dt(cls, v: Any) -> str | None:
        return _dt_iso(v)


# ── Task session (inline in /tasks/{id}/sessions) ────────────────────────────


class TaskSessionResponse(_OrmBase):
    id: str
    mode: str
    status: str
    agent_backend: str
    started_at: str

    @field_validator("mode", "status", mode="before")
    @classmethod
    def _coerce_enum(cls, v: Any) -> str:
        return _enum_name(v)

    @field_validator("started_at", mode="before")
    @classmethod
    def _coerce_dt(cls, v: Any) -> str:
        result = _dt_iso(v)
        return result or ""


# ── Project ───────────────────────────────────────────────────────────────────


class ProjectResponse(_OrmBase):
    id: str
    name: str
    active: bool = False


# ── Repository ────────────────────────────────────────────────────────────────


class RepositoryResponse(_OrmBase):
    id: str
    project_id: str
    name: str
    path: str
    default_branch: str
    selected: bool = False


# ── Session event ─────────────────────────────────────────────────────────────


class EventResponse(_OrmBase):
    id: str
    session_id: str | None = None
    type: str = Field(validation_alias="event_type")
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str

    @field_validator("type", mode="before")
    @classmethod
    def _coerce_event_type(cls, v: Any) -> str:
        """Accept both StrEnum and plain str."""
        return _enum_name(v)

    @field_validator("created_at", mode="before")
    @classmethod
    def _coerce_dt(cls, v: Any) -> str:
        result = _dt_iso(v)
        return result or ""


# ── Chat ──────────────────────────────────────────────────────────────────────


class ChatMessageResponse(BaseModel):
    role: str
    content: str


class ChatSessionSummaryResponse(BaseModel):
    id: str
    label: str
    source: str
    agent_backend: str | None = None
    updated_at: str
    message_count: int


class ChatSessionResponse(ChatSessionSummaryResponse):
    messages: list[ChatMessageResponse]


# ── Schema export helper ─────────────────────────────────────────────────────

# All response models that map to TS interfaces.
RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "ActiveSessionResponse": ActiveSessionResponse,
    "ReviewVerdictResponse": ReviewVerdictResponse,
    "TaskResponse": TaskResponse,
    "TaskSessionResponse": TaskSessionResponse,
    "ProjectResponse": ProjectResponse,
    "RepositoryResponse": RepositoryResponse,
    "EventResponse": EventResponse,
    "ChatMessageResponse": ChatMessageResponse,
    "ChatSessionSummaryResponse": ChatSessionSummaryResponse,
    "ChatSessionResponse": ChatSessionResponse,
}
