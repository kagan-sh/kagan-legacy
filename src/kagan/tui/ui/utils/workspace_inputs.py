"""Shared conversion helpers for workspace repo inputs."""

from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.core.scalars import non_empty_str
from kagan.core.services.workspaces import RepoWorkspaceInput

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence


def repo_details_to_workspace_inputs(
    repo_details: Sequence[Mapping[str, object]],
) -> list[RepoWorkspaceInput]:
    """Convert project-repo detail mappings to ``RepoWorkspaceInput`` values."""
    inputs: list[RepoWorkspaceInput] = []
    for repo in repo_details:
        repo_id = non_empty_str(repo.get("id"))
        repo_path = non_empty_str(repo.get("path"))
        target_branch = non_empty_str(repo.get("default_branch"))
        if repo_id is None or repo_path is None or target_branch is None:
            raise ValueError(
                "Each selected repo must include non-empty id, path, and default_branch"
            )
        inputs.append(
            RepoWorkspaceInput(
                repo_id=repo_id,
                repo_path=repo_path,
                target_branch=target_branch,
            )
        )
    return inputs


__all__ = ["repo_details_to_workspace_inputs"]
