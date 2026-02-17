"""Typed input models for GitHub plugin use cases."""

from __future__ import annotations

from dataclasses import dataclass


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


__all__ = [
    "AcquireLeaseInput",
    "AutoCreateReviewPrInput",
    "CheckPrCiStatusInput",
    "ConnectRepoInput",
    "ContractProbeInput",
    "CreatePrForTaskInput",
    "GetLeaseStateInput",
    "GetPrReviewCommentsInput",
    "LinkPrToTaskInput",
    "MergeGithubPrInput",
    "ReconcilePrStatusInput",
    "ReleaseLeaseInput",
    "SyncIssuesInput",
    "SyncTaskStatusInput",
    "ValidateReviewTransitionInput",
]
