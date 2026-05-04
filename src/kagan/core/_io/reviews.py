"""Shared Pydantic request models for review operations.

``server/_task_routes.py`` imports ReviewDecideRequest from here.  The MCP
review toolset (review_decide, review_verdict, review_merge) uses different
argument shapes — the MCP surface separates verdict recording from decision
making, while the REST surface collapses them.  No shared model is possible
without silently changing the MCP contract.

Wire shapes (REST JSON) are unchanged by this module.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ReviewDecideRequest(BaseModel):
    """Request model for POST /api/tasks/{task_id}/review/decide.

    ``action`` must be one of: approve, reject, merge, rebase.
    ``feedback`` is required when action is 'reject'.
    """

    model_config = ConfigDict(extra="ignore")

    action: str = Field(..., max_length=50)
    feedback: str | None = Field(default=None, max_length=50_000)
