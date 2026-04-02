"""Typed event models for KaganClient using Pydantic.

Events are used for real-time streaming via subscribe_events().
Each event includes a sequence number for gap detection and ordering.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class Event(BaseModel):
    """Base class for all client events.

    Attributes:
        seq: Monotonically increasing sequence number for gap detection.
             Consumers should detect gaps (seq_n+1 != seq_n + 1) and resync.
        ts: ISO 8601 timestamp when the event was generated.
    """

    seq: int = Field(..., description="Sequence number for ordering and gap detection")
    ts: str = Field(
        default_factory=lambda: datetime.now().isoformat(),
        description="Event timestamp",
    )


class TaskCreatedEvent(Event):
    """Emitted when a new task is created."""

    type: Literal["task_created"] = "task_created"
    task_id: str
    title: str
    status: str
    project_id: str


class TaskUpdatedEvent(Event):
    """Emitted when a task is updated (title, status, priority, etc.)."""

    type: Literal["task_updated"] = "task_updated"
    task_id: str
    changes: dict[str, Any] = Field(default_factory=dict, description="Changed fields")


class TaskDeletedEvent(Event):
    """Emitted when a task is deleted."""

    type: Literal["task_deleted"] = "task_deleted"
    task_id: str


class TaskStatusChangedEvent(Event):
    """Emitted when a task moves between columns."""

    type: Literal["task_status_changed"] = "task_status_changed"
    task_id: str
    from_status: str
    to_status: str


class SessionStartedEvent(Event):
    """Emitted when an agent session starts on a task."""

    type: Literal["session_started"] = "session_started"
    task_id: str
    session_id: str
    agent_backend: str


class SessionEndedEvent(Event):
    """Emitted when an agent session ends (completed, failed, or cancelled)."""

    type: Literal["session_ended"] = "session_ended"
    task_id: str
    session_id: str
    status: str  # completed, failed, cancelled


class SessionOutputEvent(Event):
    """Emitted for agent output chunks during a session."""

    type: Literal["session_output"] = "session_output"
    task_id: str
    session_id: str | None
    chunk: str


class SettingsChangedEvent(Event):
    """Emitted when settings are modified."""

    type: Literal["settings_changed"] = "settings_changed"
    keys: list[str] = Field(default_factory=list, description="Changed setting keys")


# Union type for all events
TaskEvent = TaskCreatedEvent | TaskUpdatedEvent | TaskDeletedEvent | TaskStatusChangedEvent
SessionEvent = SessionStartedEvent | SessionEndedEvent | SessionOutputEvent
AnyEvent = TaskEvent | SessionEvent | SettingsChangedEvent


__all__ = [
    "AnyEvent",
    "Event",
    "SessionEndedEvent",
    "SessionEvent",
    "SessionOutputEvent",
    "SessionStartedEvent",
    "SettingsChangedEvent",
    "TaskCreatedEvent",
    "TaskDeletedEvent",
    "TaskEvent",
    "TaskStatusChangedEvent",
    "TaskUpdatedEvent",
]
