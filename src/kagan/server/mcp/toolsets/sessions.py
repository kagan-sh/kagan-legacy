"""kagan.server.mcp.toolsets.sessions — Session lifecycle, verification, checkpoints, and insights.

13 tools: run_start, run_cancel, run_get, run_detach, run_summary,
verify_step, verification_summary, checkpoint_create, checkpoint_list,
session_rewind, insight_add, insight_list, insight_remove.
"""

from pathlib import Path
from typing import Any, cast

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

from kagan.core import (
    Checkpoint,
    InsightCategory,
    StepVerdict,
    StepVerification,
    VerificationSummary,
    create_checkpoint,
    list_checkpoints,
    resolve_default_agent_backend,
    resolve_launcher,
    rewind_to_checkpoint,
)
from kagan.core.errors import (
    InsightError,
    KaganError,
    NotFoundError,
    RewindError,
    SessionError,
    ValidationError,
    VerificationError,
)
from kagan.server.mcp._policy import is_tool_allowed
from kagan.server.mcp.server import ServerOptions, get_context
from kagan.server.mcp.toolsets import mcp_error_boundary

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


async def _get_latest_session(client: Any, task_id: str) -> Any:
    return await client.tasks.sessions.get_latest(task_id)


# ---------------------------------------------------------------------------
# Verification helpers
# ---------------------------------------------------------------------------

_VALID_VERDICTS = frozenset(v.value for v in StepVerdict)

# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------


async def _resolve_worktree_path(app: Any, task_id: str) -> Path:
    """Resolve task_id to a validated worktree Path.

    Raises RewindError if the task does not exist or has no provisioned worktree.
    """
    try:
        await app.client.tasks.get(task_id)
    except NotFoundError as exc:
        raise RewindError(task_id, f"task not found: {exc}") from exc
    ws = await app.client.worktrees.get(task_id)
    if ws is None:
        raise RewindError(task_id, "no worktree provisioned for this task")
    return Path(ws.worktree_path)


# ---------------------------------------------------------------------------
# Insight helpers
# ---------------------------------------------------------------------------

# Prefix used when persisting insights as TaskNote entries.
_INSIGHT_PREFIX = "[INSIGHT:"
_INSIGHT_PREFIX_END = "]"


def _make_note_content(category: InsightCategory, content: str) -> str:
    """Encode an insight as a TaskNote content string."""
    return f"{_INSIGHT_PREFIX}{category.value.upper()}{_INSIGHT_PREFIX_END} {content}"


def _parse_note_content(raw: str) -> tuple[InsightCategory, str] | None:
    """Decode a TaskNote content string into (category, content).

    Returns None if the note is not an insight note.
    """
    if not raw.startswith(_INSIGHT_PREFIX):
        return None
    end = raw.find(_INSIGHT_PREFIX_END, len(_INSIGHT_PREFIX))
    if end == -1:
        return None
    cat_str = raw[len(_INSIGHT_PREFIX) : end].lower()
    try:
        category = InsightCategory(cat_str)
    except ValueError:
        return None
    content = raw[end + 1 :].strip()
    return category, content


def _validate_category(category: str) -> InsightCategory:
    """Validate and return an InsightCategory from a raw string."""
    normalized = category.strip().lower()
    try:
        return InsightCategory(normalized)
    except ValueError:
        allowed = ", ".join(c.value for c in InsightCategory)
        raise ValidationError(
            "category",
            f"Unknown category {category!r}. Allowed values: {allowed}",
        ) from None


# ===================================================================
# Session lifecycle tools
# ===================================================================


@mcp_error_boundary
async def _run_start(
    task_id: str,
    ctx: Context,
    agent_backend: str | None = None,
    launcher: str | None = None,
    persona: str | None = None,
) -> dict:
    """Start a managed or attached run for a task.

    Creates the task worktree first if one does not already exist.
    """
    app = get_context(ctx)

    ws = await app.client.worktrees.get(task_id)
    if ws is None:
        try:
            ws = await app.client.worktrees.create(task_id)
        except (KaganError, OSError, RuntimeError, ValueError) as prov_exc:
            raise SessionError(
                None, f"Failed to provision workspace for task {task_id!r}: {prov_exc}"
            ) from prov_exc
    settings = await app.client.settings.get()
    resolved_backend = agent_backend or resolve_default_agent_backend(settings)

    if launcher is None:
        session = await app.client.tasks.run(
            task_id,
            agent_backend=resolved_backend,
            persona=persona,
        )
        return {
            "session_id": session.id,
            "task_id": task_id,
            "status": "STARTED",
            "agent_backend": resolved_backend,
            "persona": session.persona,
        }

    launcher_key, ide_name = resolve_launcher(launcher)
    session = await app.client.tasks.run(
        task_id,
        agent_backend=resolved_backend,
        launcher=launcher_key,
        ide=ide_name,
        persona=persona,
    )
    return {
        "session_id": session.id,
        "task_id": task_id,
        "status": "STARTED",
        "agent_backend": resolved_backend,
        "launcher": launcher,
        "persona": session.persona,
    }


