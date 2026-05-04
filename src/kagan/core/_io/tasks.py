"""Shared Pydantic request models for task operations.

Both ``server/_task_routes.py`` (REST) and ``server/mcp/toolsets/tasks.py``
(MCP) import from here.  One canonical class per operation — no duplicate
argument shaping between surfaces.

Wire shapes (REST JSON and MCP arg schemas) are unchanged by this module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class _CriteriaMixin(BaseModel):
    """Shared acceptance-criteria validation reused by create and update."""

    acceptance_criteria: list[str] | None = None

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def _validate_criteria(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("acceptance_criteria must be a list of strings")
        if len(v) > 50:
            raise ValueError("acceptance_criteria must have at most 50 items")
        for i, item in enumerate(v):
            if not isinstance(item, str):
                raise ValueError(f"acceptance_criteria[{i}] must be a string")
            if len(item) > 2000:
                raise ValueError(f"acceptance_criteria[{i}] exceeds 2000 characters")
        return v


class TaskCreateRequest(_CriteriaMixin):
    """Canonical request model for creating a single task.

    Used by both the REST POST /api/tasks handler and the MCP task_create
    tool (single-task path).  Fields match the ``Tasks.create()`` aggregate
    signature; validation constraints are the REST surface's existing rules.
    """

    model_config = ConfigDict(extra="ignore")

    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=50_000)
    priority: str | int | None = None
    base_branch: str | None = Field(default=None, max_length=255)
    agent_backend: str | None = Field(default=None, max_length=255)
    launcher: str | None = Field(default=None, max_length=255)
    repo_id: str | None = Field(default=None, max_length=255)
    github_issue: str | None = Field(default=None, max_length=255)


class TaskUpdateRequest(_CriteriaMixin):
    """Canonical request model for updating task fields.

    Used by the REST PATCH /api/tasks/{id} handler.
    """

    model_config = ConfigDict(extra="ignore")

    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=50_000)
    priority: str | int | None = None
    base_branch: str | None = Field(default=None, max_length=255)
    agent_backend: str | None = Field(default=None, max_length=255)
    launcher: str | None = Field(default=None, max_length=255)
    repo_id: str | None = Field(default=None, max_length=255)
