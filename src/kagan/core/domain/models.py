"""Canonical Pydantic domain models shared across core, SDK, and MCP."""

from __future__ import annotations

from datetime import datetime  # noqa: TC003
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, field_validator, model_validator

from kagan.core.domain.coercion import (
    coerce_plan_priority,
    coerce_plan_todo_status,
    coerce_task_priority,
    coerce_task_status,
    coerce_task_type,
)
from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType


class FrozenDomainModel(BaseModel):
    """Shared immutable Pydantic base for cross-boundary domain payloads."""

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


class PlanItem(FrozenDomainModel):
    """Planner task item shared by planner, SDK, and MCP."""

    title: str = ""
    type: Literal["AUTO", "PAIR"] = "PAIR"
    description: str = ""
    acceptance_criteria: list[str] = Field(default_factory=list)
    priority: Literal["low", "medium", "high"] = "medium"

    @model_validator(mode="before")
    @classmethod
    def normalize_type_from_wire(cls, data: object) -> object:
        """Accept ``task_type`` wire key as alias for ``type``."""
        if not isinstance(data, dict):
            return data
        if "type" in data:
            return data
        task_type = data.get("task_type")
        if task_type is None:
            return data
        return {**data, "type": task_type}

    @field_validator("title", "description", mode="before")
    @classmethod
    def normalize_text_fields(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("type", mode="before")
    @classmethod
    def normalize_type(cls, value: object) -> str:
        return coerce_task_type(value, default=TaskType.PAIR).value

    @field_validator("priority", mode="before")
    @classmethod
    def normalize_priority(cls, value: object) -> Literal["low", "medium", "high"]:
        return coerce_plan_priority(value)

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def coerce_criteria(cls, value: object) -> list[object]:
        if value is None:
            return []
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            return value
        return [value]

    @field_validator("acceptance_criteria")
    @classmethod
    def clean_criteria(cls, value: list[object]) -> list[str]:
        cleaned: list[str] = []
        for item in value:
            text = str(item).strip()
            if text:
                cleaned.append(text)
        return cleaned


class PlanTodo(FrozenDomainModel):
    """Planner todo item shared by planner, SDK, and MCP."""

    content: str = ""
    status: Literal["pending", "in_progress", "completed", "failed"] = "completed"

    @field_validator("content", mode="before")
    @classmethod
    def normalize_content(cls, value: object) -> str:
        if value is None:
            return ""
        return str(value).strip()

    @field_validator("status", mode="before")
    @classmethod
    def normalize_status(
        cls,
        value: object,
    ) -> Literal["pending", "in_progress", "completed", "failed"]:
        return coerce_plan_todo_status(value)


class Project(FrozenDomainModel):
    """Canonical project payload."""

    id: str = ""
    name: str = ""
    description: str = ""
    last_opened_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def normalize_id(cls, data: object) -> object:
        if isinstance(data, dict) and "id" not in data and "project_id" in data:
            return {**data, "id": data["project_id"]}
        return data


class Repo(FrozenDomainModel):
    """Canonical repository payload."""

    id: str = ""
    name: str = ""
    display_name: str | None = None
    path: str = ""
    default_branch: str = "main"
    scripts: dict[str, str] = Field(default_factory=dict)


class TaskRuntimeState(FrozenDomainModel):
    """Canonical runtime snapshot for task scheduling/execution state."""

    is_running: bool = False
    is_reviewing: bool = False
    is_blocked: bool = False
    blocked_reason: str | None = None
    blocked_by_task_ids: list[str] = Field(default_factory=list)
    overlap_hints: list[str] = Field(default_factory=list)
    blocked_at: str | None = None
    is_pending: bool = False
    pending_reason: str | None = None
    pending_at: str | None = None


class Task(FrozenDomainModel):
    """Canonical task payload."""

    id: str = ""
    project_id: str = ""
    parent_id: str | None = None
    title: str = ""
    description: str = ""
    status: TaskStatus = TaskStatus.BACKLOG
    priority: TaskPriority = TaskPriority.MEDIUM
    task_type: TaskType = TaskType.PAIR
    terminal_backend: str | None = None
    agent_backend: str | None = None
    acceptance_criteria: list[str] = Field(default_factory=list)
    base_branch: str | None = None
    created_at: str = ""
    updated_at: str = ""
    runtime: TaskRuntimeState = Field(default_factory=TaskRuntimeState)

    @computed_field
    @property
    def short_id(self) -> str:
        return (self.id or "")[:8]

    def get_agent_config(self, config: Any) -> Any:
        """Resolve task agent config with task-level override and global fallback."""
        from kagan.core.builtin_agents import get_builtin_agent
        from kagan.core.config import get_fallback_agent_config

        if self.agent_backend:
            if builtin := get_builtin_agent(self.agent_backend):
                return builtin.config
            if agent_cfg := config.get_agent(self.agent_backend):
                return agent_cfg

        default_agent = config.general.default_worker_agent
        if builtin := get_builtin_agent(default_agent):
            return builtin.config
        if agent_cfg := config.get_agent(default_agent):
            return agent_cfg

        return get_fallback_agent_config()

    @model_validator(mode="before")
    @classmethod
    def parse_enums(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data

        payload = dict(data)
        if "status" in payload:
            payload["status"] = coerce_task_status(payload["status"], default=TaskStatus.BACKLOG)
        if "priority" in payload:
            payload["priority"] = coerce_task_priority(
                payload["priority"],
                default=TaskPriority.MEDIUM,
            )
        if "task_type" in payload:
            payload["task_type"] = coerce_task_type(payload["task_type"], default=TaskType.PAIR)
        return payload


class TaskSummary(FrozenDomainModel):
    """Compact task summary for list views and coordination tools."""

    task_id: str = ""
    title: str = ""
    status: str | None = None
    description: str | None = None
    scratchpad: str | None = None
    acceptance_criteria: list[str] | None = None
    runtime: TaskRuntimeState | None = None


class Execution(FrozenDomainModel):
    """Execution process payload."""

    id: str = ""
    session_id: str | None = None
    run_reason: str | None = None
    executor_action: dict[str, Any] = Field(default_factory=dict)
    status: str | None = None
    exit_code: int | None = None
    dropped: bool = False
    started_at: str | None = None
    completed_at: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutionLogEntry(FrozenDomainModel):
    """Execution log entry payload."""

    id: str = ""
    execution_process_id: str | None = None
    logs: str = ""
    byte_size: int = 0
    inserted_at: str | None = None


class RuntimeContext(FrozenDomainModel):
    """Runtime context payload."""

    project_id: str | None = None
    repo_id: str | None = None


class StartupDecision(FrozenDomainModel):
    """Startup decision payload from runtime service."""

    project_id: str | None = None
    preferred_repo_id: str | None = None
    preferred_path: str | None = None
    suggest_cwd: bool = False
    cwd_path: str | None = None
    cwd_is_git_repo: bool = False
    should_open_project: bool = False


class RuntimeView(FrozenDomainModel):
    """Runtime task view payload."""

    task_id: str = ""
    phase: str | None = None
    execution_id: str | None = None
    run_count: int = 0
    has_running_agent: bool = False
    has_review_agent: bool = False
    runtime: TaskRuntimeState = Field(default_factory=TaskRuntimeState)


_CANONICAL_DOMAIN_MODELS: tuple[type[FrozenDomainModel], ...] = (
    PlanItem,
    PlanTodo,
    Project,
    Repo,
    TaskRuntimeState,
    Task,
    TaskSummary,
    Execution,
    ExecutionLogEntry,
    RuntimeContext,
    StartupDecision,
    RuntimeView,
)

for _model in _CANONICAL_DOMAIN_MODELS:
    # Ensure forward annotations are resolved at import time.
    _model.model_rebuild()
del _model


__all__ = [
    "Execution",
    "ExecutionLogEntry",
    "FrozenDomainModel",
    "PlanItem",
    "PlanTodo",
    "Project",
    "Repo",
    "RuntimeContext",
    "RuntimeView",
    "StartupDecision",
    "Task",
    "TaskRuntimeState",
    "TaskSummary",
]
