"""Environment diagnostic command."""

from __future__ import annotations

import asyncio
import sys
from dataclasses import dataclass
from typing import Literal, cast

import click

from kagan.core.command_utils import cached_which
from kagan.core.config import DOCTOR_VERBOSITY_VALUES, KaganConfig
from kagan.core.domain.pair_terminal_backends import (
    ANTIGRAVITY_BACKEND,
    CURSOR_BACKEND,
    KIRO_BACKEND,
    NVIM_BACKEND,
    TMUX_BACKEND,
    VSCODE_BACKEND,
    WINDSURF_BACKEND,
    coerce_pair_terminal_backend,
)
from kagan.core.paths import get_config_path


class _CheckStatus:
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


type DoctorVerbosity = Literal["tldr", "short", "technical"]


def _with_sources(hint: str, *sources: str) -> str:
    """Append source links to a hint block."""
    if not sources:
        return hint

    lines = [hint, "Sources:"]
    lines.extend(f"- {source}" for source in sources)
    return "\n".join(lines)


def _os_quick_cli(*, macos: str, ubuntu: str, windows: str) -> str:
    return "\n".join(
        (
            f"   macOS: {macos}",
            f"   Ubuntu: {ubuntu}",
            f"   Windows: {windows}",
        )
    )


def _three_path_hint(*, why: str, beginner: str, quick_cli: str, verify: str) -> str:
    """Build deterministic troubleshooting guidance (exactly three fix paths)."""
    return "\n".join(
        (
            f"Why: {why}",
            f"1) Beginner: {beginner}",
            "2) Quick CLI (pick your OS):",
            quick_cli,
            f"3) Verify: {verify}",
        )
    )


@dataclass(frozen=True)
class DoctorCheckResult:
    """Single doctor check result."""

    name: str
    status: str
    detail: str
    hint: str = ""


@dataclass(frozen=True)
class DoctorReport:
    """Aggregated doctor check output."""

    checks: list[DoctorCheckResult]

    @property
    def has_failure(self) -> bool:
        """Whether any critical check failed."""
        return any(check.status == _CheckStatus.FAIL for check in self.checks)


def _status_icon(status: str) -> str:
    if status == _CheckStatus.PASS:
        return click.style("[PASS]", fg="green")
    if status == _CheckStatus.WARN:
        return click.style("[WARN]", fg="yellow")
    return click.style("[FAIL]", fg="red")


def _render_hint_lines(hint: str, *, verbosity: DoctorVerbosity) -> list[str]:
    """Render hint lines according to requested verbosity."""
    lines = hint.splitlines()
    if not lines:
        return []

    if verbosity == "technical":
        return lines

    beginner_line = next((line for line in lines if line.startswith("1) Beginner:")), "")
    verify_line = next((line for line in lines if line.startswith("3) Verify:")), "")
    first_source = next((line[2:] for line in lines if line.startswith("- ")), "")
    why_line = next((line for line in lines if line.startswith("Why:")), "")

    if verbosity == "tldr":
        return [beginner_line or verify_line or why_line or lines[0]]

    # short
    rendered: list[str] = []
    if beginner_line:
        rendered.append(beginner_line)
    if verify_line:
        rendered.append(verify_line)
    if first_source:
        rendered.append(f"Source: {first_source}")
    if not rendered:
        rendered.append(lines[0])
    return rendered


def resolve_doctor_verbosity(override: str | None = None) -> DoctorVerbosity:
    """Resolve effective doctor verbosity from explicit override or persisted config."""
    if override is not None:
        normalized = override.strip().lower()
        if normalized in DOCTOR_VERBOSITY_VALUES:
            return cast("DoctorVerbosity", normalized)
        return "short"

    try:
        config = KaganConfig.load(get_config_path())
    except Exception:  # quality-allow-broad-except
        return "short"

    configured = str(config.general.doctor_verbosity).strip().lower()
    if configured in DOCTOR_VERBOSITY_VALUES:
        return cast("DoctorVerbosity", configured)
    return "short"


