"""TUI command with startup doctor gate.

The doctor gate now runs inside the TUI via DoctorModal for FAIL cases.
WARN-only doctor results continue startup without degraded-performance
messaging. The CLI-level hard exit has been replaced with an in-TUI modal path
so users get a guided remediation flow for blocking failures.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

import click
from loguru import logger

if TYPE_CHECKING:
    from kagan.cli.doctor import DoctorCheck


def _collect_startup_checks(*, skip_preflight: bool) -> list[DoctorCheck]:
    """Run doctor checks and return them for in-TUI routing.

    Returns an empty list when ``skip_preflight`` is True so the app
    starts without displaying any doctor UI.
    """
    if skip_preflight:
        return []

    from kagan.cli.doctor import run_doctor_checks

    return run_doctor_checks()


def _launch_tui(
    *,
    db_path: str | Path | None = None,
    startup_chat_session_id: str | None = None,
    startup_checks: list[DoctorCheck] | None = None,
) -> None:
    from kagan.tui.app import KaganApp

    app = KaganApp(
        db_path=db_path,
        startup_chat_session_id=startup_chat_session_id,
        startup_checks=startup_checks,
    )
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
    from kagan.core import install_asyncio_subprocess_exception_filter

    install_asyncio_subprocess_exception_filter()
    startup_checks = _collect_startup_checks(skip_preflight=skip_preflight)

    db_path: str | Path | None = None
    if db:
        db_path = Path(db).expanduser().resolve(strict=False)

    try:
        _launch_tui(
            db_path=db_path,
            startup_chat_session_id=session_id,
            startup_checks=startup_checks,
        )
    except ImportError as exc:
        logger.exception("TUI module import failed")
        raise click.ClickException(
            "TUI module is unavailable in this build. "
            "Run `kagan doctor` to diagnose missing dependencies."
        ) from exc
