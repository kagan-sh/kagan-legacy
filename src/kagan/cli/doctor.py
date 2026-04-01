import os
import re
import shutil
import subprocess
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import click
from loguru import logger

from kagan.cli._bootstrap import make_client, run_async
from kagan.core import (
    CLAUDE_CODE_BACKEND,
    CODEX_BACKEND,
    PreflightCheckResult,
    get_backend_spec,
    resolve_default_agent_backend,
)
from kagan.core.errors import KaganError
from kagan.core.plugins import PluginManager
from kagan.runtime_env import noisy_env_keys


@dataclass(frozen=True)
class DoctorCheck:
    name: str
    status: str
    message: str
    fix_hint: str
    verify_hint: str


def _parse_zellij_version() -> tuple[int, ...] | None:
    try:
        out = subprocess.run(
            ["zellij", "--version"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()
        match = re.search(r"(\d+\.\d+\.\d+)", out)
        if match:
            return tuple(int(p) for p in match.group(1).split("."))
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return None


def _default_agent_backend_name() -> str:
    return os.environ.get("KAGAN_AGENT_BACKEND", resolve_default_agent_backend({}))


async def _resolve_doctor_backend_name(client: object) -> str:
    settings_ops = getattr(client, "settings", None)
    get_settings = cast(
        "Callable[[], Awaitable[object]] | None",
        getattr(settings_ops, "get", None),
    )
    if callable(get_settings):
        try:
            settings = await get_settings()
            if isinstance(settings, dict):
                return resolve_default_agent_backend(settings)
        except (KaganError, RuntimeError, OSError, ValueError):
            logger.opt(exception=True).debug(
                "Doctor could not read default agent backend from settings"
            )
    return _default_agent_backend_name()


def _agent_executable(backend_name: str) -> str:
    try:
        executable = get_backend_spec(backend_name).executable
        if executable:
            return executable
    except (ImportError, KaganError):
        pass
    return backend_name


def _which_command() -> str:
    return "where" if sys.platform == "win32" else "which"


def _backend_verify_hint(backend_name: str) -> str:
    executable = _agent_executable(backend_name)
    if backend_name in {CLAUDE_CODE_BACKEND, CODEX_BACKEND}:
        return f"{executable} --version"
    return f"{_which_command()} {executable}"


def _reference_backend_guidance(backend_name: str) -> str | None:
    try:
        guidance = get_backend_spec(backend_name).guidance_hints()
    except (ImportError, KaganError):
        return None
    return " ".join(guidance) if guidance else None


_VERIFY_HINTS: dict[str, str | Callable[[], str]] = {
    "git": "git --version",
    "tmux": "tmux -V",
    "db": "kagan projects",
    "ide": "echo $TERM_PROGRAM",
    "gh cli": "gh --version",
    "gh auth": "gh auth token",
}


def _verify_hint(name: str) -> str:
    hint = _VERIFY_HINTS.get(name, "ls")
    return hint() if callable(hint) else hint


async def _load_and_collect_plugin_checks(manager: PluginManager) -> list[PreflightCheckResult]:
    await manager.load()
    return manager.preflight()


def _collect_doctor_checks() -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []
    client = make_client()
    try:
        default_backend = run_async(_resolve_doctor_backend_name(client))
        preflight = run_async(client.preflight(agent_backend=_agent_executable(default_backend)))
        for check in preflight:
            name = check.name.replace("_", " ")
            message = check.message
            verify_hint = _verify_hint(name)
            if name == "agent backend":
                message = f"Default agent backend '{default_backend}': {check.message}"
                verify_hint = _backend_verify_hint(default_backend)
                reference_guidance = _reference_backend_guidance(default_backend)
                fix_hint = check.fix_hint
                if reference_guidance and check.status != "pass":
                    fix_hint = (
                        f"{check.fix_hint} {reference_guidance}".strip()
                        if check.fix_hint
                        else reference_guidance
                    )
            else:
                fix_hint = check.fix_hint
            checks.append(
                DoctorCheck(
                    name=name,
                    status=str(check.status),
                    message=message,
                    fix_hint=fix_hint,
                    verify_hint=verify_hint,
                )
            )

        if shutil.which("code") or os.environ.get("TERM_PROGRAM"):
            checks.append(
                DoctorCheck(
                    name="ide",
                    status="pass",
                    message="IDE integration detected",
                    fix_hint="",
                    verify_hint=_verify_hint("ide"),
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    name="ide",
                    status="warn",
                    message="IDE integration not detected",
                    fix_hint="Open this project in a supported editor for richer workflows",
                    verify_hint=_verify_hint("ide"),
                )
            )

        if os.environ.get("ZELLIJ"):
            zellij_version = _parse_zellij_version()
            if zellij_version and zellij_version < (0, 42, 0):
                checks.append(
                    DoctorCheck(
                        name="terminal multiplexer",
                        status="warn",
                        message=(
                            f"Zellij {'.'.join(map(str, zellij_version))} has known rendering"
                            " issues with Textual TUIs"
                        ),
                        fix_hint="Upgrade Zellij to >= 0.42.0 (fixes synchronized output bug)",
                        verify_hint="zellij --version",
                    )
                )
            else:
                checks.append(
                    DoctorCheck(
                        name="terminal multiplexer",
                        status="pass",
                        message="Zellij detected (compatible version)",
                        fix_hint="",
                        verify_hint="zellij --version",
                    )
                )

        cwd = Path.cwd()
        if (cwd / "pyproject.toml").exists():
            checks.append(
                DoctorCheck(
                    name="project config",
                    status="pass",
                    message="pyproject.toml found",
                    fix_hint="",
                    verify_hint="test -f pyproject.toml",
                )
            )
        else:
            checks.append(
                DoctorCheck(
                    name="project config",
                    status="warn",
                    message="pyproject.toml not found in current directory",
                    fix_hint="Run this command from your project root",
                    verify_hint="pwd",
                )
            )

        noisy_keys = noisy_env_keys()
        active_noisy = [key for key in noisy_keys if os.environ.get(key)]
        if active_noisy:
            checks.append(
                DoctorCheck(
                    name="startup env",
                    status="warn",
                    message=(
                        "Debug allocator environment variables are set: " + ", ".join(active_noisy)
                    ),
                    fix_hint=("Unset them before launching kagan: unset " + " ".join(active_noisy)),
                    verify_hint="env | grep -i malloc",
                )
            )

        try:
            plugin_manager = PluginManager(client)
            plugin_checks = run_async(_load_and_collect_plugin_checks(plugin_manager))
            for pc in plugin_checks:
                name = pc.name.replace("_", " ")
                checks.append(
                    DoctorCheck(
                        name=name,
                        status=str(pc.status),
                        message=pc.message,
                        fix_hint=pc.fix_hint,
                        verify_hint=_verify_hint(name),
                    )
                )
        except (ImportError, KaganError, RuntimeError):
            logger.opt(exception=True).debug("Plugin preflight collection failed")
    finally:
        close = getattr(client, "close", None)
        if callable(close):
            close()

    return checks


def _emit_tldr(checks: list[DoctorCheck]) -> None:
    total = len(checks)
    passed = sum(1 for c in checks if c.status == "pass")
    warned = sum(1 for c in checks if c.status == "warn")
    failed = sum(1 for c in checks if c.status == "fail")
    click.echo(f"doctor: {total} checks | PASS {passed} | WARN {warned} | FAIL {failed}")


def _emit_short(checks: list[DoctorCheck]) -> None:
    for check in checks:
        label = check.status.upper()
        click.echo(f"{label:<4} {check.name}: {check.message}")
        if check.status in {"warn", "fail"} and check.fix_hint:
            click.echo(f"  quick fix: {check.fix_hint}")


def _emit_technical(checks: list[DoctorCheck]) -> None:
    for check in checks:
        label = check.status.upper()
        click.echo(f"{label:<4} {check.name}")
        click.echo(f"  detail: {check.message}")
        if check.fix_hint:
            click.echo(f"  quick fix: {check.fix_hint}")
        click.echo(f"  verify: {check.verify_hint}")


@click.command(
    name="doctor",
    epilog=(
        "Examples:\n"
        "  kagan doctor                      Quick health check\n"
        "  kagan doctor --verbosity tldr     One-line summary\n"
        "  kagan doctor --verbosity technical Full diagnostic output"
    ),
)
@click.option(
    "--verbosity",
    type=click.Choice(["tldr", "short", "technical"], case_sensitive=False),
    default="short",
    show_default=True,
)
def doctor(verbosity: str) -> None:
    checks = _collect_doctor_checks()
    logger.debug("Doctor checks collected: {}", len(checks))

    if verbosity == "tldr":
        _emit_tldr(checks)
    elif verbosity == "technical":
        _emit_technical(checks)
    else:
        _emit_short(checks)

    has_failures = any(check.status == "fail" for check in checks)
    if has_failures:
        from kagan.core._logging import default_log_path

        click.echo(f"\nLog file: {default_log_path()}")

    click.get_current_context().exit(1 if has_failures else 0)


def run_doctor_checks() -> list[DoctorCheck]:
    return _collect_doctor_checks()


def render_doctor_report(
    checks: list[DoctorCheck],
    *,
    title: str = "Kagan Doctor",
    verbosity: str = "short",
) -> None:
    click.echo()
    click.secho(title, bold=True)
    click.echo()
    if verbosity == "tldr":
        _emit_tldr(checks)
    elif verbosity == "technical":
        _emit_technical(checks)
    else:
        _emit_short(checks)

    if any(c.status == "fail" for c in checks):
        from kagan.core._logging import default_log_path

        click.echo(f"\nLog file: {default_log_path()}")


def doctor_has_failures(checks: list[DoctorCheck]) -> bool:
    return any(check.status == "fail" for check in checks)
