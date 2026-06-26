import click
from loguru import logger

from kagan.cli._bootstrap import run_async


@click.command(
    name="mcp",
    help=(
        "Run MCP server on STDIO.\n\n"
        "\b\n"
        "Common usage:\n"
        "  kagan mcp --task-id <id>\n"
        "  kagan mcp --readonly"
    ),
)
@click.option("--readonly", is_flag=True, help="Read-only access mode")
@click.option("--task-id", "task_id", type=str, help="Scope the server's reports to this task")
@click.option("--data-dir", "data_dir", type=str, hidden=True)
@click.option("--project-id", "project_id", type=str, hidden=True)
def mcp(
    readonly: bool,
    task_id: str | None,
    data_dir: str | None,
    project_id: str | None,
) -> None:
    logger.debug("MCP server starting")
    from kagan.mcp.server import ServerOptions, serve

    opts = ServerOptions(
        readonly=readonly,
        task_id=task_id,
        data_dir=data_dir,
        project_id=project_id,
    )
    run_async(serve(opts))
