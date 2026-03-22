"""Pydantic request models — validated input for mutating API routes.

Each model declares exactly the fields that a route accepts.
Use ``parse_body(request, Model)`` from ``_helpers`` to validate.
"""

from __future__ import annotations

from pydantic import BaseModel, field_validator


class CreateTaskRequest(BaseModel):
    title: str
    description: str = ""
    priority: str | int | None = None
    base_branch: str | None = None
    acceptance_criteria: list[str] | None = None
    agent_backend: str | None = None
    launcher: str | None = None

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def _validate_criteria(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("acceptance_criteria must be a list of strings")
        return v


class UpdateTaskRequest(BaseModel):
    title: str | None = None
    description: str | None = None
    priority: str | int | None = None
    base_branch: str | None = None
    acceptance_criteria: list[str] | None = None
    agent_backend: str | None = None
    launcher: str | None = None

    @field_validator("acceptance_criteria", mode="before")
    @classmethod
    def _validate_criteria(cls, v: object) -> list[str] | None:
        if v is None:
            return None
        if not isinstance(v, list):
            raise ValueError("acceptance_criteria must be a list of strings")
        return v


class UpdateTaskStatusRequest(BaseModel):
    status: str


class RunTaskRequest(BaseModel):
    agent_backend: str = ""
    persona: str | None = None
    launcher: str | None = None


class ReviewDecideRequest(BaseModel):
    action: str
    feedback: str | None = None


class CreateProjectRequest(BaseModel):
    name: str


class AddRepoRequest(BaseModel):
    path: str


class FollowUpRequest(BaseModel):
    text: str

    @field_validator("text", mode="before")
    @classmethod
    def _strip_text(cls, v: object) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("text is required")
        return v.strip()
