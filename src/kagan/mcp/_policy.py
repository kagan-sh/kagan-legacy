"""kagan.mcp._policy — Role-based access control for MCP tool registration.

Single axis: AgentRole (WORKER < REVIEWER < ORCHESTRATOR).
Each role's toolset is cumulative — higher roles include all lower-role tools.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.core.enums import AgentRole

if TYPE_CHECKING:
    from kagan.mcp.server import ServerOptions

_WORKER_TOOLS = frozenset(
    {
        "task_get",
        "task_list",
        "task_search",
        "task_events",
        "task_add_note",
        "task_counts",
        "tasks_wait",
        "run_update",
        "run_summary",
        "settings_get",
        "review_conflicts",
        "plugins_preflight",
    }
)

_REVIEWER_TOOLS = _WORKER_TOOLS | frozenset(
    {
        "review_set_criterion_verdict",
        "review_clear_verdicts",
    }
)

_ORCHESTRATOR_TOOLS = _REVIEWER_TOOLS | frozenset(
    {
        "task_create",
        "task_update",
        "task_batch_create",
        "task_delete",
        "run_start",
        "run_cancel",
        "review_decide",
        "review_continue_rebase",
        "review_abort_rebase",
        "project_list",
        "project_create",
        "project_delete",
        "project_set_active",
        "project_add_repo",
        "project_set_repo_default_branch",
        "repo_list",
        "settings_set",
        "audit_list",
        "plugins_sync",
        "persona_preset_audit",
        "persona_preset_import",
        "persona_preset_export",
        "persona_preset_whitelist_list",
        "persona_preset_whitelist_add",
        "persona_preset_whitelist_remove",
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
