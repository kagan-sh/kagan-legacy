"""Destructive reset command for Kagan data."""

from __future__ import annotations

import asyncio
import shutil
from pathlib import Path

import click

from kagan.constants import DEFAULT_DB_PATH
from kagan.paths import get_cache_dir, get_config_dir, get_data_dir, get_worktree_base_dir


async def _get_projects(db_path: str) -> list[tuple[str, str]]:
    """Return list of (id, name) for all projects in the database."""
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel import select

    from kagan.adapters.db.engine import create_db_engine
    from kagan.adapters.db.schema import Project

    engine = await create_db_engine(db_path)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            result = await session.execute(select(Project.id, Project.name).order_by(Project.name))
            return [(row[0], row[1]) for row in result.all()]
    finally:
        await engine.dispose()


async def _delete_project_data(db_path: str, project_id: str) -> str:
    """Delete all data for a project. Returns project name."""
    from sqlalchemy import delete, update
    from sqlalchemy.ext.asyncio import async_sessionmaker
    from sqlmodel import col, select

    from kagan.adapters.db.engine import create_db_engine
    from kagan.adapters.db.schema import (
        CodingAgentTurn,
        ExecutionProcess,
        ExecutionProcessLog,
        ExecutionProcessRepoState,
        Image,
        Merge,
        Project,
        ProjectRepo,
        Session,
        Task,
        TaskLink,
        TaskTag,
        Workspace,
        WorkspaceRepo,
    )

    engine = await create_db_engine(db_path)
    session_factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with session_factory() as session:
            proj = await session.get(Project, project_id)
            if not proj:
                msg = f"Project {project_id} not found"
                raise ValueError(msg)
            project_name = proj.name

            ws_rows = await session.execute(
                select(Workspace.id).where(col(Workspace.project_id) == project_id)
            )
            ws_ids = [r[0] for r in ws_rows.all()]

            sess_ids: list[str] = []
            if ws_ids:
                sess_rows = await session.execute(
                    select(Session.id).where(col(Session.workspace_id).in_(ws_ids))
                )
                sess_ids = [r[0] for r in sess_rows.all()]

            exec_ids: list[str] = []
            if sess_ids:
                exec_rows = await session.execute(
                    select(ExecutionProcess.id).where(
                        col(ExecutionProcess.session_id).in_(sess_ids)
                    )
                )
                exec_ids = [r[0] for r in exec_rows.all()]

            if exec_ids:
                for model in (
                    ExecutionProcessRepoState,
                    ExecutionProcessLog,
                    CodingAgentTurn,
                ):
                    await session.execute(
                        delete(model).where(col(model.execution_process_id).in_(exec_ids))
                    )

                await session.execute(
                    delete(ExecutionProcess).where(col(ExecutionProcess.id).in_(exec_ids))
                )

            if sess_ids:
                await session.execute(delete(Session).where(col(Session.id).in_(sess_ids)))

            if ws_ids:
                wr_rows = await session.execute(
                    select(WorkspaceRepo).where(col(WorkspaceRepo.workspace_id).in_(ws_ids))
                )
                for (wr,) in wr_rows.all():
                    if wr.worktree_path:
                        shutil.rmtree(wr.worktree_path, ignore_errors=True)

                w_rows = await session.execute(
                    select(Workspace).where(col(Workspace.id).in_(ws_ids))
                )
                for (workspace,) in w_rows.all():
                    if workspace.path and Path(workspace.path).exists():
                        shutil.rmtree(workspace.path, ignore_errors=True)

                await session.execute(delete(Merge).where(col(Merge.workspace_id).in_(ws_ids)))
                await session.execute(
                    delete(WorkspaceRepo).where(col(WorkspaceRepo.workspace_id).in_(ws_ids))
                )
                await session.execute(delete(Workspace).where(col(Workspace.id).in_(ws_ids)))

            task_rows = await session.execute(
                select(Task.id).where(col(Task.project_id) == project_id)
            )
            task_ids = [r[0] for r in task_rows.all()]

            if task_ids:
                await session.execute(
                    delete(TaskLink).where(
                        col(TaskLink.task_id).in_(task_ids)
                        | col(TaskLink.ref_task_id).in_(task_ids)
                    )
                )
                await session.execute(delete(TaskTag).where(col(TaskTag.task_id).in_(task_ids)))
                await session.execute(delete(Image).where(col(Image.task_id).in_(task_ids)))
                await session.execute(
                    update(Task)
                    .where(col(Task.project_id) == project_id)
                    .where(col(Task.parent_id).isnot(None))
                    .values(parent_id=None)
                )
                await session.execute(delete(Task).where(col(Task.project_id) == project_id))

            await session.execute(
                delete(ProjectRepo).where(col(ProjectRepo.project_id) == project_id)
            )
            await session.execute(delete(Project).where(col(Project.id) == project_id))

            await session.commit()
            return project_name
    finally:
        await engine.dispose()


