import click
from loguru import logger

from kagan.cli._bootstrap import run_async


def _is_server_running(host: str, port: int) -> bool:
    """Check whether a kagan server is already listening by hitting /health."""
    import urllib.error
    import urllib.request

    url = f"http://{host}:{port}/health"
    try:
        with urllib.request.urlopen(url, timeout=2):
            return True
    except (OSError, urllib.error.URLError):
        return False


def _open_browser(url: str) -> None:
    import webbrowser

    try:
        webbrowser.open(url)
    except Exception:
        logger.debug("Could not open browser automatically")


def _resolve_lan_ip() -> str:
    """Detect the machine's LAN-facing IP address.

    Uses the UDP-connect trick: connect a datagram socket to an external
    address (never actually sends data) and read back the local endpoint.
    Falls back to ``127.0.0.1`` if detection fails.
    """
    import socket

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(("8.8.8.8", 80))
            return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"


@click.command(
    name="web",
    help=(
        "Open the Kagan web UI in your browser.\n\n"
        "Starts the bundled local dashboard and opens a browser window.\n"
        "The dashboard always talks to the same `kagan web` instance that\n"
        "serves it. If a server is already running on the target port,\n"
        "opens the browser without starting a new one.\n\n"
        "Common usage:\n"
        "  kagan web\n"
        "  kagan web --port 9000\n"
        "  kagan web --host 0.0.0.0 --no-open"
    ),
)
@click.option("--host", default="127.0.0.1", show_default=True, help="Bind host")
@click.option("--port", default=8765, show_default=True, type=int, help="Bind port")
@click.option("--no-open", is_flag=True, help="Don't auto-open browser")
@click.option("--readonly", is_flag=True, help="Read-only access tier")
@click.option("--admin", is_flag=True, help="Admin access tier")
@click.option("--db", "db_path", type=str, hidden=True)
@click.option("--project-id", "project_id", type=str, hidden=True)
@click.option(
    "--dev",
    "dev_mode",
    is_flag=True,
    hidden=True,
    help="Skip web bundle check (for dev with Vite proxy)",
)
def web(
    host: str,
    port: int,
    no_open: bool,
    readonly: bool,
    admin: bool,
    db_path: str | None,
    project_id: str | None,
    dev_mode: bool,
) -> None:
    from kagan.server._web_ui import has_web_bundle

    if not dev_mode and not has_web_bundle():
        raise click.ClickException(
            "Web UI bundle not found. Please reinstall kagan to get the bundled web assets."
        )

    if readonly and admin:
        raise click.UsageError("--readonly and --admin are mutually exclusive")

    browse_host = "127.0.0.1" if host == "0.0.0.0" else host
    url = f"http://{browse_host}:{port}"

    if _is_server_running(host, port):
        click.echo("\nServer already running:\n")
        click.echo(f"  Local:   http://127.0.0.1:{port}")
        if host in ("0.0.0.0", "::"):
            lan_ip = _resolve_lan_ip()
            if lan_ip != "127.0.0.1":
                click.echo(f"  Network: http://{lan_ip}:{port}")
        click.echo()
        if not no_open:
            _open_browser(url)
        return

    click.echo("\nKagan web dashboard:\n")
    click.echo(f"  Local:   http://127.0.0.1:{port}")
    if host in ("0.0.0.0", "::"):
        lan_ip = _resolve_lan_ip()
        if lan_ip != "127.0.0.1":
            click.echo(f"  Network: http://{lan_ip}:{port}")
    click.echo()
    if not no_open:
        # Schedule browser open after a short delay so the server has time to start.
        import threading

        timer = threading.Timer(1.5, _open_browser, args=[url])
        timer.daemon = True
        timer.start()

    logger.debug("Web UI server starting")

    from kagan.mcp.server import ServerOptions
    from kagan.server import ApiServerOptions, serve_http

    mcp_opts = ServerOptions(
        readonly=readonly,
        admin=not readonly,  # Local orchestrator gets admin by default
        db_path=db_path,
        project_id=project_id,
    )
    opts = ApiServerOptions(
        mcp_opts=mcp_opts,
        host=host,
        port=port,
        web_ui=not dev_mode,  # Serve bundled UI unless in dev mode
        dev_mode=dev_mode,  # Skip auth in dev mode
    )
    run_async(serve_http(opts))