@mcp_error_boundary
async def _run_cancel(task_id: str, ctx: Context) -> dict:
    """Cancel a task run and stop its active session."""
    app = get_context(ctx)
    await app.client.tasks.cancel(task_id)
    return {"task_id": task_id, "cancelled": True}


@mcp_error_boundary
async def _run_get(task_id: str, ctx: Context) -> dict[str, Any]:
    """Get the latest task and session status for a task.

    When a session exists, also returns context window usage fields:
    context_window_used, context_window_size, usage_ratio, needs_compaction.
    """
    from kagan.core import COMPACTION_THRESHOLD, ContextCompactor

    app = get_context(ctx)
    task = await app.client.tasks.get(task_id)
    raw_session = await app.client.tasks.sessions.get_latest(task_id)
    session = (
        raw_session if (raw_session is not None and raw_session.launcher is not None) else None
    )

    result: dict[str, Any] = {
        "task_id": task_id,
        "task_status": task.status.value,
        "session_id": session.id if session is not None else None,
        "session_status": (session.status.value if session is not None else None),
    }

    if session is not None:
        used = session.context_window_used or 0
        size = session.context_window_size or 0
        compactor = ContextCompactor(threshold=COMPACTION_THRESHOLD)
        compactor.update_usage(used, size)
        result["context_window_used"] = used
        result["context_window_size"] = size
        result["usage_ratio"] = compactor.usage_ratio
        result["needs_compaction"] = compactor.needs_compaction

    return result


@mcp_error_boundary
async def _run_detach(task_id: str, ctx: Context) -> dict[str, Any]:
    """Detach from an interactive session and update task state."""
    app = get_context(ctx)
    return cast("dict[str, Any]", await app.client.tasks.detach(task_id))


@mcp_error_boundary
async def _run_summary(ctx: Context, task_ids: list[str] | None = None) -> dict:
    """Summarize runs, sessions, worktrees, and token usage for tasks."""
    app = get_context(ctx)
    tasks = await app.client.tasks.list()
    id_filter = set(task_ids or [])
    if id_filter:
        tasks = [task for task in tasks if task.id in id_filter]

    rows: list[dict[str, Any]] = []
    for task in tasks:
        session = await _get_latest_session(app.client, task.id)
        ws = None
        try:
            ws = await app.client.worktrees.get(task.id)
        except (KaganError, OSError) as exc:
            logger.debug("Failed to fetch worktree for task {}: {}", task.id, exc)
        row: dict[str, Any] = {
            "task_id": task.id,
            "status": task.status.value,
            "agent_backend": task.agent_backend,
            "worktree_path": ws.worktree_path if ws is not None else None,
            "session_id": session.id if session is not None else None,
            "session_backend": session.agent_backend if session is not None else None,
        }
        if session is not None:
            row["token_usage"] = {
                "input_tokens": session.input_tokens,
                "output_tokens": session.output_tokens,
                "context_window_used": session.context_window_used,
                "context_window_size": session.context_window_size,
                "cost_amount": session.cost_amount,
                "cost_currency": session.cost_currency,
            }
        else:
            row["token_usage"] = {
                "input_tokens": None,
                "output_tokens": None,
                "context_window_used": None,
                "context_window_size": None,
                "cost_amount": None,
                "cost_currency": None,
            }
        rows.append(row)
    return {"rows": rows}


# ===================================================================
# Verification tools
# ===================================================================


@mcp_error_boundary
async def _verify_step(
    task_id: str,
    step_index: int,
    step_description: str,
    verdict: str,
    reason: str,
    ctx: Context,
) -> dict[str, Any]:
    """Record the outcome of a plan step verification.

    Call this after completing each major step in a task to signal whether the
    step passed or failed verification. verdict must be one of: PASS, FAIL, SKIP.

    step_index is the 0-based position of the step in the plan.
    step_description is a short human-readable label for the step.
    reason is a one-line justification with evidence.

    Returns dict with: task_id, session_id, step_index, step_description,
    verdict, reason, verified_at.
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
        "step_verified",
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
) -> dict[str, Any]:
    """Return aggregated step verification results for a task.

    If session_id is provided, only steps from that session are included.

    Returns dict with: task_id, session_id, total, passed, failed, all_passed,
    steps (list of step dicts).
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
        if event.event_type != "step_verified":
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


# ===================================================================
# Checkpoint tools
# ===================================================================