def _format_size(size_bytes: int | float) -> str:
    """Format byte size to human-readable string."""
    size = float(size_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def _reset_all(existing_dirs: list[tuple[str, Path]], force: bool) -> None:
    """Nuclear reset: delete all Kagan directories."""
    click.echo()
    click.secho(
        "WARNING: This will permanently delete the following:",
        fg="red",
        bold=True,
    )
    click.echo()

    total_size = 0
    for name, path in existing_dirs:
        dir_size = sum(f.stat().st_size for f in path.rglob("*") if f.is_file())
        total_size += dir_size
        size_str = _format_size(dir_size)

        click.echo(f"  {click.style('•', fg='red')} {name}: {click.style(str(path), fg='cyan')}")
        click.echo(f"    Size: {size_str}")

        key_files = list(path.glob("*"))[:5]
        if key_files:
            click.echo("    Contains:")
            for file_path in key_files:
                click.echo(f"      - {file_path.name}")
            remaining = len(list(path.glob("*"))) - 5
            if remaining > 0:
                click.echo(f"      ... and {remaining} more items")
        click.echo()

    click.echo(f"Total size: {click.style(_format_size(total_size), fg='yellow', bold=True)}")
    click.echo()
    click.secho("This action cannot be undone!", fg="red", bold=True)
    click.echo()

    if not force:
        confirmed = click.prompt(
            click.style("Type 'yes' to confirm deletion", fg="yellow"),
            default="",
            show_default=False,
        )
        if confirmed.lower() != "yes":
            click.secho("Reset cancelled.", fg="green")
            return

    click.echo()
    click.echo("Removing Kagan directories...")

    errors: list[tuple[str, Path, OSError]] = []
    for name, path in existing_dirs:
        try:
            shutil.rmtree(path)
            click.echo(f"  {click.style('✓', fg='green')} Removed {name}: {path}")
        except OSError as error:
            errors.append((name, path, error))
            click.echo(f"  {click.style('✗', fg='red')} Failed to remove {name}: {error}")

    click.echo()
    if errors:
        click.secho(f"Reset completed with {len(errors)} error(s).", fg="yellow")
    else:
        click.secho(
            "Reset complete. All Kagan data has been removed.",
            fg="green",
            bold=True,
        )


@click.command()
@click.option(
    "--force",
    "-f",
    is_flag=True,
    help="Skip confirmation prompt (use with caution)",
)
def reset(force: bool) -> None:
    """Remove all Kagan configuration, data, and cache files.

    This is a DESTRUCTIVE operation that will permanently delete:
    - Configuration files (config.toml, profiles.toml)
    - Database (kagan.db with all tasks and history)
    - Cache files
    - Worktree directories

    Without --force, presents a menu to reset all or a specific project.
    Use --force to skip prompts and do a full nuclear reset.
    """
    dirs_to_remove: list[tuple[str, Path]] = [
        ("Config directory", get_config_dir()),
        ("Data directory", get_data_dir()),
        ("Cache directory", get_cache_dir()),
        ("Worktree directory", get_worktree_base_dir()),
    ]

    seen_paths: set[Path] = set()
    existing_dirs: list[tuple[str, Path]] = []
    for name, path in dirs_to_remove:
        if path.exists() and path not in seen_paths:
            existing_dirs.append((name, path))
            seen_paths.add(path)

    if not existing_dirs:
        click.secho("Nothing to reset - no Kagan directories found.", fg="yellow")
        return

    if force:
        _reset_all(existing_dirs, force=True)
        return

    db_file = Path(DEFAULT_DB_PATH)
    projects: list[tuple[str, str]] = []
    if db_file.exists():
        import contextlib

        with contextlib.suppress(Exception):
            projects = asyncio.run(_get_projects(DEFAULT_DB_PATH))

    if not projects:
        _reset_all(existing_dirs, force=False)
        return

    click.echo()
    click.secho("What would you like to reset?", bold=True)
    click.echo()
    click.echo(f"  {click.style('1', fg='cyan', bold=True)}) Reset all (nuclear wipe)")
    for i, (project_id, project_name) in enumerate(projects, start=2):
        click.echo(
            f"  {click.style(str(i), fg='cyan', bold=True)}) "
            f"Project: {project_name} (id: {project_id})"
        )
    click.echo()

    choice = click.prompt(
        "Select option",
        type=click.IntRange(1, len(projects) + 1),
        default=1,
    )

    if choice == 1:
        _reset_all(existing_dirs, force=False)
        return

    project_id, project_name = projects[choice - 2]
    click.echo()
    confirmed = click.prompt(
        click.style(
            f"Type 'yes' to delete project '{project_name}'",
            fg="yellow",
        ),
        default="",
        show_default=False,
    )
    if confirmed.lower() != "yes":
        click.secho("Reset cancelled.", fg="green")
        return

    click.echo()
    click.echo(f"Deleting project '{project_name}'...")
    try:
        asyncio.run(_delete_project_data(DEFAULT_DB_PATH, project_id))
        click.secho(
            f"Project '{project_name}' has been removed.",
            fg="green",
            bold=True,
        )
    except Exception as error:
        click.secho(f"Failed to delete project: {error}", fg="red")
