import click
from loguru import logger

from kagan.cli._bootstrap import make_client, run_async


@click.command(name="reset")
@click.option("--project", "project_name", type=str, help="Reset a single project by name")
@click.option("--force", is_flag=True, help="Skip confirmation")
def reset(project_name: str | None, force: bool) -> None:
    logger.info("Reset initiated")
    if not force:
        click.confirm("This will delete data. Continue?", abort=True)

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
