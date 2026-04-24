from __future__ import annotations

import asyncio
import contextlib
from functools import wraps
from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from pydantic import BaseModel, ValidationError
from starlette.responses import JSONResponse

from kagan.core import TaskStatus
from kagan.core.errors import InvalidTransitionError, KaganError, NotFoundError
from kagan.server._access import http_forbidden, is_access_allowed
from kagan.server._envelope import WireEnvelope
from kagan.server.mcp.server import get_server_context
from kagan.server.responses import (
    ActiveSessionResponse,
    DiffSummaryResponse,
    ReviewVerdictResponse,
    TaskResponse,
)

if TYPE_CHECKING:
    from collections.abc import Awaitable, Callable

    from mcp.server.fastmcp import FastMCP

    from kagan.server._access import AccessTier


def _ok(data: Any, status: int = 200) -> JSONResponse:
    return JSONResponse(WireEnvelope(ok=True, data=data).model_dump(), status_code=status)


def _err(msg: str, status: int = 400, *, error_code: str | None = None) -> JSONResponse:
    payload = WireEnvelope(ok=False, error=msg).model_dump()
    if error_code is not None:
        payload["error_code"] = error_code
    return JSONResponse(payload, status_code=status)


async def parse_body[T: BaseModel](request: Any, model: type[T]) -> T:
    """Parse and validate a JSON request body against a Pydantic model."""
    payload = await request.json()
    if not isinstance(payload, dict):
        raise ValueError("Request body must be a JSON object")
    return model.model_validate(payload)


def _error_response(exc: Exception) -> JSONResponse:
    error_code = cast("str | None", getattr(exc, "code", None))
    if isinstance(exc, NotFoundError):
        logger.debug("Route handler not found error: {}", exc)
        return _err(str(exc), status=404, error_code=error_code)
    if isinstance(exc, InvalidTransitionError):
        logger.debug("Route handler invalid transition: {}", exc)
        return _err(str(exc), status=409, error_code=error_code)
    if isinstance(exc, KaganError):
        logger.debug("Route handler kagan error: {}", exc)
        return _err(str(exc), status=400, error_code=error_code)
    if isinstance(exc, KeyError):
        logger.debug("Route handler missing field: {}", exc)
        field = exc.args[0] if exc.args else "unknown"
        return _err(f"Missing field: {field}", status=400, error_code=error_code)
    if isinstance(exc, ValidationError):
        logger.debug("Route handler validation error: {}", exc)
        return _err(str(exc), status=422, error_code=error_code)
    if isinstance(exc, ValueError | TypeError):
        logger.debug("Route handler validation error: {}", exc)
        return _err(str(exc), status=400, error_code=error_code)
    if isinstance(exc, FileNotFoundError | NotADirectoryError):
        logger.debug("Route handler path error: {}", exc)
        return _err(str(exc), status=400, error_code=error_code)
    if isinstance(exc, PermissionError):
        logger.debug("Route handler permission denied: {}", exc)
        return _err(str(exc), status=403, error_code=error_code)

    logger.exception("Unexpected error in route handler")
    return _err("Internal server error", status=500)