def _check_python_version() -> DoctorCheckResult:
    """Check Python version is 3.12+."""
    vi = sys.version_info
    version = f"{vi[0]}.{vi[1]}.{vi[2]}"
    if vi >= (3, 12):
        return DoctorCheckResult(
            name="Python version",
            status=_CheckStatus.PASS,
            detail=f"Python {version}",
        )
    return DoctorCheckResult(
        name="Python version",
        status=_CheckStatus.FAIL,
        detail=f"Python {version} (3.12+ required)",
        hint=_with_sources(
            _three_path_hint(
                why="Kagan requires Python 3.12+ for runtime and typing guarantees.",
                beginner=(
                    "Use python.org installers (Windows/macOS) or Ubuntu's official "
                    "Python packages."
                ),
                quick_cli=_os_quick_cli(
                    macos="brew install python@3.12",
                    ubuntu="sudo apt update && sudo apt install -y python3-full",
                    windows=(
                        "winget install 9NQ7512CXL7T -e "
                        "--accept-package-agreements --disable-interactivity"
                    ),
                ),
                verify=(
                    "Run `python3 --version` (or `py -V`) and confirm 3.12+. "
                    "On Windows, run `py install 3.12` if no 3.12 runtime is installed."
                ),
            ),
            "https://docs.python.org/3/using/windows.html",
            "https://www.python.org/downloads/latest/pymanager/",
            "https://documentation.ubuntu.com/ubuntu-for-developers/howto/python-setup/",
            "https://formulae.brew.sh/formula/python%403.12",
        ),
    )


def _check_git() -> DoctorCheckResult:
    """Check git is available."""
    path = cached_which("git")
    if path is not None:
        return DoctorCheckResult(name="Git", status=_CheckStatus.PASS, detail="git found")
    return DoctorCheckResult(
        name="Git",
        status=_CheckStatus.FAIL,
        detail="git not found",
        hint=_with_sources(
            _three_path_hint(
                why="Kagan uses git worktrees and git commits for task execution.",
                beginner="Install from https://git-scm.com/downloads and restart your terminal.",
                quick_cli=_os_quick_cli(
                    macos="git --version  # prompts Apple CLT install if missing",
                    ubuntu="sudo apt update && sudo apt install -y git-all",
                    windows="winget install --id Git.Git -e --source winget",
                ),
                verify="Run `git --version` then re-run `kagan`.",
            ),
            "https://git-scm.com/book/en/v2/Getting-Started-Installing-Git",
            "https://learn.microsoft.com/en-us/windows/package-manager/winget/install",
        ),
    )


async def _check_git_version_async() -> DoctorCheckResult:
    """Check git version is 2.5+."""
    from kagan.core.git_utils import MIN_GIT_VERSION, get_git_version

    version = await get_git_version()
    if version is None:
        return DoctorCheckResult(
            name="Git version",
            status=_CheckStatus.FAIL,
            detail="git version unknown",
            hint=_with_sources(
                _three_path_hint(
                    why="Kagan needs a working git binary and version probe for worktree safety.",
                    beginner="Reinstall Git from https://git-scm.com/downloads.",
                    quick_cli=_os_quick_cli(
                        macos="brew reinstall git",
                        ubuntu="sudo apt update && sudo apt install --reinstall -y git",
                        windows="winget install --id Git.Git -e --source winget",
                    ),
                    verify="Run `which git` (or `where git`) and `git --version`.",
                ),
                "https://git-scm.com/book/en/v2/Getting-Started-Installing-Git",
                "https://learn.microsoft.com/en-us/windows/package-manager/winget/install",
            ),
        )
    if version < MIN_GIT_VERSION:
        return DoctorCheckResult(
            name="Git version",
            status=_CheckStatus.FAIL,
            detail=f"git {version} (2.5+ required)",
            hint=_with_sources(
                _three_path_hint(
                    why="Git <2.5 lacks worktree functionality required by Kagan.",
                    beginner="Install latest Git from https://git-scm.com/downloads.",
                    quick_cli=_os_quick_cli(
                        macos="brew update && brew upgrade git",
                        ubuntu="sudo apt update && sudo apt install --only-upgrade -y git",
                        windows="winget upgrade --id Git.Git -e --source winget",
                    ),
                    verify="Run `git --version` and confirm 2.5+ before launching `kagan`.",
                ),
                "https://git-scm.com/book/en/v2/Getting-Started-Installing-Git",
                "https://learn.microsoft.com/en-us/windows/package-manager/winget/install",
            ),
        )
    return DoctorCheckResult(name="Git version", status=_CheckStatus.PASS, detail=f"git {version}")


