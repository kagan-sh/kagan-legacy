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
@click.option("--label", "import_label", default=None, help="Only sync issues with this label")
def sync(plugin_name: str, repo: str, state: str, import_label: str | None) -> None:
    """Sync external items from a plugin source into the active project."""
    if "/" not in repo:
        raise click.BadParameter("Must be in owner/repo format", param_hint="--repo")

    run_async(_sync(plugin_name, repo, state, import_label))


async def _sync(plugin_name: str, repo: str, state: str, import_label: str | None) -> None:
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
            import_label=import_label,
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
