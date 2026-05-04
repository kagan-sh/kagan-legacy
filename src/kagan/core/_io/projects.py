"""Shared Pydantic request models for project operations.

``server/_project_routes.py`` imports from here.  The MCP projects toolset
uses a different argument shape (project_setup, project_update) that combines
multiple operations — it is not a direct parallel surface for these models.

Wire shapes (REST JSON) are unchanged by this module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProjectCreateRequest(BaseModel):
    """Request model for POST /api/projects."""

    model_config = ConfigDict(extra="ignore")

    name: str = Field(..., min_length=1, max_length=255)


class RepoAddRequest(BaseModel):
    """Request model for POST /api/projects/{project_id}/repos."""

    model_config = ConfigDict(extra="ignore")

    path: str = Field(..., min_length=1, max_length=4096)
