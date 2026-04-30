"""kagan.server.mcp._policy — Role-based access control for MCP tool registration.

Single axis: AgentRole (WORKER < REVIEWER < ORCHESTRATOR).
Each role's toolset is cumulative — higher roles include all lower-role tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.core.enums import AgentRole

if TYPE_CHECKING:
    from kagan.server.mcp.server import ServerOptions

_WORKER_TOOLS = frozenset(
    {
        # tasks (4 read/wait tools)
        "task_get",
        "task_list",
        "task_events",
        "task_wait",
        # sessions (4 read/lifecycle tools)
        "run_get",
        "run_cancel",
        "run_detach",
        "run_summary",
        # review (1 read tool)
        "review_conflicts",
        # settings (1 read tool)
        "settings_get",
        # integrations (2 read tools)
        "integration_preflight",
        "integration_preview",
        # verification (2 tools — session-scoped)
        "verify_step",
        "verification_summary",
        # checkpoints (3 tools — session-scoped)
        "checkpoint_create",
        "checkpoint_list",
        "session_rewind",
        # insights (2 read/write tools)
        "insight_add",
        "insight_list",
        # analytics (3 read tools)
        "analytics_backend_stats",
        "analytics_session_timeline",
        "analytics_export",
    }
)

_REVIEWER_TOOLS = _WORKER_TOOLS | frozenset(
    {
        "review_verdict",
        "review_clear_verdicts",
    }
)

_ORCHESTRATOR_TOOLS = _REVIEWER_TOOLS | frozenset(
    {
        # tasks (3 write tools)
        "task_create",
        "task_update",
        "task_delete",
        # sessions (1 write tool)
        "run_start",
        # review (3 write tools)
        "review_decide",
        "review_merge",
        "review_rebase",
        # projects (3 tools)
        "project_list",
        "project_setup",
        "project_update",
        # settings (1 write tool)
        "settings_set",
        # diagnostics (1 tool)
        "audit_list",
        # integrations (1 write tool)
        "integration_sync",
        # personas (4 tools)
        "persona_inspect",
        "persona_import",
        "persona_export",
        "persona_trust",
        # insights (1 destructive tool)
        "insight_remove",
    }
)

ROLE_TOOLS: dict[AgentRole, frozenset[str]] = {
    AgentRole.WORKER: _WORKER_TOOLS,
    AgentRole.REVIEWER: _REVIEWER_TOOLS,
    AgentRole.ORCHESTRATOR: _ORCHESTRATOR_TOOLS,
}

ALL_TOOL_NAMES: frozenset[str] = _ORCHESTRATOR_TOOLS


def effective_role(opts: ServerOptions) -> AgentRole:
    """Determine the effective role from ServerOptions."""
    if opts.role is not None:
        return opts.role
    if opts.readonly:
        return AgentRole.WORKER
    return AgentRole.ORCHESTRATOR


def is_tool_allowed(tool_name: str, opts: ServerOptions) -> bool:
    """Return True if tool_name should be registered for the effective role."""
    return tool_name in ROLE_TOOLS[effective_role(opts)]
