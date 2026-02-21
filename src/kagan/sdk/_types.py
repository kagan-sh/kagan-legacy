"""Response types for the Kagan SDK.

All response models use Pydantic BaseModel with frozen config for immutability.
Extra fields from the wire are silently ignored (``extra="ignore"``).

Canonical domain models are defined in ``kagan.core.domain.models`` and reused
by SDK/TUI/MCP response wrappers.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, model_validator

from kagan.core.domain.models import (
    Execution,
    ExecutionLogEntry,
    FrozenDomainModel,
    PlanItem,
    PlanTodo,
    Project,
    Repo,
    Task,
)
from kagan.core.response_models import TaskLogsResponse as TaskLogsResponse
from kagan.core.response_models import TaskWaitResponse as TaskWaitResponse


class _FrozenBase(FrozenDomainModel):
    """Shared base for all SDK response models.

    * ``frozen=True`` — instances are immutable (like the former frozen dataclasses).
    * ``extra="ignore"`` — unknown keys in the wire dict are silently dropped.
    * ``populate_by_name=True`` — fields can be set by either alias or Python name.
    """


def _coerce_embedded_model(
    data: object,
    *,
    field_name: str,
    model_type: type[BaseModel],
) -> object:
    if not isinstance(data, dict):
        return data
    value = data.get(field_name)
    if isinstance(value, dict):
        return {**data, field_name: model_type.model_validate(value)}
    return data


def _coerce_embedded_model_list(
    data: object,
    *,
    field_name: str,
    model_type: type[BaseModel],
) -> object:
    if not isinstance(data, dict):
        return data
    values = data.get(field_name)
    if not isinstance(values, list):
        return data
    return {
        **data,
        field_name: [
            v if isinstance(v, model_type) else model_type.model_validate(v) for v in values
        ],
    }


# ---------------------------------------------------------------------------
# Response wrappers
# ---------------------------------------------------------------------------


class _SuccessResponse(_FrozenBase):
    success: bool = False


class _TaskScopedResponse(_SuccessResponse):
    task_id: str = ""


class _CountedResponse(_FrozenBase):
    count: int = 0


class TaskResponse(_FrozenBase):
    """Response from task operations."""

    found: bool = False
    task: Task | None = None


class TaskListResponse(_CountedResponse):
    """Response from listing tasks."""

    tasks: list[Task] = Field(default_factory=list)


class TaskCreateResponse(_TaskScopedResponse):
    """Response from creating a task."""

    title: str = ""
    status: str = ""
    message: str | None = None


class TaskUpdateResponse(_TaskScopedResponse):
    """Response from updating a task."""

    code: str = ""
    message: str | None = None
    hint: str | None = None


class TaskDeleteResponse(_TaskScopedResponse):
    """Response from deleting a task."""

    message: str = ""


class ScratchpadResponse(_FrozenBase):
    """Response from scratchpad operations."""

    task_id: str = ""
    content: str = ""
    truncated: bool = False


class TaskContextResponse(_FrozenBase):
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
    repos: list[dict[str, Any]] = Field(default_factory=list)
    repo_count: int = 0
    linked_tasks: list[dict[str, Any]] = Field(default_factory=list)


class ReviewResponse(_TaskScopedResponse):
    """Response from review operations."""

    status: str = ""
    code: str = ""
    message: str | None = None
    hint: str | None = None


class ProjectResponse(_FrozenBase):
    """Response from project operations."""

    found: bool = False
    project: Project | None = None


class ProjectListResponse(_CountedResponse):
    """Response from listing projects."""

    projects: list[Project] = Field(default_factory=list)


class ProjectCreateResponse(_SuccessResponse):
    """Response from creating a project."""

    project_id: str = ""
    name: str = ""
    description: str = ""
    repo_count: int = 0


class RepoListResponse(_CountedResponse):
    """Response from listing repos."""

    repos: list[Repo] = Field(default_factory=list)


class AddRepoResponse(_SuccessResponse):
    """Response from adding a repo to a project."""

    project_id: str = ""
    repo_id: str = ""
    repo_path: str = ""


class JobResponse(_SuccessResponse):
    """Response from job operations."""

    job_id: str = ""
    task_id: str = ""
    action: str = ""
    status: str = ""
    timed_out: bool = False
    timeout_metadata: dict[str, Any] | None = None
    message: str | None = None
    code: str | None = None
    created_at: str = ""
    updated_at: str = ""
    result: dict[str, Any] | None = None
    runtime: dict[str, Any] | None = None
    current_task_type: str | None = None


class JobListResponse(_SuccessResponse):
    """Response from listing job events."""

    job_id: str = ""
    task_id: str = ""
    events: list[dict[str, Any]] = Field(default_factory=list)
    total_events: int = 0
    returned_events: int = 0
    offset: int = 0
    limit: int = 0
    has_more: bool = False
    next_offset: int | None = None


class SessionResponse(_TaskScopedResponse):
    """Response from session operations."""

    message: str = ""
    session_name: str | None = None
    worktree_path: str | None = None
    backend: str | None = None
    already_exists: bool = False


class SessionExistsResponse(_FrozenBase):
    """Response from checking session existence."""

    task_id: str = ""
    exists: bool = False
    session_name: str = ""
    backend: str | None = None
    worktree_path: str | None = None
    prompt_path: str | None = None


class WorkspaceResponse(_SuccessResponse):
    """Response from workspace operations."""

    message: str | None = None
    code: str | None = None


class WorkspaceListResponse(_CountedResponse):
    """Response from listing workspaces."""

    workspaces: list[dict[str, Any]] = Field(default_factory=list)


class SettingsResponse(_SuccessResponse):
    """Response from settings operations."""

    settings: dict[str, Any] = Field(default_factory=dict)
    message: str | None = None
    updated: dict[str, Any] = Field(default_factory=dict)


class AuditListResponse(_CountedResponse):
    """Response from listing audit events."""

    events: list[dict[str, Any]] = Field(default_factory=list)
    truncated: bool = False


class QueuedMessage(_FrozenBase):
    """Single queued message for a session lane."""

    content: str = ""
    author: str | None = None
    metadata: dict[str, Any] | None = None
    queued_at: str = ""


class TaskWaitAnyResponse(_FrozenBase):
    """Response from waiting for any task lifecycle change."""

    changed: bool = False
    timed_out: bool = False
    task_id: str = ""
    event_type: str | None = None
    changed_at: str | None = None
    code: str = ""
    message: str | None = None


class DiffResponse(_SuccessResponse):
    """Response from diff operations."""

    diff: str = ""
    code: str = ""


class DiagnosticsResponse(_FrozenBase):
    """Response from diagnostics operations."""

    instrumentation: dict[str, Any] = Field(default_factory=dict)


class PluginInvokeResponse(_SuccessResponse):
    """Response from plugin invocation."""

    result: Any = None
    error: str | None = None


class QueueMessageResponse(_SuccessResponse):
    """Response from queue message operations."""

    message: str | QueuedMessage | None = None
    code: str | None = None
    content: str | None = None
    author: str | None = None
    metadata: dict[str, Any] | None = None
    queued_at: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_message_payload(cls, data: object) -> object:
        payload = _coerce_embedded_model(data, field_name="message", model_type=QueuedMessage)
        if not isinstance(payload, dict):
            return payload

        # `automation.queue_message` responds with content/author/queued_at fields.
        if (
            payload.get("message") is None
            and isinstance(payload.get("content"), str)
            and isinstance(payload.get("queued_at"), str)
        ):
            payload["message"] = QueuedMessage.model_validate(
                {
                    "content": payload.get("content"),
                    "author": payload.get("author"),
                    "metadata": payload.get("metadata"),
                    "queued_at": payload.get("queued_at"),
                }
            )
        return payload


class QueueStatusResponse(_FrozenBase):
    """Response from getting queue status."""

    has_queued: bool = False
    lane: str = ""


class QueueListResponse(_CountedResponse):
    """Response from listing queued messages."""

    messages: list[QueuedMessage] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_messages(cls, data: object) -> object:
        return _coerce_embedded_model_list(data, field_name="messages", model_type=QueuedMessage)


class ExecutionResponse(_FrozenBase):
    """Response from execution operations."""

    execution: Execution | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_execution(cls, data: object) -> object:
        return _coerce_embedded_model(data, field_name="execution", model_type=Execution)


class ExecutionLogResponse(_CountedResponse):
    """Response from execution log operations."""

    entries: list[ExecutionLogEntry] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_entries(cls, data: object) -> object:
        return _coerce_embedded_model_list(data, field_name="entries", model_type=ExecutionLogEntry)


class ExecutionCountResponse(_FrozenBase):
    """Response from counting executions."""

    count: int = 0


class WorkspaceDiffResponse(_FrozenBase):
    """Response from workspace diff operations."""

    diff: str = ""


class WorkspaceCommitLogResponse(_FrozenBase):
    """Response from workspace commit log operations."""

    commits: list[str] = Field(default_factory=list)


class WorkspaceDiffStatsResponse(_FrozenBase):
    """Response from workspace diff stats operations."""

    stats: str = ""


class WorkspaceRebaseResponse(_SuccessResponse):
    """Response from workspace rebase operations."""

    message: str = ""
    conflict_files: list[str] = Field(default_factory=list)


class WorkspaceMergeResponse(_SuccessResponse):
    """Response from workspace merge operations."""

    message: str = ""
    pr_url: str | None = None


class RepoDiffResponse(_FrozenBase):
    """Response from repo diff operations."""

    repo_id: str = ""
    repo_name: str = ""
    files: list[dict[str, Any]] = Field(default_factory=list)


class AllDiffsResponse(_FrozenBase):
    """Response from getting all diffs."""

    diffs: list[dict[str, Any]] = Field(default_factory=list)


class StartupDecisionResponse(_FrozenBase):
    """Response from decide startup."""

    project_id: str | None = None
    preferred_repo_id: str | None = None
    preferred_path: str | None = None
    suggest_cwd: bool = False
    cwd_path: str | None = None
    cwd_is_git_repo: bool = False
    should_open_project: bool = False


class RepoUpdateResponse(_SuccessResponse):
    """Response from repo update operations."""

    repo_id: str = ""


class BoolResponse(_FrozenBase):
    """Generic boolean response."""

    value: bool = False
    message: str = ""


class RuntimeStateResponse(_FrozenBase):
    """Response from runtime state operations."""

    project_id: str | None = None
    repo_id: str | None = None


class RuntimeViewResponse(_FrozenBase):
    """Response from runtime view operations."""

    task_id: str = ""
    phase: str | None = None
    execution_id: str | None = None
    run_count: int = 0
    has_running_agent: bool = False
    has_review_agent: bool = False
    runtime: dict[str, Any] = Field(default_factory=dict)


class RuntimeReconcileResponse(_CountedResponse):
    """Response from runtime reconciliation operations."""

    tasks: list[dict[str, Any]] = Field(default_factory=list)


class TaskIdsResponse(_FrozenBase):
    """Response from getting task IDs."""

    task_ids: list[str] = Field(default_factory=list)


class TaskBaseBranchResponse(_FrozenBase):
    """Response from resolving task base branch."""

    branch: str = ""


class AutoOutputResponse(_FrozenBase):
    """Response from auto output operations."""

    can_open_output: bool = False
    execution_id: str | None = None
    is_running: bool = False
    output_mode: str = ""


class PluginUiCatalogResponse(_FrozenBase):
    """Response from plugin UI catalog."""

    schema_version: str = ""
    actions: list[dict[str, Any]] = Field(default_factory=list)
    forms: list[dict[str, Any]] = Field(default_factory=list)
    badges: list[dict[str, Any]] = Field(default_factory=list)
    diagnostics: list[str] = Field(default_factory=list)


class PluginUiInvokeResponse(_FrozenBase):
    """Response from plugin UI invoke."""

    ok: bool = False
    code: str = ""
    message: str = ""
    data: dict[str, Any] | None = None
    refresh: dict[str, bool] = Field(default_factory=dict)


__all__ = [
    "AddRepoResponse",
    "AllDiffsResponse",
    "AuditListResponse",
    "AutoOutputResponse",
    "BoolResponse",
    "DiagnosticsResponse",
    "DiffResponse",
    "Execution",
    "ExecutionCountResponse",
    "ExecutionLogEntry",
    "ExecutionLogResponse",
    "ExecutionResponse",
    "JobListResponse",
    "JobResponse",
    "PlanItem",
    "PlanTodo",
    "PluginInvokeResponse",
    "PluginUiCatalogResponse",
    "PluginUiInvokeResponse",
    "Project",
    "ProjectCreateResponse",
    "ProjectListResponse",
    "ProjectResponse",
    "QueueListResponse",
    "QueueMessageResponse",
    "QueueStatusResponse",
    "QueuedMessage",
    "Repo",
    "RepoDiffResponse",
    "RepoListResponse",
    "RepoUpdateResponse",
    "ReviewResponse",
    "RuntimeReconcileResponse",
    "RuntimeStateResponse",
    "RuntimeViewResponse",
    "ScratchpadResponse",
    "SessionExistsResponse",
    "SessionResponse",
    "SettingsResponse",
    "StartupDecisionResponse",
    "Task",
    "TaskContextResponse",
    "TaskCreateResponse",
    "TaskDeleteResponse",
    "TaskIdsResponse",
    "TaskListResponse",
    "TaskLogsResponse",
    "TaskResponse",
    "TaskUpdateResponse",
    "TaskWaitAnyResponse",
    "TaskWaitResponse",
    "WorkspaceCommitLogResponse",
    "WorkspaceDiffResponse",
    "WorkspaceDiffStatsResponse",
    "WorkspaceListResponse",
    "WorkspaceMergeResponse",
    "WorkspaceRebaseResponse",
    "WorkspaceResponse",
]
