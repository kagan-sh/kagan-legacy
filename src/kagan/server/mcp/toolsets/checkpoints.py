"""kagan.server.mcp.toolsets.checkpoints — Session checkpoint MCP tools."""

from pathlib import Path
from typing import Any, TypedDict

from mcp.server.fastmcp import Context, FastMCP

from kagan.core._checkpoints import (
    Checkpoint,
    create_checkpoint,
    list_checkpoints,
    rewind_to_checkpoint,
)
from kagan.core.enums import SessionEventType
from kagan.core.errors import NotFoundError, RewindError
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary


class CheckpointResult(TypedDict):
    task_id: str
    session_id: str | None
    step_index: int
    commit_sha: str
    tag_name: str
    description: str
    created_at: str


class CheckpointListResult(TypedDict):
    task_id: str
    session_id: str | None
    checkpoints: list[dict[str, Any]]


class RewindResult(TypedDict):
    task_id: str
    session_id: str | None
    step_index: int
    commit_sha: str


async def _resolve_worktree_path(app: Any, task_id: str) -> Path:
    """Resolve task_id to a validated worktree Path.

    Raises RewindError if the task has no provisioned worktree.
    """
    ws = await app.client.worktrees.get(task_id)
    if ws is None:
        raise RewindError(task_id, "no worktree provisioned for this task")
    return Path(ws.worktree_path)


@mcp_error_boundary
async def _checkpoint_create(
    task_id: str,
    step_index: int,
    ctx: Context,
    description: str = "",
) -> CheckpointResult:
    """Create a git-tag checkpoint at the current worktree HEAD.

    Captures the current HEAD commit of the task's worktree as a named
    checkpoint so the session can be rewound to this point later.

    task_id is the ID of the task whose worktree to snapshot.
    step_index is a caller-assigned integer identifying this checkpoint
    (should be monotonically increasing within a session).
    description is an optional human-readable label for the checkpoint.
    """
    app = get_context(ctx)

    try:
        await app.client.tasks.get(task_id)
    except NotFoundError as exc:
        raise RewindError(task_id, f"task not found: {exc}") from exc

    worktree_path = await _resolve_worktree_path(app, task_id)
    session_id = app.bound_session_id or app.opts.session_id

    checkpoint = await create_checkpoint(
        worktree_path,
        session_id=session_id or task_id,
        step_index=step_index,
        description=description,
    )

    if checkpoint is None:
        raise RewindError(task_id, "no commits in worktree — cannot create checkpoint")

    await app.client.tasks.events.emit(
        task_id,
        SessionEventType.CHECKPOINT_CREATED,
        checkpoint.to_dict(),
        session_id=session_id,
    )

    return {
        "task_id": task_id,
        "session_id": session_id,
        "step_index": checkpoint.step_index,
        "commit_sha": checkpoint.commit_sha,
        "tag_name": checkpoint.tag_name,
        "description": checkpoint.description,
        "created_at": checkpoint.created_at.isoformat(),
    }


@mcp_error_boundary
async def _checkpoint_list(
    task_id: str,
    ctx: Context,
) -> CheckpointListResult:
    """List all checkpoints for the task's current session.

    Returns checkpoints sorted by step_index (ascending).
    task_id is the ID of the task to query.
    """
    app = get_context(ctx)

    try:
        await app.client.tasks.get(task_id)
    except NotFoundError as exc:
        raise RewindError(task_id, f"task not found: {exc}") from exc

    worktree_path = await _resolve_worktree_path(app, task_id)
    session_id = app.bound_session_id or app.opts.session_id

    checkpoints = await list_checkpoints(
        worktree_path,
        session_id=session_id or task_id,
    )

    return {
        "task_id": task_id,
        "session_id": session_id,
        "checkpoints": [cp.to_dict() for cp in checkpoints],
    }


@mcp_error_boundary
async def _session_rewind(
    task_id: str,
    step_index: int,
    ctx: Context,
) -> RewindResult:
    """Rewind the task's worktree to the commit captured at step_index.

    Performs a hard reset of the worktree to the checkpoint's commit SHA.
    Any uncommitted changes and commits after the checkpoint are discarded.

    task_id is the ID of the task to rewind.
    step_index identifies which checkpoint to restore.
    """
    app = get_context(ctx)

    try:
        await app.client.tasks.get(task_id)
    except NotFoundError as exc:
        raise RewindError(task_id, f"task not found: {exc}") from exc

    worktree_path = await _resolve_worktree_path(app, task_id)
    session_id = app.bound_session_id or app.opts.session_id

    checkpoints = await list_checkpoints(
        worktree_path,
        session_id=session_id or task_id,
    )

    target: Checkpoint | None = None
    for cp in checkpoints:
        if cp.step_index == step_index:
            target = cp
            break

    if target is None:
        available = [cp.step_index for cp in checkpoints]
        raise RewindError(
            task_id,
            f"checkpoint at step_index={step_index} not found; available: {available}",
        )

    await rewind_to_checkpoint(worktree_path, target)

    await app.client.tasks.events.emit(
        task_id,
        SessionEventType.SESSION_REWOUND,
        {
            "session_id": session_id,
            "step_index": target.step_index,
            "commit_sha": target.commit_sha,
            "tag_name": target.tag_name,
        },
        session_id=session_id,
    )

    return {
        "task_id": task_id,
        "session_id": session_id,
        "step_index": target.step_index,
        "commit_sha": target.commit_sha,
    }


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register checkpoint domain tools on mcp, filtered by opts."""
    tools = [
        ("checkpoint_create", _checkpoint_create),
        ("checkpoint_list", _checkpoint_list),
        ("session_rewind", _session_rewind),
    ]
    for name, fn in tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
