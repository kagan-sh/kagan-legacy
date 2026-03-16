import click
from loguru import logger

from kagan.cli._bootstrap import make_client, run_async

_DEFAULT_PORT = 8765


def _shutdown_server(port: int) -> bool:
    import time
    import urllib.error
    import urllib.request

    health_url = f"http://127.0.0.1:{port}/health"
    shutdown_url = f"http://127.0.0.1:{port}/api/shutdown"

    try:
        with urllib.request.urlopen(health_url, timeout=2):
            pass
    except (OSError, urllib.error.URLError):
        return False

    click.echo(f"Shutting down server on port {port}\u2026")

    try:
        req = urllib.request.Request(shutdown_url, method="POST", data=b"")
        with urllib.request.urlopen(req, timeout=5):
            pass
    except (OSError, urllib.error.URLError):
        # Server may have already exited before sending the response.
        pass

    for _ in range(10):
        time.sleep(0.5)
        try:
            with urllib.request.urlopen(health_url, timeout=1):
                continue
        except (OSError, urllib.error.URLError):
            click.echo("Server stopped.")
            return True

    logger.warning("Server on port {} did not stop within timeout", port)
    return False


@click.command(name="reset")
@click.option("--project", "project_name", type=str, help="Reset a single project by name")
@click.option("--force", is_flag=True, help="Skip confirmation")
def reset(project_name: str | None, force: bool) -> None:
    logger.info("Reset initiated")
    if not force:
        click.confirm("This will delete data. Continue?", abort=True)

    _shutdown_server(_DEFAULT_PORT)

    client = make_client()
    try:
        if project_name:
            project = run_async(client.projects.find_by_name(project_name))
            if project is None:
                raise click.ClickException(f"Project not found: {project_name}")
            run_async(client.projects.delete(project.id))
            click.echo(f"Reset project: {project_name}")
            logger.info("Reset complete")
            return

        run_async(client.reset())
        click.echo("Reset complete")
        logger.info("Reset complete")
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
