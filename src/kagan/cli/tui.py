"""`kagan tui` — alias for the interactive session (kept for the documented command name)."""

from pathlib import Path

import click

from kagan.cli._bootstrap import run_async


def _resolve_data_dir(explicit: Path | None) -> Path:
    """An explicit --data-dir wins (tests/embedding); otherwise defer to the one
    shared resolver so tui/new/mcp/reset all agree on the ledger root."""
    if explicit is not None:
        return explicit
    from kagan.core import default_data_dir

    return default_data_dir()


@click.command(name="tui")
@click.option(
    "--data-dir", "data_dir", default=None, help="Path to the kagan data directory (ledger root)"
)
@click.option(
    "--skip-preflight",
    is_flag=True,
    envvar="KAGAN_SKIP_PREFLIGHT",
    help="Skip startup doctor checks",
)
def tui(data_dir: str | None, skip_preflight: bool) -> None:
    """Run the supervision session (same as bare `kagan`)."""
    from kagan.cli.doctor import run_doctor_checks
    from kagan.cli.session import run as session_run
    from kagan.core import git, install_asyncio_subprocess_exception_filter
    from kagan.format.doctor import render_preflight

    install_asyncio_subprocess_exception_filter()

    if not skip_preflight:
        checks = run_doctor_checks()
        if any(c.status == "fail" for c in checks):
            from kagan.format._console import print_themed

            print_themed(render_preflight(checks))
            if not click.confirm("Continue anyway?", default=False):
                return

    explicit: Path | None = None
    if data_dir:
        explicit = Path(data_dir).expanduser().resolve(strict=False)
    resolved = _resolve_data_dir(explicit)
    # repo_root is the git toplevel (where worktrees go), NOT the manifest finder —
    # so kagan works in any git repo, with or without a .kagan/repo.yaml yet.
    repo_root = git.repo_root(Path.cwd())

    run_async(session_run(data_dir=resolved, repo_root=repo_root))