async def _check_git_user_async() -> DoctorCheckResult:
    """Check git user is configured."""
    from kagan.core.git_utils import check_git_user_configured

    is_configured, error_msg = await check_git_user_configured()
    if is_configured:
        return DoctorCheckResult(
            name="Git user",
            status=_CheckStatus.PASS,
            detail="git user configured",
        )
    return DoctorCheckResult(
        name="Git user",
        status=_CheckStatus.FAIL,
        detail=f"git user not configured: {error_msg}",
        hint=_with_sources(
            _three_path_hint(
                why="Kagan needs a git identity for commits generated by task workflows.",
                beginner=(
                    'Set global identity once: `git config --global user.name "Your Name"` and '
                    '`git config --global user.email "your@email.com"`.'
                ),
                quick_cli=_os_quick_cli(
                    macos=(
                        'git config --global user.name "Your Name" && '
                        'git config --global user.email "your@email.com"'
                    ),
                    ubuntu=(
                        'git config --global user.name "Your Name" && '
                        'git config --global user.email "your@email.com"'
                    ),
                    windows=(
                        'git config --global user.name "Your Name" && '
                        'git config --global user.email "your@email.com"'
                    ),
                ),
                verify=(
                    "Run `git config --global --get user.name` and "
                    "`git config --global --get user.email`."
                ),
            ),
            "https://git-scm.com/book/en/v2/Getting-Started-First-Time-Git-Setup",
        ),
    )


def _check_uv() -> DoctorCheckResult:
    """Check uv is available."""
    path = cached_which("uv")
    if path is not None:
        return DoctorCheckResult(name="uv", status=_CheckStatus.PASS, detail="uv found")
    return DoctorCheckResult(
        name="uv",
        status=_CheckStatus.WARN,
        detail="uv not found",
        hint=_with_sources(
            _three_path_hint(
                why="uv is the recommended package/runtime tool in Kagan docs.",
                beginner="Use install docs: https://docs.astral.sh/uv/getting-started/installation/",
                quick_cli=_os_quick_cli(
                    macos="curl -LsSf https://astral.sh/uv/install.sh | sh",
                    ubuntu="curl -LsSf https://astral.sh/uv/install.sh | sh",
                    windows=(
                        "powershell -ExecutionPolicy ByPass -c "
                        '"irm https://astral.sh/uv/install.ps1 | iex"'
                    ),
                ),
                verify="Run `uv --version`.",
            ),
            "https://docs.astral.sh/uv/getting-started/installation/",
        ),
    )


def _check_tmux() -> DoctorCheckResult:
    """Check tmux is available when selected for PAIR mode."""
    path = cached_which("tmux")
    if path is not None:
        return DoctorCheckResult(name="tmux", status=_CheckStatus.PASS, detail="tmux found")
    quick_cli = _os_quick_cli(
        macos="brew install tmux",
        ubuntu="sudo apt update && sudo apt install -y tmux",
        windows="wsl --install && wsl -e sudo apt update && wsl -e sudo apt install -y tmux",
    )
    return DoctorCheckResult(
        name="tmux",
        status=_CheckStatus.WARN,
        detail="tmux not found (selected PAIR backend)",
        hint=_with_sources(
            _three_path_hint(
                why="The configured PAIR backend is tmux.",
                beginner=(
                    "Install tmux docs and use distro packages. "
                    "Windows users should install WSL first."
                ),
                quick_cli=quick_cli,
                verify="Run `tmux -V`.",
            ),
            "https://github.com/tmux/tmux/wiki/Installing",
            "https://learn.microsoft.com/en-us/windows/wsl/install",
        ),
    )


def _check_nvim() -> DoctorCheckResult:
    """Check nvim is available when selected for PAIR mode."""
    path = cached_which("nvim")
    if path is not None:
        return DoctorCheckResult(name="nvim", status=_CheckStatus.PASS, detail="nvim found")
    quick_cli = _os_quick_cli(
        macos="brew install neovim",
        ubuntu="sudo apt update && sudo apt install -y neovim",
        windows="winget install Neovim.Neovim -e --source winget",
    )
    return DoctorCheckResult(
        name="nvim",
        status=_CheckStatus.WARN,
        detail="nvim not found (selected PAIR backend)",
        hint=_with_sources(
            _three_path_hint(
                why="The configured PAIR backend is Neovim.",
                beginner="Install Neovim from https://neovim.io and restart your terminal.",
                quick_cli=quick_cli,
                verify="Run `nvim --version`.",
            ),
            "https://neovim.io",
            "https://learn.microsoft.com/en-us/windows/package-manager/winget/install",
        ),
    )


