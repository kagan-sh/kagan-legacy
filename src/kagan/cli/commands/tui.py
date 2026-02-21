"""TUI command and startup doctor gate."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import click

from kagan.cli.update import check_for_updates, prompt_and_update
from kagan.core.runtime_context import CoreRuntimeContext, resolve_runtime_context


def _ensure_core_ready_for_cli(runtime_context: CoreRuntimeContext) -> None:
    """Auto-start core daemon for TUI clients when config allows it."""
    from kagan.core.config import KaganConfig
    from kagan.core.services.runtime import ensure_core_running_sync

    config = KaganConfig.load(runtime_context.config_path)
    if not config.general.core_autostart:
        return

    try:
        ensure_core_running_sync(
            config=config,
            config_path=runtime_context.config_path,
            db_path=runtime_context.db_path,
            runtime_context=runtime_context,
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


async def _cleanup_stale_done_workspaces_via_core(
    runtime_context: CoreRuntimeContext,
    older_than_days: int,
) -> int:
    """Run stale DONE-task workspace cleanup through core API/service layers."""
    from kagan.core.bootstrap import create_app_context

    ctx = await create_app_context(
        runtime_context.config_path,
        runtime_context.db_path,
        enable_wire=False,
    )
    try:
        return await ctx.api.cleanup_stale_done_workspaces(older_than_days=older_than_days)
    finally:
        await ctx.close()


def _auto_cleanup_done_workspaces(
    runtime_context: CoreRuntimeContext | None = None,
    db_path: str | Path | None = None,
    *,
    older_than_days: int = 7,
) -> None:
    if runtime_context is None and isinstance(db_path, str) and db_path.strip() == ":memory:":
        return
    resolved_context = runtime_context or resolve_runtime_context(db_path=db_path)
    resolved_db_path = str(resolved_context.db_path)
    if resolved_db_path == ":memory:":
        return
    db_file = Path(resolved_db_path)
    if not db_file.exists():
        return
    try:
        asyncio.run(_cleanup_stale_done_workspaces_via_core(resolved_context, older_than_days))
    except Exception as exc:
        click.secho(f"Preflight cleanup failed: {exc}", fg="yellow")


def _run_startup_doctor_gate(
    *,
    runtime_context: CoreRuntimeContext | None = None,
    db_path: str | Path | None = None,
    skip_preflight: bool,
) -> None:
    """Run doctor checks silently and block startup only on critical failures."""
    if skip_preflight:
        return

    if runtime_context is not None:
        _auto_cleanup_done_workspaces(runtime_context=runtime_context)
    else:
        _auto_cleanup_done_workspaces(db_path=db_path)

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
@click.option("--db", default=None, help="Path to SQLite database")
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
def tui(db: str | None, skip_preflight: bool, skip_update_check: bool) -> None:
    """Run the Kanban TUI (default command)."""
    runtime_context = resolve_runtime_context(
        db_path=Path(db).expanduser().resolve(strict=False) if db else None
    )

    if not skip_update_check and not os.environ.get("KAGAN_SKIP_UPDATE_CHECK"):
        _check_for_updates_gate()

    _run_startup_doctor_gate(runtime_context=runtime_context, skip_preflight=skip_preflight)

    from kagan.tui.app import KaganApp, resolve_tui_mouse_enabled

    _ensure_core_ready_for_cli(runtime_context)
    app = KaganApp(runtime_context=runtime_context)
    app.run(mouse=resolve_tui_mouse_enabled())
