"""kagan.mcp.toolsets.sessions — Session lifecycle MCP tools."""

import contextlib
from enum import StrEnum
from typing import Any, TypedDict, cast

from mcp.server.fastmcp import Context, FastMCP

from kagan.core import resolve_default_agent_backend, resolve_launcher
from kagan.core.errors import KaganError, SessionError, ValidationError
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
    status: str


class SessionKillResult(TypedDict):
    task_id: str
    killed: bool


async def _get_latest_session(client: Any, task_id: str) -> Any:
    return await client.tasks.sessions.get_latest(task_id)


class SessionAction(StrEnum):
    EXISTS = "exists"
    CREATE = "create"
    GET = "get"
    KILL = "kill"
    DETACH = "detach"


_SESSION_ACTIONS = frozenset(item.value for item in SessionAction)


def _parse_session_action(action: str) -> SessionAction:
    try:
        return SessionAction(action)
    except ValueError as exc:
        raise ValidationError(
            "Unknown run_update action",
            f"{action!r}. Must be one of {sorted(_SESSION_ACTIONS)}",
        ) from exc


async def _handle_exists(client: Any, task_id: str) -> SessionExistsResult:
    from kagan.core.errors import NotFoundError

    try:
        task = await client.tasks.get(task_id)
        return {"exists": task is not None, "task_id": task_id}
    except NotFoundError:
        return {"exists": False, "task_id": task_id}


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
    return {"task_id": task_id, "status": str(task.status)}


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
        with contextlib.suppress(Exception):
            ws = await app.client.worktrees.get(task.id)
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


async def _run_update(action: str, task_id: str, ctx: Context) -> dict[str, Any]:
    app = get_context(ctx)
    return await _run_update_core(action, task_id, app.client)


@mcp_error_boundary
async def _run_update_core(action: str, task_id: str, client: Any) -> dict[str, Any]:
    parsed = _parse_session_action(action)
    if parsed is SessionAction.EXISTS:
        return cast("dict[str, Any]", await _handle_exists(client, task_id))
    if parsed is SessionAction.CREATE:
        return cast("dict[str, Any]", await _handle_create(client, task_id))
    if parsed is SessionAction.GET:
        return cast("dict[str, Any]", await _handle_get(client, task_id))
    if parsed is SessionAction.KILL:
        return cast("dict[str, Any]", await _handle_kill(client, task_id))
    if parsed is SessionAction.DETACH:
        return cast("dict[str, Any]", await client.tasks.detach(task_id))
    raise ValidationError("Unknown run_update action", repr(parsed.value))


def register(mcp: FastMCP, opts: ServerOptions) -> None:
    """Register session domain tools on mcp, filtered by opts."""
    _tools = [
        ("run_start", _run_start),
        ("run_summary", _run_summary),
        ("run_cancel", _run_cancel),
        ("run_update", _run_update),
    ]
    for name, fn in _tools:
        if is_tool_allowed(name, opts):
            mcp.tool(name=name)(fn)
