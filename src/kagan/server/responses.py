"""Pydantic response models — single source of truth for the API wire shape.

Each model declares exactly the fields that appear in JSON responses.
``from_attributes = True`` allows projecting directly from SQLModel ORM instances
via ``Model.model_validate(orm_instance)``.

The web-facing TypeScript types are generated from JSON Schema exported by these
models (see ``scripts/generate_wire_types.py``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_serializer, field_validator

from kagan.core.enums import Priority, SessionStatus, TaskStatus

# ── Tiny helpers ──────────────────────────────────────────────────────────────


def _enum_name(v: Any) -> str:
    """Coerce StrEnum/IntEnum to a wire-safe string name."""
    if hasattr(v, "name"):
        return str(v.name)
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


class _SessionSummaryBase(_OrmBase):
    status: SessionStatus
    started_at: str

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> SessionStatus:
        if isinstance(v, SessionStatus):
            return v
        return SessionStatus(str(v))

    @field_validator("started_at", mode="before")
    @classmethod
    def _coerce_started_at(cls, v: Any) -> str:
        result = _dt_iso(v)
        return result or ""

    @field_serializer("status")
    def _serialize_status(self, v: SessionStatus) -> str:
        return v.value


# ── Active-session sub-shape ──────────────────────────────────────────────────


class ActiveSessionResponse(_SessionSummaryBase):
    id: str
    launcher: str | None = None
    agent_backend: str
    agent_role: str | None = None
    context_window_used: int | None = None
    context_window_size: int | None = None
    cost_amount: float | None = None
    cost_currency: str | None = None


# ── Acceptance criterion ──────────────────────────────────────────────────────


class AcceptanceCriterionResponse(_OrmBase):
    id: str
    task_id: str
    ordinal: int
    text: str


# ── Review verdict ────────────────────────────────────────────────────────────


ReviewVerdictState = Literal["PASS", "FAIL", "SKIP"]


class ReviewVerdictResponse(_OrmBase):
    id: str
    criterion_id: str
    session_id: str | None = None
    verdict: ReviewVerdictState
    reason: str

    @field_validator("verdict", mode="before")
    @classmethod
    def _normalize_verdict(cls, v: Any) -> str:
        # The DB stores lowercase pass/fail/skip; the wire shape (and existing
        # TS clients) standardise on uppercase. Normalise here so neither side
        # has to care about casing.
        if v is None:
            return "FAIL"
        normalized = str(v).strip().upper()
        if normalized not in {"PASS", "FAIL", "SKIP"}:
            return "FAIL"
        return normalized


# ── Task ──────────────────────────────────────────────────────────────────────


class BackendSelectionResponse(BaseModel):
    """Metadata about intelligent backend selection."""

    selected_backend: str
    backend_confidence: float = Field(ge=0.0, le=1.0)
    backend_reason: str
    alternatives: list[str] = Field(default_factory=list)


class DiffSummaryResponse(BaseModel):
    """Inline diff statistics attached to REVIEW-status tasks that have a worktree."""

    files_changed: int
    additions: int
    deletions: int


class TaskResponse(_OrmBase):
    id: str
    title: str
    description: str = ""
    status: TaskStatus
    priority: Priority
    base_branch: str | None = None
    repo_id: str | None = None
    github_issue: str | None = None
    # criteria is the ORM relationship name; acceptance_criteria is the wire name
    acceptance_criteria: list[AcceptanceCriterionResponse] = Field(
        default_factory=list, validation_alias="criteria"
    )
    agent_backend: str | None = None
    launcher: str | None = None
    # Computed server-side from ReviewVerdict table (no stored field)
    review_approved: bool = False
    updated_at: str | None = None

    # Runtime-computed (not on ORM — injected after construction)
    last_event_at: str | None = None
    has_workspace: bool = False
    review_running: bool = False
    review_verdicts: list[ReviewVerdictResponse] = Field(default_factory=list)
    active_session: ActiveSessionResponse | None = None
    backend_selection: BackendSelectionResponse | None = None
    diff_summary: DiffSummaryResponse | None = None

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    @field_validator("status", mode="before")
    @classmethod
    def _coerce_status(cls, v: Any) -> TaskStatus:
        if isinstance(v, TaskStatus):
            return v
        return TaskStatus(str(v))

    @field_validator("priority", mode="before")
    @classmethod
    def _coerce_priority(cls, v: Any) -> Priority:
        if isinstance(v, Priority):
            return v
        # Handle int values (stored as IntEnum)
        try:
            return Priority(int(v))
        except (ValueError, TypeError):
            return Priority[str(v)]

    @field_validator("updated_at", mode="before")
    @classmethod
    def _coerce_dt(cls, v: Any) -> str | None:
        return _dt_iso(v)

    @field_serializer("status")
    def _serialize_status(self, v: TaskStatus) -> str:
        return v.value

    @field_serializer("priority")
    def _serialize_priority(self, v: Priority) -> str:
        return v.name


# ── Task session (inline in /tasks/{id}/sessions) ────────────────────────────


class TaskSessionResponse(_SessionSummaryBase):
    id: str
    launcher: str | None = None
    agent_backend: str
    agent_role: str | None = None


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


class ProjectFolderResolutionResponse(BaseModel):
    """How a filesystem folder maps to Kagan project/repository state."""

    path: str
    repo_path: str
    suggested_project_name: str
    is_git_repo: bool
    git_root: str | None = None
    existing_project_id: str | None = None
    existing_project_name: str | None = None
    existing_repo_id: str | None = None


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


class AgentBackendResponse(BaseModel):
    name: str
    available: bool
    reference: bool = False


class ChatAgentsResponse(BaseModel):
    backends: list[AgentBackendResponse]
    default: str


class ChatSessionSummaryResponse(BaseModel):
    id: str
    label: str
    source: str
    agent_backend: str | None = None
    project_id: str | None = None
    updated_at: str
    message_count: int


class ChatSessionResponse(ChatSessionSummaryResponse):
    messages: list[ChatMessageResponse]


class TurnInProgressResponse(BaseModel):
    ok: bool = False
    data: None = None
    error: str = "A turn is already in progress for this session"
    error_code: str = "TURN_IN_PROGRESS"
    running_since: str | None = None
    partial_chars: int = 0


class ChatMessageDetailResponse(BaseModel):
    id: int
    session_id: str
    role: str
    content: str
    terminated_at_user_request: bool
    created_at: str


# ── Filesystem browser ───────────────────────────────────────────────────────


class FsEntryResponse(BaseModel):
    """A single directory entry returned by GET /api/fs/browse."""

    name: str
    path: str
    is_dir: bool
    is_git_repo: bool
    is_link: bool


class FsBrowseResponse(BaseModel):
    """Response shape for GET /api/fs/browse."""

    path: str
    parent: str | None
    separator: str
    roots: list[str]
    entries: list[FsEntryResponse]


# ── Doctor / preflight ───────────────────────────────────────────────────────


class DoctorCheckResponse(BaseModel):
    """A single doctor check result projected from DoctorCheck."""

    name: str
    status: str
    message: str
    fix_hint: str
    verify_hint: str
    category: str
    is_blocking: bool


class DoctorReportResponse(BaseModel):
    """Aggregate report returned by GET /api/doctor."""

    checks: list[DoctorCheckResponse]
    ok: bool
    fail_count: int
    warn_count: int


# ── Integrations ─────────────────────────────────────────────────────────────


class IntegrationInfo(BaseModel):
    """Summary of a single native integration."""

    id: str
    name: str


class IntegrationSyncResult(BaseModel):
    """Result returned by POST /api/integrations/{id}/sync."""

    id: str
    created: int
    updated: int
    skipped: int
    errors: list[str] = Field(default_factory=list)


# ── Unified session ───────────────────────────────────────────────────────────


class SessionCapabilitiesResponse(_OrmBase):
    can_chat: bool
    can_stream: bool
    can_replay: bool
    can_stop: bool
    can_close: bool
    has_kagan_tools: bool


class SessionItemResponse(_OrmBase):
    id: str
    type: str
    role: str | None
    status: str
    title: str
    backend: str | None
    project_id: str | None
    task_id: str | None
    task_status: str | None = None
    session_id: str | None
    chat_session_id: str | None
    updated_at: str
    capabilities: SessionCapabilitiesResponse


class SessionsResponse(BaseModel):
    sessions: list[SessionItemResponse]


class CreateSessionRequest(BaseModel):
    type: Literal["orchestrator", "general"]
    backend: str | None = None
    title: str | None = None


# ── Session replay ────────────────────────────────────────────────────────────


class SessionReplayEvent(BaseModel):
    """A single persisted session event returned by the replay endpoint."""

    id: str
    session_id: str | None = None
    event_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: str

    @field_validator("created_at", mode="before")
    @classmethod
    def _coerce_dt(cls, v: Any) -> str:
        result = _dt_iso(v)
        return result or ""


class SessionReplayPage(BaseModel):
    """Paginated response for GET /api/v1/sessions/{session_id}/replay."""

    events: list[SessionReplayEvent]
    next_cursor: str | None = None
    has_more: bool = False


# ── Mentions ──────────────────────────────────────────────────────────────────


class MentionResponse(BaseModel):
    """A single result from the dual-source mention autocomplete endpoint."""

    source: str  # "kagan" or "github"
    id: str  # insert form: "kagan#<short_id>" or "#<number>"
    title: str
    state: str | None = None


# ── Schema export helper ─────────────────────────────────────────────────────

# All response models that map to TS interfaces.
RESPONSE_MODELS: dict[str, type[BaseModel]] = {
    "ActiveSessionResponse": ActiveSessionResponse,
    "AcceptanceCriterionResponse": AcceptanceCriterionResponse,
    "ReviewVerdictResponse": ReviewVerdictResponse,
    "DiffSummaryResponse": DiffSummaryResponse,
    "TaskResponse": TaskResponse,
    "TaskSessionResponse": TaskSessionResponse,
    "ProjectResponse": ProjectResponse,
    "RepositoryResponse": RepositoryResponse,
    "ProjectFolderResolutionResponse": ProjectFolderResolutionResponse,
    "EventResponse": EventResponse,
    "AgentBackendResponse": AgentBackendResponse,
    "ChatAgentsResponse": ChatAgentsResponse,
    "ChatMessageResponse": ChatMessageResponse,
    "ChatMessageDetailResponse": ChatMessageDetailResponse,
    "ChatSessionSummaryResponse": ChatSessionSummaryResponse,
    "ChatSessionResponse": ChatSessionResponse,
    "TurnInProgressResponse": TurnInProgressResponse,
    "DoctorCheckResponse": DoctorCheckResponse,
    "DoctorReportResponse": DoctorReportResponse,
    "FsEntryResponse": FsEntryResponse,
    "FsBrowseResponse": FsBrowseResponse,
    "IntegrationInfo": IntegrationInfo,
    "IntegrationSyncResult": IntegrationSyncResult,
    "MentionResponse": MentionResponse,
    "SessionCapabilitiesResponse": SessionCapabilitiesResponse,
    "SessionItemResponse": SessionItemResponse,
    "SessionsResponse": SessionsResponse,
    "CreateSessionRequest": CreateSessionRequest,
    "SessionReplayEvent": SessionReplayEvent,
    "SessionReplayPage": SessionReplayPage,
}
