"""Destructive reset command — informative about what will be deleted."""

import shutil
from pathlib import Path

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


def _format_size(size_bytes: int | float) -> str:
    size = float(size_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _dir_size(path: Path) -> int:
    if not path.exists():
        return 0
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _get_data_dirs() -> list[tuple[str, Path, str]]:
    """Return (label, path, description) for all Kagan directories."""
    import os

    from platformdirs import user_config_dir, user_data_dir, user_log_dir, user_state_dir

    data_dir = Path(os.environ.get("KAGAN_DATA_DIR") or user_data_dir("kagan", "kagan"))
    config_dir = Path(os.environ.get("KAGAN_CONFIG_DIR") or user_config_dir("kagan", "kagan"))
    default_worktree_dir = Path(user_state_dir("kagan", "kagan")) / "worktrees"
    wt_override = os.environ.get("KAGAN_WORKTREE_BASE")
    worktree_dir = Path(wt_override).expanduser() if wt_override else default_worktree_dir
    log_dir = Path(user_log_dir("kagan", "kagan"))

    return [
        ("Database", data_dir, "All projects, tasks, sessions, and history"),
        ("Configuration", config_dir, "config.toml and profile settings"),
        ("Worktrees", worktree_dir, "Git worktree checkouts for task execution"),
        ("Logs", log_dir, "Application log files"),
    ]


def _safe_to_remove_tree(label: str, path: Path) -> bool:
    if label != "Worktrees":
        return True

    from platformdirs import user_state_dir

    default_worktree_dir = (Path(user_state_dir("kagan", "kagan")) / "worktrees").resolve()
    try:
        return path.resolve() == default_worktree_dir
    except OSError:
        return False


def _query(engine, fn):
    """Run a read-only DB query synchronously."""
    from sqlmodel import Session as DBSession

    with DBSession(engine) as session:
        return fn(session)


def _collect_stats(client) -> dict:
    """Gather database statistics for the impact summary."""
    from sqlmodel import func, select

    from kagan.core.models import Repository, Session, Task, Worktree

    engine = client._engine
    projects = run_async(client.projects.list())
    task_count = _query(engine, lambda s: s.exec(select(func.count(Task.id))).one())
    session_count = _query(engine, lambda s: s.exec(select(func.count(Session.id))).one())
    worktree_count = _query(engine, lambda s: s.exec(select(func.count(Worktree.id))).one())
    repo_count = _query(engine, lambda s: s.exec(select(func.count(Repository.id))).one())
    return {
        "projects": projects,
        "task_count": task_count,
        "session_count": session_count,
        "worktree_count": worktree_count,
        "repo_count": repo_count,
    }


def _collect_project_stats(client, project_id: str) -> dict:
    """Gather per-project database statistics."""
    from sqlmodel import col, func, select

    from kagan.core.models import Repository, Session, Task, Worktree

    engine = client._engine
    task_count = _query(
        engine,
        lambda s: s.exec(
            select(func.count(Task.id)).where(col(Task.project_id) == project_id)
        ).one(),
    )
    task_ids: list[str] = _query(
        engine,
        lambda s: [
            t.id for t in s.exec(select(Task).where(col(Task.project_id) == project_id)).all()
        ],
    )
    session_count: int = 0
    worktree_count: int = 0
    if task_ids:
        session_count = _query(
            engine,
            lambda s: s.exec(
                select(func.count(Session.id)).where(col(Session.task_id).in_(task_ids))
            ).one(),
        )
        worktree_count = _query(
            engine,
            lambda s: s.exec(
                select(func.count(Worktree.id)).where(col(Worktree.task_id).in_(task_ids))
            ).one(),
        )
    repo_count = _query(
        engine,
        lambda s: s.exec(
            select(func.count(Repository.id)).where(col(Repository.project_id) == project_id)
        ).one(),
    )
    return {
        "task_count": task_count,
        "session_count": session_count,
        "worktree_count": worktree_count,
        "repo_count": repo_count,
    }


def _print_full_impact(stats: dict) -> None:
    """Print a detailed summary of what a full reset will destroy."""
    click.echo()
    click.secho("WARNING: Full reset — this will permanently delete:", fg="red", bold=True)
    click.echo()

    dirs = _get_data_dirs()
    total_size = 0
    for label, path, description in dirs:
        if not path.exists():
            continue
        size = _dir_size(path)
        total_size += size
        click.echo(f"  {click.style('•', fg='red')} {label}: {click.style(str(path), fg='cyan')}")
        click.echo(f"    {description} ({_format_size(size)})")

    click.echo()

    projects = stats["projects"]
    click.secho("Database contents:", bold=True)
    click.echo(f"  Projects:   {len(projects)}")
    for p in projects:
        click.echo(f"              {click.style('•', fg='yellow')} {p.name}")
    click.echo(f"  Tasks:      {stats['task_count']}")
    click.echo(f"  Sessions:   {stats['session_count']}")
    click.echo(f"  Worktrees:  {stats['worktree_count']}")
    click.echo(f"  Repos:      {stats['repo_count']}")
    click.echo()
    click.echo(f"Total disk usage: {click.style(_format_size(total_size), fg='yellow', bold=True)}")
    click.echo()
    click.secho("This action cannot be undone!", fg="red", bold=True)
    click.echo()


def _print_project_impact(project_name: str, stats: dict) -> None:
    """Print what deleting a single project will destroy."""
    click.echo()
    click.secho(
        f"WARNING: This will permanently delete project '{project_name}':",
        fg="red",
        bold=True,
    )
    click.echo()
    click.echo(f"  Tasks:      {stats['task_count']}")
    click.echo(f"  Sessions:   {stats['session_count']}")
    click.echo(f"  Worktrees:  {stats['worktree_count']}")
    click.echo(f"  Repos:      {stats['repo_count']}")
    click.echo()
    click.secho("This action cannot be undone!", fg="red", bold=True)
    click.echo()


def _confirm_destructive(prompt_text: str) -> bool:
    """Require the user to type 'yes' for destructive operations."""
    confirmed = click.prompt(
        click.style(prompt_text, fg="yellow"),
        default="",
        show_default=False,
    )
    return confirmed.lower() == "yes"


def _prompt_reset_choice(projects: list) -> int:
    """Show an interactive menu: full reset or per-project."""
    click.echo()
    click.secho("What would you like to reset?", bold=True)
    click.echo()
    click.echo(f"  {click.style('1', fg='cyan', bold=True)}) Full reset (all data)")
    for i, project in enumerate(projects, start=2):
        click.echo(f"  {click.style(str(i), fg='cyan', bold=True)}) Project: {project.name}")
    click.echo()
    return click.prompt(
        "Select option",
        type=click.IntRange(1, len(projects) + 1),
        default=1,
    )


def _do_full_reset(client, force: bool) -> None:
    """Execute a full reset: wipe DB and remove all data directories."""
    try:
        stats = _collect_stats(client)
    except Exception:
        stats = {
            "projects": [],
            "task_count": "?",
            "session_count": "?",
            "worktree_count": "?",
            "repo_count": "?",
        }

    if not force:
        _print_full_impact(stats)
        if not _confirm_destructive("Type 'yes' to confirm full reset"):
            click.secho("Reset cancelled.", fg="green")
            return

    _shutdown_server(_DEFAULT_PORT)

    click.echo()
    click.echo("Resetting database...")
    run_async(client.reset())
    click.echo(f"  {click.style('✓', fg='green')} Database wiped and recreated")

    dirs = _get_data_dirs()
    for label, path, _desc in dirs:
        if not path.exists():
            continue
        # Don't delete the data dir itself (DB was just recreated there),
        # but do clean worktrees and logs
        if label == "Database":
            continue
        if not _safe_to_remove_tree(label, path):
            click.echo(
                f"  {click.style('!', fg='yellow')} Skipped {label}: {path} "
                "(external override requires manual cleanup)"
            )
            continue
        try:
            shutil.rmtree(path)
            click.echo(f"  {click.style('✓', fg='green')} Removed {label}: {path}")
        except OSError as err:
            click.echo(f"  {click.style('✗', fg='red')} Failed to remove {label}: {err}")

    click.echo()
    click.secho("Reset complete. All Kagan data has been removed.", fg="green", bold=True)
    logger.info("Full reset complete")


def _do_project_reset(client, project, force: bool) -> None:
    """Delete a single project with an impact summary."""
    try:
        stats = _collect_project_stats(client, project.id)
    except Exception:
        stats = {
            "task_count": "?",
            "session_count": "?",
            "worktree_count": "?",
            "repo_count": "?",
        }

    if not force:
        _print_project_impact(project.name, stats)
        if not _confirm_destructive(f"Type 'yes' to delete project '{project.name}'"):
            click.secho("Reset cancelled.", fg="green")
            return

    _shutdown_server(_DEFAULT_PORT)

    click.echo()
    click.echo(f"Deleting project '{project.name}'...")
    run_async(client.projects.delete(project.id))
    click.secho(
        f"Project '{project.name}' has been removed.",
        fg="green",
        bold=True,
    )
    logger.info("Project '{}' deleted", project.name)


def _do_dry_run(client, project_name: str | None) -> None:
    """Show what would be deleted without deleting anything."""
    if project_name:
        project = run_async(client.projects.find_by_name(project_name))
        if project is None:
            raise click.ClickException(f"Project not found: {project_name}")
        try:
            stats = _collect_project_stats(client, project.id)
        except Exception:
            stats = {
                "task_count": "?",
                "session_count": "?",
                "worktree_count": "?",
                "repo_count": "?",
            }
        _print_project_impact(project.name, stats)
    else:
        try:
            stats = _collect_stats(client)
        except Exception:
            stats = {
                "projects": [],
                "task_count": "?",
                "session_count": "?",
                "worktree_count": "?",
                "repo_count": "?",
            }
        _print_full_impact(stats)
    click.secho("Dry run — no changes made.", fg="cyan", bold=True)


@click.command(
    name="reset",
    epilog=(
        "Examples:\n"
        "  kagan reset                   Interactive reset menu\n"
        "  kagan reset --project myapp   Delete a single project\n"
        "  kagan reset --dry-run         Preview what would be deleted\n"
        "  kagan reset --force           Full reset without confirmation"
    ),
)
@click.option("--project", "project_name", type=str, help="Reset a single project by name")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation (use with caution)")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
def reset(project_name: str | None, force: bool, dry_run: bool) -> None:
    """Remove Kagan data with a detailed impact summary.

    Without --project, presents a menu to reset all data or a specific project.
    With --project, deletes only that project's data.

    This is a DESTRUCTIVE operation that will permanently delete:
    - Database (all projects, tasks, sessions, and history)
    - Configuration files (config.toml, profiles)
    - Worktree directories (git checkouts)
    - Log files

    Without --force, shows exactly what will be deleted and requires
    typing 'yes' to confirm.
    """
    logger.info("Reset initiated")

    client = make_client()
    try:
        if dry_run:
            if force:
                raise click.UsageError("--force has no effect with --dry-run")
            _do_dry_run(client, project_name)
            return

        if project_name:
            project = run_async(client.projects.find_by_name(project_name))
            if project is None:
                raise click.ClickException(f"Project not found: {project_name}")
            _do_project_reset(client, project, force)
            return

        if force:
            _do_full_reset(client, force=True)
            return

        # Interactive mode: show menu if projects exist
        projects = run_async(client.projects.list())
        if not projects:
            _do_full_reset(client, force=False)
            return

        choice = _prompt_reset_choice(projects)
        if choice == 1:
            _do_full_reset(client, force=False)
        else:
            project = projects[choice - 2]
            _do_project_reset(client, project, force=False)
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()
