"""Shared Pydantic request models for chat session operations.

``server/_chat_routes.py`` imports from here for session CRUD endpoints.
The MCP sessions toolset handles agent run lifecycle (not chat sessions),
so it is not a consumer of these models — but having them here prevents
future drift if a parallel MCP surface is added.

Wire shapes (REST JSON) are unchanged by this module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Attachment(BaseModel):
    """A single file attachment carried in a ``/stream`` request body.

    Validated at the boundary via ``_AttachmentBody`` so downstream code
    reads typed attributes rather than doing ``str(a.get("data", ""))``.
    ``extra="ignore"`` because clients may forward additional metadata we
    do not need to store.
    """

    model_config = ConfigDict(extra="ignore", frozen=True)

    type: str = ""
    name: str = ""
    mime_type: str = ""
    data: str  # required — entries without data are filtered by the validator


class AttachmentBody(BaseModel):
    """Parses the ``attachments`` array from a ``/stream`` request body.

    ``extra="ignore"`` so unrelated top-level keys in the body are dropped
    without validation errors. Used by ``server/_chat_routes._parse_attachments``
    to validate the inbound JSON list at the transport boundary.
    """

    model_config = ConfigDict(extra="ignore")

    attachments: list[Attachment] = Field(default_factory=list)


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
    session_type: str | None = Field(default=None, max_length=64)

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