def _check_vscode_cli() -> DoctorCheckResult:
    """Check VS Code CLI is available when selected for PAIR mode."""
    path = cached_which("code")
    if path is not None:
        return DoctorCheckResult(name="VS Code CLI", status=_CheckStatus.PASS, detail="code found")
    return DoctorCheckResult(
        name="VS Code CLI",
        status=_CheckStatus.WARN,
        detail="code not found (selected PAIR backend)",
        hint=_with_sources(
            _three_path_hint(
                why="The configured PAIR backend is VS Code.",
                beginner=(
                    "Install VS Code and ensure the `code` command is available in PATH "
                    "(Shell Command: Install 'code' command in PATH)."
                ),
                quick_cli=_os_quick_cli(
                    macos="brew install --cask visual-studio-code",
                    ubuntu="sudo snap install code --classic",
                    windows="winget install Microsoft.VisualStudioCode -e --source winget",
                ),
                verify="Run `code --version`.",
            ),
            "https://code.visualstudio.com/docs/setup/setup-overview",
            "https://code.visualstudio.com/download",
        ),
    )


def _check_cursor_cli() -> DoctorCheckResult:
    """Check Cursor CLI is available when selected for PAIR mode."""
    path = cached_which("cursor")
    if path is not None:
        return DoctorCheckResult(name="Cursor CLI", status=_CheckStatus.PASS, detail="cursor found")
    return DoctorCheckResult(
        name="Cursor CLI",
        status=_CheckStatus.WARN,
        detail="cursor not found (selected PAIR backend)",
        hint=_with_sources(
            _three_path_hint(
                why="The configured PAIR backend is Cursor.",
                beginner="Install Cursor and enable the `cursor` CLI command in PATH.",
                quick_cli=_os_quick_cli(
                    macos="brew install --cask cursor",
                    ubuntu="Install Cursor AppImage/deb and enable CLI from app settings",
                    windows="winget install CursorAI.Cursor -e --source winget",
                ),
                verify="Run `cursor --version`.",
            ),
            "https://cursor.com/downloads",
            "https://learn.microsoft.com/en-us/windows/package-manager/winget/install",
        ),
    )


def _check_windsurf_cli() -> DoctorCheckResult:
    """Check Windsurf CLI is available when selected for PAIR mode."""
    path = cached_which("windsurf")
    if path is not None:
        return DoctorCheckResult(
            name="Windsurf CLI", status=_CheckStatus.PASS, detail="windsurf found"
        )
    return DoctorCheckResult(
        name="Windsurf CLI",
        status=_CheckStatus.WARN,
        detail="windsurf not found (selected PAIR backend)",
        hint=_with_sources(
            _three_path_hint(
                why="The configured PAIR backend is Windsurf.",
                beginner=(
                    "Install Windsurf and ensure the `windsurf` CLI command is available in PATH."
                ),
                quick_cli=_os_quick_cli(
                    macos="brew install --cask windsurf",
                    ubuntu="Download Windsurf from https://windsurf.com/download",
                    windows="Download Windsurf from https://windsurf.com/download",
                ),
                verify="Run `windsurf --version`.",
            ),
            "https://windsurf.com/download",
        ),
    )


def _check_kiro_cli() -> DoctorCheckResult:
    """Check Kiro CLI is available when selected for PAIR mode."""
    path = cached_which("kiro")
    if path is not None:
        return DoctorCheckResult(name="Kiro CLI", status=_CheckStatus.PASS, detail="kiro found")
    return DoctorCheckResult(
        name="Kiro CLI",
        status=_CheckStatus.WARN,
        detail="kiro not found (selected PAIR backend)",
        hint=_with_sources(
            _three_path_hint(
                why="The configured PAIR backend is Kiro.",
                beginner="Install Kiro and ensure the `kiro` CLI command is available in PATH.",
                quick_cli=_os_quick_cli(
                    macos="Download Kiro from https://kiro.dev/downloads",
                    ubuntu="Download Kiro from https://kiro.dev/downloads",
                    windows="Download Kiro from https://kiro.dev/downloads",
                ),
                verify="Run `kiro --version`.",
            ),
            "https://kiro.dev/downloads",
        ),
    )


