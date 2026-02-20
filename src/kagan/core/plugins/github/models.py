"""GitHub plugin models, repo state, and task context."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel, ConfigDict

from kagan.core.plugins.github.gh_adapter import (
    GITHUB_CONNECTION_KEY,
    load_connection_metadata,
    resolve_connection_repo_name,
)
from kagan.core.plugins.github.sync import (
    GITHUB_ISSUE_MAPPING_KEY,
    GITHUB_LEASE_ENFORCEMENT_KEY,
    GITHUB_SYNC_CHECKPOINT_KEY,
    GITHUB_TASK_PR_MAPPING_KEY,
    IssueMapping,
    SyncCheckpoint,
    TaskPRMapping,
    load_checkpoint,
    load_lease_enforcement,
    load_mapping,
    load_repo_default_mode,
    load_task_pr_mapping,
)

if TYPE_CHECKING:
    from collections.abc import Mapping

    from kagan.core.domain.enums import TaskType


# ── Input models ─────────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class ContractProbeInput:
    """Input payload for contract probe calls."""

    echo: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectRepoInput:
    """Input payload for connect_repo."""

    project_id: str | None
    repo_id: str | None = None


@dataclass(frozen=True, slots=True)
class SyncIssuesInput:
    """Input payload for sync_issues."""

    project_id: str | None
    repo_id: str | None = None


@dataclass(frozen=True, slots=True)
class AcquireLeaseInput:
    """Input payload for acquire_lease."""

    project_id: str | None
    repo_id: str | None = None
    issue_number: int | str | None = None
    force_takeover: bool = False


@dataclass(frozen=True, slots=True)
class ReleaseLeaseInput:
    """Input payload for release_lease."""

    project_id: str | None
    repo_id: str | None = None
    issue_number: int | str | None = None


@dataclass(frozen=True, slots=True)
class GetLeaseStateInput:
    """Input payload for get_lease_state."""

    project_id: str | None
    repo_id: str | None = None
    issue_number: int | str | None = None


@dataclass(frozen=True, slots=True)
class CreatePrForTaskInput:
    """Input payload for create_pr_for_task."""

    project_id: str | None
    repo_id: str | None = None
    task_id: str | None = None
    title: str | None = None
    body: str | None = None
    draft: bool = False


@dataclass(frozen=True, slots=True)
class LinkPrToTaskInput:
    """Input payload for link_pr_to_task."""

    project_id: str | None
    repo_id: str | None = None
    task_id: str | None = None
    pr_number: object | None = None


@dataclass(frozen=True, slots=True)
class ReconcilePrStatusInput:
    """Input payload for reconcile_pr_status."""

    project_id: str | None
    repo_id: str | None = None
    task_id: str | None = None


@dataclass(frozen=True, slots=True)
class ValidateReviewTransitionInput:
    """Input payload for validate_review_transition."""

    task_id: str | None
    project_id: str | None


@dataclass(frozen=True, slots=True)
class SyncTaskStatusInput:
    """Input payload for sync_task_status."""

    task_id: str | None
    project_id: str | None
    to_status: str | None = None


@dataclass(frozen=True, slots=True)
class AutoCreateReviewPrInput:
    """Input payload for auto_create_review_pr."""

    task_id: str | None
    project_id: str | None


@dataclass(frozen=True, slots=True)
class CheckPrCiStatusInput:
    """Input payload for check_ci_status."""

    task_id: str | None
    project_id: str | None


@dataclass(frozen=True, slots=True)
class MergeGithubPrInput:
    """Input payload for merge_pr."""

    task_id: str | None
    project_id: str | None
    merge_method: str = "merge"


@dataclass(frozen=True, slots=True)
class GetPrReviewCommentsInput:
    """Input payload for get_pr_review_comments."""

    task_id: str | None
    project_id: str | None


# ── Typed connection/repo models ─────────────────────────────────────────────


class GitHubConnection(BaseModel):
    """Normalized GitHub connection metadata. Use for stable dict shapes."""

    model_config = ConfigDict(extra="ignore")

    owner: str = ""
    repo: str = ""
    full_name: str = ""
    default_branch: str = "main"


class GitHubTaskSummary(BaseModel):
    """Brief task summary for sync/PR flows."""

    model_config = ConfigDict(extra="ignore")

    task_id: str = ""
    title: str = ""
    status: str = ""
    issue_number: int | None = None
    pr_number: int | None = None


# ── Repo state (connection, mappings, checkpoints) ─────────────────────────


@dataclass(frozen=True, slots=True)
class ConnectionState:
    """Normalized connection metadata state."""

    raw_value: object | None
    normalized: dict[str, Any] | None
    needs_rewrite: bool


def load_connection_state(scripts: Mapping[str, object] | None) -> ConnectionState:
    """Load and normalize connection metadata from persisted repo scripts."""
    raw_value = scripts.get(GITHUB_CONNECTION_KEY) if scripts else None
    parsed_value = raw_value
    if isinstance(raw_value, str):
        try:
            parsed_value = json.loads(raw_value)
        except json.JSONDecodeError:
            parsed_value = None

    normalized = load_connection_metadata(parsed_value)
    needs_rewrite = (
        isinstance(parsed_value, dict) and normalized is not None and parsed_value != normalized
    )
    return ConnectionState(
        raw_value=raw_value,
        normalized=normalized,
        needs_rewrite=needs_rewrite,
    )


def resolve_owner_repo(connection: Mapping[str, Any]) -> tuple[str, str] | None:
    """Resolve owner/repo tuple from normalized connection metadata."""
    owner = str(connection.get("owner") or "").strip()
    repo_name = resolve_connection_repo_name(connection)
    if not owner or not repo_name:
        return None
    return owner, repo_name


def load_sync_checkpoint_state(scripts: Mapping[str, object] | None) -> SyncCheckpoint:
    """Load sync checkpoint from persisted repo scripts."""
    return load_checkpoint(scripts)


def load_issue_mapping_state(scripts: Mapping[str, object] | None) -> IssueMapping:
    """Load issue mapping from persisted repo scripts."""
    return load_mapping(scripts)


def load_repo_default_mode_state(scripts: Mapping[str, object] | None) -> TaskType | None:
    """Load repo default task mode from persisted repo scripts."""
    return load_repo_default_mode(scripts)


def load_lease_enforcement_state(scripts: Mapping[str, object] | None) -> bool:
    """Load repo-level lease enforcement policy from persisted repo scripts."""
    return load_lease_enforcement(scripts)


def load_pr_mapping_state(scripts: Mapping[str, object] | None) -> TaskPRMapping:
    """Load PR mapping from persisted repo scripts."""
    return load_task_pr_mapping(scripts)


def encode_connection_update(connection_metadata: Mapping[str, Any]) -> dict[str, str]:
    """Encode connection metadata update payload for repo script storage."""
    return {GITHUB_CONNECTION_KEY: json.dumps(dict(connection_metadata))}


def encode_sync_state_update(
    checkpoint: SyncCheckpoint,
    mapping: IssueMapping,
) -> dict[str, str]:
    """Encode sync checkpoint and issue mapping update payload."""
    return {
        GITHUB_SYNC_CHECKPOINT_KEY: json.dumps(checkpoint.to_dict()),
        GITHUB_ISSUE_MAPPING_KEY: json.dumps(mapping.to_dict()),
    }


def encode_pr_mapping_update(mapping: TaskPRMapping) -> dict[str, str]:
    """Encode task-to-PR mapping update payload."""
    return {GITHUB_TASK_PR_MAPPING_KEY: json.dumps(mapping.to_dict())}


def encode_lease_enforcement_update(enabled: bool) -> dict[str, str]:
    """Encode lease enforcement policy update payload."""
    return {GITHUB_LEASE_ENFORCEMENT_KEY: json.dumps(enabled)}


# ── Task context (issue/PR lookup) ───────────────────────────────────────────


def resolve_github_context(
    task_id: str,
    repos_scripts: list[Mapping[str, object] | None],
) -> tuple[int | None, int | None]:
    """Resolve GitHub issue number and PR number for a task."""
    issue_number: int | None = None
    pr_number: int | None = None

    for scripts in repos_scripts:
        if not scripts:
            continue

        if issue_number is None:
            mapping = load_issue_mapping_state(scripts)
            issue_number = mapping.get_issue_number(task_id)

        if pr_number is None:
            pr_mapping = load_pr_mapping_state(scripts)
            pr_link = pr_mapping.get_pr(task_id)
            if pr_link is not None:
                pr_number = pr_link.pr_number

        if issue_number is not None and pr_number is not None:
            break

    return issue_number, pr_number


def build_github_context_index(
    task_ids: set[str],
    repos_scripts: list[Mapping[str, object] | None],
) -> dict[str, tuple[int | None, int | None]]:
    """Build a batch index of GitHub context for multiple tasks."""
    issue_map: dict[str, int] = {}
    pr_map: dict[str, int] = {}

    for scripts in repos_scripts:
        if not scripts:
            continue

        mapping = load_issue_mapping_state(scripts)
        for tid in task_ids:
            if tid not in issue_map:
                issue_num = mapping.get_issue_number(tid)
                if issue_num is not None:
                    issue_map[tid] = issue_num

        pr_mapping = load_pr_mapping_state(scripts)
        for tid in task_ids:
            if tid not in pr_map:
                pr_link = pr_mapping.get_pr(tid)
                if pr_link is not None:
                    pr_map[tid] = pr_link.pr_number

    return {
        tid: (issue_map.get(tid), pr_map.get(tid))
        for tid in task_ids
        if tid in issue_map or tid in pr_map
    }


__all__ = [
    "AcquireLeaseInput",
    "AutoCreateReviewPrInput",
    "CheckPrCiStatusInput",
    "ConnectRepoInput",
    "ConnectionState",
    "ContractProbeInput",
    "CreatePrForTaskInput",
    "GetLeaseStateInput",
    "GetPrReviewCommentsInput",
    "GitHubConnection",
    "GitHubTaskSummary",
    "LinkPrToTaskInput",
    "MergeGithubPrInput",
    "ReconcilePrStatusInput",
    "ReleaseLeaseInput",
    "SyncIssuesInput",
    "SyncTaskStatusInput",
    "ValidateReviewTransitionInput",
    "build_github_context_index",
    "encode_connection_update",
    "encode_lease_enforcement_update",
    "encode_pr_mapping_update",
    "encode_sync_state_update",
    "load_connection_state",
    "load_issue_mapping_state",
    "load_lease_enforcement_state",
    "load_pr_mapping_state",
    "load_repo_default_mode_state",
    "load_sync_checkpoint_state",
    "resolve_github_context",
    "resolve_owner_repo",
]
