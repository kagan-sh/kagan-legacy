"""Review gate engine: the universal checks the local mirror does not run.

Build/types/tests are the mirror's job (RepoConfig.checks, run by the local
mirror). This adds the diff heuristics (in-scope, minimal, secrets, shared env)
and a mutation probe that proves the test command can actually fail — all
returned as canonical Findings (TUI-GATE-02). The review rubric is NOT echoed
here as findings (F15): it is the lens the adversarial validator reviews through
(fed into the validator prompt, lever 2), not a list of open questions.
"""

import asyncio
import re
from pathlib import Path

from kagan.core import git
from kagan.core.config import RepoConfig  # noqa: TC001 — no `from __future__ import annotations`
from kagan.core.models import Finding, Task
from kagan.core.paths import is_run_artifact, matches_scope
from kagan.runtime_env import build_sanitized_subprocess_environment

# Files whose presence in a diff is always suspicious (TUI-GATE-02 secrets).
# .env/.envrc must end the basename (so .env.example, a safe template, is not
# flagged); .pem matches any real key filename, not only a bare ".pem".
_SECRET_RE = re.compile(
    r"(^|/)(\.env|\.envrc)($|/)|(^|/)(secrets?\.|\.ssh/|\.aws/|id_rsa)|[^/]\.pem$"
)


def _fid(prefix: str, n: int) -> str:
    return f"{prefix}-{n:03d}"


