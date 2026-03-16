"""kagan.mcp.toolsets.sessions — Session lifecycle MCP tools."""

from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import Any

from mcp.server.fastmcp import Context, FastMCP

from kagan.core.errors import KaganError, SessionError, ValidationError
from kagan.mcp._policy import is_tool_allowed
from kagan.mcp.server import ServerOptions, get_context
from kagan.mcp.toolsets import mcp_error_boundary


async def _get_latest_session(client: Any, task_id: str) -> Any:
    """Return the most recent session for a task, or None."""
    return await client.tasks.sessions.get_latest(task_id)


class SessionAction(StrEnum):
    EXISTS = "exists"
    CREATE = "create"
    GET = "get"
    KILL = "kill"
    FINISH = "finish"


_SESSION_ACTIONS = frozenset(item.value for item in SessionAction)


class SessionStartAction(StrEnum):
    RUN = "run"
    PAIR = "pair"


def _resolve_default_agent_backend(settings: dict[str, str]) -> str:
    return settings.get("default_agent_backend") or "claude-code"


def _parse_session_action(action: str) -> SessionAction:
    try:
        return SessionAction(action)
    except ValueError as exc:
        raise ValidationError(
            "Unknown run_update action",
            f"{action!r}. Must be one of {sorted(_SESSION_ACTIONS)}",
        ) from exc


async def _handle_exists(client: Any, task_id: str) -> dict:
    from kagan.core.errors import NotFoundError

    try:
        task = await client.tasks.get(task_id)
        return {"exists": task is not None, "task_id": task_id}
    except NotFoundError:
        return {"exists": False, "task_id": task_id}


async def _handle_create(client: Any, task_id: str) -> dict:
    ws = await client.worktrees.get(task_id)
    if ws is None:
        try:
            ws = await client.worktrees.create(task_id)
        except (KaganError, OSError, RuntimeError, ValueError) as prov_exc:
            raise SessionError(
                None, f"Failed to provision workspace for task {task_id!r}: {prov_exc}"
            ) from prov_exc
    settings = await client.settings.get()
    backend = _resolve_default_agent_backend(settings)
    launcher = settings.get("pair_launcher", "tmux")
    from kagan.core import resolve_launcher as _resolve_launcher

    launcher_key, ide_name = _resolve_launcher(launcher)
    session = await client.tasks.pair(
        task_id,
        agent_backend=backend,
        launcher=launcher_key,
        ide=ide_name,
    )
    return {"session_id": session.id, "task_id": task_id}


async def _handle_get(client: Any, task_id: str) -> dict:
    task = await client.tasks.get(task_id)
    return {"task_id": task_id, "status": str(task.status)}


async def _handle_kill(client: Any, task_id: str) -> dict:
    await client.tasks.cancel(task_id)
    return {"task_id": task_id, "killed": True}


@mcp_error_boundary
async def _run_start(
    task_id: str,
    ctx: Context,
    action: str = "run",
    agent_backend: str | None = None,
    launcher: str | None = None,
    persona: str | None = None,
) -> dict:
    """Start an agent session for a task.

    If no workspace exists for the task, one is provisioned automatically.
    ``agent_backend`` overrides the default from settings when provided.
    """
    app = get_context(ctx)
    try:
        parsed_action = SessionStartAction(action)
    except ValueError as exc:
        raise ValidationError(
            "Unknown run_start action",
            f"{action!r}. Must be one of {[a.value for a in SessionStartAction]}",
        ) from exc

    ws = await app.client.worktrees.get(task_id)
    if ws is None:
        try:
            ws = await app.client.worktrees.create(task_id)
        except (KaganError, OSError, RuntimeError, ValueError) as prov_exc:
            raise SessionError(
                None, f"Failed to provision workspace for task {task_id!r}: {prov_exc}"
            ) from prov_exc
    settings = await app.client.settings.get()
    resolved_backend = agent_backend or _resolve_default_agent_backend(settings)

    if parsed_action is SessionStartAction.RUN:
        session = await app.client.tasks.run(
            task_id,
            agent_backend=resolved_backend,
            persona=persona,
        )
        return {
            "session_id": session.id,
            "task_id": task_id,
            "status": "STARTED",
            "action": parsed_action.value,
            "mode": "AUTO",
            "agent_backend": resolved_backend,
            "persona": session.persona,
        }

    resolved_launcher = launcher or settings.get("pair_launcher", "tmux")
    from kagan.core import resolve_launcher

    launcher_key, ide_name = resolve_launcher(resolved_launcher)
    session = await app.client.tasks.pair(
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
        "action": parsed_action.value,
        "mode": "PAIR",
        "agent_backend": resolved_backend,
        "launcher": resolved_launcher,
        "persona": session.persona,
    }


@mcp_error_boundary
async def _run_cancel(session_id: str, task_id: str, ctx: Context) -> dict:
    """Cancel a running session."""
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

    rows: list[dict[str, str | None]] = []
    for task in tasks:
        session = await _get_latest_session(app.client, task.id)
        rows.append(
            {
                "task_id": task.id,
                "status": task.status.value,
                "execution_mode": task.execution_mode.value,
                "agent_backend": task.agent_backend,
                "session_id": session.id if session is not None else None,
                "session_backend": session.agent_backend if session is not None else None,
            }
        )
    return {"rows": rows}


async def _run_update(action: str, task_id: str, ctx: Context) -> dict:
    """Manage PAIR session lifecycle: exists, create, get, or kill."""
    app = get_context(ctx)
    return await _run_update_core(action, task_id, app.client)


@mcp_error_boundary
async def _run_update_core(action: str, task_id: str, client: Any) -> dict:
    """Dispatch run_update action against the real core client."""
    parsed = _parse_session_action(action)

    handlers: dict[SessionAction, Callable[[], Awaitable[dict]]] = {
        SessionAction.EXISTS: lambda: _handle_exists(client, task_id),
        SessionAction.CREATE: lambda: _handle_create(client, task_id),
        SessionAction.GET: lambda: _handle_get(client, task_id),
        SessionAction.KILL: lambda: _handle_kill(client, task_id),
        SessionAction.FINISH: lambda: client.tasks.end_pairing(task_id),
    }

    handler = handlers.get(parsed)
    if handler is None:
        raise ValidationError("Unknown run_update action", repr(parsed.value))

    return await handler()


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
