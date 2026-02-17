"""Response types for the Kagan SDK."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class TaskResponse:
    """Response from task operations."""

    found: bool = False
    task: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TaskListResponse:
    """Response from listing tasks."""

    tasks: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0


@dataclass(frozen=True, slots=True)
class TaskCreateResponse:
    """Response from creating a task."""

    success: bool = False
    task_id: str = ""
    title: str = ""
    status: str = ""
    message: str | None = None


@dataclass(frozen=True, slots=True)
class TaskUpdateResponse:
    """Response from updating a task."""

    success: bool = False
    task_id: str = ""
    code: str = ""
    message: str | None = None
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class TaskDeleteResponse:
    """Response from deleting a task."""

    success: bool = False
    task_id: str = ""
    message: str = ""


@dataclass(frozen=True, slots=True)
class ScratchpadResponse:
    """Response from scratchpad operations."""

    task_id: str = ""
    content: str = ""
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class TaskContextResponse:
    """Response from getting task context."""

    task_id: str = ""
    project_id: str = ""
    title: str = ""
    description: str = ""
    status: str = ""
    acceptance_criteria: str | None = None
    scratchpad: str = ""
    workspace_id: str | None = None
    workspace_branch: str | None = None
    workspace_path: str | None = None
    repos: list[dict[str, Any]] = field(default_factory=list)
    repo_count: int = 0
    linked_tasks: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TaskLogsResponse:
    """Response from getting task logs."""

    task_id: str = ""
    logs: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0
    total_runs: int = 0
    returned_runs: int = 0
    offset: int = 0
    limit: int = 0
    has_more: bool = False
    next_offset: int | None = None
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class ReviewResponse:
    """Response from review operations."""

    success: bool = False
    task_id: str = ""
    status: str = ""
    code: str = ""
    message: str | None = None
    hint: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectResponse:
    """Response from project operations."""

    found: bool = False
    project: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ProjectListResponse:
    """Response from listing projects."""

    projects: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0


@dataclass(frozen=True, slots=True)
class ProjectCreateResponse:
    """Response from creating a project."""

    success: bool = False
    project_id: str = ""
    name: str = ""
    description: str = ""
    repo_count: int = 0


@dataclass(frozen=True, slots=True)
class RepoListResponse:
    """Response from listing repos."""

    repos: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0


@dataclass(frozen=True, slots=True)
class JobResponse:
    """Response from job operations."""

    success: bool = False
    job_id: str = ""
    task_id: str = ""
    action: str = ""
    status: str = ""
    message: str | None = None
    code: str | None = None
    created_at: str = ""
    updated_at: str = ""


@dataclass(frozen=True, slots=True)
class JobListResponse:
    """Response from listing job events."""

    success: bool = False
    job_id: str = ""
    task_id: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    total_events: int = 0
    returned_events: int = 0
    offset: int = 0
    limit: int = 0
    has_more: bool = False
    next_offset: int | None = None


@dataclass(frozen=True, slots=True)
class SessionResponse:
    """Response from session operations."""

    success: bool = False
    task_id: str = ""
    message: str = ""
    session_name: str | None = None
    worktree_path: str | None = None
    backend: str | None = None
    already_exists: bool = False


@dataclass(frozen=True, slots=True)
class SessionExistsResponse:
    """Response from checking session existence."""

    task_id: str = ""
    exists: bool = False
    session_name: str = ""
    backend: str | None = None
    worktree_path: str | None = None
    prompt_path: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceResponse:
    """Response from workspace operations."""

    success: bool = False
    message: str | None = None
    code: str | None = None


@dataclass(frozen=True, slots=True)
class WorkspaceListResponse:
    """Response from listing workspaces."""

    workspaces: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0


@dataclass(frozen=True, slots=True)
class SettingsResponse:
    """Response from settings operations."""

    success: bool = False
    settings: dict[str, Any] = field(default_factory=dict)
    message: str | None = None
    updated: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AuditListResponse:
    """Response from listing audit events."""

    events: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0
    truncated: bool = False


@dataclass(frozen=True, slots=True)
class TaskWaitResponse:
    """Response from waiting for task status change."""

    changed: bool = False
    timed_out: bool = False
    task_id: str = ""
    previous_status: str | None = None
    current_status: str | None = None
    changed_at: str | None = None
    task: dict[str, Any] | None = None
    code: str = ""
    message: str | None = None


@dataclass(frozen=True, slots=True)
class DiffResponse:
    """Response from diff operations."""

    success: bool = False
    diff: str = ""
    code: str = ""


@dataclass(frozen=True, slots=True)
class DiagnosticsResponse:
    """Response from diagnostics operations."""

    instrumentation: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class PluginInvokeResponse:
    """Response from plugin invocation."""

    success: bool = False
    result: Any = None
    error: str | None = None


@dataclass(frozen=True, slots=True)
class QueueMessageResponse:
    """Response from queue message operations."""

    success: bool = False
    message: str = ""


@dataclass(frozen=True, slots=True)
class QueueStatusResponse:
    """Response from getting queue status."""

    has_queued: bool = False
    lane: str = ""


@dataclass(frozen=True, slots=True)
class QueueListResponse:
    """Response from listing queued messages."""

    messages: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0


@dataclass(frozen=True, slots=True)
class ExecutionResponse:
    """Response from execution operations."""

    execution: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class ExecutionLogResponse:
    """Response from execution log operations."""

    entries: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0


@dataclass(frozen=True, slots=True)
class ExecutionCountResponse:
    """Response from counting executions."""

    count: int = 0


@dataclass(frozen=True, slots=True)
class PlannerDraftResponse:
    """Response from planner draft operations."""

    success: bool = False
    message: str = ""


@dataclass(frozen=True, slots=True)
class PlannerDraftListResponse:
    """Response from listing planner drafts."""

    drafts: list[dict[str, Any]] = field(default_factory=list)
    count: int = 0


@dataclass(frozen=True, slots=True)
class WorkspaceDiffResponse:
    """Response from workspace diff operations."""

    diff: str = ""


@dataclass(frozen=True, slots=True)
class WorkspaceCommitLogResponse:
    """Response from workspace commit log operations."""

    commits: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class WorkspaceDiffStatsResponse:
    """Response from workspace diff stats operations."""

    stats: str = ""


@dataclass(frozen=True, slots=True)
class WorkspaceRebaseResponse:
    """Response from workspace rebase operations."""

    success: bool = False
    message: str = ""
    conflict_files: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class WorkspaceMergeResponse:
    """Response from workspace merge operations."""

    success: bool = False
    message: str = ""
    pr_url: str | None = None


@dataclass(frozen=True, slots=True)
class RepoDiffResponse:
    """Response from repo diff operations."""

    repo_id: str = ""
    repo_name: str = ""
    files: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class AllDiffsResponse:
    """Response from getting all diffs."""

    diffs: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class StartupDecisionResponse:
    """Response from decide startup."""

    project_id: str | None = None
    preferred_repo_id: str | None = None
    preferred_path: str | None = None
    suggest_cwd: bool = False
    cwd_path: str | None = None
    cwd_is_git_repo: bool = False
    should_open_project: bool = False


@dataclass(frozen=True, slots=True)
class RepoUpdateResponse:
    """Response from repo update operations."""

    success: bool = False
    repo_id: str = ""


@dataclass(frozen=True, slots=True)
class BoolResponse:
    """Generic boolean response."""

    value: bool = False
    message: str = ""


@dataclass(frozen=True, slots=True)
class RuntimeStateResponse:
    """Response from runtime state operations."""

    project_id: str | None = None
    repo_id: str | None = None


@dataclass(frozen=True, slots=True)
class RuntimeViewResponse:
    """Response from runtime view operations."""

    view: dict[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TaskIdsResponse:
    """Response from getting task IDs."""

    task_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class TaskBaseBranchResponse:
    """Response from resolving task base branch."""

    branch: str = ""


@dataclass(frozen=True, slots=True)
class AutoOutputResponse:
    """Response from auto output operations."""

    can_open_output: bool = False
    execution_id: str | None = None
    is_running: bool = False
    output_mode: str = ""


@dataclass(frozen=True, slots=True)
class PluginUiCatalogResponse:
    """Response from plugin UI catalog."""

    schema_version: str = ""
    actions: list[dict[str, Any]] = field(default_factory=list)
    forms: list[dict[str, Any]] = field(default_factory=list)
    badges: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True, slots=True)
class PluginUiInvokeResponse:
    """Response from plugin UI invoke."""

    ok: bool = False
    code: str = ""
    message: str = ""
    data: dict[str, Any] | None = None


__all__ = [
    "AllDiffsResponse",
    "AuditListResponse",
    "AutoOutputResponse",
    "BoolResponse",
    "DiagnosticsResponse",
    "DiffResponse",
    "ExecutionCountResponse",
    "ExecutionLogResponse",
    "ExecutionResponse",
    "JobListResponse",
    "JobResponse",
    "PlannerDraftListResponse",
    "PlannerDraftResponse",
    "PluginInvokeResponse",
    "PluginUiCatalogResponse",
    "PluginUiInvokeResponse",
    "ProjectCreateResponse",
    "ProjectListResponse",
    "ProjectResponse",
    "QueueListResponse",
    "QueueMessageResponse",
    "QueueStatusResponse",
    "RepoDiffResponse",
    "RepoUpdateResponse",
    "ReviewResponse",
    "RuntimeStateResponse",
    "RuntimeViewResponse",
    "ScratchpadResponse",
    "SessionExistsResponse",
    "SessionResponse",
    "SettingsResponse",
    "StartupDecisionResponse",
    "TaskContextResponse",
    "TaskCreateResponse",
    "TaskDeleteResponse",
    "TaskIdsResponse",
    "TaskListResponse",
    "TaskLogsResponse",
    "TaskResponse",
    "TaskUpdateResponse",
    "TaskWaitResponse",
    "WorkspaceCommitLogResponse",
    "WorkspaceDiffResponse",
    "WorkspaceDiffStatsResponse",
    "WorkspaceListResponse",
    "WorkspaceMergeResponse",
    "WorkspaceRebaseResponse",
    "WorkspaceResponse",
]
