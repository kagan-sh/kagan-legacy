"""SQLModel table classes for kagan.core — single class is both validation model and DB table."""

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import sqlalchemy.exc
from pydantic import field_serializer
from sqlalchemy import JSON, Boolean, Column, Index, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel

from kagan.core.enums import Priority, SessionStatus, TaskStatus


def _new_id() -> str:
    return uuid4().hex[:16]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class Project(SQLModel, table=True):
    __tablename__ = "projects"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    name: str = Field(index=True)
    description: str = Field(default="")
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class Repository(SQLModel, table=True):
    __tablename__ = "repos"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str | None = Field(default=None, foreign_key="projects.id", index=True)
    name: str = Field(index=True)
    path: str = Field(unique=True, index=True)
    default_branch: str = Field(default="main")
    scripts: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class Task(SQLModel, table=True):
    __tablename__ = "tasks"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    project_id: str = Field(foreign_key="projects.id", index=True)
    repo_id: str | None = Field(default=None, foreign_key="repos.id", index=True)
    title: str = Field(index=True)
    description: str = Field(default="")
    status: TaskStatus = Field(default=TaskStatus.BACKLOG, index=True)
    priority: Priority = Field(default=Priority.MEDIUM, index=True)

    @field_serializer("priority")
    @classmethod
    def _serialize_priority(cls, v: Priority) -> str:
        return v.name

    agent_backend: str | None = Field(default=None)
    launcher: str | None = Field(default=None)
    base_branch: str | None = Field(default=None)
    max_retries: int = Field(default=0)
    success_command: str | None = Field(default=None)
    task_type: str | None = Field(default=None, index=True)
    github_issue: str | None = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)

    # Relationships
    criteria: list["AcceptanceCriterion"] = Relationship(
        back_populates="task",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "select"},
    )

    # Backward-compat shim for TUI / consumers that previously accessed this
    # as a plain attribute when it was a DB column.
    @property
    def acceptance_criteria(self) -> list[str]:
        """Return acceptance criterion texts in ordinal order.

        Reads from the eagerly-loaded `criteria` relationship. Callers that
        go through _tasks.py list/get/create operations have this pre-loaded.
        Returns [] when the relationship cannot be resolved (e.g. detached
        instance, session closed) so callers don't have to special-case.
        """
        try:
            criteria = self.criteria
        except (AttributeError, sqlalchemy.exc.SQLAlchemyError):
            return []
        if not criteria:
            return []
        return [c.text for c in sorted(criteria, key=lambda c: c.ordinal)]


class AcceptanceCriterion(SQLModel, table=True):
    __tablename__ = "acceptance_criteria"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    ordinal: int = Field(default=0)
    text: str = Field(max_length=500)

    # Relationships
    task: Task | None = Relationship(back_populates="criteria")
    verdicts: list["ReviewVerdict"] = Relationship(
        back_populates="criterion",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "select"},
    )


class ReviewVerdict(SQLModel, table=True):
    __tablename__ = "review_verdicts"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    criterion_id: str = Field(foreign_key="acceptance_criteria.id", index=True)
    session_id: str | None = Field(default=None, foreign_key="sessions.id", index=True)
    verdict: str = Field(description="pass, fail, or skip")
    reason: str = Field(default="")
    created_at: datetime = Field(default_factory=_utc_now, index=True)

    # Relationships
    criterion: AcceptanceCriterion | None = Relationship(back_populates="verdicts")


class Worktree(SQLModel, table=True):
    __tablename__ = "worktrees"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    repo_id: str = Field(foreign_key="repos.id", index=True)
    worktree_path: str
    branch_name: str
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


class Session(SQLModel, table=True):
    __tablename__ = "sessions"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    agent_backend: str
    status: SessionStatus = Field(default=SessionStatus.PENDING, index=True)
    launcher: str | None = Field(default=None)
    pid: int | None = Field(default=None)
    started_at: datetime = Field(default_factory=_utc_now)
    ended_at: datetime | None = Field(default=None)
    persona: str | None = Field(default=None)
    attempt: int = Field(default=1)
    input_tokens: int | None = Field(default=None)
    output_tokens: int | None = Field(default=None)
    context_window_used: int | None = Field(default=None)
    context_window_size: int | None = Field(default=None)
    cost_amount: float | None = Field(default=None)
    cost_currency: str | None = Field(default=None)
    agent_role: str | None = Field(default=None, index=True)
    fail_reason: str | None = Field(default=None)


