"""kagan.server.mcp.toolsets._path_validation — cwd containment helpers.

Provides a single async function used by bash_exec and terminal_run to
enforce that an agent-supplied cwd stays within the bound task's worktree
when a task_id is present in the MCP context.

Without a bound task the check is skipped and a warning is emitted so the
audit trail records the unconstrained execution.

TC001/TC002/TC003 suppressed per MCP convention.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

from kagan.core.errors import ValidationError

if TYPE_CHECKING:
    from kagan.server.mcp.server import ServerContext


async def assert_cwd_contained(
    cwd: str | None,
    tool_name: str,
    app: ServerContext,
) -> None:
    """Raise ValidationError when cwd escapes the bound task's worktree.

    When task_id is bound the cwd (if provided) must resolve to a path
    inside the worktree root.  Passing cwd=None is always safe — the
    subprocess inherits the server process cwd, which is outside agent
    control.

    When no task is bound the function returns without error but logs a
    warning so the audit trail shows unconstrained execution.
    """
    if cwd is None:
        return

    task_id = app.bound_task_id
    if task_id is None:
        # No binding — legitimate orchestrator-shell usage; warn for audit.
        logger.warning(
            "{}: cwd supplied without a bound task — containment not enforced (cwd={})",
            tool_name,
            cwd,
        )
        return

    worktree = await app.client.worktrees.get(task_id)
    if worktree is None:
        # Task exists but no worktree yet (e.g. BACKLOG task called directly).
        # Refuse rather than skip — the invariant must hold once a task is bound.
        raise ValidationError(
            "cwd",
            f"task {task_id!r} has no worktree; cannot validate cwd containment",
        )

    worktree_root = Path(worktree.worktree_path).resolve()
    requested = Path(cwd).resolve(strict=False)

    if not requested.is_relative_to(worktree_root):
        raise ValidationError(
            "cwd",
            f"cwd {cwd!r} resolves to {requested} which is outside the task "
            f"worktree {worktree_root}",
        )
