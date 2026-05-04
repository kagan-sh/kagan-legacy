"""Shared Pydantic request models for chat session operations.

``server/_chat_routes.py`` imports from here for session CRUD endpoints.
The MCP sessions toolset handles agent run lifecycle (not chat sessions),
so it is not a consumer of these models — but having them here prevents
future drift if a parallel MCP surface is added.

Wire shapes (REST JSON) are unchanged by this module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class ChatSessionCreateRequest(BaseModel):
    """Request model for POST /api/chat/sessions.

    Replaces the previous raw ``body.get(...)`` parsing with Pydantic
    validation so missing/malformed fields are caught at the boundary.
    """

    model_config = ConfigDict(extra="ignore")

    agent_backend: str | None = Field(default=None, max_length=255)
    label: str | None = Field(default=None, max_length=255)
    source: str = Field(default="web", max_length=64)
    project_id: str | None = Field(default=None, max_length=255)

    @field_validator("source", mode="before")
    @classmethod
    def _normalise_source(cls, v: object) -> str:
        """Coerce to str, strip whitespace, default to 'web' if blank."""
        s = str(v or "").strip()
        return s if s else "web"


class ChatSessionPatchRequest(BaseModel):
    """Request model for PATCH /api/chat/sessions/{session_id}.

    Only ``agent_backend`` is patchable today.  Additional fields may be
    added here as the API evolves without touching the route handler.
    """

    model_config = ConfigDict(extra="ignore")

    agent_backend: str | None = Field(default=None, max_length=255)
