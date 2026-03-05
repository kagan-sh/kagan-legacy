"""kagan.mcp._policy — 3-tier access control for MCP tool registration."""

from enum import Enum, auto

from kagan.mcp.server import ServerOptions


class AccessTier(Enum):
    """Minimum access tier required to register a tool."""

    READONLY = auto()
    STANDARD = auto()
    ADMIN = auto()


# Maps tool name → minimum AccessTier required to register it.
TOOL_TIERS: dict[str, AccessTier] = {
    # Read-only tools (always available)
    "task_get": AccessTier.READONLY,
    "task_list": AccessTier.READONLY,
    "task_search": AccessTier.READONLY,
    "task_events": AccessTier.READONLY,
    "tasks_wait": AccessTier.READONLY,
    "task_counts": AccessTier.READONLY,
    "run_summary": AccessTier.READONLY,
    "project_list": AccessTier.READONLY,
    "repo_list": AccessTier.READONLY,
    "settings_get": AccessTier.READONLY,
    "audit_list": AccessTier.READONLY,
    "persona_preset_audit": AccessTier.READONLY,
    "persona_preset_whitelist_list": AccessTier.READONLY,
    # Standard-tier tools (read + write)
    "task_create": AccessTier.STANDARD,
    "task_update": AccessTier.STANDARD,
    "task_add_note": AccessTier.STANDARD,
    "run_start": AccessTier.STANDARD,
    "run_cancel": AccessTier.STANDARD,
    "run_update": AccessTier.STANDARD,
    "project_set_active": AccessTier.STANDARD,
    "project_add_repo": AccessTier.STANDARD,
    "project_set_repo_default_branch": AccessTier.STANDARD,
    "review_decide": AccessTier.STANDARD,
    "review_continue_rebase": AccessTier.STANDARD,
    "review_abort_rebase": AccessTier.STANDARD,
    "review_conflicts": AccessTier.READONLY,
    "task_batch_create": AccessTier.STANDARD,
    # Admin-only tools
    "task_delete": AccessTier.ADMIN,
    "project_create": AccessTier.ADMIN,
    "project_delete": AccessTier.ADMIN,
    "settings_set": AccessTier.ADMIN,
    "persona_preset_import": AccessTier.ADMIN,
    "persona_preset_export": AccessTier.ADMIN,
    "persona_preset_whitelist_add": AccessTier.ADMIN,
    "persona_preset_whitelist_remove": AccessTier.ADMIN,
    # Plugin tools
    "plugins_sync": AccessTier.ADMIN,
    "plugins_preflight": AccessTier.READONLY,
}


def _effective_tier(opts: ServerOptions) -> AccessTier:
    """Compute the effective access tier from ServerOptions."""
    if opts.admin:
        return AccessTier.ADMIN
    if opts.readonly:
        return AccessTier.READONLY
    return AccessTier.STANDARD


def is_tool_allowed(tool_name: str, opts: ServerOptions) -> bool:
    """Return True if tool_name should be registered given opts."""
    required = TOOL_TIERS.get(tool_name, AccessTier.STANDARD)
    effective = _effective_tier(opts)
    # Order in enum definition determines access level
    return effective.value >= required.value
