"""kagan.mcp.toolsets.sessions — Session lifecycle MCP tools."""

from typing import Any, TypedDict, cast

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

from kagan.core import resolve_default_agent_backend, resolve_launcher
from kagan.core.enums import SessionStatus
from kagan.core.errors import KaganError, SessionError
from kagan.mcp._policy import is_tool_allowed
from kagan.mcp.server import ServerOptions, get_context
from kagan.mcp.toolsets import mcp_error_boundary


class SessionExistsResult(TypedDict):
    exists: bool
    task_id: str


class SessionCreateResult(TypedDict):
    session_id: str
    task_id: str


class SessionGetResult(TypedDict):
    task_id: str
    task_status: str
    session_id: str | None
    session_status: str | None


class SessionKillResult(TypedDict):
    task_id: str
    killed: bool


def _attached_session_or_none(session: Any) -> Any:
    if session is None or session.launcher is None:
        return None
    return session


async def _get_latest_session(client: Any, task_id: str) -> Any:
    return await client.tasks.sessions.get_latest(task_id)


async def _handle_exists(client: Any, task_id: str) -> SessionExistsResult:
    from kagan.core.errors import NotFoundError

    try:
        await client.tasks.get(task_id)
    except NotFoundError:
        return {"exists": False, "task_id": task_id}

    # Assumes get_latest returns None rather than NotFoundError when no sessions exist.
    session = _attached_session_or_none(await client.tasks.sessions.get_latest(task_id))
    has_attached_session = session is not None and session.status in {
        SessionStatus.PENDING,
        SessionStatus.RUNNING,
    }
    return {"exists": has_attached_session, "task_id": task_id}


async def _handle_create(client: Any, task_id: str) -> SessionCreateResult:
    ws = await client.worktrees.get(task_id)
    if ws is None:
        try:
            ws = await client.worktrees.create(task_id)
        except (KaganError, OSError, RuntimeError, ValueError) as prov_exc:
            raise SessionError(
                None, f"Failed to provision workspace for task {task_id!r}: {prov_exc}"
            ) from prov_exc
    settings = await client.settings.get()
    backend = resolve_default_agent_backend(settings)
    launcher = settings.get("attached_launcher", "tmux")
    launcher_key, ide_name = resolve_launcher(launcher)
    session = await client.tasks.run(
        task_id,
        agent_backend=backend,
        launcher=launcher_key,
        ide=ide_name,
    )
    return {"session_id": session.id, "task_id": task_id}


async def _handle_get(client: Any, task_id: str) -> SessionGetResult:
    task = await client.tasks.get(task_id)
    session = _attached_session_or_none(await client.tasks.sessions.get_latest(task_id))
    return {
        "task_id": task_id,
        "task_status": task.status.value,
        "session_id": session.id if session is not None else None,
        "session_status": (session.status.value if session is not None else None),
    }


async def _handle_kill(client: Any, task_id: str) -> SessionKillResult:
    await client.tasks.cancel(task_id)
    return {"task_id": task_id, "killed": True}


@mcp_error_boundary
async def _run_start(
    task_id: str,
    ctx: Context,
    agent_backend: str | None = None,
    launcher: str | None = None,
    persona: str | None = None,
) -> dict:
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
async def _run_cancel(session_id: str, task_id: str, ctx: Context) -> dict:
    app = get_context(ctx)
    await app.client.tasks.cancel(task_id)
    return {"session_id": session_id, "task_id": task_id, "cancelled": True}


@mcp_error_boundary
async def _run_summary(ctx: Context, task_ids: list[str] | None = None) -> dict:
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


@mcp_error_boundary
async def _run_exists(task_id: str, ctx: Context) -> dict[str, Any]:
    """Check whether a task has an interactive session."""
    app = get_context(ctx)
    return cast("dict[str, Any]", await _handle_exists(app.client, task_id))


@mcp_error_boundary
async def _run_create(task_id: str, ctx: Context) -> dict[str, Any]:
    """Start an interactive session for a task."""
    app = get_context(ctx)
    return cast("dict[str, Any]", await _handle_create(app.client, task_id))


@mcp_error_boundary
async def _run_get(task_id: str, ctx: Context) -> dict[str, Any]:
    """Get the latest task and session status for a task."""
    app = get_context(ctx)
    return cast("dict[str, Any]", await _handle_get(app.client, task_id))


@mcp_error_boundary
async def _run_kill(task_id: str, ctx: Context) -> dict[str, Any]:
    """Cancel a task run by task id."""
    app = get_context(ctx)
    return cast("dict[str, Any]", await _handle_kill(app.client, task_id))


@mcp_error_boundary
async def _run_detach(task_id: str, ctx: Context) -> dict[str, Any]:
    """Detach from an interactive session and update task state."""
    app = get_context(ctx)
    return cast("dict[str, Any]", await app.client.tasks.detach(task_id))


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register session domain tools on mcp, filtered by opts."""
    _tools = [
        ("run_start", _run_start),
        ("run_summary", _run_summary),
        ("run_cancel", _run_cancel),
        ("run_exists", _run_exists),
        ("run_create", _run_create),
        ("run_get", _run_get),
        ("run_kill", _run_kill),
        ("run_detach", _run_detach),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
