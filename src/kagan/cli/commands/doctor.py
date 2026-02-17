"""Environment diagnostic command."""

from __future__ import annotations

import asyncio
import platform
import sys

import click

from kagan.core.command_utils import cached_which


class _CheckStatus:
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


def _status_icon(status: str) -> str:
    if status == _CheckStatus.PASS:
        return click.style("[PASS]", fg="green")
    if status == _CheckStatus.WARN:
        return click.style("[WARN]", fg="yellow")
    return click.style("[FAIL]", fg="red")


def _check_python_version() -> tuple[str, str, str]:
    """Check Python version is 3.12+."""
    vi = sys.version_info
    version = f"{vi[0]}.{vi[1]}.{vi[2]}"
    if vi >= (3, 12):
        return _CheckStatus.PASS, f"Python {version}", ""
    return (
        _CheckStatus.FAIL,
        f"Python {version} (3.12+ required)",
        "Install Python 3.12+: https://www.python.org/downloads/",
    )


def _check_git() -> tuple[str, str, str]:
    """Check git is available."""
    path = cached_which("git")
    if path is not None:
        return _CheckStatus.PASS, "git found", ""
    return (
        _CheckStatus.FAIL,
        "git not found",
        "Install git: brew install git (macOS) or apt install git (Linux)",
    )


async def _check_git_version_async() -> tuple[str, str, str]:
    """Check git version is 2.5+."""
    from kagan.core.git_utils import MIN_GIT_VERSION, get_git_version

    version = await get_git_version()
    if version is None:
        return _CheckStatus.FAIL, "git version unknown", "Ensure git is installed and in PATH"
    if version < MIN_GIT_VERSION:
        return (
            _CheckStatus.FAIL,
            f"git {version} (2.5+ required)",
            "Upgrade git: brew upgrade git (macOS) or apt upgrade git (Linux)",
        )
    return _CheckStatus.PASS, f"git {version}", ""


async def _check_git_user_async() -> tuple[str, str, str]:
    """Check git user is configured."""
    from kagan.core.git_utils import check_git_user_configured

    is_configured, error_msg = await check_git_user_configured()
    if is_configured:
        return _CheckStatus.PASS, "git user configured", ""
    return (
        _CheckStatus.WARN,
        f"git user not configured: {error_msg}",
        'Run: git config --global user.name "Your Name" && '
        'git config --global user.email "your@email.com"',
    )


def _check_uv() -> tuple[str, str, str]:
    """Check uv is available."""
    path = cached_which("uv")
    if path is not None:
        return _CheckStatus.PASS, "uv found", ""
    return (
        _CheckStatus.WARN,
        "uv not found",
        "Install uv: curl -LsSf https://astral.sh/uv/install.sh | sh",
    )


def _check_tmux() -> tuple[str, str, str]:
    """Check tmux is available (needed for PAIR mode)."""
    path = cached_which("tmux")
    if path is not None:
        return _CheckStatus.PASS, "tmux found", ""
    system = platform.system()
    if system == "Darwin":
        hint = "Install tmux: brew install tmux"
    elif system == "Windows":
        hint = "tmux requires WSL2 on Windows, or use vscode/cursor backend"
    else:
        hint = "Install tmux: sudo apt install tmux"
    return _CheckStatus.WARN, "tmux not found (needed for PAIR mode)", hint


def _check_npx() -> tuple[str, str, str]:
    """Check npx is available (needed for ACP agents)."""
    path = cached_which("npx")
    if path is not None:
        return _CheckStatus.PASS, "npx found", ""
    return (
        _CheckStatus.WARN,
        "npx not found (needed for some ACP agents)",
        "Install Node.js (includes npx): https://nodejs.org",
    )


def _check_project_config() -> tuple[str, str, str]:
    """Check if kagan config directory exists."""
    from kagan.core.paths import get_config_dir

    config_dir = get_config_dir()
    if config_dir.exists():
        return _CheckStatus.PASS, f"config directory exists ({config_dir})", ""
    return (
        _CheckStatus.WARN,
        "config directory not found",
        "Run 'kagan' to initialize configuration",
    )


async def _run_async_checks() -> list[tuple[str, str, str, str]]:
    """Run async checks (git version, git user) and return results."""
    results: list[tuple[str, str, str, str]] = []
    status, detail, hint = await _check_git_version_async()
    results.append(("Git version", status, detail, hint))
    status, detail, hint = await _check_git_user_async()
    results.append(("Git user", status, detail, hint))
    return results


@click.command()
def doctor() -> None:
    """Run environment diagnostics and report issues.

    Checks Python version, git, tmux, uv, npx, and project
    configuration. Each check reports PASS, WARN, or FAIL with
    an actionable fix hint on failure.

    Exit code 0 if all critical checks pass, 1 otherwise.
    """
    checks: list[tuple[str, str, str, str]] = []

    # Synchronous checks
    sync_items: list[tuple[str, tuple[str, str, str]]] = [
        ("Python version", _check_python_version()),
        ("Git", _check_git()),
        ("uv", _check_uv()),
        ("tmux", _check_tmux()),
        ("npx", _check_npx()),
        ("Project config", _check_project_config()),
    ]
    for name, (status, detail, hint) in sync_items:
        checks.append((name, status, detail, hint))

    # Async checks (git version + user) — only if git is available
    git_available = any(
        name == "Git" and status == _CheckStatus.PASS for name, status, _, _ in checks
    )
    if git_available:
        async_results = asyncio.run(_run_async_checks())
        checks.extend(async_results)

    # Output
    click.echo()
    click.secho("Kagan Doctor", bold=True)
    click.echo()

    has_failure = False
    for name, status, detail, hint in checks:
        icon = _status_icon(status)
        click.echo(f"  {icon} {name}: {detail}")
        if hint:
            click.echo(f"         Hint: {hint}")
        if status == _CheckStatus.FAIL:
            has_failure = True

    click.echo()
    if has_failure:
        click.secho("Some checks failed. Fix the issues above and re-run.", fg="red")
        raise SystemExit(1)
    else:
        click.secho("All critical checks passed.", fg="green", bold=True)