@mcp_error_boundary
async def _checkpoint_create(
    task_id: str,
    step_index: int,
    ctx: Context,
    description: str = "",
) -> dict[str, Any]:
    """Create a git-tag checkpoint at the current worktree HEAD.

    Captures the current HEAD commit of the task's worktree as a named
    checkpoint so the session can be rewound to this point later.

    task_id is the ID of the task whose worktree to snapshot.
    step_index is a caller-assigned integer identifying this checkpoint
    (should be monotonically increasing within a session).
    description is an optional human-readable label for the checkpoint.

    Returns dict with: task_id, session_id, step_index, commit_sha,
    tag_name, description, created_at.
    """
    app = get_context(ctx)
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
        "checkpoint_created",
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
) -> dict[str, Any]:
    """List all checkpoints for the task's current session.

    Returns checkpoints sorted by step_index (ascending).
    task_id is the ID of the task to query.

    Returns dict with: task_id, session_id, checkpoints (list of checkpoint dicts).
    """
    app = get_context(ctx)
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
) -> dict[str, Any]:
    """Rewind the task's worktree to the commit captured at step_index.

    Performs a hard reset of the worktree to the checkpoint's commit SHA.
    Any uncommitted changes and commits after the checkpoint are discarded.

    task_id is the ID of the task to rewind.
    step_index identifies which checkpoint to restore.

    Returns dict with: task_id, session_id, step_index, commit_sha.
    """
    app = get_context(ctx)
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
        "session_rewound",
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


# ===================================================================
# Insight tools
# ===================================================================


@mcp_error_boundary
async def _insight_add(
    ctx: Context,
    task_id: str,
    category: str,
    content: str,
) -> dict[str, Any]:
    """Add a project insight for a task.

    Insights are categorized observations extracted from agent sessions.
    Valid categories: pattern, error, architecture, preference, dependency.
    The insight is persisted as a TaskNote and will be surfaced in future
    task prompts alongside [LEARNING] notes.
    """
    app = get_context(ctx)
    cat = _validate_category(category)
    content = content.strip()
    if not content:
        raise ValidationError("content", "content must not be empty")

    note_content = _make_note_content(cat, content)
    await app.client.tasks.add_note(task_id, note_content)

    session_id = app.bound_session_id or app.opts.session_id
    await app.client.tasks.events.emit(
        task_id,
        "insight_extracted",
        {"category": cat.value, "content": content},
        session_id=session_id,
    )

    return {
        "task_id": task_id,
        "category": cat.value,
        "content": content,
        "persisted": True,
    }


@mcp_error_boundary
async def _insight_list(ctx: Context, task_id: str) -> dict[str, Any]:
    """List all insights recorded for a task.

    Returns insights grouped by category with their content.
    """
    app = get_context(ctx)
    notes = await app.client.tasks.list_notes(task_id)

    insights: list[dict[str, Any]] = []
    for note in notes:
        parsed = _parse_note_content(note.content)
        if parsed is None:
            continue
        cat, content = parsed
        insights.append(
            {
                "category": cat.value,
                "content": content,
                "created_at": note.created_at.isoformat(),
            }
        )

    by_category: dict[str, int] = {}
    for item in insights:
        by_category[item["category"]] = by_category.get(item["category"], 0) + 1

    return {
        "task_id": task_id,
        "insights": insights,
        "total": len(insights),
        "by_category": by_category,
    }


@mcp_error_boundary
async def _insight_remove(
    ctx: Context,
    task_id: str,
    content: str,
) -> dict[str, Any]:
    """Remove an insight from a task by matching its content text.

    Performs a case-insensitive exact content match. Returns removed=True if
    a matching insight was found and deleted, removed=False otherwise.
    """
    app = get_context(ctx)
    content = content.strip()
    if not content:
        raise InsightError("content must not be empty")

    notes = await app.client.tasks.list_notes(task_id)
    target_lower = content.lower()

    removed = False
    for note in notes:
        parsed = _parse_note_content(note.content)
        if parsed is None:
            continue
        _, note_content = parsed
        if note_content.strip().lower() == target_lower:
            await app.client.tasks.delete_note(task_id, note.id)
            removed = True
            break

    return {
        "task_id": task_id,
        "content": content,
        "removed": removed,
    }


# ===================================================================
# Registration
# ===================================================================


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register session domain tools on mcp, filtered by opts."""
    _tools = [
        ("run_start", _run_start),
        ("run_cancel", _run_cancel),
        ("run_get", _run_get),
        ("run_detach", _run_detach),
        ("run_summary", _run_summary),
        ("verify_step", _verify_step),
        ("verification_summary", _verification_summary),
        ("checkpoint_create", _checkpoint_create),
        ("checkpoint_list", _checkpoint_list),
        ("session_rewind", _session_rewind),
        ("insight_add", _insight_add),
        ("insight_list", _insight_list),
        ("insight_remove", _insight_remove),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
