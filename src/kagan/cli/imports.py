from pathlib import Path

import click

from kagan.cli._bootstrap import make_client, run_async
from kagan.core.integrations.github import (
    canonical_repo_slug,
    detect_github_repo_slug_from_origin,
    format_github_setup_message,
    github_blocking_checks,
    github_preflight_checks,
    normalize_github_state,
    sync_github_issues,
)
from kagan.core.models import Project


@click.group(name="import")
def import_cmd() -> None:
    pass


@import_cmd.command(name="github")
@click.option("--repo", default=None, help="Repository in owner/repo format")
@click.option(
    "--state",
    type=click.Choice(["open", "closed", "all"], case_sensitive=False),
    default="open",
    show_default=True,
    help="Issue state to import",
)
@click.option("--label", "import_label", default=None, help="Only import issues with this label")
@click.option("--yes", is_flag=True, help="Skip confirmation prompt")
def import_github(repo: str | None, state: str, import_label: str | None, yes: bool) -> None:
    run_async(_import_github(repo=repo, state=state, import_label=import_label, yes=yes))


def _print_setup_checks() -> None:
    click.echo("Before importing, make sure GitHub CLI is ready:")
    click.echo("  - Install gh: https://cli.github.com")
    click.echo("  - Sign in: gh auth login")


async def _resolve_project(client) -> Project | None:
    projects = await client.projects.list()
    if not projects:
        return None

    active_project_id = client.active_project_id or projects[0].id
    await client.projects.set_active(active_project_id)
    return await client.projects.get(active_project_id)


async def _import_github(
    *, repo: str | None, state: str, import_label: str | None, yes: bool
) -> None:
    client = make_client()
    try:
        project = await _resolve_project(client)
        if project is None:
            click.echo("No projects found yet. Open `kagan` and create a project first.")
            return

        checks = await github_preflight_checks(client)
        blocking = github_blocking_checks(checks)
        if blocking:
            click.echo(format_github_setup_message(checks))
            raise click.ClickException("Complete setup and run this command again.")

        try:
            candidate_repo = repo
            if candidate_repo is None:
                detected = await detect_github_repo_slug_from_origin(Path.cwd())
                if detected is not None:
                    candidate_repo = detected
                    click.echo(f"Detected repository from origin: {detected}")

            repo_slug = canonical_repo_slug(
                candidate_repo
                if candidate_repo is not None
                else click.prompt("Repository (owner/repo)", type=str)
            )
            normalized_state = normalize_github_state(state)
        except ValueError as exc:
            raise click.BadParameter(str(exc)) from exc

        if not yes:
            _print_setup_checks()
            confirmed = click.confirm(
                (
                    f"Import {normalized_state} issues from {repo_slug} into "
                    f"project '{project.name}'?"
                ),
                default=True,
            )
            if not confirmed:
                click.echo("Import cancelled.")
                return

        result = await sync_github_issues(
            client,
            project_id=project.id,
            repo_slug=repo_slug,
            state=normalized_state,
            import_label=import_label,
        )
        click.echo(
            f"Import complete: {result.created} created, "
            f"{result.skipped} skipped, {len(result.errors)} errors"
        )
        for err in result.errors:
            click.echo(f"  error: {err}")
    finally:
        client.close()
