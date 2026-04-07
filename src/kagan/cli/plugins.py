"""Plugin management CLI commands."""

import click

from kagan.cli._bootstrap import make_client, run_async


@click.group(name="plugins")
def plugins() -> None:
    """Manage kagan plugins."""


@plugins.command()
@click.argument("plugin_name")
@click.option("--repo", required=True, help="Repository in owner/repo format")
@click.option("--state", default="open", show_default=True, help="Issue state: open, closed, all")
@click.option("--label", "labels", multiple=True, help="Filter by label (repeatable)")
@click.option("--limit", default=100, type=int, show_default=True, help="Max issues to fetch")
@click.option("--issues", "issue_numbers", default=None, help="Comma-separated issue numbers")
def sync(
    plugin_name: str,
    repo: str,
    state: str,
    labels: tuple[str, ...],
    limit: int,
    issue_numbers: str | None,
) -> None:
    """Sync external items from a plugin source into the active project."""
    if "/" not in repo:
        raise click.BadParameter("Must be in owner/repo format", param_hint="--repo")

    parsed_numbers = [int(n.strip()) for n in issue_numbers.split(",")] if issue_numbers else None
    run_async(_sync(plugin_name, repo, state, labels, limit, parsed_numbers))


async def _sync(
    plugin_name: str,
    repo: str,
    state: str,
    labels: tuple[str, ...],
    limit: int,
    issue_numbers: list[int] | None,
) -> None:
    from kagan.core.plugins import PluginManager

    client = make_client()
    try:
        projects = await client.projects.list()
        if not projects:
            click.echo("No projects found. Create a project first: kagan tui")
            return
        await client.projects.set_active(projects[0].id)
        project_id = projects[0].id

        manager = PluginManager(client)
        await manager.load()

        for warning in manager.community_warnings:
            click.echo(warning)

        if plugin_name not in manager.available:
            available = ", ".join(manager.available) or "(none)"
            raise click.ClickException(f"Unknown plugin: {plugin_name!r}. Installed: {available}")

        owner, repo_name = repo.split("/", 1)
        from kagan.core.plugins._github import GitHubImportConfig

        config = GitHubImportConfig(
            owner=owner,
            repo=repo_name,
            state=state,
            labels=tuple(labels),
            limit=limit,
            issue_numbers=tuple(issue_numbers) if issue_numbers else (),
        )
        import_plugin = manager.get_import(plugin_name)
        import_plugin.configure(config)

        result = await manager.sync(plugin_name, project_id=project_id)
        click.echo(
            f"Sync complete: {result.created} created, "
            f"{result.skipped} skipped, {len(result.errors)} errors"
        )
        for err in result.errors:
            click.echo(f"  error: {err}")
    finally:
        client.close()


@plugins.command()
@click.argument("plugin_name")
@click.option("--repo", required=True, help="Repository in owner/repo format")
@click.option("--state", default="open", show_default=True, help="Issue state: open, closed, all")
@click.option("--label", "labels", multiple=True, help="Filter by label (repeatable)")
@click.option("--limit", default=100, type=int, show_default=True, help="Max issues to fetch")
def preview(plugin_name: str, repo: str, state: str, labels: tuple[str, ...], limit: int) -> None:
    """Preview available issues from a plugin source."""
    run_async(_preview(plugin_name, repo, state, labels, limit))


async def _preview(
    plugin_name: str, repo: str, state: str, labels: tuple[str, ...], limit: int,
) -> None:
    from kagan.core.integrations.github import preview_github_issues

    client = make_client()
    try:
        projects = await client.projects.list()
        if not projects:
            click.echo("No projects found. Create a project first.")
            return
        await client.projects.set_active(projects[0].id)

        issues = await preview_github_issues(
            client,
            project_id=projects[0].id,
            repo_slug=repo,
            state=state,
            labels=list(labels),
            limit=limit,
        )
        if not issues:
            click.echo("No issues match the filters.")
            return

        click.echo(f"{'#':<6} {'Title':<50} {'State':<8} {'Labels':<20} {'Synced'}")
        click.echo("-" * 90)
        for issue in issues:
            labels_str = ", ".join(issue["labels"][:3])
            synced = "yes" if issue["already_synced"] else ""
            num = issue["number"]
            title = issue["title"][:49]
            st = issue["state"]
            click.echo(f"#{num:<5} {title:<50} {st:<8} {labels_str[:19]:<20} {synced}")
    finally:
        client.close()


@plugins.command(name="list")
def list_plugins() -> None:
    run_async(_list_plugins())


async def _list_plugins() -> None:
    from kagan.core.plugins import PluginManager

    client = make_client()
    try:
        manager = PluginManager(client)
        await manager.load()

        for warning in manager.community_warnings:
            click.echo(warning)

        if not manager.available:
            click.echo("No plugins installed.")
            return

        for name in manager.available:
            meta = manager.get_meta(name)
            if meta and meta.builtin:
                click.echo(f"  {name} (built-in)")
            elif meta:
                click.echo(f"  {name} (community: {meta.package} v{meta.version})")
            else:
                click.echo(f"  {name}")
    finally:
        client.close()


@plugins.command()
@click.argument("plugin_name", required=False)
def check(plugin_name: str | None) -> None:
    run_async(_check_plugins(plugin_name))


async def _check_plugins(plugin_name: str | None) -> None:
    from kagan.core.plugins import PluginManager

    client = make_client()
    try:
        manager = PluginManager(client)
        await manager.load()

        for warning in manager.community_warnings:
            click.echo(warning)

        if plugin_name and plugin_name not in manager.available:
            available = ", ".join(manager.available) or "(none)"
            raise click.ClickException(f"Unknown plugin: {plugin_name!r}. Installed: {available}")

        checks = manager.get(plugin_name).preflight() if plugin_name else manager.preflight()

        if not checks:
            click.echo("No checks to run.")
            return

        for c in checks:
            label = str(c.status).upper()
            click.echo(f"  {label:<4} {c.name}: {c.message}")
            if c.fix_hint:
                click.echo(f"       fix: {c.fix_hint}")
    finally:
        client.close()
