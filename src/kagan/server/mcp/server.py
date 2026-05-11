"""kagan.server.mcp.server — MCP server factory."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from loguru import logger
from mcp.server.fastmcp import Context, FastMCP

if TYPE_CHECKING:
    from kagan.core import KaganCore
    from kagan.core.enums import AgentRole


@dataclass(frozen=True, slots=True)
class ServerOptions:
    readonly: bool = False
    admin: bool = False
    session_id: str | None = None
    enable_instrumentation: bool = False
    db_path: str | None = None
    project_id: str | None = None
    role: AgentRole | None = field(default=None)

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
    presence: Any | None = None
    shutdown_event: Any | None = None


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

    from kagan.server._sse_fanout import register_lifecycle_broadcast

    register_lifecycle_broadcast(client)

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
        await client.aclose()


def create_server(opts: ServerOptions) -> FastMCP:
    """Create and return a configured kagan MCP server with all toolsets registered."""
    from kagan.server.mcp.prompts import register as register_prompts
    from kagan.server.mcp.resources import register as register_resources
    from kagan.server.mcp.toolsets import register_all_toolsets

    instructions = (
        "Kagan — AI-powered Kanban board MCP server for autonomous development workflows.\n"
        "Tools are registered dynamically — use tools/list to discover available capabilities.\n"
        "\n"
        "Run behavior (IMPORTANT — clarify at run_start time):\n"
        "- Managed run (default): Agent runs autonomously in the background to completion.\n"
        "- Attached run: Agent launches interactively in a terminal session via launcher.\n"
        "When starting runs, ask whether interactive attachment is needed. Default to managed "
        "run when preference is not specified. Use launcher selection for attached runs.\n"
        "\n"
        "Tool result truthfulness protocol:\n"
        "- Never claim a mutation succeeded unless the tool call returned success "
        "and payload values.\n"
        "- For task_create/task_update, echo persisted fields from tool results "
        "(especially status and acceptance_criteria).\n"
        "- If any item fails in batch operations, report partial success explicitly "
        "with counts and failed indexes.\n"
        "- If a claim depends on current state and payload is incomplete, call task_get before "
        "summarizing.\n"
        "\n"
        "Workflow: create tasks (task_create) → start agents (run_start) → "
        "monitor (task_wait/run_summary) → review (review_decide) → "
        "merge (review_merge).\n"
        "\n"
        "Agent roles: WORKER (own-task ops + board awareness), "
        "REVIEWER (verdicts + read), ORCHESTRATOR (full control). "
        "Tools are filtered by role at registration time."
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
