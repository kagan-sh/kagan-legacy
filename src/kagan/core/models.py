"""SQLModel table classes for kagan.core — single class is both validation model and DB table."""

from datetime import UTC, datetime
from typing import Any, Literal, TypedDict
from uuid import uuid4

from pydantic import field_serializer
from sqlalchemy import JSON, Column
from sqlmodel import Field, SQLModel

from kagan.core.enums import Priority, SessionEventType, SessionStatus, TaskStatus


def _new_id() -> str:
    return uuid4().hex[:16]


def _utc_now() -> datetime:
    return datetime.now(UTC)


class ReviewVerdict(TypedDict):
    criterion_index: int
    verdict: Literal["PASS", "FAIL"]
    reason: str


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
    acceptance_criteria: list[str] = Field(default_factory=list, sa_column=Column(JSON))
    review_approved: bool = Field(default=False)
    review_verdicts: list[ReviewVerdict] = Field(default_factory=list, sa_column=Column(JSON))
    max_retries: int = Field(default=0)
    success_command: str | None = Field(default=None)
    created_at: datetime = Field(default_factory=_utc_now)
    updated_at: datetime = Field(default_factory=_utc_now)


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


class SessionEvent(SQLModel, table=True):
    __tablename__ = "task_events"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    task_id: str = Field(foreign_key="tasks.id", index=True)
    session_id: str | None = Field(default=None, foreign_key="sessions.id", index=True)
    event_type: SessionEventType = Field(index=True)
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


class AuditEntry(SQLModel, table=True):
    __tablename__ = "audit_entries"  # type: ignore[assignment]

    id: str = Field(default_factory=_new_id, primary_key=True)
    action: str = Field(index=True)
    entity_type: str = Field(index=True)
    entity_id: str = Field(index=True)
    detail: dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=_utc_now)


__all__ = [
    "AuditEntry",
    "Project",
    "Repository",
    "ReviewVerdict",
    "Session",
    "SessionEvent",
    "Setting",
    "Task",
    "TaskNote",
    "Worktree",
    "_utc_now",
]
