"""kagan.mcp.server — MCP server factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import TYPE_CHECKING

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from kagan.core import KaganCore


@dataclass(frozen=True, slots=True)
class ServerOptions:
    readonly: bool = False
    admin: bool = False
    session_id: str | None = None
    enable_instrumentation: bool = False
    db_path: str | None = None  # optional path for KaganCore; None = default
    project_id: str | None = None  # if set, activate this project at lifespan start

    def __post_init__(self) -> None:
        if self.readonly and self.admin:
            raise ValueError("readonly and admin are mutually exclusive")


@dataclass(frozen=True, slots=True)
class ServerContext:
    client: KaganCore
    opts: ServerOptions
    bound_session_id: str | None = None
    bound_task_id: str | None = None
    bound_project_id: str | None = None


_SERVER_OPTS: dict[int, ServerOptions] = {}
_SERVER_CONTEXTS: dict[int, ServerContext] = {}


def get_context(ctx: Context) -> ServerContext:
    """Extract ServerContext from an MCP lifespan context."""
    app = ctx.request_context.lifespan_context
    if isinstance(app, ServerContext):
        return app
    raise ValueError("MCP app context is not available")


def _set_server_context(mcp: FastMCP, app: ServerContext | None) -> None:
    server_key = id(mcp)
    if app is None:
        _SERVER_CONTEXTS.pop(server_key, None)
        return
    _SERVER_CONTEXTS[server_key] = app


def get_server_context(mcp: FastMCP) -> ServerContext | None:
    return _SERVER_CONTEXTS.get(id(mcp))


async def _resolve_binding(client: KaganCore, session_id: str) -> tuple[str | None, str | None]:
    return await client.tasks.sessions.resolve_binding(session_id)


async def _ensure_active_project(client: KaganCore) -> str:
    projects = await client.projects.list()
    if projects:
        await client.projects.set_active(projects[0].id)
        return projects[0].id

    project = await client.projects.create("Default Project")
    await client.projects.set_active(project.id)
    return project.id


@asynccontextmanager
async def _lifespan(mcp: FastMCP) -> AsyncIterator[ServerContext]:
    opts = _SERVER_OPTS.get(id(mcp), ServerOptions())
    from kagan.core import KaganCore, install_asyncio_subprocess_exception_filter

    install_asyncio_subprocess_exception_filter()
    client = KaganCore(db_path=opts.db_path)
    logger.debug("MCP lifespan: client initialized")

    bound_session_id: str | None = opts.session_id
    bound_task_id: str | None = None
    bound_project_id: str | None = None

    if opts.project_id is not None:
        await client.projects.set_active(opts.project_id)
        bound_project_id = opts.project_id
        logger.debug("MCP lifespan: project activated via explicit project_id")
    elif opts.session_id is not None:
        bound_task_id, bound_project_id = await _resolve_binding(client, opts.session_id)
        if bound_project_id is not None:
            await client.projects.set_active(bound_project_id)
            logger.debug("MCP lifespan: project activated via session binding")
    if bound_project_id is None:
        bound_project_id = await _ensure_active_project(client)
        logger.debug("MCP lifespan: fallback project activated")

    ctx = ServerContext(
        client=client,
        opts=opts,
        bound_session_id=bound_session_id,
        bound_task_id=bound_task_id,
        bound_project_id=bound_project_id,
    )
    _set_server_context(mcp, ctx)
    try:
        yield ctx
    finally:
        logger.debug("MCP lifespan: shutting down")
        _set_server_context(mcp, None)
        client.close()


def create_server(opts: ServerOptions) -> FastMCP:
    """Create and return a configured kagan MCP server with all toolsets registered."""
    from kagan.mcp.prompts import register as register_prompts  # avoid circular at module level
    from kagan.mcp.resources import register as register_resources  # avoid circular at module level
    from kagan.mcp.toolsets import register_all_toolsets  # avoid circular at module level

    instructions = (
        "Kagan — AI-powered Kanban board MCP server for autonomous development workflows.\n"
        "\n"
        "Core capabilities:\n"
        "- Task lifecycle: task_create, task_list, task_get, task_update, task_delete, "
        "task_search, task_batch_create, task_add_note, task_events, tasks_wait, task_counts\n"
        "- Run control: run_start (run/pair agents), run_summary, "
        "run_cancel, run_update\n"
        "- Project management: project_list, project_create, project_set_active, project_delete, "
        "project_add_repo, repo_list\n"
        "- Review: review_decide (approve/reject/merge/rebase), review_conflicts, "
        "review_continue_rebase, review_abort_rebase\n"
        "- Settings: settings_get, settings_set, audit_list\n"
        "- Diagnostics: diagnostics_get_instrumentation\n"
        "\n"
        "Execution modes (IMPORTANT — clarify with user when creating tasks):\n"
        "- AUTO (default): Agent works independently to completion. Best for "
        "well-defined tasks with clear acceptance criteria.\n"
        "- PAIR: Agent works interactively as a co-pilot with the user in a tmux session. "
        "Best for exploratory work, complex debugging, or when the user wants hands-on "
        "control.\n"
        "When creating tasks, ALWAYS ask the user whether they want AUTO or PAIR mode "
        "if they have not specified. Briefly explain the difference: AUTO runs the agent "
        "independently, PAIR opens an interactive co-pilot session. Default to AUTO "
        "when the user does not express a preference. When batch-creating tasks, consider which "
        "tasks suit AUTO vs PAIR and recommend accordingly.\n"
        "\n"
        "Tool result truthfulness protocol:\n"
        "- Never claim a mutation succeeded unless the tool call returned success "
        "and payload values.\n"
        "- For task_create/task_update/task_batch_create, echo persisted fields from tool results "
        "(especially execution_mode, status, acceptance_criteria).\n"
        "- If any item fails in batch operations, report partial success explicitly "
        "with counts and failed indexes.\n"
        "- If a claim depends on current state and payload is incomplete, call task_get before "
        "summarizing.\n"
        "\n"
        "Workflow: create tasks (task_batch_create) → start agents (run_start) → "
        "monitor (tasks_wait/run_summary) → review (review_decide) → merge.\n"
        "\n"
        "Access tiers: admin (full control), standard (task-scoped), readonly (read only). "
        "Tools are filtered by access tier at registration time."
    )
    mcp = FastMCP(name="kagan", instructions=instructions, lifespan=_lifespan)
    _SERVER_OPTS[id(mcp)] = opts
    register_all_toolsets(mcp, opts)
    register_resources(mcp, opts)
    register_prompts(mcp, opts)
    logger.info("MCP server created")
    return mcp


async def serve(opts: ServerOptions) -> None:
    """Create the kagan MCP server and run it over STDIO transport."""
    mcp = create_server(opts)
    logger.info("MCP server starting on STDIO")
    await mcp.run_stdio_async()
