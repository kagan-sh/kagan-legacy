"""kagan.mcp.toolsets.review — Review domain MCP tools."""

import asyncio
from enum import StrEnum

from mcp.server.fastmcp import Context, FastMCP

from kagan.core import build_conflict_resolution_feedback
from kagan.core.errors import MergeConflictError
from kagan.mcp._policy import is_tool_allowed
from kagan.mcp.server import ServerContext, ServerOptions, get_context
from kagan.mcp.toolsets import mcp_error_boundary


class ReviewAction(StrEnum):
    APPROVE = "approve"
    REJECT = "reject"
    MERGE = "merge"
    REBASE = "rebase"


_VALID_ACTIONS = frozenset(item.value for item in ReviewAction)


def _parse_action(action: str) -> ReviewAction:
    try:
        return ReviewAction(action)
    except ValueError as exc:
        raise ValueError(
            f"Unknown review action: {action!r}. Must be one of {sorted(_VALID_ACTIONS)}"
        ) from exc


def _register_review_decide(mcp: FastMCP) -> None:
    @mcp.tool()
    @mcp_error_boundary
    async def review_decide(
        task_id: str,
        action: str,
        ctx: Context,
        feedback: str | None = None,
        target_branch: str | None = None,
    ) -> dict:
        """Apply a review action (approve, reject, merge, rebase) to a task.

        Approve and merge require that the task has acceptance criteria.
        Tasks without acceptance criteria must be reviewed manually by a human.
        """
        parsed = _parse_action(action)
        app = get_context(ctx)

        # Gate: tasks without acceptance criteria cannot be auto-approved/merged
        if parsed in (ReviewAction.APPROVE, ReviewAction.MERGE):
            task = await app.client.tasks.get(task_id)
            criteria = [c.strip() for c in (task.acceptance_criteria or []) if c and c.strip()]
            if not criteria:
                return {
                    "task_id": task_id,
                    "action": "blocked",
                    "reason_code": "MANUAL_REVIEW_REQUIRED",
                    "reason": (
                        "This task has no acceptance criteria. "
                        "Cannot auto-approve — manual human review required."
                    ),
                }

        match parsed:
            case ReviewAction.APPROVE:
                await app.client.reviews.approve(task_id)
            case ReviewAction.REJECT:
                if feedback is None:
                    raise ValueError("feedback is required for reject action")
                await app.client.reviews.reject(task_id, feedback=feedback)
            case ReviewAction.MERGE:
                return await _handle_merge(app, task_id, feedback)
            case ReviewAction.REBASE:
                await app.client.reviews.rebase(task_id)
        return {"task_id": task_id, "action": parsed.value, "feedback": feedback}


async def _handle_merge(app: ServerContext, task_id: str, feedback: str | None) -> dict:
    """Execute a merge action and return the result dict."""
    try:
        await app.client.reviews.merge(task_id)
    except MergeConflictError as exc:
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
    return {"task_id": task_id, "action": "merge", "feedback": feedback}


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

        Call this once per criterion during review, BEFORE calling review_decide.
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
    if is_tool_allowed("review_decide", opts):
        _register_review_decide(mcp)
    if is_tool_allowed("review_conflicts", opts):
        _register_review_conflicts(mcp)
    if is_tool_allowed("review_continue_rebase", opts):
        _register_review_continue_rebase(mcp)
    if is_tool_allowed("review_abort_rebase", opts):
        _register_review_abort_rebase(mcp)
    if is_tool_allowed("review_set_criterion_verdict", opts):
        _register_review_set_criterion_verdict(mcp)
    if is_tool_allowed("review_clear_verdicts", opts):
        _register_review_clear_verdicts(mcp)
