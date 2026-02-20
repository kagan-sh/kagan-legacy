"""TUI command and startup doctor gate."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import click

from kagan.cli.update import check_for_updates, prompt_and_update
from kagan.core.constants import DEFAULT_DB_PATH
from kagan.core.paths import get_config_path


def _ensure_core_ready_for_cli(db_path: str) -> None:
    """Auto-start core daemon for TUI clients when config allows it."""
    from kagan.core.config import KaganConfig
    from kagan.core.services.runtime import ensure_core_running_sync

    config = KaganConfig.load(get_config_path())
    if not config.general.core_autostart:
        return

    try:
        ensure_core_running_sync(
            config=config,
            config_path=get_config_path(),
            db_path=Path(db_path),
        )
    except Exception as exc:
        click.secho(f"Failed to start core daemon: {exc}", fg="red")
        sys.exit(1)


def _check_for_updates_gate() -> None:
    """Check for updates and prompt user before starting TUI."""
    result = check_for_updates()

    if result.is_dev or result.is_local or result.error:
        return

    if result.update_available:
        click.echo()
        click.secho("A newer version of kagan is available!", fg="yellow", bold=True)
        click.echo(f"  Current: {click.style(result.current_version, fg='red')}")
        click.echo(f"  Latest:  {click.style(result.latest_version, fg='green', bold=True)}")
        click.echo()

        if click.confirm("Would you like to update before starting?", default=True):
            updated = prompt_and_update(result, force=True)
            if updated:
                click.echo()
                click.secho("Please restart kagan to use the new version.", fg="cyan")
                sys.exit(0)
        else:
            click.echo("Continuing with current version...")
            click.echo()


async def _cleanup_stale_done_workspaces_via_core(db_path: str, older_than_days: int) -> int:
    """Run stale DONE-task workspace cleanup through core API/service layers."""
    from kagan.core.bootstrap import create_app_context

    ctx = await create_app_context(get_config_path(), Path(db_path), enable_wire=False)
    try:
        return await ctx.api.cleanup_stale_done_workspaces(older_than_days=older_than_days)
    finally:
        await ctx.close()


def _auto_cleanup_done_workspaces(db_path: str, *, older_than_days: int = 7) -> None:
    if db_path == ":memory:":
        return
    db_file = Path(db_path)
    if not db_file.exists():
        return
    try:
        asyncio.run(_cleanup_stale_done_workspaces_via_core(db_path, older_than_days))
    except Exception as exc:
        click.secho(f"Preflight cleanup failed: {exc}", fg="yellow")


def _run_startup_doctor_gate(*, db_path: str, skip_preflight: bool) -> None:
    """Run doctor checks silently and block startup only on critical failures."""
    if skip_preflight:
        return

    _auto_cleanup_done_workspaces(db_path)

    from kagan.cli.commands.doctor import (
        render_doctor_report,
        resolve_doctor_verbosity,
        run_doctor_checks,
    )

    report = run_doctor_checks()
    if not report.has_failure:
        return

    render_doctor_report(
        report,
        title="Kagan Doctor (startup)",
        verbosity=resolve_doctor_verbosity(),
    )
    click.echo()
    click.secho(
        "Blocking issues prevent TUI startup. Resolve the issues above and run `kagan` again.",
        fg="red",
    )
    raise SystemExit(1)


@click.command()
@click.option("--db", default=DEFAULT_DB_PATH, help="Path to SQLite database")
@click.option(
    "--skip-preflight",
    is_flag=True,
    help="Skip startup doctor checks (development only)",
)
@click.option(
    "--skip-update-check",
    is_flag=True,
    envvar="KAGAN_SKIP_UPDATE_CHECK",
    help="Skip update check on startup",
)
def tui(db: str, skip_preflight: bool, skip_update_check: bool) -> None:
    """Run the Kanban TUI (default command)."""
    db_path = db

    if not skip_update_check and not os.environ.get("KAGAN_SKIP_UPDATE_CHECK"):
        _check_for_updates_gate()

    _run_startup_doctor_gate(db_path=db_path, skip_preflight=skip_preflight)

    from kagan.tui.app import KaganApp, resolve_tui_mouse_enabled

    _ensure_core_ready_for_cli(db_path)
    app = KaganApp(db_path=db_path)
    app.run(mouse=resolve_tui_mouse_enabled())
