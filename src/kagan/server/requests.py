"""Pydantic request models — validated input for mutating API routes.

Each model declares exactly the fields that a route accepts.
Use ``parse_body(request, Model)`` from ``_helpers`` to validate.

Canonical definitions live in ``kagan.core._io.*`` so both REST routes and
MCP toolsets share a single source of truth.
"""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator

from kagan.core import ReviewDecideRequest

__all__ = [
    "FollowUpRequest",
    "ReviewDecideRequest",
    "RunTaskRequest",
    "UpdateTaskStatusRequest",
]


class UpdateTaskStatusRequest(BaseModel):
    status: str = Field(..., max_length=50)


class RunTaskRequest(BaseModel):
    agent_backend: str | None = Field(default=None, max_length=255)
    persona: str | None = Field(default=None, max_length=255)
    launcher: str | None = Field(default=None, max_length=255)


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
