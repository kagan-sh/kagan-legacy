"""Planner proposal models and conversions.

Boundary rule:
- Pydantic models are used for cross-boundary payload contracts.
- Dataclasses are used for internal, ephemeral conversion state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from acp.schema import PlanEntry
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from kagan.core.adapters.db.schema import Task as RuntimeTask
from kagan.core.domain.coercion import coerce_task_priority, coerce_task_type
from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType
from kagan.core.domain.models import PlanItem, PlanTodo
from kagan.core.time import utc_now


@dataclass(frozen=True, slots=True)
class PlannerTaskDraft:
    """Internal planner task state after payload validation."""

    title: str
    description: str
    acceptance_criteria: list[str]
    priority: TaskPriority
    task_type: TaskType


class ProposedTodo(PlanTodo):
    """Planner todo entry for plan display."""

    model_config = ConfigDict(extra="ignore")

    content: str = Field(..., min_length=1, max_length=200)


class ProposedTask(PlanItem):
    """Planner task proposal parsed from tool call arguments."""

    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., min_length=1, max_length=200)
    description: str = Field("", max_length=10000)

    @model_validator(mode="before")
    @classmethod
    def coerce_task_type_alias(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        if "task_type" not in value:
            return value

        normalized = dict(value)
        task_type = normalized.get("task_type")
        existing = normalized.get("type")
        if existing is not None and str(existing).strip().upper() != str(task_type).strip().upper():
            msg = "Conflicting task type values: 'type' and 'task_type' must match"
            raise ValueError(msg)

        normalized["type"] = task_type
        return normalized


class PlanProposal(BaseModel):
    """Validated plan proposal from the planner tool call."""

    model_config = ConfigDict(extra="ignore")

    tasks: list[ProposedTask] = Field(..., min_length=1)
    todos: list[ProposedTodo] = Field(default_factory=list)

    @field_validator("todos", mode="before")
    @classmethod
    def _coerce_todos(cls, v: Any) -> list[Any]:
        """Coerce invalid todos input to empty list (LLM might send wrong type)."""
        if v is None:
            return []
        if isinstance(v, list):
            return v
        return []

    def to_task_drafts(self) -> list[PlannerTaskDraft]:
        """Convert validated payload DTOs to internal draft state."""
        drafts: list[PlannerTaskDraft] = []
        for item in self.tasks:
            priority = coerce_task_priority(item.priority, default=TaskPriority.MEDIUM)
            if priority is None:
                priority = TaskPriority.MEDIUM
            task_type = coerce_task_type(item.type, default=TaskType.PAIR)
            if task_type is None:
                task_type = TaskType.PAIR
            drafts.append(
                PlannerTaskDraft(
                    title=item.title[:200],
                    description=item.description,
                    acceptance_criteria=list(item.acceptance_criteria),
                    priority=priority,
                    task_type=task_type,
                )
            )
        return drafts

    def to_tasks(self) -> list[RuntimeTask]:
        """Convert internal draft state into runtime task models."""
        from uuid import uuid4

        tasks: list[RuntimeTask] = []
        for draft in self.to_task_drafts():
            now = utc_now()
            tasks.append(
                RuntimeTask(
                    id=uuid4().hex[:8],
                    project_id="plan",
                    title=draft.title,
                    description=draft.description,
                    status=TaskStatus.BACKLOG,
                    priority=draft.priority,
                    task_type=draft.task_type,
                    agent_backend=None,
                    parent_id=None,
                    acceptance_criteria=draft.acceptance_criteria,
                    created_at=now,
                    updated_at=now,
                )
            )
        return tasks

    def to_plan_entries(self) -> list[PlanEntry]:
        """Convert todos to plan display entries."""
        entries: list[PlanEntry] = []
        for todo in self.todos:
            status = "completed" if todo.status == "failed" else todo.status
            entries.append(PlanEntry(content=todo.content, status=status, priority="medium"))
        return entries


__all__ = [
    "PlanProposal",
    "PlannerTaskDraft",
    "ProposedTask",
    "ProposedTodo",
]
