import click
from loguru import logger

from kagan.cli._bootstrap import run_async


@click.command(
    name="mcp",
    help=(
        "Run MCP server on STDIO.\n\n"
        "Access tiers:\n"
        "  default: read + write tools (safe mutations)\n"
        "  --readonly: read-only tools/resources/prompts\n"
        "  --admin: includes destructive/admin tools\n\n"
        "Common usage:\n"
        "  kagan mcp --readonly\n"
        "  kagan mcp --session-id <id>\n"
        "  kagan mcp --admin --enable-internal-instrumentation"
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
def mcp(
    readonly: bool,
    admin: bool,
    session_id: str | None,
    db_path: str | None,
    project_id: str | None,
    enable_internal_instrumentation: bool,
) -> None:
    logger.debug("MCP server starting")
    if readonly and admin:
        raise click.UsageError("--readonly and --admin are mutually exclusive")

    from kagan.mcp.server import ServerOptions, serve

    opts = ServerOptions(
        readonly=readonly,
        admin=admin,
        session_id=session_id,
        enable_instrumentation=enable_internal_instrumentation,
        db_path=db_path,
        project_id=project_id,
    )
    run_async(serve(opts))
