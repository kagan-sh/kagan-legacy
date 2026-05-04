"""kagan.server.mcp.toolsets.review — Review domain MCP tools.

6 tools: review_decide, review_verdict, review_clear_verdicts, review_merge,
review_rebase, review_conflicts.
"""

import asyncio

from mcp.server.fastmcp import Context, FastMCP

from kagan.core import build_conflict_resolution_feedback, db_async
from kagan.core.errors import MergeConflictError, ValidationError
from kagan.core.models import AcceptanceCriterion, Task
from kagan.server._helpers import _manual_review_payload
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerContext, ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary


async def _has_acceptance_criteria(task_id: str, engine: object) -> bool:
    from sqlmodel import select as _select

    criteria = await db_async(
        engine,  # type: ignore[arg-type]
        lambda s: list(
            s.exec(_select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task_id)).all()
        ),
    )
    return bool(criteria)


@mcp_error_boundary
async def _review_decide(task_id: str, verdict: str, ctx: Context, feedback: str = "") -> dict:
    """Approve or reject a review-ready task.

    verdict must be "approve" or "reject".
    feedback is required when verdict is "reject" and ignored on "approve".
    """
    app = get_context(ctx)
    normalized_verdict = verdict.strip().lower()

    if normalized_verdict not in ("approve", "reject"):
        raise ValidationError("verdict", f"Must be 'approve' or 'reject', got {verdict!r}")

    if normalized_verdict == "approve":
        if not await _has_acceptance_criteria(task_id, app.client.engine):
            return _manual_review_payload(task_id)
        await app.client.reviews.approve(task_id)
        return {"task_id": task_id, "action": "approve"}

    # reject
    if not feedback.strip():
        raise ValidationError("feedback", "feedback is required when rejecting a task")
    await app.client.reviews.reject(task_id, feedback=feedback)
    return {"task_id": task_id, "action": "reject", "feedback": feedback}


@mcp_error_boundary
async def _review_merge(task_id: str, ctx: Context) -> dict:
    """Merge an approved task into its base branch."""
    app = get_context(ctx)
    task = await app.client.tasks.get(task_id)
    if not await _has_acceptance_criteria(task_id, app.client.engine):
        return _manual_review_payload(task_id)
    return await _handle_merge(app, task_id, task)


async def _handle_merge(app: ServerContext, task_id: str, task: Task) -> dict:
    """Execute a merge action and return the result dict."""
    try:
        await app.client.reviews.merge(task_id)
    except MergeConflictError as exc:
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


@mcp_error_boundary
async def _review_rebase(task_id: str, action: str, ctx: Context) -> dict:
    """Start, continue, or abort a rebase of the task branch onto its base branch.

    action must be "start", "continue", or "abort".
    """
    app = get_context(ctx)
    normalized_action = action.strip().lower()

    if normalized_action == "start":
        await app.client.reviews.rebase(task_id)
        return {"task_id": task_id, "action": "rebase"}
    elif normalized_action == "continue":
        await app.client.reviews.continue_rebase(task_id)
        return {"task_id": task_id, "action": "rebase_continue"}
    elif normalized_action == "abort":
        await app.client.reviews.abort_rebase(task_id)
        return {"task_id": task_id, "action": "abort_conflicts"}
    else:
        raise ValidationError("action", f"Must be 'start', 'continue', or 'abort', got {action!r}")


@mcp_error_boundary
async def _review_conflicts(task_id: str, ctx: Context) -> dict:
    """Return merge or rebase conflict details for a task."""
    app = get_context(ctx)
    return await app.client.reviews.conflicts(task_id)


@mcp_error_boundary
async def _review_verdict(
    task_id: str,
    criterion_index: int,
    verdict: str,
    reason: str,
    ctx: Context,
) -> dict:
    """Record a pass or fail verdict for a single acceptance criterion.

    Call this once per criterion during review, BEFORE calling review_decide.
    verdict must be 'pass' or 'fail'. reason is a one-line justification.
    """
    from sqlmodel import select as _select

    app = get_context(ctx)
    await app.client.reviews.set_criterion_verdict(task_id, criterion_index, verdict, reason)
    total = len(
        await db_async(
            app.client.engine,
            lambda s: list(
                s.exec(
                    _select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task_id)
                ).all()
            ),
        )
    )
    return {
        "task_id": task_id,
        "criterion_index": criterion_index,
        "verdict": verdict,
        "reason": reason,
        "total_criteria": total,
    }


@mcp_error_boundary
async def _review_clear_verdicts(task_id: str, ctx: Context) -> dict:
    """Clear all AI review verdicts for a task. Call before starting a new review."""
    app = get_context(ctx)
    await app.client.reviews.clear_verdicts(task_id)
    return {"task_id": task_id, "verdicts_cleared": True}


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register review domain tools on mcp, filtered by opts."""
    plain_tools = [
        ("review_decide", _review_decide),
        ("review_merge", _review_merge),
        ("review_rebase", _review_rebase),
        ("review_conflicts", _review_conflicts),
        ("review_verdict", _review_verdict),
        ("review_clear_verdicts", _review_clear_verdicts),
    ]
    for name, fn in plain_tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
