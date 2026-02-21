"""Pydantic response models for MCP tools.

MCP-specific models compose canonical domain types from kagan.core.domain.models
with recovery envelopes (RecoveryResponse) for tool responses.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from kagan.core.domain.models import (
    AgentLogEntry,
    PlanItem,
    PlanTodo,
    Project,
    Repo,
    TaskRuntimeState,
    TaskSummary,
)
from kagan.core.domain.pair_terminal_backends import PairTerminalBackendLiteral
from kagan.core.response_models import TaskWaitResponse as _CoreTaskWaitResponse


class RecoveryResponse(BaseModel):
    """Shared recovery envelope for actionable MCP responses."""

    message: str | None = Field(default=None, description="Human-readable status message")
    code: str | None = Field(default=None, description="Machine-readable status code")
    hint: str | None = Field(default=None, description="Actionable remediation guidance")
    next_tool: str | None = Field(default=None, description="Suggested next MCP tool")
    next_arguments: dict[str, object] | None = Field(
        default=None,
        description="Suggested arguments for next_tool",
    )


class MutatingResponse(RecoveryResponse):
    """Base response for mutating MCP tools."""

    success: bool = Field(description="Whether the operation succeeded")


class TaskScopedMutatingResponse(MutatingResponse):
    """Base response for mutating MCP tools that target a specific task."""

    task_id: str = Field(description="ID of the task")


class JobScopedResponse(MutatingResponse):
    """Base response for MCP tools scoped to a specific asynchronous job."""

    job_id: str = Field(description="Core job identifier")
    task_id: str = Field(description="ID of the associated task")


class _CountedResponse(BaseModel):
    """Shared list/count envelope for MCP collection responses."""

    count: int = Field(default=0, description="Total number of items returned")


class TaskWaitResponse(_CoreTaskWaitResponse):
    """MCP response from task_wait long-poll tool."""

    # Override code to nullable for MCP recovery protocol
    code: str | None = None  # type: ignore[assignment]
    hint: str | None = Field(default=None, description="Actionable remediation guidance")
    next_tool: str | None = Field(default=None, description="Suggested next MCP tool")
    next_arguments: dict[str, object] | None = Field(
        default=None, description="Suggested arguments for next_tool"
    )


class PlanProposalResponse(MutatingResponse):
    """Response from plan_submit tool."""

    status: str = Field(description="'received' when plan was accepted")
    task_count: int = Field(description="Number of tasks in the proposal")
    todo_count: int = Field(description="Number of todos in the proposal")
    tasks: list[PlanItem] | None = Field(
        default=None,
        description="Echoed normalized task payload for ACP clients that need robust parsing",
    )
    todos: list[PlanTodo] | None = Field(
        default=None,
        description="Echoed normalized todo payload for ACP clients that need robust parsing",
    )


class TaskListResponse(_CountedResponse):
    """Response from task_list tool."""

    tasks: list[TaskSummary] = Field(default_factory=list, description="List of tasks")


class TaskLogsResponse(RecoveryResponse):
    """Response from task_logs tool."""

    task_id: str = Field(description="ID of the task")
    logs: list[AgentLogEntry] = Field(default_factory=list, description="Ordered log entries")
    count: int = Field(default=0, description="Number of logs returned")
    total_runs: int = Field(default=0, description="Total runs available for this task")
    returned_runs: int = Field(default=0, description="Number of runs included in this page")
    offset: int = Field(default=0, description="Page offset used for this response")
    limit: int = Field(default=0, description="Page limit used for this response")
    has_more: bool = Field(default=False, description="Whether additional runs are available")
    next_offset: int | None = Field(default=None, description="Offset for the next page")
    truncated: bool = Field(
        default=False,
        description="Whether log content was reduced for transport safety",
    )


class TaskCreateResponse(TaskScopedMutatingResponse):
    """Response from task_create tool."""

    title: str = Field(description="Task title")
    status: str = Field(description="Initial status (usually 'backlog')")


class JobResponse(JobScopedResponse):
    """Response from job_start, job_poll, and job_cancel tools."""

    action: str | None = Field(default=None, description="Submitted job action")
    status: str | None = Field(default=None, description="Current job status")
    timed_out: bool | None = Field(
        default=None,
        description="Whether job_poll(wait=true) returned before terminal status due to timeout",
    )
    timeout_metadata: dict[str, object] | None = Field(
        default=None,
        description="Structured timeout metadata from core when available",
    )
    created_at: str | None = Field(default=None, description="Job creation timestamp")
    updated_at: str | None = Field(default=None, description="Job last update timestamp")
    result: dict[str, object] | None = Field(
        default=None,
        description="Terminal action result payload when available",
    )
    runtime: TaskRuntimeState | None = Field(
        default=None,
        description="Runtime metadata extracted from result payload when available",
    )
    current_task_type: str | None = Field(
        default=None,
        description="Current task execution mode when relevant (AUTO or PAIR)",
    )


class JobEvent(BaseModel):
    """A single event emitted during asynchronous job execution."""

    job_id: str | None = Field(default=None, description="Core job identifier")
    task_id: str | None = Field(default=None, description="Associated task ID")
    status: str | None = Field(default=None, description="Job status at the time of this event")
    timestamp: str | None = Field(default=None, description="ISO timestamp for this event")
    message: str | None = Field(default=None, description="Human-readable event summary")
    code: str | None = Field(
        default=None,
        description="Machine-readable event code when available",
    )


class JobEventsResponse(JobScopedResponse):
    """Response from job_poll(events=true) tool."""

    events: list[JobEvent] = Field(
        default_factory=list,
        description="Ordered list of job events",
    )
    total_events: int = Field(default=0, description="Total events available for this job")
    returned_events: int = Field(default=0, description="Number of events in this page")
    offset: int = Field(default=0, description="Page offset used for this response")
    limit: int = Field(default=0, description="Page limit used for this response")
    has_more: bool = Field(default=False, description="Whether additional events are available")
    next_offset: int | None = Field(default=None, description="Offset for the next page")


class TaskDeleteResponse(TaskScopedMutatingResponse):
    """Response from task_delete tool."""


class ProjectInfo(Project):
    """MCP project summary. Uses project_id in JSON for MCP contract."""

    id: str = Field(
        default="",
        validation_alias="project_id",
        serialization_alias="project_id",
        description="Unique project identifier",
    )


class ProjectListResponse(_CountedResponse):
    """Response from project_list tool."""

    projects: list[ProjectInfo] = Field(default_factory=list, description="List of projects")


class ProjectOpenResponse(MutatingResponse):
    """Response from project_open tool. Composes recovery envelope with project data."""

    project_id: str = Field(description="ID of the opened project")
    name: str = Field(description="Project name")


class RepoListItem(Repo):
    """MCP repo summary. Uses repo_id in JSON for MCP contract."""

    id: str = Field(
        default="",
        validation_alias="repo_id",
        serialization_alias="repo_id",
        description="Unique repository identifier",
    )


class RepoListResponse(_CountedResponse):
    """Response from repo_list tool."""

    repos: list[RepoListItem] = Field(default_factory=list, description="List of repositories")


class ReviewActionResponse(TaskScopedMutatingResponse):
    """Response from the review tool (approve, reject, merge, rebase actions)."""


class AuditEvent(BaseModel):
    """A single audit event entry."""

    event_id: str | None = Field(default=None, description="Unique event identifier")
    occurred_at: str | None = Field(default=None, description="ISO timestamp of the event")
    actor_type: str | None = Field(default=None, description="Type of actor (user, agent, system)")
    actor_id: str | None = Field(default=None, description="Identifier of the actor")
    capability: str | None = Field(default=None, description="Capability that produced the event")
    command_name: str | None = Field(default=None, description="Command that was executed")
    success: bool | None = Field(default=None, description="Whether the command succeeded")


class AuditTailResponse(_CountedResponse):
    """Response from audit_list tool."""

    events: list[AuditEvent] = Field(default_factory=list, description="List of audit events")


class InstrumentationSnapshotResponse(BaseModel):
    """Response from internal diagnostics instrumentation tool."""

    enabled: bool = Field(description="Whether instrumentation collection is enabled")
    log_events: bool = Field(description="Whether structured instrumentation logs are enabled")
    counters: dict[str, int] = Field(
        default_factory=dict,
        description="Counter aggregates keyed by metric name",
    )
    timings: dict[str, dict[str, float | int]] = Field(
        default_factory=dict,
        description="Timing aggregates keyed by metric name",
    )


class SettingsGetResponse(BaseModel):
    """Response from settings_get tool."""

    settings: dict[str, object] = Field(
        default_factory=dict,
        description="Allowlisted settings snapshot keyed by dotted paths",
    )


class SettingsUpdateResponse(MutatingResponse):
    """Response from settings_set tool."""

    updated: dict[str, object] = Field(
        default_factory=dict,
        description="Fields accepted and applied in this update request",
    )
    settings: dict[str, object] = Field(
        default_factory=dict,
        description="Settings snapshot after update (or current snapshot on failure)",
    )


class PluginToolResponse(MutatingResponse):
    """Generic response envelope for plugin-contributed MCP tools."""

    plugin_id: str = Field(default="", description="Plugin that handled the operation")
    capability: str = Field(default="", description="Plugin capability namespace")
    method: str = Field(default="", description="Operation method name")
    data: dict[str, object] = Field(
        default_factory=dict,
        description="Plugin-specific response payload",
    )


WorkflowStatusInput = Literal[
    "BACKLOG",
    "IN_PROGRESS",
    "REVIEW",
    "DONE",
    "backlog",
    "in_progress",
    "review",
    "done",
]
TaskTypeInput = Literal["AUTO", "PAIR", "auto", "pair"]
TaskStatusInput = WorkflowStatusInput
TaskPriorityInput = Literal["LOW", "MED", "MEDIUM", "HIGH", "low", "med", "medium", "high"]
JobActionInput = Literal["start_agent", "stop_agent"]
TerminalBackendInput = PairTerminalBackendLiteral
ReviewActionInput = Literal["approve", "reject", "merge", "rebase"]
RejectionActionInput = Literal["reopen", "return", "in_progress", "backlog"]
SessionActionInput = Literal["open", "read", "close"]


__all__ = [
    "AgentLogEntry",
    "AuditEvent",
    "AuditTailResponse",
    "InstrumentationSnapshotResponse",
    "JobActionInput",
    "JobEvent",
    "JobEventsResponse",
    "JobResponse",
    "MutatingResponse",
    "PlanProposalResponse",
    "PluginToolResponse",
    "ProjectInfo",
    "ProjectListResponse",
    "ProjectOpenResponse",
    "RecoveryResponse",
    "RejectionActionInput",
    "RepoListItem",
    "RepoListResponse",
    "ReviewActionInput",
    "ReviewActionResponse",
    "SessionActionInput",
    "SettingsGetResponse",
    "SettingsUpdateResponse",
    "TaskCreateResponse",
    "TaskDeleteResponse",
    "TaskListResponse",
    "TaskLogsResponse",
    "TaskPriorityInput",
    "TaskRuntimeState",
    "TaskScopedMutatingResponse",
    "TaskStatusInput",
    "TaskSummary",
    "TaskTypeInput",
    "TaskWaitResponse",
    "TerminalBackendInput",
    "WorkflowStatusInput",
]
