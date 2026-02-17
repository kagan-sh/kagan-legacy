"""Auto-generation of MCP tools from SDK methods.

This module provides infrastructure for generating MCP tools from the Kagan SDK.
Tools are registered with FastMCP using helper functions that wrap SDK operations.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from mcp.server.fastmcp import Context
from mcp.server.session import ServerSession
from mcp.types import ToolAnnotations

from kagan.core.agents import planner as planner_models
from kagan.core.policy import (
    AuditMethod,
    CapabilityProfile,
    DiagnosticsMethod,
    JobsMethod,
    PlanMethod,
    ProjectsMethod,
    ProtocolCapability,
    ReviewMethod,
    SessionsMethod,
    SettingsMethod,
    TasksMethod,
    protocol_call,
)
from kagan.mcp._response_models import (
    AuditTailResponse,
    PlanProposalResponse,
    ProjectListResponse,
    RepoListResponse,
    TaskListResponse,
    TaskLogsResponse,
    TaskRuntimeState,
    TaskWaitResponse,
)

if TYPE_CHECKING:
    from collections.abc import Callable

    from mcp.server.fastmcp import FastMCP

    from kagan.mcp._response_models import RepoListResponse
    from kagan.mcp.tools import CoreClientBridge

logger = logging.getLogger(__name__)

_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
_MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)

TASK_TYPE_AUTO = "AUTO"
TASK_TYPE_PAIR = "PAIR"
TASK_TYPE_VALUES = frozenset({TASK_TYPE_AUTO, TASK_TYPE_PAIR})

JOB_NON_TERMINAL_STATUSES = frozenset({"queued", "running"})
JOB_TERMINAL_STATUSES = frozenset({"succeeded", "failed", "cancelled"})

DEFAULT_JOB_POLL_WAIT_TIMEOUT_SECONDS = 1.5

_PROTOCOL_CALLS = {
    "plan_propose": protocol_call(ProtocolCapability.PLAN, PlanMethod.PROPOSE),
    "tasks_get": protocol_call(ProtocolCapability.TASKS, TasksMethod.GET),
    "tasks_scratchpad": protocol_call(ProtocolCapability.TASKS, TasksMethod.SCRATCHPAD),
    "tasks_list": protocol_call(ProtocolCapability.TASKS, TasksMethod.LIST),
    "tasks_logs": protocol_call(ProtocolCapability.TASKS, TasksMethod.LOGS),
    "tasks_wait": protocol_call(ProtocolCapability.TASKS, TasksMethod.WAIT),
    "tasks_update_scratchpad": protocol_call(
        ProtocolCapability.TASKS, TasksMethod.UPDATE_SCRATCHPAD
    ),
    "tasks_create": protocol_call(ProtocolCapability.TASKS, TasksMethod.CREATE),
    "tasks_update": protocol_call(ProtocolCapability.TASKS, TasksMethod.UPDATE),
    "tasks_move": protocol_call(ProtocolCapability.TASKS, TasksMethod.MOVE),
    "tasks_delete": protocol_call(ProtocolCapability.TASKS, TasksMethod.DELETE),
    "projects_list": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.LIST),
    "projects_repos": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.REPOS),
    "projects_create": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.CREATE),
    "projects_open": protocol_call(ProtocolCapability.PROJECTS, ProjectsMethod.OPEN),
    "audit_list": protocol_call(ProtocolCapability.AUDIT, AuditMethod.LIST),
    "jobs_submit": protocol_call(ProtocolCapability.JOBS, JobsMethod.SUBMIT),
    "jobs_get": protocol_call(ProtocolCapability.JOBS, JobsMethod.GET),
    "jobs_wait": protocol_call(ProtocolCapability.JOBS, JobsMethod.WAIT),
    "jobs_events": protocol_call(ProtocolCapability.JOBS, JobsMethod.EVENTS),
    "jobs_cancel": protocol_call(ProtocolCapability.JOBS, JobsMethod.CANCEL),
    "sessions_create": protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.CREATE),
    "sessions_exists": protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.EXISTS),
    "sessions_kill": protocol_call(ProtocolCapability.SESSIONS, SessionsMethod.KILL),
    "review_request": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.REQUEST),
    "settings_get": protocol_call(ProtocolCapability.SETTINGS, SettingsMethod.GET),
    "settings_update": protocol_call(ProtocolCapability.SETTINGS, SettingsMethod.UPDATE),
    "diagnostics_instrumentation": protocol_call(
        ProtocolCapability.DIAGNOSTICS, DiagnosticsMethod.INSTRUMENTATION
    ),
    "review_approve": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.APPROVE),
    "review_reject": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.REJECT),
    "review_merge": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.MERGE),
    "review_rebase": protocol_call(ProtocolCapability.REVIEW, ReviewMethod.REBASE),
}


@dataclass(frozen=True, slots=True)
class ToolRegistrationContext:
    """Callbacks required by full-mode tool registration."""

    require_bridge: Callable[..., CoreClientBridge]
    runtime_state_from_raw: Callable[[dict[str, Any] | None], TaskRuntimeState | None]


@dataclass(frozen=True, slots=True)
class SharedToolRegistrationContext:
    """Callbacks required by shared tool registration."""

    require_bridge: Callable[..., CoreClientBridge]
    runtime_state_from_raw: Callable[[dict[str, Any] | None], TaskRuntimeState | None]


MCPContext = Context[ServerSession, Any]


def _normalize_mode(mode: str) -> str:
    return "full" if mode.lower() == "full" else "summary"


def _int_or_none(value: object) -> int | None:
    if isinstance(value, int):
        return value
    if isinstance(value, str):
        try:
            return int(value)
        except ValueError:
            return None
    return None


def _str_or_none(value: object) -> str | None:
    if isinstance(value, str):
        return value
    return None


def _dict_or_none(value: object) -> dict[str, object] | None:
    if isinstance(value, dict):
        return {str(k): v for k, v in value.items()}
    return None


def _normalize_agent_log_entries(logs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Normalize log entries from raw response."""
    normalized = []
    for log in logs:
        if not isinstance(log, dict):
            continue
        run = log.get("run")
        content = log.get("content")
        created_at = log.get("created_at")
        if run is None or content is None or created_at is None:
            continue
        normalized.append(
            {
                "run": int(run),
                "content": str(content),
                "created_at": str(created_at),
            }
        )
    return normalized


