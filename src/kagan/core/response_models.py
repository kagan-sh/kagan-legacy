"""Canonical response models shared between MCP and SDK layers."""

from __future__ import annotations

from pydantic import Field, model_validator

from kagan.core.domain.models import AgentLogEntry, FrozenDomainModel, Task


class TaskWaitResponse(FrozenDomainModel):
    """Canonical response for task_wait operations."""

    changed: bool = False
    timed_out: bool = False
    task_id: str = ""
    previous_status: str | None = None
    current_status: str | None = None
    changed_at: str | None = None
    task: Task | None = None
    code: str = ""
    message: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_task(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        value = data.get("task")
        if isinstance(value, dict):
            return {**data, "task": Task.model_validate(value)}
        return data


class TaskLogsResponse(FrozenDomainModel):
    """Canonical response for task_logs operations."""

    task_id: str = ""
    logs: list[AgentLogEntry] = Field(default_factory=list)
    count: int = 0
    total_runs: int = 0
    returned_runs: int = 0
    offset: int = 0
    limit: int = 0
    has_more: bool = False
    next_offset: int | None = None
    truncated: bool = False


__all__ = [
    "TaskLogsResponse",
    "TaskWaitResponse",
]