class SessionEvent(SQLModel, table=True):
    __tablename__ = "task_events"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    session_id: str | None = Field(default=None, foreign_key="sessions.id", index=True)
    # ``event_type`` stores the AgentEvent variant ``kind`` string
    # (e.g. ``"output_chunk"``, ``"agent_completed"``).  All new rows use
    # lowercase kind strings; the column is plain TEXT in the database.
    event_type: str = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utc_now)


class TaskNote(SQLModel, table=True):
    __tablename__ = "notes"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    content: str
    created_at: datetime = Field(default_factory=_utc_now)


class Setting(SQLModel, table=True):
    __tablename__ = "settings"  # type: ignore[assignment]

    key: str = Field(primary_key=True)
    value: str


class TelemetryEvent(SQLModel, table=True):
    """System-level telemetry events not tied to a specific task or session."""

    __tablename__ = "telemetry_events"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    event_type: str = Field(index=True)
    payload: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utc_now)


class AuditEntry(SQLModel, table=True):
    __tablename__ = "audit_entries"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utc_now)


class EventLogEntry(SQLModel, table=True):
    """Append-only frame store for chat and task event streams.

    seq   — per-(session_id, kind) monotonic counter; assigned by EventLog.
    idx   — logical entry index for patch frames (matches ``/entries/{idx}``);
            append/finalize rows reuse the target entry's idx.  Seeded from
            max(create-patch idx) on restart (legacy rows fall back to max(idx)).
    ts    — UTC timestamp of insertion.
    frame — arbitrary JSON payload.

    Note: session_id is intentionally stored without a FK constraint at the DB
    level.  A SQLite RENAME TABLE quirk in migration 6f4d63a80a1e causes alembic
    to store ``REFERENCES sessions_old`` rather than ``REFERENCES sessions`` when
    the FK is declared in model metadata and a fresh DB is migrated.  Application-
    level integrity is enforced: EventLog.append() always receives a valid
    session_id.  The FK will be added in a future migration.
    """

    __tablename__ = "event_log"  # type: ignore[assignment]
    __table_args__ = (
        UniqueConstraint("session_id", "kind", "seq", name="uq_event_log_session_kind_seq"),
        Index("ix_event_log_session_kind_seq", "session_id", "kind", "seq"),
    )

    id: str = Field(default_factory=_new_id, primary_key=True)
    session_id: str = Field(index=True)  # no FK — see class docstring
    kind: str = Field()
    seq: int = Field()
    idx: int = Field()
    ts: datetime = Field(default_factory=_utc_now)
    frame: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))


class ChatSession(SQLModel, table=True):
    __tablename__ = "chat_sessions"  # type: ignore[assignment]
    __table_args__ = (Index("ix_chat_sessions_project_id_updated_at", "project_id", "updated_at"),)

    id: str = Field(default_factory=_new_id, primary_key=True)
    label: str
    source: str
    agent_backend: str | None = Field(default=None)
    project_id: str | None = Field(default=None, foreign_key="projects.id", index=True)
    session_type: str = Field(
        default="orchestrator",
        index=True,
        sa_column_kwargs={"server_default": "orchestrator"},
    )
    created_at: datetime = Field(default_factory=_utc_now, index=True)
    updated_at: datetime = Field(default_factory=_utc_now, index=True)

    messages: list["ChatMessage"] = Relationship(
        back_populates="session",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "select",
            "order_by": "ChatMessage.id",
        },
    )


class ChatMessage(SQLModel, table=True):
    __tablename__ = "chat_messages"  # type: ignore[assignment]
    __table_args__ = (Index("ix_chat_messages_session_id_id", "session_id", "id"),)

    id: int | None = Field(default=None, primary_key=True)  # autoincrement
    session_id: str = Field(foreign_key="chat_sessions.id", index=True)
    role: str  # "user" | "assistant" | "system"
    content: str
    terminated_at_user_request: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="0"),
    )
    created_at: datetime = Field(default_factory=_utc_now, index=True)

    session: ChatSession | None = Relationship(back_populates="messages")


__all__ = [
    "AcceptanceCriterion",
    "AuditEntry",
    "ChatMessage",
    "ChatSession",
    "EventLogEntry",
    "Project",
    "Repository",
    "ReviewVerdict",
    "Session",
    "SessionEvent",
    "Setting",
    "Task",
    "TaskNote",
    "TelemetryEvent",
    "Worktree",
    "_utc_now",
]
