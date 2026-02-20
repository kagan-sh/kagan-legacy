"""UI-facing Protocol types to decouple TUI from DB schema models."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from datetime import datetime

    from kagan.core.config import KaganConfig
    from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType


class TaskView(Protocol):
    """Task shape consumed by TUI widgets/screens."""

    id: str
    short_id: str
    project_id: str
    title: str
    description: str
    status: TaskStatus
    priority: TaskPriority
    task_type: TaskType
    terminal_backend: object
    agent_backend: str | None
    parent_id: str | None
    acceptance_criteria: list[str]
    base_branch: str | None
    created_at: datetime | str
    updated_at: datetime | str

    def get_agent_config(self, config: KaganConfig) -> Any: ...


class RepoView(Protocol):
    """Repository shape consumed by TUI widgets/screens."""

    id: str
    name: str
    display_name: str | None
    path: str
    default_branch: str | None
    scripts: dict[str, object] | None


class ProjectView(Protocol):
    """Project shape consumed by TUI widgets/screens."""

    id: str
    name: str


__all__ = ["ProjectView", "RepoView", "TaskView"]
