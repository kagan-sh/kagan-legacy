"""TUI command with startup doctor gate."""

from pathlib import Path

import click
from loguru import logger


def _run_doctor_gate(*, skip_preflight: bool) -> bool:
    if skip_preflight:
        return True

    from kagan.cli.doctor import (
        doctor_has_failures,
        render_doctor_report,
        run_doctor_checks,
    )

    checks = run_doctor_checks()

    if not doctor_has_failures(checks):
        return True

    render_doctor_report(checks, title="Kagan Doctor (startup)", verbosity="short")
    click.echo()
    click.secho(
        "Blocking issues prevent TUI startup. "
        "Resolve the issues above and run `kagan` again, "
        "or run `kagan doctor --verbosity technical` for full details.",
        fg="red",
    )
    return False


def _launch_tui(
    *,
    db_path: str | Path | None = None,
    startup_chat_session_id: str | None = None,
) -> None:
    from kagan.tui.app import KaganApp

    app = KaganApp(db_path=db_path, startup_chat_session_id=startup_chat_session_id)
    app.run()


@click.command(name="tui")
@click.option("--db", default=None, help="Path to SQLite database")
@click.option(
    "-s",
    "--session-id",
    "session_id",
    type=str,
    default=None,
    help="Pre-attach orchestrator chat to a persisted session.",
)
@click.option(
    "--skip-preflight",
    is_flag=True,
    envvar="KAGAN_SKIP_PREFLIGHT",
    help="Skip startup doctor checks",
)
def tui(db: str | None, session_id: str | None, skip_preflight: bool) -> None:
    """Run the Kanban TUI (default command)."""
    if not _run_doctor_gate(skip_preflight=skip_preflight):
        raise SystemExit(1)

    db_path: str | Path | None = None
    if db:
        db_path = Path(db).expanduser().resolve(strict=False)

    try:
        _launch_tui(db_path=db_path, startup_chat_session_id=session_id)
    except ImportError as exc:
        logger.exception("TUI module import failed")
        raise click.ClickException(
            "TUI module is unavailable in this build. "
            "Run `kagan doctor` to diagnose missing dependencies."
        ) from exc
