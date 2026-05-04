"""kagan.server.mcp.toolsets — Domain toolset registry."""

from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, cast

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

from kagan.core.errors import KaganError
from kagan.server.mcp.server import ServerOptions, get_context


def _sanitize_params(kwargs: dict[str, Any], max_length: int = 200) -> dict[str, str]:
    """Sanitize tool parameters for audit logging (truncate large values)."""
    sanitized: dict[str, str] = {}
    for key, value in kwargs.items():
        serialized = str(value)
        if len(serialized) > max_length:
            sanitized[key] = f"{serialized[:max_length]}..."
        else:
            sanitized[key] = serialized
    return sanitized


def mcp_error_boundary[**P, R](fn: Callable[P, Awaitable[R]]) -> Callable[P, Awaitable[R]]:
    @wraps(fn)
    async def _wrapped(*args: P.args, **kwargs: P.kwargs) -> R:
        tool_name = fn.__name__
        ctx = None
        role = None
        session_id = None

        # Extract MCP context and server metadata if available
        for arg in args:
            if isinstance(arg, Context):
                ctx = arg
                break

        if ctx is not None:
            try:
                app = get_context(ctx)
                session_id = app.bound_session_id or app.opts.session_id
                role = app.opts.role.value if app.opts.role else None
            except (ValueError, AttributeError):
                # Lifespan not running (e.g. tests without a live server);
                # degrade gracefully — audit metadata is best-effort only.
                pass

        sanitized_kwargs = _sanitize_params(kwargs)

        # Audit log: tool invocation
        log_context = {"audit": True, "tool": tool_name, "role": role or "unknown"}
        logger.bind(**log_context).info(
            "MCP tool invoked",
            session_id=session_id,
            params=sanitized_kwargs,
        )

        try:
            result = await fn(*args, **kwargs)
            # Audit log: tool success
            logger.bind(**log_context).info(
                "MCP tool completed",
                session_id=session_id,
                outcome="success",
            )
            return result
        except KaganError as exc:
            # KaganError subclasses propagate unchanged
            logger.bind(**log_context).warning(
                "MCP tool raised KaganError",
                session_id=session_id,
                outcome="error",
                error_type=type(exc).__name__,
            )
            raise
        except (OSError, RuntimeError, ValueError, TypeError) as exc:
            # Wrap non-Kagan errors as KaganError for consistent MCP error handling
            logger.bind(**log_context).warning(
                "MCP tool raised standard error",
                session_id=session_id,
                outcome="error",
                error_type=type(exc).__name__,
            )
            raise KaganError(str(exc)) from exc
        except Exception as exc:
            # Unexpected errors
            logger.bind(**log_context).error(
                "MCP tool raised unexpected error",
                session_id=session_id,
                outcome="error",
                error_type=type(exc).__name__,
            )
            raise KaganError(f"Unexpected error in {tool_name}: {exc}") from exc

    return cast("Callable[P, Awaitable[R]]", _wrapped)


def register_all_toolsets(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register all domain toolsets on the MCP server."""
    from kagan.server.mcp.toolsets.analytics import register as register_analytics
    from kagan.server.mcp.toolsets.diagnostics import register as register_diagnostics
    from kagan.server.mcp.toolsets.fs import register as register_fs
    from kagan.server.mcp.toolsets.integrations import register as register_integrations
    from kagan.server.mcp.toolsets.personas import register as register_personas
    from kagan.server.mcp.toolsets.projects import register as register_projects
    from kagan.server.mcp.toolsets.review import register as register_review
    from kagan.server.mcp.toolsets.sessions import register as register_sessions
    from kagan.server.mcp.toolsets.settings import register as register_settings
    from kagan.server.mcp.toolsets.tasks import register as register_tasks

    register_tasks(mcp, opts)
    register_sessions(mcp, opts)
    register_projects(mcp, opts)
    register_review(mcp, opts)
    register_settings(mcp, opts)
    register_personas(mcp, opts)
    register_diagnostics(mcp, opts)
    register_integrations(mcp, opts)
    register_analytics(mcp, opts)
    register_fs(mcp, opts)
