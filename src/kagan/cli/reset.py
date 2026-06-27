"""Destructive reset command — wipes the ledger, worktrees, and logs."""

import contextlib
import shutil
import sys
from pathlib import Path

import click
from loguru import logger

from kagan.cli._bootstrap import make_client, run_async


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
    """Return (label, path, description) for the v2 on-disk layout. The ledger and
    worktrees are repo-scoped (ADR-0001); the manifest (.kagan/repo.yaml) and the
    reviews/ decision log are the committable subset (§3.6), so they are the user's
    own tracked artifacts and deliberately NOT in the kill-list."""
    from platformdirs import user_log_dir

    from kagan.core import default_data_dir, git

    root = git.repo_root(Path.cwd()) or Path.cwd()
    return [
        ("Ledger", default_data_dir(), "All task state and event history"),
        ("Worktrees", root / ".kagan_worktrees", "Per-task git worktree checkouts"),
        ("Logs", Path(user_log_dir("kagan", "kagan")), "Application log files"),
    ]


def _prune_worktrees() -> None:
    """rm -rf leaves .git/worktrees/<name> dangling (P5); prune so the paths reuse."""
    from kagan.core import git

    root = git.repo_root(Path.cwd())
    if root is None:
        return
    with contextlib.suppress(Exception):
        run_async(git.worktree_prune(root))


def _remove_kagan_gitignore_line() -> bool:
    """Remove the repo-root .gitignore line kagan appends for worktree checkouts."""
    from kagan.core import git

    root = git.repo_root(Path.cwd())
    if root is None:
        return False
    path = root / ".gitignore"
    if not path.exists():
        return False
    lines = path.read_text(encoding="utf-8").splitlines()
    kept = [line for line in lines if line.strip() != ".kagan_worktrees/"]
    if kept == lines:
        return False
    if kept:
        path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    else:
        path.unlink()
    return True


def _delete_kagan_task_branches() -> tuple[list[str], list[str]]:
    from kagan.core import git

    root = git.repo_root(Path.cwd())
    if root is None:
        return [], []
    try:
        return run_async(git.delete_kagan_task_branches(root))
    except Exception:
        logger.exception("Failed to delete kagan task branches during reset")
        return [], ["kagan/task-*"]


def _print_full_impact() -> None:
    click.echo()
    click.secho("WARNING: Full reset — this will permanently delete:", fg="red", bold=True)
    click.echo()

    total_size = 0
    for label, path, description in _get_data_dirs():
        if not path.exists():
            continue
        size = _dir_size(path)
        total_size += size
        click.echo(f"  {click.style('•', fg='red')} {label}: {click.style(str(path), fg='cyan')}")
        click.echo(f"    {description} ({_format_size(size)})")

    click.echo()
    click.echo(f"Total disk usage: {click.style(_format_size(total_size), fg='yellow', bold=True)}")
    click.echo()
    click.secho("This action cannot be undone!", fg="red", bold=True)
    click.echo()


def _confirm_destructive(prompt_text: str) -> bool:
    """Require the user to type 'yes' for confirmation.

    Fails CLOSED on non-interactive stdin: an open pipe that never delivers a line
    would hang forever, and a stray piped 'yes' would silently authorize a wipe. A
    scripted caller passes --yes/--force instead of feeding the prompt."""
    if not sys.stdin.isatty():
        click.secho(
            "Non-interactive stdin; refusing to reset. Re-run with --yes to confirm.",
            fg="yellow",
            err=True,
        )
        return False
    try:
        confirmed = click.prompt(
            click.style(prompt_text, fg="yellow"), default="", show_default=False
        )
    except click.Abort:
        return False
    return confirmed.lower() == "yes"


def _do_full_reset(client, force: bool) -> None:
    """Wipe the database and remove the data directories."""
    if not force:
        _print_full_impact()
        if not _confirm_destructive("Type 'yes' to confirm full reset"):
            click.secho("Reset cancelled.", fg="green")
            return

    click.echo()
    click.echo("Resetting ledger...")
    run_async(client.reset())
    click.echo(f"  {click.style('✓', fg='green')} Ledger wiped and recreated")

    for label, path, _desc in _get_data_dirs():
        if not path.exists() or label == "Ledger":
            continue
        try:
            shutil.rmtree(path)
            click.echo(f"  {click.style('✓', fg='green')} Removed {label}: {path}")
        except OSError as err:
            click.echo(f"  {click.style('✗', fg='red')} Failed to remove {label}: {err}")

    # Prune unconditionally: the checkout directory may already be gone while git
    # metadata still has a dangling .git/worktrees entry.
    _prune_worktrees()
    if _remove_kagan_gitignore_line():
        click.echo(f"  {click.style('✓', fg='green')} Removed .kagan_worktrees/ from .gitignore")
    deleted, failed = _delete_kagan_task_branches()
    if deleted:
        click.echo(f"  {click.style('✓', fg='green')} Deleted branches: {', '.join(deleted)}")
    if failed:
        click.echo(f"  {click.style('!', fg='yellow')} Branches still present: {', '.join(failed)}")

    click.echo()
    message = (
        "Reset complete. Ledger state was recreated; "
        "worktrees and logs were removed where possible."
    )
    click.secho(
        message,
        fg="green",
        bold=True,
    )
    logger.info("Full reset complete")


@click.command(
    name="reset",
    epilog=(
        "\b\n"
        "Examples:\n"
        "  kagan reset            Interactive full reset (requires 'yes')\n"
        "  kagan reset --dry-run  Preview what would be deleted\n"
        "  kagan reset --yes      Full reset without the interactive prompt"
    ),
)
@click.option("--force", "-f", is_flag=True, help="Skip confirmation (use with caution)")
@click.option("--yes", "-y", is_flag=True, help="Skip the interactive confirmation prompt")
@click.option("--dry-run", is_flag=True, help="Show what would be deleted without deleting")
def reset(force: bool, yes: bool, dry_run: bool) -> None:
    """Destructively reset Kagan data: ledger, worktrees, logs.

    Without --yes/--force, shows the impact and requires typing 'yes' at an
    interactive prompt. On non-interactive stdin the prompt fails closed.
    """
    logger.info("Reset initiated")

    skip_prompt = force or yes

    if dry_run:
        if skip_prompt:
            raise click.UsageError("--yes/--force has no effect with --dry-run")
        _print_full_impact()
        click.secho("Dry run — no changes made.", fg="cyan", bold=True)
        return

    client = make_client()
    try:
        _do_full_reset(client, force=skip_prompt)
    finally:
        client.close()
