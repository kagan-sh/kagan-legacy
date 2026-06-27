"""Doctor environment checks — minimal and dependency-free (skeleton).

The v2 rebuild can extend these (repo manifest, agent backends from the
launch-recipe set). For now we verify the host has what the harness needs.
"""

import json
import shutil
import subprocess
import sys
from dataclasses import dataclass

from kagan.core.config import find_repo_root, load_repo_config
from kagan.core.errors import ConfigurationError
from kagan.runtime_env import build_sanitized_subprocess_environment

# Agent CLIs the harness can drive as opaque subprocesses.
_AGENT_CLIS = ("claude", "codex", "kimi", "opencode")


@dataclass(slots=True)
class DoctorCheck:
    name: str
    status: str  # "pass" | "warn" | "fail"
    message: str
    fix_hint: str = ""
    verify_hint: str = ""
    category: str = "environment"


def run_doctor_checks() -> list[DoctorCheck]:
    checks: list[DoctorCheck] = []

    git = shutil.which("git")
    checks.append(
        DoctorCheck(
            name="git",
            status="pass" if git else "fail",
            message=f"found at {git}" if git else "git not found on PATH",
            fix_hint="" if git else "Install git: https://git-scm.com/downloads",
            verify_hint="git --version",
        )
    )

    py_ok = sys.version_info >= (3, 14)
    checks.append(
        DoctorCheck(
            name="python",
            status="pass" if py_ok else "fail",
            message=f"Python {sys.version_info.major}.{sys.version_info.minor}",
            fix_hint="" if py_ok else "Kagan requires Python 3.14+",
            verify_hint="python --version",
        )
    )

    found = [cli for cli in _AGENT_CLIS if shutil.which(cli)]
    checks.append(
        DoctorCheck(
            name="agent CLI",
            status="pass" if found else "warn",
            message=(
                "found: " + ", ".join(found)
                if found
                else "no agent CLI on PATH (claude/codex/kimi/opencode)"
            ),
            fix_hint="" if found else "Install at least one agent CLI to run tasks.",
            verify_hint="claude --version",
        )
    )

    gh = shutil.which("gh")
    checks.append(
        DoctorCheck(
            name="gh",
            status="pass" if gh else "warn",
            message=f"found at {gh}" if gh else "GitHub CLI not found (optional, for PR workflows)",
            fix_hint="" if gh else "Install gh: https://cli.github.com",
            verify_hint="gh auth status",
        )
    )

    checks.append(_check_repo_manifest())

    models = _check_manifest_models()
    if models is not None:
        checks.append(models)

    protection = _check_branch_protection()
    if protection is not None:
        checks.append(protection)

    return checks


def _base_branch() -> str:
    root = find_repo_root()
    if root is None:
        return "main"
    try:
        return load_repo_config(root).base_branch
    except ConfigurationError:
        return "main"


def _has_remote() -> bool:
    try:
        out = subprocess.run(
            ["git", "remote"],
            capture_output=True,
            text=True,
            env=build_sanitized_subprocess_environment(),
            timeout=5,
        )
    except OSError, subprocess.SubprocessError:
        return False
    return out.returncode == 0 and bool(out.stdout.strip())