def _check_antigravity_cli() -> DoctorCheckResult:
    """Check Google Antigravity CLI is available when selected for PAIR mode."""
    path = cached_which("agy")
    if path is not None:
        return DoctorCheckResult(
            name="Antigravity CLI", status=_CheckStatus.PASS, detail="agy found"
        )
    return DoctorCheckResult(
        name="Antigravity CLI",
        status=_CheckStatus.WARN,
        detail="agy not found (selected PAIR backend)",
        hint=_with_sources(
            _three_path_hint(
                why="The configured PAIR backend is Google Antigravity.",
                beginner=(
                    "Install Antigravity and ensure the `agy` CLI command is available in PATH."
                ),
                quick_cli=_os_quick_cli(
                    macos="Download Antigravity from https://antigravity.dev",
                    ubuntu="Download Antigravity from https://antigravity.dev",
                    windows="Download Antigravity from https://antigravity.dev",
                ),
                verify="Run `agy --version`.",
            ),
            "https://antigravity.dev",
        ),
    )


def _configured_pair_terminal_backend() -> str:
    """Resolve configured PAIR terminal backend from config file."""
    try:
        config = KaganConfig.load(get_config_path())
        backend = str(config.general.default_pair_terminal_backend).strip().lower()
    except Exception:  # quality-allow-broad-except
        return TMUX_BACKEND
    normalized = coerce_pair_terminal_backend(backend)
    return normalized if normalized is not None else TMUX_BACKEND


_PAIR_BACKEND_DOCTOR_CHECKS = {
    TMUX_BACKEND: _check_tmux,
    NVIM_BACKEND: _check_nvim,
    VSCODE_BACKEND: _check_vscode_cli,
    CURSOR_BACKEND: _check_cursor_cli,
    WINDSURF_BACKEND: _check_windsurf_cli,
    KIRO_BACKEND: _check_kiro_cli,
    ANTIGRAVITY_BACKEND: _check_antigravity_cli,
}


def _check_pair_terminal_backend() -> DoctorCheckResult:
    """Check the currently selected PAIR terminal backend."""
    backend = _configured_pair_terminal_backend()
    check = _PAIR_BACKEND_DOCTOR_CHECKS.get(backend, _check_tmux)
    return check()


def _check_npx() -> DoctorCheckResult:
    """Check npx is available (needed for ACP agents)."""
    path = cached_which("npx")
    if path is not None:
        return DoctorCheckResult(name="npx", status=_CheckStatus.PASS, detail="npx found")
    return DoctorCheckResult(
        name="npx",
        status=_CheckStatus.WARN,
        detail="npx not found (needed for some ACP agents)",
        hint=_with_sources(
            _three_path_hint(
                why="Some ACP agent backends are executed via npx.",
                beginner="Install Node.js LTS from https://nodejs.org/en/download.",
                quick_cli=_os_quick_cli(
                    macos="brew install node",
                    ubuntu="sudo apt update && sudo apt install -y nodejs npm",
                    windows="winget install OpenJS.NodeJS.LTS -e --source winget",
                ),
                verify="Run `node --version` and `npx --version`.",
            ),
            "https://nodejs.org/en/download",
            "https://formulae.brew.sh/formula/node",
            "https://documentation.ubuntu.com/wsl/latest/tutorials/develop-with-ubuntu-wsl/",
            "https://learn.microsoft.com/en-us/windows/package-manager/winget/install",
        ),
    )


def _check_project_config() -> DoctorCheckResult:
    """Check if kagan config directory exists."""
    from kagan.core.paths import get_config_dir

    config_dir = get_config_dir()
    if config_dir.exists():
        return DoctorCheckResult(
            name="Project config",
            status=_CheckStatus.PASS,
            detail=f"config directory exists ({config_dir})",
        )
    return DoctorCheckResult(
        name="Project config",
        status=_CheckStatus.WARN,
        detail="config directory not found",
        hint=_with_sources(
            _three_path_hint(
                why="Configuration stores defaults, agent settings, and startup behavior.",
                beginner="Run `kagan` once and complete onboarding.",
                quick_cli=_os_quick_cli(
                    macos=f'mkdir -p "{config_dir}" && kagan',
                    ubuntu=f'mkdir -p "{config_dir}" && kagan',
                    windows=f'mkdir "{config_dir}" && kagan',
                ),
                verify=f"Confirm path exists: `{config_dir}`.",
            ),
            "https://docs.kagan.sh/quickstart/",
        ),
    )


