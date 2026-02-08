"""Shared git command runner and canonical status parsing."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from fnmatch import fnmatch
from typing import TYPE_CHECKING

from kagan.constants import KAGAN_GENERATED_PATTERNS

if TYPE_CHECKING:
    from collections.abc import Sequence
    from pathlib import Path


@dataclass(frozen=True)
class GitCommandResult:
    """Result of a git command invocation."""

    returncode: int
    stdout: str
    stderr: str


class GitCommandRunner:
    """Run git commands in subprocesses."""

    async def run(self, cwd: Path, args: Sequence[str], *, check: bool = True) -> GitCommandResult:
        try:
            proc = await asyncio.create_subprocess_exec(
                "git",
                *args,
                cwd=cwd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError as exc:  # pragma: no cover - environment dependent
            raise RuntimeError("git executable not found") from exc

        stdout_bytes, stderr_bytes = await proc.communicate()
        returncode = proc.returncode if proc.returncode is not None else 1
        stdout = stdout_bytes.decode() if stdout_bytes else ""
        stderr = stderr_bytes.decode() if stderr_bytes else ""

        if check and returncode != 0:
            cmd = " ".join(args)
            err = stderr.strip() or stdout.strip() or "unknown git error"
            raise RuntimeError(f"git {cmd} failed (rc={returncode}): {err}")

        return GitCommandResult(returncode=returncode, stdout=stdout, stderr=stderr)


class GitAdapterBase:
    """Base helper for git adapters with shared execution and status checks."""

    def __init__(self, runner: GitCommandRunner | None = None) -> None:
        self._runner = runner or GitCommandRunner()

    async def _run_git(
        self,
        cwd: Path,
        args: Sequence[str],
        *,
        check: bool = True,
    ) -> tuple[str, str]:
        result = await self._runner.run(cwd, args, check=check)
        return result.stdout, result.stderr

    async def _run_git_result(self, cwd: Path, args: Sequence[str]) -> tuple[int, str, str]:
        result = await self._runner.run(cwd, args, check=False)
        return result.returncode, result.stdout, result.stderr

    async def _has_uncommitted_changes(self, cwd: Path) -> bool:
        stdout, _ = await self._run_git(cwd, ["status", "--porcelain"], check=False)
        return has_tracked_uncommitted_changes(stdout)


def has_tracked_uncommitted_changes(status_output: str) -> bool:
    """Check `git status --porcelain` output for relevant uncommitted changes.

    Canonical behavior:
    - Ignore untracked files.
    - Ignore Kagan-generated/config files.
    - Treat all other tracked changes as uncommitted.
    """
    if not status_output.strip():
        return False

    for raw_line in status_output.splitlines():
        line = raw_line.rstrip()
        if not line:
            continue

        status = line[:2]
        if status == "??":
            continue

        path_segment = line[3:] if len(line) > 3 else ""
        for path in _extract_status_paths(path_segment):
            if path and not _is_kagan_generated_path(path):
                return True

    return False


def _extract_status_paths(path_segment: str) -> list[str]:
    raw_paths = path_segment.split(" -> ") if " -> " in path_segment else [path_segment]
    return [_normalize_status_path(path) for path in raw_paths]


def _normalize_status_path(path: str) -> str:
    normalized = path.strip()
    if len(normalized) >= 2 and normalized[0] == normalized[-1] == '"':
        return normalized[1:-1]
    return normalized


def _is_kagan_generated_path(path: str) -> bool:
    normalized = path.strip().lstrip("./")

    for pattern in KAGAN_GENERATED_PATTERNS:
        if pattern.endswith("/"):
            prefix = pattern.rstrip("/")
            if normalized == prefix or normalized.startswith(f"{prefix}/"):
                return True
            continue

        if fnmatch(normalized, pattern):
            return True

    return False