def _is_allowed(profile: str, capability: str, method: str) -> bool:
    """Return whether profile may call capability.method."""
    from kagan.core.policy import CAPABILITY_PROFILES, CapabilityProfile

    if profile == str(CapabilityProfile.MAINTAINER):
        return True
    try:
        normalized_profile = CapabilityProfile(profile)
    except ValueError:
        return False
    return protocol_call(capability, method) in CAPABILITY_PROFILES.get(
        normalized_profile, frozenset()
    )


def register_shared_tools(
    mcp: FastMCP,
    *,
    allows_all: Callable[..., bool],
    effective_profile: str,
    helpers: SharedToolRegistrationContext,
) -> None:
    """Register planner/read-only/shared MCP tools."""
    _require_bridge = helpers.require_bridge
    _runtime_state_from_raw = helpers.runtime_state_from_raw

    if allows_all(_PROTOCOL_CALLS["plan_propose"]) and effective_profile == str(
        CapabilityProfile.PLANNER
    ):

        @mcp.tool(annotations=_MUTATING)
        async def plan_submit(
            tasks: list[planner_models.ProposedTask],
            todos: list[planner_models.ProposedTodo] | None = None,
            ctx: MCPContext | None = None,
        ) -> PlanProposalResponse:
            """Submit a structured plan proposal for planner mode."""
            proposal = planner_models.PlanProposal.model_validate(
                {"tasks": tasks, "todos": todos or []}
            )
            return PlanProposalResponse(
                success=True,
                status="received",
                message="Plan proposal received",
                task_count=len(proposal.tasks),
                todo_count=len(proposal.todos),
                tasks=[task.model_dump(mode="json") for task in proposal.tasks],
                todos=[todo.model_dump(mode="json") for todo in proposal.todos],
            )

    if allows_all(_PROTOCOL_CALLS["tasks_get"], _PROTOCOL_CALLS["tasks_scratchpad"]):
        from kagan.mcp._response_models import TaskSummary

        @mcp.tool(annotations=_READ_ONLY)
        async def task_get(
            task_id: str,
            include_scratchpad: bool | None = None,
            include_logs: bool | None = None,
            include_review: bool | None = None,
            mode: str = "summary",
            ctx: MCPContext | None = None,
        ) -> dict[str, object]:
            """Get task details (summary/full) or bounded full context."""
            bridge = _require_bridge(ctx)
            if mode == "context":
                raw = await bridge.get_context(task_id)
                raw_runtime = raw.get("runtime")
                if isinstance(raw_runtime, dict):
                    raw["runtime"] = _runtime_state_from_raw(raw_runtime)
                return raw

            raw = await bridge.get_task(
                task_id,
                include_scratchpad=include_scratchpad,
                include_logs=include_logs,
                include_review=include_review,
                mode=mode,
            )
            raw_runtime = raw.get("runtime")
            if isinstance(raw_runtime, dict):
                raw["runtime"] = _runtime_state_from_raw(raw_runtime)
            if include_logs:
                raw_logs = raw.get("logs")
                if isinstance(raw_logs, list):
                    raw["logs"] = _normalize_agent_log_entries(raw_logs)
            return raw

    if allows_all(_PROTOCOL_CALLS["tasks_logs"]):
        # Import at module level to allow FastMCP to inspect type annotations
        from kagan.mcp._response_models import TaskLogsResponse

        @mcp.tool(annotations=_READ_ONLY)
        async def task_logs(
            task_id: str,
            limit: int = 5,
            offset: int = 0,
            ctx: MCPContext | None = None,
        ) -> TaskLogsResponse:
            """Get paginated task logs."""
            bridge = _require_bridge(ctx)
            raw = await bridge.list_task_logs(task_id=task_id, limit=limit, offset=offset)
            normalized_logs = _normalize_agent_log_entries(raw.get("logs"))

            total_runs = _int_or_none(raw.get("total_runs"))
            returned_runs = _int_or_none(raw.get("returned_runs"))
            page_offset = _int_or_none(raw.get("offset"))
            page_limit = _int_or_none(raw.get("limit"))
            next_offset = _int_or_none(raw.get("next_offset"))
            has_more_raw = raw.get("has_more")
            has_more = has_more_raw if isinstance(has_more_raw, bool) else next_offset is not None

            return TaskLogsResponse(
                task_id=raw.get("task_id", task_id),
                logs=normalized_logs,
                count=_int_or_none(raw.get("count")) or len(normalized_logs),
                total_runs=total_runs if total_runs is not None else len(normalized_logs),
                returned_runs=returned_runs if returned_runs is not None else len(normalized_logs),
                offset=page_offset if page_offset is not None else offset,
                limit=page_limit if page_limit is not None else limit,
                has_more=has_more,
                next_offset=next_offset,
                truncated=bool(raw.get("truncated", False)),
                message=_str_or_none(raw.get("message")),
                code=_str_or_none(raw.get("code")),
                hint=_str_or_none(raw.get("hint")),
                next_tool=_str_or_none(raw.get("next_tool")),
                next_arguments=_dict_or_none(raw.get("next_arguments")),
            )

    if allows_all(_PROTOCOL_CALLS["tasks_list"]):
        from kagan.mcp._response_models import TaskListResponse, TaskSummary

        @mcp.tool(annotations=_READ_ONLY)
        async def task_list(
            project_id: str | None = None,
            filter: str | None = None,
            exclude_task_ids: list[str] | None = None,
            include_scratchpad: bool = False,
            ctx: MCPContext | None = None,
        ) -> TaskListResponse:
            """List tasks with optional coordination filters."""
            bridge = _require_bridge(ctx)
            raw = await bridge.list_tasks(
                project_id=project_id,
                filter=filter,
                exclude_task_ids=exclude_task_ids,
                include_scratchpad=include_scratchpad,
            )
            tasks = [
                TaskSummary(
                    task_id=t["id"],
                    title=t["title"],
                    status=t.get("status"),
                    description=t.get("description"),
                    scratchpad=t.get("scratchpad"),
                    acceptance_criteria=t.get("acceptance_criteria"),
                    runtime=_runtime_state_from_raw(t.get("runtime")),
                )
                for t in raw.get("tasks", [])
            ]
            return TaskListResponse(tasks=tasks, count=raw.get("count", len(tasks)))

    if allows_all(_PROTOCOL_CALLS["tasks_wait"]):
        from kagan.mcp._response_models import TaskWaitResponse

        @mcp.tool(annotations=_READ_ONLY)
        async def task_wait(
            task_id: str,
            timeout_seconds: float | str | None = None,
            wait_for_status: list[str] | str | None = None,
            from_updated_at: str | None = None,
            ctx: MCPContext | None = None,
        ) -> TaskWaitResponse:
            """Wait for task status change or timeout (long-poll)."""
            bridge = _require_bridge(ctx)
            raw = await bridge.wait_task(
                task_id,
                timeout_seconds=timeout_seconds,
                wait_for_status=wait_for_status,
                from_updated_at=from_updated_at,
            )
            return TaskWaitResponse(
                changed=bool(raw.get("changed", False)),
                timed_out=bool(raw.get("timed_out", False)),
                task_id=raw.get("task_id", task_id),
                previous_status=_str_or_none(raw.get("previous_status")),
                current_status=_str_or_none(raw.get("current_status")),
                changed_at=_str_or_none(raw.get("changed_at")),
                task=raw.get("task"),
                code=_str_or_none(raw.get("code")),
                message=_str_or_none(raw.get("message")),
            )

    if allows_all(_PROTOCOL_CALLS["projects_list"]):
        from kagan.mcp._response_models import ProjectInfo, ProjectListResponse

        @mcp.tool(annotations=_READ_ONLY)
        async def project_list(
            limit: int = 10,
            ctx: MCPContext | None = None,
        ) -> ProjectListResponse:
            """List recent projects."""
            bridge = _require_bridge(ctx)
            raw = await bridge.list_projects(limit=limit)
            projects = [
                ProjectInfo(
                    project_id=p["id"],
                    name=p["name"],
                    description=p.get("description"),
                )
                for p in raw.get("projects", [])
            ]
            return ProjectListResponse(projects=projects, count=raw.get("count", len(projects)))

    if allows_all(_PROTOCOL_CALLS["projects_repos"]):
        from kagan.mcp._response_models import RepoListItem, RepoListResponse

        @mcp.tool(annotations=_READ_ONLY)
        async def repo_list(
            project_id: str,
            ctx: MCPContext | None = None,
        ) -> RepoListResponse:
            """List repos for a project."""
            bridge = _require_bridge(ctx)
            raw = await bridge.list_repos(project_id)
            repos = [
                RepoListItem(
                    repo_id=r["id"],
                    name=r["name"],
                    display_name=r.get("display_name"),
                    path=str(r.get("path", "")),
                )
                for r in raw.get("repos", [])
            ]
            return RepoListResponse(repos=repos, count=raw.get("count", len(repos)))

    if allows_all(_PROTOCOL_CALLS["audit_list"]):
        from kagan.mcp._response_models import AuditEvent, AuditTailResponse

        @mcp.tool(annotations=_READ_ONLY)
        async def audit_list(
            capability: str | None = None,
            limit: int = 50,
            ctx: MCPContext | None = None,
        ) -> AuditTailResponse:
            """List recent audit events."""
            bridge = _require_bridge(ctx)
            raw = await bridge.tail_audit(capability=capability, limit=limit)
            events = [
                AuditEvent(
                    event_id=e.get("id"),
                    occurred_at=e.get("occurred_at"),
                    actor_type=e.get("actor_type"),
                    actor_id=e.get("actor_id"),
                    capability=e.get("capability"),
                    command_name=e.get("command_name"),
                    success=e.get("success"),
                )
                for e in raw.get("events", [])
            ]
            return AuditTailResponse(events=events, count=raw.get("count", len(events)))


__all__ = [
    "MCPContext",
    "SharedToolRegistrationContext",
    "ToolRegistrationContext",
    "register_shared_tools",
]