def _check_agent_backend() -> DoctorCheckResult:
    """Require at least one installed AI agent backend for TUI workflows."""
    from kagan.core.builtin_agents import get_all_agent_availability

    availability = get_all_agent_availability()
    available = [result.agent.config.name for result in availability if result.is_available]
    if available:
        names = ", ".join(available)
        detail = f"{len(available)} available ({names})"
        return DoctorCheckResult(
            name="AI agent backend",
            status=_CheckStatus.PASS,
            detail=detail,
        )

    install_lines = [
        "Why: TUI task execution requires at least one installed AI agent backend.",
        "1) Beginner: Pick one AI CLI and follow its docs:",
    ]
    for index, result in enumerate(availability, start=1):
        agent = result.agent
        install_lines.append(f"   {index}. {agent.config.name}")
        install_lines.append(f"      Docs: {agent.docs_url or 'No docs URL available'}")
    install_lines.append("2) Quick CLI (pick one install command):")
    for index, result in enumerate(availability, start=1):
        agent = result.agent
        install_lines.append(f"   {index}. {agent.install_command}")
        if agent.docs_url:
            install_lines.append(f"      ({agent.config.name}) {agent.docs_url}")
    install_lines.append(
        "3) Verify: Run your selected agent command (e.g. `codex --version`) then run `kagan`."
    )

    hint = "\n".join(install_lines)
    return DoctorCheckResult(
        name="AI agent backend",
        status=_CheckStatus.FAIL,
        detail="no supported AI agent backend found in PATH",
        hint=hint,
    )


async def _run_async_checks() -> list[DoctorCheckResult]:
    """Run async checks (git version, git user) and return results."""
    results: list[DoctorCheckResult] = []
    results.append(await _check_git_version_async())
    results.append(await _check_git_user_async())
    return results


def run_doctor_checks() -> DoctorReport:
    """Run all doctor checks and return a structured report."""
    checks: list[DoctorCheckResult] = []

    sync_checks = [
        _check_python_version(),
        _check_git(),
        _check_uv(),
        _check_pair_terminal_backend(),
        _check_npx(),
        _check_project_config(),
        _check_agent_backend(),
    ]
    checks.extend(sync_checks)

    # Async checks (git version + user) — only if git is available
    git_available = any(
        check.name == "Git" and check.status == _CheckStatus.PASS for check in checks
    )
    if git_available:
        checks.extend(asyncio.run(_run_async_checks()))

    return DoctorReport(checks=checks)


def render_doctor_report(
    report: DoctorReport,
    *,
    title: str = "Kagan Doctor",
    verbosity: DoctorVerbosity = "short",
) -> None:
    """Render a doctor report to stdout."""
    click.echo()
    click.secho(title, bold=True)
    click.echo()

    checks = report.checks
    if verbosity == "tldr":
        checks = [check for check in report.checks if check.status != _CheckStatus.PASS]
        if not checks:
            click.echo(f"  {_status_icon(_CheckStatus.PASS)} No warnings or failures detected")
            return

    for check in checks:
        icon = _status_icon(check.status)
        click.echo(f"  {icon} {check.name}: {check.detail}")
        if check.hint:
            lines = _render_hint_lines(check.hint, verbosity=verbosity)
            click.echo(f"         Hint: {lines[0]}")
            for line in lines[1:]:
                click.echo(f"               {line}")


@click.command()
@click.option(
    "--verbosity",
    type=click.Choice(("tldr", "short", "technical"), case_sensitive=False),
    default=None,
    help="Output detail level (defaults to general.doctor_verbosity in config).",
)
def doctor(verbosity: str | None) -> None:
    """Run environment diagnostics and report startup blockers and warnings."""
    report = run_doctor_checks()
    normalized_verbosity = resolve_doctor_verbosity(verbosity)
    render_doctor_report(report, verbosity=normalized_verbosity)

    click.echo()
    if report.has_failure:
        if normalized_verbosity != "technical":
            click.secho(
                "For full rationale and official references: `kagan doctor --verbosity technical`.",
                fg="yellow",
            )
        click.secho("Some checks failed. Fix the issues above and re-run.", fg="red")
        raise SystemExit(1)

    if normalized_verbosity != "technical":
        click.secho(
            "For full rationale and official references: `kagan doctor --verbosity technical`.",
            fg="cyan",
        )
    click.secho("All critical checks passed.", fg="green", bold=True)


__all__ = [
    "DoctorCheckResult",
    "DoctorReport",
    "render_doctor_report",
    "resolve_doctor_verbosity",
    "run_doctor_checks",
]