class GateEngine:
    MAX_FILES = 20  # ponytail: flat minimal-diff threshold; raise if real diffs trip it

    def __init__(self, *, repo_root: Path, config: RepoConfig | None = None) -> None:
        self.repo_root = Path(repo_root)
        self.config = config

    async def run(self, task: Task) -> list[Finding]:
        if task.worktree_path is None:
            return []
        wt = Path(task.worktree_path)
        files = await self._changed_files(wt, task.base_branch)

        findings: list[Finding] = []
        findings += self._scope(task, files)
        findings += self._secrets(files)
        findings += self._shared_env(files)
        findings += self._minimal(files)
        findings += await self._mutation_probe(wt)
        findings += await self._security(task, wt)
        return findings

    async def _changed_files(self, wt: Path, base_branch: str) -> list[str]:
        # Committed diff (base..HEAD) + uncommitted untracked files (P5). Untracked
        # via `git ls-files --others`: a clean tree exits 0 with empty output, a
        # dirty one exits 0 with names — never check=True (no exit-1 = error here).
        diff_text = await git.diff(wt, base_branch=base_branch)
        tracked = git.parse_diff_changed_files(diff_text)
        untracked = await git.run_git(
            ["ls-files", "--others", "--exclude-standard"], cwd=wt, check=False
        )
        extra = [ln.strip() for ln in untracked.splitlines() if ln.strip()]
        files = list(dict.fromkeys(tracked + extra))
        # Drop kagan's own run-artifacts (.mcp.json, .kagan/ask, .kagan/prompt*,
        # .kagan/agent.log) — kagan wrote them, not the agent, so they must not trip
        # scope/minimal/secrets. Same RUN_ARTIFACTS set the harvest path strips, so
        # both converge on one definition (core/paths.is_run_artifact).
        return [f for f in files if not is_run_artifact(f)]

    def _scope(self, task: Task, files: list[str]) -> list[Finding]:
        scope = [s for s in task.scope if s]
        if not scope:
            return []
        # Scope is path globs (src/**) OR bare prefixes (src/) — the one canonical
        # matcher handles both, the same matcher drift detection uses, so a scope
        # behaves identically in the gate and in drift.
        out = [f for f in files if not matches_scope(f, scope)]
        return [
            Finding(
                id=_fid("scope", i),
                severity="blocking",
                location=f,
                message="edit outside declared scope",
                source="machine",
            )
            for i, f in enumerate(out, start=1)
        ]

    def _secrets(self, files: list[str]) -> list[Finding]:
        hits = [f for f in files if _SECRET_RE.search(f)]
        return [
            Finding(
                id=_fid("secret", i),
                severity="blocking",
                location=f,
                message="secret or credential file modified",
                source="security",
            )
            for i, f in enumerate(hits, start=1)
        ]

    def _shared_env(self, files: list[str]) -> list[Finding]:
        pinned = (self.config.pinned if self.config else None) or []
        hits = [
            f for f in files if any(f == p or f.startswith(p.rstrip("/") + "/") for p in pinned)
        ]
        return [
            Finding(
                id=_fid("env", i),
                severity="blocking",
                location=f,
                message="pinned shared-environment path modified",
                source="security",
            )
            for i, f in enumerate(hits, start=1)
        ]

    def _minimal(self, files: list[str]) -> list[Finding]:
        if len(files) <= self.MAX_FILES:
            return []
        return [
            Finding(
                id="minimal-001",
                severity="question",
                location=".",
                message=f"diff is not minimal: {len(files)} files changed",
            )
        ]

    async def _mutation_probe(self, wt: Path) -> list[Finding]:
        """Inject a failing test and confirm the test command reports it.

        A test command that still exits 0 with a guaranteed-failing test present
        is a tautology, not a real gate (TUI-GATE-02 "tests can actually fail").
        """
        command = self._declared_test_command()
        if command is None:
            return [
                Finding(
                    id="mutation-001",
                    severity="question",
                    location=".",
                    message="mutation probe skipped: no test check declared",
                )
            ]
        # The probe only works if the runner collects an injected pytest file.
        # Non-python suites are already declared machine checks; don't emit a false
        # "no test check declared" advisory for repos whose runner cannot collect
        # this Python probe.
        if not re.search(r"\b(pytest|py\.test)\b", command):
            return []
        probe = wt / "_kagan_mutation_probe_test.py"
        probe.write_text("def test_kagan_mutation_probe():\n    assert False\n", encoding="utf-8")
        try:
            rc = await _run(command, wt)
        finally:
            probe.unlink(missing_ok=True)
        if rc == 0:
            return [
                Finding(
                    id="mutation-001",
                    severity="blocking",
                    location=".",
                    message="mutation probe: test command passed with a failing test "
                    "present — tests cannot actually fail",
                )
            ]
        return []

    def _declared_test_command(self) -> str | None:
        if not self.config:
            return None
        for name, command in self.config.checks.items():
            text = f"{name} {command}".lower()
            if re.search(r"\btests?\b", text) or any(
                hint in text
                for hint in (
                    "pytest",
                    "py.test",
                    "cargo test",
                    "go test",
                    "npm test",
                    "pnpm test",
                    "yarn test",
                    "vitest",
                    "jest",
                    "swift test",
                )
            ):
                return command
        return None

    async def _security(self, task: Task, wt: Path) -> list[Finding]:
        """Lever 3: run the repo's SAST command in the worktree. A non-zero exit is
        a finding — blocking on high-risk scope, advisory ("question") elsewhere
        (DESIGN L168). No command declared = an explicit "skipped" finding, never a
        silent pass (Rule 12: absence must be visible)."""
        command = self.config.security if self.config else None
        if not command:
            return [
                Finding(
                    id="security-001",
                    severity="question",
                    location=".",
                    message="security scan skipped: no security command declared",
                    source="security",
                )
            ]
        rc, tail = await _run_capture(command, wt)
        if rc == 0:
            return []
        severity = "blocking" if task.risk == "high" else "question"
        return [
            Finding(
                id="security-001",
                severity=severity,
                location=".",
                message=f"security scan reported issues (rc={rc})\n{tail}".strip(),
                source="security",
            )
        ]


async def _run(command: str, cwd: Path) -> int:
    # P6: clean env (the repo's sanitizer), not os.environ. Output captured and
    # dropped — only the exit code matters for the probe; the mirror owns log capture.
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        env=build_sanitized_subprocess_environment(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return proc.returncode or 0


_SECURITY_TIMEOUT = 300.0
_SECURITY_OUTPUT_TAIL = 2000


async def _run_capture(command: str, cwd: Path) -> tuple[int, str]:
    # The security finding quotes the SAST output, so unlike the probe this keeps
    # the tail. A bounded timeout so a hung scanner can't wedge the gate forever.
    proc = await asyncio.create_subprocess_shell(
        command,
        cwd=cwd,
        env=build_sanitized_subprocess_environment(),
        stdin=asyncio.subprocess.DEVNULL,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.STDOUT,
    )
    try:
        out, _ = await asyncio.wait_for(proc.communicate(), timeout=_SECURITY_TIMEOUT)
        rc = proc.returncode if proc.returncode is not None else 1
        tail = out.decode(errors="replace")[-_SECURITY_OUTPUT_TAIL:]
    except TimeoutError:
        proc.kill()
        await proc.wait()
        rc, tail = 1, f"security scan timed out after {_SECURITY_TIMEOUT}s"
    return rc, tail
