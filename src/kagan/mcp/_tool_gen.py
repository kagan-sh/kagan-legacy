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
from kagan.core.domain.models import AgentLogEntry, PlanItem, PlanTodo, Task
from kagan.core.policy import CapabilityProfile
from kagan.core.protocol_constants import DEFAULT_EVENTS_LIMIT, DEFAULT_TASK_LOG_LIMIT
from kagan.core.scalars import (
    dict_str_keys_or_none,
    int_or_none,
    str_or_none,
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
from kagan.mcp._tool_policy import PROTOCOL_CALLS

if TYPE_CHECKING:
    from collections.abc import Callable

    from mcp.server.fastmcp import FastMCP

    from kagan.mcp._response_models import RepoListResponse
    from kagan.sdk._transport import SDKTransport

logger = logging.getLogger(__name__)

_READ_ONLY = ToolAnnotations(readOnlyHint=True, destructiveHint=False, idempotentHint=True)
_MUTATING = ToolAnnotations(readOnlyHint=False, destructiveHint=False, idempotentHint=False)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, idempotentHint=False)

_PROTOCOL_CALLS = PROTOCOL_CALLS


@dataclass(frozen=True, slots=True)
class ToolRegistrationContext:
    """Callbacks required by full-mode tool registration."""

    require_transport: Callable[..., SDKTransport]
    runtime_state_from_raw: Callable[[dict[str, Any] | None], TaskRuntimeState | None]


@dataclass(frozen=True, slots=True)
class SharedToolRegistrationContext:
    """Callbacks required by shared tool registration."""

    require_transport: Callable[..., SDKTransport]
    runtime_state_from_raw: Callable[[dict[str, Any] | None], TaskRuntimeState | None]


MCPContext = Context[ServerSession, Any]


def _normalize_mode(mode: str) -> str:
    return "full" if mode.lower() == "full" else "summary"


def _normalize_agent_log_entries(logs: list[dict[str, Any]]) -> list[AgentLogEntry]:
    """Normalize log entries from raw response."""
    normalized: list[AgentLogEntry] = []
    for log in logs:
        if not isinstance(log, dict):
            continue
        run = log.get("run")
        content = log.get("content")
        created_at = log.get("created_at")
        if run is None or content is None or created_at is None:
            continue
        normalized.append(
            AgentLogEntry(
                run=int(run),
                content=str(content),
                created_at=str(created_at),
            )
        )
    return normalized


