"""System health checks for kagan.core — fail blocks operations, warn is informational.

Severity rules for agent backends (documented here and enforced in check_agent_backends):

Rule 1 — Zero installed:
    The default backend check is FAIL (triggers DoctorModal zero-ready blocking state).
    All other backend checks are WARN.

Rule 2 — Default missing, at least one other installed:
    The default backend check is FAIL.
    Installed non-default backends are PASS.
    Uninstalled non-default backends are WARN.

Rule 3 — Default installed:
    The default backend check is PASS.
    Installed non-default backends are PASS.
    Uninstalled non-default backends are WARN.
"""

import shutil
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

from loguru import logger


class CheckStatus(StrEnum):
    PASS = "pass"
    WARN = "warn"
    FAIL = "fail"


@dataclass(frozen=True)
class PreflightCheckResult:
    name: str
    status: CheckStatus
    message: str
    fix_hint: str

    @property
    def is_blocking(self) -> bool:
        return self.status == CheckStatus.FAIL


def check_git() -> PreflightCheckResult:
    git = shutil.which("git")
    if git is None:
        return PreflightCheckResult(
            name="git",
            status=CheckStatus.FAIL,
            message="git not found on PATH",
            fix_hint="Install git: brew install git (macOS) or apt install git (Linux)",
        )
    return PreflightCheckResult(
        name="git",
        status=CheckStatus.PASS,
        message=f"git found at {git}",
        fix_hint="",
    )


def check_tmux() -> PreflightCheckResult:
    import sys

    if sys.platform == "win32":
        return PreflightCheckResult(
            name="tmux",
            status=CheckStatus.WARN,
            message="tmux is not available on Windows",
            fix_hint="Use VS Code, Cursor, or another IDE launcher instead",
        )
    tmux = shutil.which("tmux")
    if tmux is None:
        return PreflightCheckResult(
            name="tmux",
            status=CheckStatus.WARN,
            message="tmux not found on PATH — ATTACHED tmux sessions unavailable",
            fix_hint="Install tmux: brew install tmux (macOS) or apt install tmux (Linux)",
        )
    return PreflightCheckResult(
        name="tmux",
        status=CheckStatus.PASS,
        message=f"tmux found at {tmux}",
        fix_hint="",
    )


def check_db_writability(db_path: Path) -> PreflightCheckResult:
    try:
        db_path.parent.mkdir(parents=True, exist_ok=True)
        probe = db_path.parent / ".kagan_write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return PreflightCheckResult(
            name="db",
            status=CheckStatus.PASS,
            message=f"DB path is writable: {db_path}",
            fix_hint="",
        )
    except OSError as exc:
        return PreflightCheckResult(
            name="db",
            status=CheckStatus.FAIL,
            message=f"DB path is not writable: {db_path} — {exc}",
            fix_hint=f"Ensure the directory {db_path.parent} exists and is writable",
        )


def check_agent_backend(executable: str) -> PreflightCheckResult:
    """Check a single agent backend executable (legacy single-backend path).

    Returns WARN (not FAIL) when missing — severity escalation to FAIL requires
    calling check_agent_backends() which applies the multi-backend severity rules.
    """
    found = shutil.which(executable)
    if found is None:
        return PreflightCheckResult(
            name="agent_backend",
            status=CheckStatus.WARN,
            message=f"Agent backend '{executable}' not found on PATH",
            fix_hint=f"Install '{executable}' or configure a different agent backend in Settings",
        )
    return PreflightCheckResult(
        name="agent_backend",
        status=CheckStatus.PASS,
        message=f"Agent backend '{executable}' found at {found}",
        fix_hint="",
    )


def check_agent_backends(default_backend: str | None) -> list[PreflightCheckResult]:
    """Survey all registered backends and classify each result by severity.

    Emits one PreflightCheckResult per registered backend using
    list_available_backends() from kagan.core._agent under the hood.

    Severity rules:
    - Zero of N installed → default is FAIL, rest are WARN.
    - Default missing but at least one other installed → default FAIL,
      installed others PASS, uninstalled others WARN.
    - Default installed → default PASS, uninstalled others WARN,
      installed others PASS.

    The FAIL severity on the default backend check triggers DoctorModal's
    zero-ready blocking state (``any(check.status == "fail")`` is True).

    Args:
        default_backend: The canonical backend name (e.g. "claude-code").
            When None, falls back to "claude-code" for the default slot.

    Returns:
        A list of PreflightCheckResult, one per registered backend,
        with the default backend listed first.
    """
    from kagan.core._agent import get_backend_spec, list_available_backends

    availability = list_available_backends()
    any_installed = any(availability.values())

    resolved_default = default_backend or "claude-code"

    results: list[PreflightCheckResult] = []

    # --- Default backend slot ---
    try:
        _default_spec = get_backend_spec(resolved_default)
        default_executable = _default_spec.executable
    except Exception:
        default_executable = resolved_default
    default_installed = availability.get(resolved_default, False)

    if default_installed:
        default_status = CheckStatus.PASS
        default_msg = (
            f"Default agent backend '{resolved_default}' found (executable: {default_executable})"
        )
        default_hint = ""
    elif any_installed:
        # Default missing but at least one other is available → FAIL
        default_status = CheckStatus.FAIL
        default_msg = (
            f"Default agent backend '{resolved_default}'"
            f" (executable: {default_executable}) not found on PATH"
        )
        default_hint = (
            f"Install '{default_executable}' or change the default backend in Settings"
            " to one that is already installed"
        )
    else:
        # Zero of N installed → also FAIL for default
        default_status = CheckStatus.FAIL
        default_msg = (
            f"Default agent backend '{resolved_default}'"
            f" (executable: {default_executable}) not found on PATH"
            " — no agent backends are installed"
        )
        default_hint = (
            f"Install at least one agent backend."
            f" For '{resolved_default}': install '{default_executable}'."
            " Run `kg doctor` for setup guidance."
        )

    results.append(
        PreflightCheckResult(
            name=f"agent_backend:{resolved_default}",
            status=default_status,
            message=default_msg,
            fix_hint=default_hint,
        )
    )
    logger.debug("Preflight backend (default) {}: {}", resolved_default, default_status)

    # --- Non-default backend slots ---
    for name, installed in availability.items():
        if name == resolved_default:
            continue
        try:
            executable = get_backend_spec(name).executable
        except Exception:
            executable = name
        if installed:
            status = CheckStatus.PASS
            msg = f"Agent backend '{name}' (executable: {executable}) found"
            hint = ""
        else:
            status = CheckStatus.WARN
            msg = f"Agent backend '{name}' (executable: {executable}) not found on PATH"
            hint = f"Install '{executable}' to enable the '{name}' backend"

        results.append(
            PreflightCheckResult(
                name=f"agent_backend:{name}",
                status=status,
                message=msg,
                fix_hint=hint,
            )
        )
        logger.debug("Preflight backend {} = {}", name, status)

    return results


def run_all_checks(
    db_path: Path,
    agent_backend: str | None = None,
) -> list[PreflightCheckResult]:
    """Run all system health checks.

    When agent_backend is provided, surveys all 14 registered backends using
    check_agent_backends() with agent_backend as the default. The default
    backend result uses FAIL severity when not installed (triggers DoctorModal).
    """
    results: list[PreflightCheckResult] = [check_git(), check_tmux(), check_db_writability(db_path)]
    for result in results:
        logger.debug("Preflight: {} = {}", result.name, result.status)

    backend_results = check_agent_backends(agent_backend)
    results.extend(backend_results)

    return results
