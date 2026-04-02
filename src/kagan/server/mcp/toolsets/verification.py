"""kagan.server.mcp.toolsets.verification — Plan step verification MCP tools."""

from typing import Any, TypedDict

from mcp.server.fastmcp import Context, FastMCP

from kagan.core._verification import StepVerdict, StepVerification, VerificationSummary
from kagan.core.enums import SessionEventType
from kagan.core.errors import NotFoundError, VerificationError
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary

_VALID_VERDICTS = frozenset(v.value for v in StepVerdict)


class VerifyStepResult(TypedDict):
    task_id: str
    session_id: str | None
    step_index: int
    step_description: str
    verdict: str
    reason: str
    verified_at: str


class VerificationSummaryResult(TypedDict):
    task_id: str
    session_id: str | None
    total: int
    passed: int
    failed: int
    all_passed: bool
    steps: list[dict[str, Any]]


@mcp_error_boundary
async def _verify_step(
    task_id: str,
    step_index: int,
    step_description: str,
    verdict: str,
    reason: str,
    ctx: Context,
) -> VerifyStepResult:
    """Record the outcome of a plan step verification.

    Call this after completing each major step in a task to signal whether the
    step passed or failed verification. verdict must be one of: PASS, FAIL, SKIP.

    step_index is the 0-based position of the step in the plan.
    step_description is a short human-readable label for the step.
    reason is a one-line justification with evidence.
    """
    app = get_context(ctx)

    verdict_upper = verdict.strip().upper()
    if verdict_upper not in _VALID_VERDICTS:
        raise VerificationError(
            task_id,
            f"invalid verdict {verdict!r} — must be one of {sorted(_VALID_VERDICTS)}",
        )

    # Validate task exists
    try:
        await app.client.tasks.get(task_id)
    except NotFoundError as exc:
        raise VerificationError(task_id, f"task not found: {exc}") from exc

    step_verdict = StepVerdict(verdict_upper)
    step = StepVerification(
        step_index=step_index,
        step_description=step_description,
        verdict=step_verdict,
        reason=reason,
    )

    session_id = app.bound_session_id or app.opts.session_id

    payload = step.to_dict()
    payload["session_id"] = session_id

    await app.client.tasks.events.emit(
        task_id,
        SessionEventType.STEP_VERIFIED,
        payload,
        session_id=session_id,
    )

    return {
        "task_id": task_id,
        "session_id": session_id,
        "step_index": step.step_index,
        "step_description": step.step_description,
        "verdict": step.verdict.value,
        "reason": step.reason,
        "verified_at": step.verified_at.isoformat(),
    }


@mcp_error_boundary
async def _verification_summary(
    task_id: str,
    ctx: Context,
    session_id: str | None = None,
) -> VerificationSummaryResult:
    """Return aggregated step verification results for a task.

    If session_id is provided, only steps from that session are included.
    Returns counts of passed, failed, and skipped steps plus individual details.
    """
    app = get_context(ctx)

    resolved_session_id = session_id or app.bound_session_id or app.opts.session_id

    # Validate task exists
    try:
        await app.client.tasks.get(task_id)
    except NotFoundError as exc:
        raise VerificationError(task_id, f"task not found: {exc}") from exc

    # Retrieve all STEP_VERIFIED events for this task (paginated in batches)
    _MAX_STEPS = 500
    events = await app.client.tasks.events.list(
        task_id,
        session_id=resolved_session_id,
        limit=_MAX_STEPS,
    )

    summary = VerificationSummary(
        task_id=task_id,
        session_id=resolved_session_id or "",
    )

    for event in events:
        if event.event_type != SessionEventType.STEP_VERIFIED:
            continue
        p = event.payload if isinstance(event.payload, dict) else {}
        try:
            step = StepVerification(
                step_index=int(p.get("step_index", 0)),
                step_description=str(p.get("step_description", "")),
                verdict=StepVerdict(str(p.get("verdict", StepVerdict.SKIP))),
                reason=str(p.get("reason", "")),
            )
        except (ValueError, KeyError):
            continue
        summary.steps.append(step)

    return {
        "task_id": summary.task_id,
        "session_id": resolved_session_id,
        "total": summary.total,
        "passed": summary.passed,
        "failed": summary.failed,
        "all_passed": summary.all_passed,
        "steps": [s.to_dict() for s in summary.steps],
    }


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register verification domain tools on mcp, filtered by opts."""
    tools = [
        ("verify_step", _verify_step),
        ("verification_summary", _verification_summary),
    ]
    for name, fn in tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
