"""System health checks for kagan.core — fail blocks operations, warn is informational."""

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


def run_all_checks(
    db_path: Path,
    agent_backend: str | None = None,
) -> list[PreflightCheckResult]:
    results: list[PreflightCheckResult] = [check_git(), check_tmux(), check_db_writability(db_path)]
    for result in results:
        logger.debug("Preflight: {} = {}", result.name, result.status)

    if agent_backend is not None:
        result = check_agent_backend(agent_backend)
        results.append(result)
        logger.debug("Preflight: {} = {}", result.name, result.status)

    return results
