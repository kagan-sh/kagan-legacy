import click
from loguru import logger

from kagan.cli._bootstrap import check_and_install_update


@click.command(name="update", short_help="Update kagan to the latest released version.")
@click.option("--check-only", is_flag=True, help="Only check for updates")
@click.option("--prerelease", is_flag=True, help="Allow pre-release versions")
@click.option("--force", is_flag=True, help="Force reinstall even when current")
def update(check_only: bool, prerelease: bool, force: bool) -> None:
    """Update kagan to the latest released version (or --check-only to just report)."""
    logger.debug("Update command invoked")
    ok, message = check_and_install_update(
        check_only=check_only,
        prerelease=prerelease,
        force=force,
    )
    if not ok and not check_only and not message.startswith("Already up to date"):
        raise click.ClickException(message)
    click.echo(message)
