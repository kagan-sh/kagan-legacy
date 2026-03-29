"""Pydantic request models — validated input for mutating API routes.

Each model declares exactly the fields that a route accepts.
Use ``parse_body(request, Model)`` from ``_helpers`` to validate.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class _CriteriaMixin(BaseModel):
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


class CreateTaskRequest(_CriteriaMixin):
    title: str = Field(..., min_length=1, max_length=500)
    description: str = Field(default="", max_length=50_000)
    priority: str | int | None = None
    base_branch: str | None = Field(default=None, max_length=255)
    agent_backend: str | None = Field(default=None, max_length=255)
    launcher: str | None = Field(default=None, max_length=255)


class UpdateTaskRequest(_CriteriaMixin):
    title: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=50_000)
    priority: str | int | None = None
    base_branch: str | None = Field(default=None, max_length=255)
    agent_backend: str | None = Field(default=None, max_length=255)
    launcher: str | None = Field(default=None, max_length=255)


class UpdateTaskStatusRequest(BaseModel):
    status: str = Field(..., max_length=50)


class RunTaskRequest(BaseModel):
    agent_backend: str | None = Field(default=None, max_length=255)
    persona: str | None = Field(default=None, max_length=255)
    launcher: str | None = Field(default=None, max_length=255)


class ReviewDecideRequest(BaseModel):
    action: str = Field(..., max_length=50)
    feedback: str | None = Field(default=None, max_length=50_000)


class CreateProjectRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)


class AddRepoRequest(BaseModel):
    path: str = Field(..., min_length=1, max_length=4096)


class FollowUpRequest(BaseModel):
    text: str = Field(..., max_length=50_000)

    @field_validator("text", mode="before")
    @classmethod
    def _strip_text(cls, v: object) -> str:
        if not isinstance(v, str):
            raise TypeError("text must be a string")
        stripped = v.strip()
        if not stripped:
            raise ValueError("text must not be empty")
        return stripped
