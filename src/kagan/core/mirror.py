"""Local CI mirror: run the repo's declared checks in a worktree (TUI-MIRROR-01/02).

Results land in Task.checks as CheckResult; this module owns the runner, the gate owns
which checks are universal. Checks run via shell with a clean env (P6) — never os.environ.
"""

import asyncio
from pathlib import Path

from loguru import logger

from kagan.core.config import RepoConfig  # noqa: TC001 — no `from __future__ import annotations`
from kagan.core.git import base_has_moved
from kagan.core.models import CheckResult
from kagan.runtime_env import build_sanitized_subprocess_environment

_TIMEOUT = 300.0
_OUTPUT_TAIL = 4000  # keep the last few KB; full logs live in the agent stream


async def run_mirror(worktree_path: str | Path, config: RepoConfig) -> list[CheckResult]:
    """Run every declared check in the worktree and collect CheckResults."""
    cwd = Path(worktree_path)
    return [await _run_one(name, cmd, cwd) for name, cmd in config.checks.items()]


async def _run_one(name: str, command: str, cwd: Path) -> CheckResult:
    logger.debug("mirror check {}: {}", name, command)
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        env=build_sanitized_subprocess_environment(),  # P6 clean env, never os.environ
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
        rc = proc.returncode if proc.returncode is not None else 1
        tail = out.decode(errors="replace")[-_OUTPUT_TAIL:]
    except TimeoutError:
        proc.kill()
        await proc.wait()
        rc, tail = 1, f"check timed out after {_TIMEOUT}s"
    return CheckResult(name=name, passed=rc == 0, detail=f"rc={rc}\n{tail}".strip())


async def base_drift_warning(worktree_path: str | Path, base_branch: str) -> str | None:
    """Warn if base moved so codegen/generated artifacts would pull upstream drift."""
    moved, behind = await base_has_moved(worktree_path, base_branch)
    if not moved:
        return None
    return (
        f"Base {base_branch} is {behind} commit(s) ahead; rebase before codegen "
        "or generated artifacts may pull unrelated upstream changes."
    )