def register_shared_tools(
    mcp: FastMCP,
    *,
    allows_all: Callable[..., bool],
    effective_profile: str,
    helpers: SharedToolRegistrationContext,
) -> None:
    """Register planner/read-only/shared MCP tools."""
    from kagan.mcp.tools import mcp_get_task, mcp_wait_task

    _require_transport = helpers.require_transport
    _runtime_state_from_raw = helpers.runtime_state_from_raw

    _plan_profiles = (
        str(CapabilityProfile.PLANNER),
        str(CapabilityProfile.PAIR_WORKER),
        str(CapabilityProfile.OPERATOR),
        str(CapabilityProfile.MAINTAINER),
    )
    if allows_all(_PROTOCOL_CALLS["plan_propose"]) and effective_profile in _plan_profiles:

        async def _plan_proposal_impl(
            tasks: list[planner_models.ProposedTask],
            todos: list[planner_models.ProposedTodo] | None = None,
        ) -> PlanProposalResponse:
            proposal = planner_models.PlanProposal.model_validate(
                {"tasks": tasks, "todos": todos or []}
            )
            plan_items = [
                PlanItem(
                    title=t.title,
                    type=t.type,
                    description=t.description,
                    acceptance_criteria=t.acceptance_criteria,
                    priority=t.priority,
                )
                for t in proposal.tasks
            ]
            plan_todos = [PlanTodo(content=t.content, status=t.status) for t in proposal.todos]
            return PlanProposalResponse(
                success=True,
                status="received",
                message="Plan proposal received",
                task_count=len(plan_items),
                todo_count=len(plan_todos),
                tasks=plan_items,
                todos=plan_todos,
            )

        @mcp.tool(annotations=_MUTATING)
        async def plan_submit(
            tasks: list[planner_models.ProposedTask],
            todos: list[planner_models.ProposedTodo] | None = None,
            ctx: MCPContext | None = None,
        ) -> PlanProposalResponse:
            """Submit a structured plan proposal for planner mode."""
            return await _plan_proposal_impl(tasks, todos)

        @mcp.tool(annotations=_MUTATING)
        async def plan_tasks(
            tasks: list[planner_models.ProposedTask],
            todos: list[planner_models.ProposedTodo] | None = None,
            ctx: MCPContext | None = None,
        ) -> PlanProposalResponse:
            """Create multiple tasks from a natural-language request (orchestrator)."""
            return await _plan_proposal_impl(tasks, todos)

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
            transport = _require_transport(ctx)
            if mode == "context":
                raw = await transport.query("tasks", "context", {"task_id": task_id})
                raw_runtime = raw.get("runtime")
                if isinstance(raw_runtime, dict):
                    raw["runtime"] = _runtime_state_from_raw(raw_runtime)
                return raw

            raw = await mcp_get_task(
                transport,
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
                    raw["logs"] = [
                        entry.model_dump(mode="json")
                        for entry in _normalize_agent_log_entries(raw_logs)
                    ]
            return raw

    if allows_all(_PROTOCOL_CALLS["tasks_logs"]):
        # Import at module level to allow FastMCP to inspect type annotations
        from kagan.mcp._response_models import TaskLogsResponse

        @mcp.tool(annotations=_READ_ONLY)
        async def task_logs(
            task_id: str,
            limit: int = DEFAULT_TASK_LOG_LIMIT,
            offset: int = 0,
            ctx: MCPContext | None = None,
        ) -> TaskLogsResponse:
            """Get paginated task logs."""
            transport = _require_transport(ctx)
            raw = await transport.query(
                "tasks", "logs", {"task_id": task_id, "limit": limit, "offset": offset}
            )
            normalized_logs = _normalize_agent_log_entries(raw.get("logs"))

            total_runs = int_or_none(raw.get("total_runs"))
            returned_runs = int_or_none(raw.get("returned_runs"))
            page_offset = int_or_none(raw.get("offset"))
            page_limit = int_or_none(raw.get("limit"))
            next_offset = int_or_none(raw.get("next_offset"))
            has_more_raw = raw.get("has_more")
            has_more = has_more_raw if isinstance(has_more_raw, bool) else next_offset is not None

            return TaskLogsResponse(
                task_id=raw.get("task_id", task_id),
                logs=normalized_logs,
                count=int_or_none(raw.get("count")) or len(normalized_logs),
                total_runs=total_runs if total_runs is not None else len(normalized_logs),
                returned_runs=returned_runs if returned_runs is not None else len(normalized_logs),
                offset=page_offset if page_offset is not None else offset,
                limit=page_limit if page_limit is not None else limit,
                has_more=has_more,
                next_offset=next_offset,
                truncated=bool(raw.get("truncated", False)),
                message=str_or_none(raw.get("message")),
                code=str_or_none(raw.get("code")),
                hint=str_or_none(raw.get("hint")),
                next_tool=str_or_none(raw.get("next_tool")),
                next_arguments=dict_str_keys_or_none(raw.get("next_arguments")),
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
            transport = _require_transport(ctx)
            params: dict[str, Any] = {}
            if project_id:
                params["project_id"] = project_id
            if filter:
                params["filter"] = filter
            if exclude_task_ids:
                params["exclude_task_ids"] = exclude_task_ids
            if include_scratchpad:
                params["include_scratchpad"] = include_scratchpad
            raw = await transport.query("tasks", "list", params)
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
            transport = _require_transport(ctx)
            raw = await mcp_wait_task(
                transport,
                task_id,
                timeout_seconds=timeout_seconds,
                wait_for_status=wait_for_status,
                from_updated_at=from_updated_at,
            )
            task_raw = raw.get("task")
            task = (
                task_raw
                if isinstance(task_raw, Task)
                else Task.model_validate(task_raw)
                if isinstance(task_raw, dict)
                else None
            )
            return TaskWaitResponse(
                changed=bool(raw.get("changed", False)),
                timed_out=bool(raw.get("timed_out", False)),
                task_id=raw.get("task_id", task_id),
                previous_status=str_or_none(raw.get("previous_status")),
                current_status=str_or_none(raw.get("current_status")),
                changed_at=str_or_none(raw.get("changed_at")),
                task=task,
                code=str_or_none(raw.get("code")),
                message=str_or_none(raw.get("message")),
            )

    if allows_all(_PROTOCOL_CALLS["projects_list"]):
        from kagan.mcp._response_models import ProjectInfo, ProjectListResponse

        @mcp.tool(annotations=_READ_ONLY)
        async def project_list(
            limit: int = 10,
            ctx: MCPContext | None = None,
        ) -> ProjectListResponse:
            """List recent projects."""
            transport = _require_transport(ctx)
            raw = await transport.query("projects", "list", {"limit": limit})
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
            transport = _require_transport(ctx)
            raw = await transport.query("projects", "repos", {"project_id": project_id})
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
            limit: int = DEFAULT_EVENTS_LIMIT,
            ctx: MCPContext | None = None,
        ) -> AuditTailResponse:
            """List recent audit events."""
            transport = _require_transport(ctx)
            params: dict[str, Any] = {"limit": limit}
            if capability:
                params["capability"] = capability
            raw = await transport.query("audit", "list", params)
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
