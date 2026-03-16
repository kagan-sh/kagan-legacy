import click
from loguru import logger

from kagan.cli._bootstrap import run_async


@click.command(
    name="serve",
    help=(
        "Run the Kagan HTTP API server.\n\n"
        "Starts a REST + WebSocket server for local integrations.\n\n"
        "Common usage:\n"
        "  kagan serve\n"
        "  kagan serve --host 0.0.0.0 --port 8765 --tls"
        "  kagan serve --readonly"
    ),
)
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host")
@click.option("--port", default=8765, show_default=True, type=int, help="Bind port")
@click.option("--readonly", is_flag=True, help="Read-only access tier")
@click.option("--admin", is_flag=True, help="Admin access tier")
@click.option("--db", "db_path", type=str, hidden=True)
@click.option("--project-id", "project_id", type=str, hidden=True)
@click.option("--tls", "enable_tls", is_flag=True, help="Enable HTTPS with self-signed certificate")
def serve(
    host: str,
    port: int,
    readonly: bool,
    admin: bool,
    db_path: str | None,
    project_id: str | None,
    enable_tls: bool,
) -> None:
    logger.debug("API server starting")
    if readonly and admin:
        raise click.UsageError("--readonly and --admin are mutually exclusive")

    from kagan.mcp.server import ServerOptions
    from kagan.server import ApiServerOptions, serve_http

    mcp_opts = ServerOptions(
        readonly=readonly,
        admin=admin,
        db_path=db_path,
        project_id=project_id,
    )
    opts = ApiServerOptions(
        mcp_opts=mcp_opts,
        host=host,
        port=port,
        enable_tls=enable_tls,
    )

    click.echo("\nKagan API server:\n")
    click.echo(f"  Local:   http{'s' if enable_tls else ''}://127.0.0.1:{port}")
    if host in ("0.0.0.0", "::"):
        from kagan.cli.web import _resolve_lan_ip

        lan_ip = _resolve_lan_ip()
        if lan_ip != "127.0.0.1":
            click.echo(f"  Network: http{'s' if enable_tls else ''}://{lan_ip}:{port}")
    click.echo()

    run_async(serve_http(opts))
