from __future__ import annotations

import asyncio
from functools import wraps
from typing import TYPE_CHECKING, Any, cast

from loguru import logger
from starlette.responses import JSONResponse

from kagan.core import TaskStatus
from kagan.core.errors import InvalidTransitionError, KaganError, NotFoundError
from kagan.mcp.server import get_server_context
from kagan.server._access import http_forbidden, is_access_allowed
from kagan.wire.envelopes import WireEnvelope
from kagan.wire.models import WireTask, WireTaskActiveSession, utc_iso

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
    if isinstance(exc, ValueError | TypeError):
        logger.debug("Route handler validation error: {}", exc)
        return _err(str(exc), status=400, error_code=error_code)

    logger.exception("Unexpected error in route handler")
    return _err("Internal server error", status=500)


def task_to_wire(task: Any, *, runtime: dict[str, Any] | None = None) -> WireTask:
    runtime = runtime or {}
    active_session = runtime.get("active_session")
    is_review_task = (
        getattr(getattr(task, "status", None), "value", None) == TaskStatus.REVIEW.value
    )
    return WireTask(
        id=task.id,
        title=task.title,
        description=getattr(task, "description", ""),
        status=task.status.value,
        priority=task.priority.name,
        execution_mode=task.execution_mode.value,
        base_branch=getattr(task, "base_branch", None),
        acceptance_criteria=getattr(task, "acceptance_criteria", []),
        agent_backend=getattr(task, "agent_backend", None),
        launcher=getattr(task, "launcher", None),
        review_approved=getattr(task, "review_approved", False),
        review_verdicts=getattr(task, "review_verdicts", []) or [],
        updated_at=utc_iso(getattr(task, "updated_at", None)),
        last_event_at=cast("str | None", runtime.get("last_event_at")),
        has_workspace=bool(runtime.get("has_workspace", False)),
        review_running=is_review_task and isinstance(active_session, dict),
        active_session=(
            WireTaskActiveSession(**active_session) if isinstance(active_session, dict) else None
        ),
    )


def task_to_wire_dict(task: Any, *, runtime: dict[str, Any] | None = None) -> dict[str, Any]:
    return task_to_wire(task, runtime=runtime).model_dump(mode="json")


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
