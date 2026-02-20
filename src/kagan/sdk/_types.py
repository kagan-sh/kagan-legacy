"""Response types for the Kagan SDK.

All response models use Pydantic BaseModel with frozen config for immutability.
Extra fields from the wire are silently ignored (``extra="ignore"``).

Canonical domain models are defined in ``kagan.core.domain.models`` and reused
by SDK/TUI/MCP response wrappers.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from kagan.core.domain.models import (
    Execution,
    ExecutionLogEntry,
    PlanItem,
    PlanTodo,
    Project,
    Repo,
    Task,
)


class _FrozenBase(BaseModel):
    """Shared base for all SDK response models.

    * ``frozen=True`` — instances are immutable (like the former frozen dataclasses).
    * ``extra="ignore"`` — unknown keys in the wire dict are silently dropped.
    * ``populate_by_name=True`` — fields can be set by either alias or Python name.
    """

    model_config = ConfigDict(frozen=True, extra="ignore", populate_by_name=True)


# ---------------------------------------------------------------------------
# Response wrappers
# ---------------------------------------------------------------------------


class TaskResponse(_FrozenBase):
    """Response from task operations."""

    found: bool = False
    task: Task | None = None


class TaskListResponse(_FrozenBase):
    """Response from listing tasks."""

    tasks: list[Task] = []
    count: int = 0


class TaskCreateResponse(_FrozenBase):
    """Response from creating a task."""

    success: bool = False
    task_id: str = ""
    title: str = ""
    status: str = ""
    message: str | None = None


class TaskUpdateResponse(_FrozenBase):
    """Response from updating a task."""

    success: bool = False
    task_id: str = ""
    code: str = ""
    message: str | None = None
    hint: str | None = None


class TaskDeleteResponse(_FrozenBase):
    """Response from deleting a task."""

    success: bool = False
    task_id: str = ""
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
    repos: list[dict[str, Any]] = []
    repo_count: int = 0
    linked_tasks: list[dict[str, Any]] = []


class TaskLogsResponse(_FrozenBase):
    """Response from getting task logs."""

    task_id: str = ""
    logs: list[dict[str, Any]] = []
    count: int = 0
    total_runs: int = 0
    returned_runs: int = 0
    offset: int = 0
    limit: int = 0
    has_more: bool = False
    next_offset: int | None = None
    truncated: bool = False


class ReviewResponse(_FrozenBase):
    """Response from review operations."""

    success: bool = False
    task_id: str = ""
    status: str = ""
    code: str = ""
    message: str | None = None
    hint: str | None = None


class ProjectResponse(_FrozenBase):
    """Response from project operations."""

    found: bool = False
    project: Project | None = None


class ProjectListResponse(_FrozenBase):
    """Response from listing projects."""

    projects: list[Project] = []
    count: int = 0


class ProjectCreateResponse(_FrozenBase):
    """Response from creating a project."""

    success: bool = False
    project_id: str = ""
    name: str = ""
    description: str = ""
    repo_count: int = 0


class RepoListResponse(_FrozenBase):
    """Response from listing repos."""

    repos: list[Repo] = []
    count: int = 0


class AddRepoResponse(_FrozenBase):
    """Response from adding a repo to a project."""

    success: bool = False
    project_id: str = ""
    repo_id: str = ""
    repo_path: str = ""


class JobResponse(_FrozenBase):
    """Response from job operations."""

    success: bool = False
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


class JobListResponse(_FrozenBase):
    """Response from listing job events."""

    success: bool = False
    job_id: str = ""
    task_id: str = ""
    events: list[dict[str, Any]] = []
    total_events: int = 0
    returned_events: int = 0
    offset: int = 0
    limit: int = 0
    has_more: bool = False
    next_offset: int | None = None


class SessionResponse(_FrozenBase):
    """Response from session operations."""

    success: bool = False
    task_id: str = ""
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


class WorkspaceResponse(_FrozenBase):
    """Response from workspace operations."""

    success: bool = False
    message: str | None = None
    code: str | None = None


class WorkspaceListResponse(_FrozenBase):
    """Response from listing workspaces."""

    workspaces: list[dict[str, Any]] = []
    count: int = 0


class SettingsResponse(_FrozenBase):
    """Response from settings operations."""

    success: bool = False
    settings: dict[str, Any] = {}
    message: str | None = None
    updated: dict[str, Any] = {}


class AuditListResponse(_FrozenBase):
    """Response from listing audit events."""

    events: list[dict[str, Any]] = []
    count: int = 0
    truncated: bool = False


class QueuedMessage(_FrozenBase):
    """Single queued message for a session lane."""

    content: str = ""
    author: str | None = None
    metadata: dict[str, Any] | None = None
    queued_at: str = ""


class PlannerDraft(_FrozenBase):
    """Planner draft proposal from list_pending_planner_drafts."""

    id: str | None = None
    project_id: str | None = None
    repo_id: str | None = None
    status: str | None = None
    created_at: str | None = None
    tasks_json: list[dict[str, Any]] = Field(default_factory=list)
    todos_json: list[dict[str, Any]] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def _coerce_list_fields(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        out = dict(data)
        if out.get("tasks_json") is None:
            out["tasks_json"] = []
        if out.get("todos_json") is None:
            out["todos_json"] = []
        return out


class TaskWaitResponse(_FrozenBase):
    """Response from waiting for task status change."""

    changed: bool = False
    timed_out: bool = False
    task_id: str = ""
    previous_status: str | None = None
    current_status: str | None = None
    changed_at: str | None = None
    task: Task | None = None
    code: str = ""
    message: str | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_task(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        task_val = data.get("task")
        if task_val is not None and isinstance(task_val, dict):
            data = {**data, "task": Task.model_validate(task_val)}
        return data


class DiffResponse(_FrozenBase):
    """Response from diff operations."""

    success: bool = False
    diff: str = ""
    code: str = ""


class DiagnosticsResponse(_FrozenBase):
    """Response from diagnostics operations."""

    instrumentation: dict[str, Any] = {}


class PluginInvokeResponse(_FrozenBase):
    """Response from plugin invocation."""

    success: bool = False
    result: Any = None
    error: str | None = None


class QueueMessageResponse(_FrozenBase):
    """Response from queue message operations."""

    success: bool = False
    message: str = ""


class QueueStatusResponse(_FrozenBase):
    """Response from getting queue status."""

    has_queued: bool = False
    lane: str = ""


class QueueListResponse(_FrozenBase):
    """Response from listing queued messages."""

    messages: list[QueuedMessage] = []
    count: int = 0

    @model_validator(mode="before")
    @classmethod
    def _coerce_messages(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        msgs = data.get("messages", [])
        if isinstance(msgs, list):
            coerced = [
                m if isinstance(m, QueuedMessage) else QueuedMessage.model_validate(m) for m in msgs
            ]
            data = {**data, "messages": coerced}
        return data


class ExecutionResponse(_FrozenBase):
    """Response from execution operations."""

    execution: Execution | None = None

    @model_validator(mode="before")
    @classmethod
    def _coerce_execution(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        exec_val = data.get("execution")
        if exec_val is not None and isinstance(exec_val, dict):
            data = {**data, "execution": Execution.model_validate(exec_val)}
        return data


class ExecutionLogResponse(_FrozenBase):
    """Response from execution log operations."""

    entries: list[ExecutionLogEntry] = []
    count: int = 0

    @model_validator(mode="before")
    @classmethod
    def _coerce_entries(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        entries_val = data.get("entries", [])
        if isinstance(entries_val, list):
            coerced = [
                e if isinstance(e, ExecutionLogEntry) else ExecutionLogEntry.model_validate(e)
                for e in entries_val
            ]
            data = {**data, "entries": coerced}
        return data


class ExecutionCountResponse(_FrozenBase):
    """Response from counting executions."""

    count: int = 0


class PlannerDraftResponse(_FrozenBase):
    """Response from planner draft operations."""

    success: bool = False
    message: str = ""


class PlannerDraftListResponse(_FrozenBase):
    """Response from listing planner drafts."""

    drafts: list[PlannerDraft] = []
    count: int = 0

    @model_validator(mode="before")
    @classmethod
    def _coerce_drafts(cls, data: object) -> object:
        if not isinstance(data, dict):
            return data
        drafts_val = data.get("drafts", [])
        if isinstance(drafts_val, list):
            coerced = [
                d if isinstance(d, PlannerDraft) else PlannerDraft.model_validate(d)
                for d in drafts_val
            ]
            data = {**data, "drafts": coerced}
        return data


class WorkspaceDiffResponse(_FrozenBase):
    """Response from workspace diff operations."""

    diff: str = ""


class WorkspaceCommitLogResponse(_FrozenBase):
    """Response from workspace commit log operations."""

    commits: list[str] = []


class WorkspaceDiffStatsResponse(_FrozenBase):
    """Response from workspace diff stats operations."""

    stats: str = ""


class WorkspaceRebaseResponse(_FrozenBase):
    """Response from workspace rebase operations."""

    success: bool = False
    message: str = ""
    conflict_files: list[str] = []


class WorkspaceMergeResponse(_FrozenBase):
    """Response from workspace merge operations."""

    success: bool = False
    message: str = ""
    pr_url: str | None = None


class RepoDiffResponse(_FrozenBase):
    """Response from repo diff operations."""

    repo_id: str = ""
    repo_name: str = ""
    files: list[dict[str, Any]] = []


class AllDiffsResponse(_FrozenBase):
    """Response from getting all diffs."""

    diffs: list[dict[str, Any]] = []


class StartupDecisionResponse(_FrozenBase):
    """Response from decide startup."""

    project_id: str | None = None
    preferred_repo_id: str | None = None
    preferred_path: str | None = None
    suggest_cwd: bool = False
    cwd_path: str | None = None
    cwd_is_git_repo: bool = False
    should_open_project: bool = False


class RepoUpdateResponse(_FrozenBase):
    """Response from repo update operations."""

    success: bool = False
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
    runtime: dict[str, Any] = {}


class RuntimeReconcileResponse(_FrozenBase):
    """Response from runtime reconciliation operations."""

    tasks: list[dict[str, Any]] = []
    count: int = 0


class TaskIdsResponse(_FrozenBase):
    """Response from getting task IDs."""

    task_ids: list[str] = []


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
    actions: list[dict[str, Any]] = []
    forms: list[dict[str, Any]] = []
    badges: list[dict[str, Any]] = []
    diagnostics: list[str] = []


class PluginUiInvokeResponse(_FrozenBase):
    """Response from plugin UI invoke."""

    ok: bool = False
    code: str = ""
    message: str = ""
    data: dict[str, Any] | None = None
    refresh: dict[str, bool] = {}


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
    "PlannerDraft",
    "PlannerDraftListResponse",
    "PlannerDraftResponse",
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
    "TaskWaitResponse",
    "WorkspaceCommitLogResponse",
    "WorkspaceDiffResponse",
    "WorkspaceDiffStatsResponse",
    "WorkspaceListResponse",
    "WorkspaceMergeResponse",
    "WorkspaceRebaseResponse",
    "WorkspaceResponse",
]
