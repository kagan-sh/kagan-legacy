"""kagan.mcp.toolsets.review — Review domain MCP tools."""

import asyncio

from mcp.server.fastmcp import Context, FastMCP

from kagan.core import build_conflict_resolution_feedback
from kagan.core.errors import MergeConflictError
from kagan.mcp._policy import is_tool_allowed
from kagan.mcp.server import ServerContext, ServerOptions, get_context
from kagan.mcp.toolsets import mcp_error_boundary


async def _require_acceptance_criteria(
    app: ServerContext, task_id: str
) -> tuple[dict | None, object]:
    task = await app.client.tasks.get(task_id)
    criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
    if criteria:
        return None, task
    return {
        "task_id": task_id,
        "action": "blocked",
        "reason_code": "MANUAL_REVIEW_REQUIRED",
        "reason": (
            "This task has no acceptance criteria. "
            "Cannot auto-approve — manual human review required."
        ),
    }, task


@mcp_error_boundary
async def _review_approve(task_id: str, ctx: Context) -> dict:
    """Approve a review-ready task."""
    app = get_context(ctx)
    blocked, _task = await _require_acceptance_criteria(app, task_id)
    if blocked is not None:
        return blocked
    await app.client.reviews.approve(task_id)
    return {"task_id": task_id, "action": "approve"}


@mcp_error_boundary
async def _review_reject(task_id: str, feedback: str, ctx: Context) -> dict:
    """Reject a review-ready task with feedback."""
    app = get_context(ctx)
    await app.client.reviews.reject(task_id, feedback=feedback)
    return {"task_id": task_id, "action": "reject", "feedback": feedback}


@mcp_error_boundary
async def _review_merge(task_id: str, ctx: Context) -> dict:
    """Merge an approved task into its base branch."""
    app = get_context(ctx)
    blocked, task = await _require_acceptance_criteria(app, task_id)
    if blocked is not None:
        return blocked
    return await _handle_merge(app, task_id, task)


@mcp_error_boundary
async def _review_rebase(task_id: str, ctx: Context) -> dict:
    """Rebase a task branch onto its current base branch."""
    app = get_context(ctx)
    await app.client.reviews.rebase(task_id)
    return {"task_id": task_id, "action": "rebase"}


async def _handle_merge(app: ServerContext, task_id: str, task: object | None = None) -> dict:
    """Execute a merge action and return the result dict."""
    try:
        await app.client.reviews.merge(task_id)
    except MergeConflictError as exc:
        if task is None:
            task = await app.client.tasks.get(task_id)
        ws = await app.client.worktrees.get(task_id)
        repo = None
        if ws is not None:
            repo = await asyncio.to_thread(app.client.worktrees._get_repo, ws.repo_id)
        branch = task.base_branch or (repo.default_branch if repo else "main")
        feedback_text = build_conflict_resolution_feedback(
            conflict_files=exc.conflict_files,
            target_branch=branch,
            task_title=task.title,
        )
        return {
            "task_id": task_id,
            "action": "merge",
            "status": "conflict",
            "conflict_files": exc.conflict_files,
            "target_branch": branch,
            "suggested_feedback": feedback_text,
        }
    return {"task_id": task_id, "action": "merge"}


def _register_review_conflicts(mcp: FastMCP) -> None:
    @mcp.tool()
    @mcp_error_boundary
    async def review_conflicts(task_id: str, ctx: Context) -> dict:
        app = get_context(ctx)
        return await app.client.reviews.conflicts(task_id)


def _register_review_continue_rebase(mcp: FastMCP) -> None:
    @mcp.tool()
    @mcp_error_boundary
    async def review_continue_rebase(task_id: str, ctx: Context) -> dict:
        app = get_context(ctx)
        await app.client.reviews.continue_rebase(task_id)
        return {"task_id": task_id, "action": "rebase_continue"}


def _register_review_abort_rebase(mcp: FastMCP) -> None:
    @mcp.tool()
    @mcp_error_boundary
    async def review_abort_rebase(task_id: str, ctx: Context) -> dict:
        app = get_context(ctx)
        await app.client.reviews.abort_rebase(task_id)
        return {"task_id": task_id, "action": "abort_conflicts"}


def _register_review_set_criterion_verdict(mcp: FastMCP) -> None:
    @mcp.tool()
    @mcp_error_boundary
    async def review_set_criterion_verdict(
        task_id: str,
        criterion_index: int,
        verdict: str,
        reason: str,
        ctx: Context,
    ) -> dict:
        """Report the AI review verdict for a single acceptance criterion.

        Call this once per criterion during review, BEFORE calling review_approve
        or review_reject.
        verdict must be 'PASS' or 'FAIL'. reason is a one-line justification.
        """
        app = get_context(ctx)
        task = await app.client.reviews.set_criterion_verdict(
            task_id, criterion_index, verdict, reason
        )
        return {
            "task_id": task_id,
            "criterion_index": criterion_index,
            "verdict": verdict,
            "reason": reason,
            "total_criteria": len(task.acceptance_criteria or []),
        }


def _register_review_clear_verdicts(mcp: FastMCP) -> None:
    @mcp.tool()
    @mcp_error_boundary
    async def review_clear_verdicts(task_id: str, ctx: Context) -> dict:
        """Clear all AI review verdicts for a task. Call before starting a new review."""
        app = get_context(ctx)
        await app.client.reviews.clear_verdicts(task_id)
        return {"task_id": task_id, "verdicts_cleared": True}


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register review domain tools on mcp, filtered by opts."""
    plain_tools = [
        ("review_approve", _review_approve),
        ("review_reject", _review_reject),
        ("review_merge", _review_merge),
        ("review_rebase", _review_rebase),
    ]
    wrapped_tools = [
        ("review_conflicts", _register_review_conflicts),
        ("review_continue_rebase", _register_review_continue_rebase),
        ("review_abort_rebase", _register_review_abort_rebase),
        ("review_set_criterion_verdict", _register_review_set_criterion_verdict),
        ("review_clear_verdicts", _register_review_clear_verdicts),
    ]
    for name, fn in plain_tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
    for name, registrar in wrapped_tools:
        if is_tool_allowed(name, opts):
            registrar(mcp)