def _check_branch_protection() -> DoctorCheck | None:
    """Probe whether the base branch is branch-protected on the remote (governance
    level 4 — the wall the never-reach-main story leans on but kagan can't own). Only
    a remote-side rule actually stops a push to main; kagan only scrubs creds locally.

    Returns None (no check shown) when there's nothing to probe — gh absent (the
    separate gh check already warns) or no git remote (a local-only repo). Otherwise
    WARN-not-FAIL: kagan can't fix the remote, only make the gap visible."""
    if not shutil.which("gh") or not _has_remote():
        return None

    branch = _base_branch()
    name = "branch protection"
    fix = (
        f"Protect {branch} on the remote (require pull-request reviews) so a push can't "
        "reach it unreviewed — kagan gates locally but cannot enforce the remote."
    )
    verify = f"gh api repos/{{owner}}/{{repo}}/branches/{branch}/protection"
    try:
        proc = subprocess.run(
            ["gh", "api", f"repos/{{owner}}/{{repo}}/branches/{branch}/protection"],
            capture_output=True,
            text=True,
            env=build_sanitized_subprocess_environment(),
            timeout=8,
        )
    except OSError, subprocess.SubprocessError:
        return DoctorCheck(
            name=name,
            status="warn",
            message="could not run gh to verify branch protection",
            fix_hint=fix,
            verify_hint=verify,
            category="configuration",
        )

    if proc.returncode == 0:
        try:
            requires_review = "required_pull_request_reviews" in json.loads(proc.stdout)
        except json.JSONDecodeError, ValueError:
            requires_review = False
        if requires_review:
            return DoctorCheck(
                name=name,
                status="pass",
                message=f"{branch} requires pull-request reviews on the remote",
                category="configuration",
            )
        return DoctorCheck(
            name=name,
            status="warn",
            message=f"{branch} is protected but does not require reviews",
            fix_hint=fix,
            verify_hint=verify,
            category="configuration",
        )

    err = (proc.stderr or proc.stdout).lower()
    if "not protected" in err:
        message = f"{branch} is NOT branch-protected — a push can reach it unreviewed"
    elif any(s in err for s in ("auth", "not logged", "gh auth login")):
        message = "gh is not authenticated — cannot verify branch protection"
    else:
        message = "could not verify branch protection on the remote"
    return DoctorCheck(
        name=name,
        status="warn",
        message=message,
        fix_hint=fix,
        verify_hint=verify,
        category="configuration",
    )


def _check_manifest_models() -> DoctorCheck | None:
    """Warn when a CLI configured with builder/reviewer models in `agents.<cli>` isn't on
    PATH — those tasks would silently fall back to the CLI default. The model id itself is
    passed verbatim to the CLI, so kagan does not (and cannot) validate it; that is the
    CLI's own job at spawn."""
    repo_root = find_repo_root()
    if repo_root is None:
        return None
    try:
        cfg = load_repo_config(repo_root)
    except ConfigurationError:
        return None

    missing: list[str] = []
    for cli in _AGENT_CLIS:
        models = cfg.agents.for_cli(cli)
        if (models.builder or models.reviewer) and not shutil.which(cli):
            missing.append(cli)
    if not missing:
        return None
    return DoctorCheck(
        name="manifest models",
        status="warn",
        message=(
            f"models configured for {', '.join(missing)} but that CLI isn't on PATH — "
            "those tasks use the CLI default"
        ),
        fix_hint="Install the CLI, or move the models under an agent CLI on your PATH.",
        category="configuration",
    )


def _check_repo_manifest() -> DoctorCheck:
    repo_root = find_repo_root()
    if repo_root is None:
        return DoctorCheck(
            name="repo manifest",
            status="fail",
            message="no .kagan/repo.yaml found in this directory or its ancestors",
            fix_hint="Run `kagan init` to create .kagan/repo.yaml and a starter review rubric.",
            category="configuration",
        )
    try:
        cfg = load_repo_config(repo_root)
    except ConfigurationError as exc:
        return DoctorCheck(
            name="repo manifest",
            status="fail",
            message=exc.detail,
            fix_hint=exc.hint,
            category="configuration",
        )
    return DoctorCheck(
        name="repo manifest",
        status="pass",
        message=(
            f"valid manifest ({len(cfg.services)} service(s), "
            f"{len(cfg.checks)} check(s), {len(cfg.pinned)} pinned)"
        ),
        category="configuration",
    )


def doctor_has_failures(checks: list[DoctorCheck]) -> bool:
    return any(check.status == "fail" for check in checks)


__all__ = ["DoctorCheck", "doctor_has_failures", "run_doctor_checks"]
