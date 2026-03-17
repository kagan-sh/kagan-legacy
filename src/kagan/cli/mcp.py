import click
from loguru import logger

from kagan.cli._bootstrap import run_async


@click.command(
    name="mcp",
    help=(
        "Run MCP server on STDIO.\n\n"
        "Agent roles:\n"
        "  WORKER: own-task ops + board awareness (default for agents)\n"
        "  REVIEWER: read + verdict tools\n"
        "  ORCHESTRATOR: full project control (default when no role)\n\n"
        "Common usage:\n"
        "  kagan mcp --role WORKER --session-id <id>\n"
        "  kagan mcp --role ORCHESTRATOR\n"
        "  kagan mcp --enable-internal-instrumentation"
    ),
)
@click.option("--readonly", is_flag=True, help="Read-only tier")
@click.option("--admin", is_flag=True, help="Admin tier")
@click.option("--session-id", type=str, help="Bind server context to a session")
@click.option("--db", "db_path", type=str, hidden=True)
@click.option("--project-id", "project_id", type=str, hidden=True)
@click.option(
    "--enable-internal-instrumentation",
    is_flag=True,
    help="Expose diagnostics instrumentation tool",
)
@click.option(
    "--role",
    type=str,
    default=None,
    help="Agent role (WORKER, REVIEWER, ORCHESTRATOR). Controls which MCP tools are available.",
)
def mcp(
    readonly: bool,
    admin: bool,
    session_id: str | None,
    db_path: str | None,
    project_id: str | None,
    enable_internal_instrumentation: bool,
    role: str | None,
) -> None:
    logger.debug("MCP server starting")
    if readonly and admin:
        raise click.UsageError("--readonly and --admin are mutually exclusive")

    from kagan.core.enums import AgentRole
    from kagan.mcp.server import ServerOptions, serve

    resolved_role: AgentRole | None = None
    if role is not None:
        try:
            resolved_role = AgentRole(role)
        except ValueError:
            valid = ", ".join(r.value for r in AgentRole)
            raise click.UsageError(f"Invalid role {role!r}. Must be one of: {valid}") from None

    opts = ServerOptions(
        readonly=readonly,
        admin=admin,
        session_id=session_id,
        enable_instrumentation=enable_internal_instrumentation,
        db_path=db_path,
        project_id=project_id,
        role=resolved_role,
    )
    run_async(serve(opts))
