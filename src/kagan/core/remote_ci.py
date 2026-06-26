"""Read-only remote CI status via the gh CLI (TUI-MIRROR-03, TUI-POSTPR-01/04, Q2).

NEVER writes to the remote: only `gh pr checks --json`. gh presence is a doctor_checks
concern; here, a missing gh / non-zero exit / bad JSON all degrade to status="unknown".

Normalizes gh's raw conclusions into the canonical Task.remote_ci_status vocabulary
("pass" | "fail" | "pending" | "unknown") before returning — the ledger and inbox never
see raw gh words. "fail" is the canonical token shared with the ledger (ci_failed) and the
inbox (precedence).
"""

import asyncio
import json
from pathlib import Path

from loguru import logger

from kagan.core.models import CheckResult, Task
from kagan.runtime_env import build_sanitized_subprocess_environment

# gh conclusion words -> canonical Task.remote_ci_status token. Anything unmapped -> "unknown".
_FAIL = {
    "FAILURE",
    "FAILED",
    "ERROR",
    "CANCELLED",
    "TIMED_OUT",
    "ACTION_REQUIRED",
    "STARTUP_FAILURE",
    "FAILING",
}
_PENDING = {"PENDING", "IN_PROGRESS", "QUEUED", "WAITING", "EXPECTED", ""}
_PASS = {"SUCCESS", "PASS", "NEUTRAL", "SKIPPED"}

# Bound the gh call (parity with git.TIMEOUT_DEFAULT): a network-stalled gh must
# never hang the ship / CI-poll path. A timeout degrades to "unknown"/None, the
# same as every other gh failure here.
_TIMEOUT = 20.0


class RemoteCi:
    def __init__(self, repo_root: str | Path) -> None:
        self.repo_root = Path(repo_root)

    async def fetch(self, task: Task) -> tuple[str, list[CheckResult]]:
        """Return (canonical_status, per-check CheckResults). status is the normalized
        token pass/fail/pending/unknown; the ledger stores it verbatim in
        Task.remote_ci_status (the inbox derives ci_failed == status == "fail")."""
        if not task.remote_pr_url:
            return "unknown", []

        raw = await self._gh_json(["pr", "checks", task.remote_pr_url, "--json", "name,state,link"])
        rows = raw if isinstance(raw, list) else []
        checks = [
            CheckResult(
                name=str(r.get("name", "")),
                passed=str(r.get("state", "")).upper() in _PASS,
                detail=f"{r.get('state', '')} {r.get('link', '')}".strip(),
            )
            for r in rows
        ]
        return _overall(rows), checks

    async def pr_url(self, branch: str | None) -> str | None:
        """Read-only `gh pr view <branch> --json url` -> the PR URL, or None.

        Lever 7 prereq (DESIGN §lever-7): captured at mark_pushed so the inert CI
        tripwire (fetch) and the CFR metric go live. Best-effort: gh absent / no
        PR yet (human pushed before `gh pr create`) / bad JSON all degrade to None
        via the existing _gh_json guards — the caller must not block on this."""
        if not branch:
            return None
        raw = await self._gh_json(["pr", "view", branch, "--json", "url"])
        if isinstance(raw, dict):
            url = raw.get("url")
            return url if isinstance(url, str) and url else None
        return None

    async def _gh_json(self, args: list[str]) -> object:
        try:
            proc = await asyncio.create_subprocess_exec(
                "gh",
                *args,
                cwd=self.repo_root,
                env=build_sanitized_subprocess_environment(),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
        except FileNotFoundError:
            logger.debug("gh not on PATH; remote CI unknown")
            return None
        try:
            out, err = await asyncio.wait_for(proc.communicate(), timeout=_TIMEOUT)
        except TimeoutError:
            logger.debug("gh {} timed out after {}s; remote CI unknown", " ".join(args), _TIMEOUT)
            proc.kill()
            await proc.wait()
            return None
        if proc.returncode != 0:
            logger.debug("gh {} failed: {}", " ".join(args), err.decode(errors="replace"))
            return None
        try:
            return json.loads(out.decode(errors="replace"))
        except json.JSONDecodeError:
            return None


def _overall(rows: list) -> str:
    """Normalize gh conclusions to the canonical token. "fail" wins over "pending" wins
    over "pass"; an empty set or any unmapped word -> "unknown"."""
    if not rows:
        return "unknown"
    states = {str(r.get("state", "")).upper() for r in rows}
    if states & _FAIL:
        return "fail"
    if states & _PENDING:
        return "pending"
    if states <= _PASS:
        return "pass"
    return "unknown"