def task_to_wire_dict(
    task: Any,
    *,
    runtime: dict[str, Any] | None = None,
    review_approved: bool | None = None,
    diff_summary: dict[str, int] | None = None,
    review_verdicts: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Serialize a Task ORM instance to a JSON-safe dict for the wire."""
    resp = TaskResponse.model_validate(task)
    runtime = runtime or {}
    active_session = runtime.get("active_session")
    is_review_task = (
        getattr(getattr(task, "status", None), "value", None) == TaskStatus.REVIEW.value
    )
    resp.last_event_at = runtime.get("last_event_at")
    resp.has_workspace = bool(runtime.get("has_workspace", False))
    resp.review_running = is_review_task and isinstance(active_session, dict)
    resp.active_session = (
        ActiveSessionResponse(**active_session) if isinstance(active_session, dict) else None
    )
    if diff_summary is not None and is_review_task:
        resp.diff_summary = DiffSummaryResponse(
            files_changed=diff_summary.get("files", 0),
            additions=diff_summary.get("insertions", 0),
            deletions=diff_summary.get("deletions", 0),
        )
    if review_verdicts is not None:
        resp.review_verdicts = [ReviewVerdictResponse(**v) for v in review_verdicts]
        if review_approved is None:
            verdict_by_criterion = {
                str(v.get("criterion_id")): str(v.get("verdict"))
                for v in review_verdicts
            }
            criteria = getattr(task, "criteria", []) or []
            review_approved = bool(criteria) and all(
                verdict_by_criterion.get(getattr(criterion, "id", "")) == "PASS"
                for criterion in criteria
            )
    resp.review_approved = bool(review_approved)
    return resp.model_dump(mode="json")


async def safe_diff_stats(ctx: Any, task_id: str) -> dict[str, int] | None:
    """Fetch diff stats for a single task worktree; return None on transient failure."""
    with contextlib.suppress(KaganError, OSError, RuntimeError, AttributeError):
        stats = await ctx.client.worktrees.diff_stats(task_id)
        return dict(stats)
    return None


async def review_diff_summaries(
    ctx: Any, tasks: list[Any], runtime: dict[str, dict[str, Any]]
) -> dict[str, dict[str, int] | None]:
    """Compute diff stats only for review tasks with workspaces."""
    review_ids = [
        task.id
        for task in tasks
        if getattr(task.status, "value", task.status) == TaskStatus.REVIEW.value
        and runtime.get(task.id, {}).get("has_workspace", False)
    ]
    if not review_ids:
        return {}
    results = await asyncio.gather(
        *(safe_diff_stats(ctx, task_id) for task_id in review_ids),
        return_exceptions=False,
    )
    return dict(zip(review_ids, results, strict=True))


async def task_review_verdicts(ctx: Any, task_id: str) -> list[dict[str, str | None]]:
    """Return the latest ReviewVerdict row per criterion for a task."""
    import sqlalchemy as sa
    from sqlmodel import select

    from kagan.core._db_helpers import _db_async
    from kagan.core.models import AcceptanceCriterion, ReviewVerdict

    def op(session: Any) -> list[dict[str, str | None]]:
        criteria = list(
            session.exec(
                select(AcceptanceCriterion).where(AcceptanceCriterion.task_id == task_id)
            ).all()
        )
        rows: list[dict[str, str | None]] = []
        for criterion in criteria:
            latest = session.exec(
                select(ReviewVerdict)
                .where(ReviewVerdict.criterion_id == criterion.id)
                .order_by(sa.text("rowid DESC"))
            ).first()
            if latest is not None:
                rows.append(
                    {
                        "id": latest.id,
                        "criterion_id": latest.criterion_id,
                        "session_id": latest.session_id,
                        "verdict": latest.verdict,
                        "reason": latest.reason,
                    }
                )
        return rows

    with contextlib.suppress(Exception):
        return await _db_async(ctx.client.engine, op)
    return []


async def bulk_task_review_verdicts(
    ctx: Any, task_ids: list[str]
) -> dict[str, list[dict[str, str | None]]]:
    if not task_ids:
        return {}
    results = await asyncio.gather(
        *(task_review_verdicts(ctx, task_id) for task_id in task_ids),
        return_exceptions=False,
    )
    return dict(zip(task_ids, results, strict=True))


async def task_wire_dict(ctx: Any, task_id: str, *, task: Any | None = None) -> dict[str, Any]:
    """Load one task with the runtime fields used by board and SSE clients."""
    task = task if task is not None else await ctx.client.tasks.get(task_id)
    runtime = await ctx.client.tasks.runtime_summary(task_id)
    diff_summary = None
    if getattr(task.status, "value", task.status) == TaskStatus.REVIEW.value and runtime.get(
        "has_workspace", False
    ):
        diff_summary = await safe_diff_stats(ctx, task_id)
    verdicts = await task_review_verdicts(ctx, task_id)
    return task_to_wire_dict(
        task,
        runtime=runtime,
        diff_summary=diff_summary,
        review_verdicts=verdicts,
    )


def _require_access(
    ctx: Any,
    *,
    operation: str | None = None,
    minimum_tier: AccessTier | None = None,
) -> JSONResponse | None:
    if minimum_tier is None:
        raise ValueError("Access tier is required")

    if is_access_allowed(ctx, minimum_tier):
        return None

    resolved_operation = operation or "Operation"
    return http_forbidden(operation=resolved_operation, minimum_tier=minimum_tier)


def require_context(
    mcp: FastMCP,
) -> Callable[[Callable[..., Awaitable[JSONResponse]]], Callable[..., Awaitable[JSONResponse]]]:
    def decorator(
        handler: Callable[..., Awaitable[JSONResponse]],
    ) -> Callable[..., Awaitable[JSONResponse]]:
        @wraps(handler)
        async def wrapper(*args: Any, **kwargs: Any) -> JSONResponse:
            ctx = get_server_context(mcp)
            if ctx is None:
                return _err("Server not ready", status=503)
            kwargs["ctx"] = ctx
            return await handler(*args, **kwargs)

        return wrapper

    return decorator


def handle_errors[**P](
    handler: Callable[P, Awaitable[JSONResponse]],
) -> Callable[P, Awaitable[JSONResponse]]:
    @wraps(handler)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> JSONResponse:
        try:
            return await handler(*args, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            return _error_response(exc)

    return wrapper
