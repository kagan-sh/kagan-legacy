"""Async git worktree operations for kagan.core — raises WorktreeError."""

import asyncio
import subprocess
from pathlib import Path
from typing import TypedDict

from loguru import logger

from kagan.core.errors import WorktreeError
from kagan.core.paths import is_run_artifact
from kagan.runtime_env import build_sanitized_subprocess_environment


class WorktreeEntry(TypedDict):
    path: str
    branch: str | None


TIMEOUT_DEFAULT = 30.0
TIMEOUT_FETCH = 120.0
TIMEOUT_CLONE = 300.0

# R1 ruin-guard: irreversible / work-destroying / remote-mutating verbs that kagan
# must NEVER run — enforced HERE, at the one chokepoint both the private _run_git
# (mutating internals: init/add/commit/worktree) and the public run_git
# (read-only allowlist) funnel through. The public allowlist is the stricter
# surface gate; this denylist is the structural floor so a future careless
# _run_git("push"/"reset", ...) raises instead of externalizing ruin onto the
# user's repo (rule 8: enforce, don't instruct). This guards KAGAN's own git only;
# the AGENT's git is governed separately by the spawn-env scrub (agent._agent_env).
_DENIED_GIT: frozenset[str] = frozenset(
    {"push", "merge", "rebase", "reset", "clean", "update-ref", "fetch", "pull", "remote"}
)


def _git_subcommand(args: tuple[str, ...]) -> str | None:
    """The git subcommand, skipping global flags and the value of `-c`/`-C`.

    `_run_git("-c", "commit.gpgsign=false", "commit", ...)` must resolve to "commit",
    not the `-c` value token — a naive first-non-flag scan would mis-read it."""
    it = iter(args)
    for a in it:
        if a in ("-c", "-C"):
            next(it, None)  # the flag's value is not the subcommand
            continue
        if a.startswith("-"):
            continue
        return a
    return None


async def _spawn_git(args: tuple[str, ...], cwd: Path, timeout: float) -> tuple[int, str, str]:
    """Spawn git command and return (rc, stdout, stderr). Raises TimeoutError on timeout."""
    sub = _git_subcommand(args)
    if sub in _DENIED_GIT:
        raise WorktreeError(
            f"git {sub!r} is denied (irreversible/destructive — kagan never pushes, "
            f"merges, or rewrites work; git.py R1 ruin-guard): {' '.join(args)}"
        )
    logger.debug("git {}", " ".join(args))
    proc = await asyncio.create_subprocess_exec(
        "git",
        *args,
        cwd=cwd,
        env=build_sanitized_subprocess_environment(),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(proc.communicate(), timeout=timeout)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        raise
    stdout = stdout_bytes.decode(errors="replace").strip()
    stderr = stderr_bytes.decode(errors="replace").strip()
    rc = proc.returncode if proc.returncode is not None else 1
    return rc, stdout, stderr


async def _run_git(
    *args: str,
    cwd: Path,
    check: bool = True,
    timeout: float = TIMEOUT_DEFAULT,
) -> tuple[str, str]:
    try:
        rc, stdout, stderr = await _spawn_git(args, cwd, timeout)
    except TimeoutError:
        cmd = " ".join(args)
        raise WorktreeError(f"git command timed out after {timeout}s: git {cmd}") from None
    if check and rc != 0:
        cmd = " ".join(args)
        logger.warning("git {} failed (rc={})", cmd, rc)
        detail = stderr or stdout or "unknown git error"
        raise WorktreeError(f"git {cmd} failed (rc={rc}): {detail}")
    return stdout, stderr


async def _run_git_result(
    *args: str,
    cwd: Path,
    timeout: float = TIMEOUT_DEFAULT,
) -> tuple[int, str, str]:
    try:
        rc, stdout, stderr = await _spawn_git(args, cwd, timeout)
    except TimeoutError:
        cmd = " ".join(args)
        logger.warning("git {} timed out after {}s", cmd, timeout)
        return 1, "", f"git command timed out after {timeout}s: git {cmd}"
    if rc != 0:
        cmd = " ".join(args)
        logger.warning("git {} failed (rc={})", cmd, rc)
    return rc, stdout, stderr


def repo_root(start: Path) -> Path | None:
    """Toplevel of the git repo containing `start`, or None outside one.

    Sync so the CLI entrypoint can scope the ledger before the event loop starts.
    """
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            env=build_sanitized_subprocess_environment(),
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return Path(out.stdout.strip()).resolve()


def _git_config_get(start: Path, key: str) -> str | None:
    try:
        out = subprocess.run(
            ["git", "-C", str(start), "config", "--get", key],
            capture_output=True,
            text=True,
            env=build_sanitized_subprocess_environment(),
        )
    except OSError:
        return None
    value = out.stdout.strip()
    return value if out.returncode == 0 and value else None


def user_identity(start: Path) -> str | None:
    """The repo's git identity as "Name <email>", or None when unset.

    Read-only config inspection — not in run_git's allowlist by design, so this
    uses the same sync subprocess pattern as repo_root. The email is the distinct
    key the multi-approver bar (lever 6) counts; cross-team distinctness needs two
    configured identities (see DESIGN §2 "user's own git identity").
    """
    email = _git_config_get(start, "user.email")
    if email is None:
        return None
    name = _git_config_get(start, "user.name")
    return f"{name} <{email}>" if name else email


async def validate_ref_name(name: str) -> bool:
    """Validate git reference name for safety (injection, traversal, reflog attacks)."""
    if not name:
        return False
    if name.startswith("-"):
        return False
    if ".." in name:
        return False
    if "@{" in name:
        return False
    # git check-ref-format with check=False for non-zero exit on invalid refs.
    try:
        await _run_git("check-ref-format", "--branch", name, cwd=Path.cwd(), check=True)
        return True
    except WorktreeError:
        return False


async def worktree_add(
    repo_path: str | Path,
    worktree_path: str | Path,
    *,
    branch: str,
    base: str = "main",
) -> None:
    """Create a new git worktree at worktree_path on a new branch from base."""
    # Validate branch and base to prevent option injection.
    if not await validate_ref_name(branch):
        raise WorktreeError(
            f"Invalid branch name '{branch}'. "
            "Branch names must be valid git references and cannot start with '-', "
            "contain '..', or contain '@{'"
        )
    if not await validate_ref_name(base):
        raise WorktreeError(
            f"Invalid base reference '{base}'. "
            "Base references must be valid git references and cannot start with '-', "
            "contain '..', or contain '@{'"
        )

    repo = Path(repo_path)
    wt = Path(worktree_path)
    wt.parent.mkdir(parents=True, exist_ok=True)

    # For fresh repos: create empty initial commit if base branch missing.
    base_exists = await _has_local_branch(repo, base)
    if not base_exists:
        has_commits, _ = await _run_git("rev-parse", "--verify", "HEAD", cwd=repo, check=False)
        if not has_commits:  # Seed empty commit for fresh repos.
            await _run_git(
                "commit",
                "--allow-empty",
                "-m",
                "chore: initialize repository",
                cwd=repo,
            )

    await _run_git("worktree", "add", "-b", branch, str(wt), base, cwd=repo)


async def is_git_repo(repo_path: str | Path) -> bool:
    repo = Path(repo_path)
    stdout, _ = await _run_git("rev-parse", "--git-dir", cwd=repo, check=False)
    return bool(stdout)


async def init_repo(
    repo_path: str | Path,
    *,
    initial_branch: str = "main",
    create_initial_commit: bool = True,
) -> None:
    repo = Path(repo_path)
    repo.mkdir(parents=True, exist_ok=True)
    if await is_git_repo(repo):
        return

    await _run_git("init", "-b", initial_branch, cwd=repo)
    if not create_initial_commit:
        return

    head, _ = await _run_git("rev-parse", "--verify", "--quiet", "HEAD", cwd=repo, check=False)
    if head:
        return

    await _run_git(
        "commit",
        "--allow-empty",
        "-m",
        "chore: initial commit",
        cwd=repo,
    )


async def worktree_remove(repo_path: str | Path, worktree_path: str | Path) -> None:
    """Remove a git worktree and prune stale refs; safe when path does not exist."""
    wt = Path(worktree_path)
    if not wt.exists():
        return
    repo = Path(repo_path)
    await _run_git("worktree", "remove", str(wt), "--force", cwd=repo, check=False)
    await _run_git("worktree", "prune", cwd=repo, check=False)


async def worktree_list(repo_path: str | Path) -> list[WorktreeEntry]:
    """List all worktrees; returns dicts with 'path' and 'branch' keys."""
    repo = Path(repo_path)
    stdout, _ = await _run_git("worktree", "list", "--porcelain", cwd=repo)
    worktrees: list[WorktreeEntry] = []
    current: WorktreeEntry | None = None
    for line in stdout.splitlines():
        if line.startswith("worktree "):
            if current is not None:
                worktrees.append(current)
            current = {"path": line[9:].strip(), "branch": None}
        elif line.startswith("branch ") and current is not None:
            ref = line[7:].strip()
            # Strip refs/heads/ prefix
            current["branch"] = ref.removeprefix("refs/heads/")
        elif line == "" and current is not None:
            worktrees.append(current)
            current = None
    if current is not None:
        worktrees.append(current)
    return worktrees


async def diff(
    worktree_path: str | Path,
    *,
    base_branch: str,
) -> str:
    """Return unified diff between worktree HEAD and base_branch."""
    wt = Path(worktree_path)
    base_ref = await _resolve_base_ref(wt, base_branch)
    stdout, _ = await _run_git("diff", f"{base_ref}..HEAD", cwd=wt)
    return stdout


async def resolve_base_ref(cwd: Path, base_branch: str) -> str:
    """Resolve the git ref used for ``git diff base..HEAD`` in a worktree."""
    return await _resolve_base_ref(cwd, base_branch)


async def _resolve_base_ref(cwd: Path, base_branch: str) -> str:
    # Prefer the local base when it is ahead of origin, else origin, else local.
    local_exists = await _has_local_branch(cwd, base_branch)
    remote_exists = await _has_remote_branch(cwd, base_branch)
    remote_ref = f"origin/{base_branch}"
    if local_exists and remote_exists:
        if await _is_local_ahead_of_origin(cwd, base_branch):
            return base_branch
        return remote_ref
    if remote_exists:
        return remote_ref
    return base_branch


async def _has_local_branch(repo: Path, branch: str) -> bool:
    stdout, _ = await _run_git(
        "rev-parse",
        "--verify",
        "--quiet",
        f"refs/heads/{branch}",
        cwd=repo,
        check=False,
    )
    return bool(stdout)


async def _has_remote_branch(repo: Path, branch: str) -> bool:
    stdout, _ = await _run_git(
        "rev-parse",
        "--verify",
        "--quiet",
        f"refs/remotes/origin/{branch}",
        cwd=repo,
        check=False,
    )
    return bool(stdout)


async def remote_has_branch(repo: Path, branch: str) -> bool | None:
    """Tri-state read-only check that ``branch`` exists on origin via ``git ls-remote
    --heads`` — used by the ship screen to verify the human actually pushed before
    flipping to PR_OPEN. ``True`` present, ``False`` absent, ``None`` unverifiable
    (no remote / network down / git error — the caller softens rather than refuses)."""
    rc, stdout, _ = await _run_git_result("ls-remote", "--heads", "origin", branch, cwd=repo)
    if rc != 0:
        return None
    return bool(stdout.strip())


async def _is_local_ahead_of_origin(repo: Path, branch: str) -> bool:
    stdout, _ = await _run_git(
        "rev-list",
        "--left-right",
        "--count",
        f"origin/{branch}...{branch}",
        cwd=repo,
        check=False,
    )
    parts = stdout.split()
    if len(parts) != 2:
        return False
    try:
        local_only = int(parts[1])
    except ValueError:
        return False
    return local_only > 0


def parse_diff_changed_files(diff_text: str) -> list[str]:
    files: list[str] = []
    for line in diff_text.splitlines():
        if not line.startswith("diff --git a/"):
            continue
        parts = line.split(" b/", maxsplit=1)
        if len(parts) != 2:
            continue
        files.append(parts[1].strip())

    return list(dict.fromkeys(files))


async def has_pending_changes(worktree_path: str | Path) -> bool:
    wt = Path(worktree_path)
    stdout, _ = await _run_git("status", "--porcelain", cwd=wt, check=False)
    for line in stdout.splitlines():
        if not line.strip():
            continue
        file_path = line[3:].strip()
        # kagan's own run-artifacts (.mcp.json, .kagan/ask, prompt, agent.log) are
        # not meaningful work; only a non-artifact change counts as pending. One
        # definition shared with the gate/harvest paths (core/paths).
        if not is_run_artifact(file_path):
            return True
    return False


async def commit_all(
    worktree_path: str | Path,
    message: str,
) -> None:
    wt = Path(worktree_path)
    await _run_git("add", "-A", cwd=wt)
    await _run_git(
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        message,
        cwd=wt,
    )
    logger.info("Auto-committed in {}: {}", wt, message)


async def base_has_moved(
    worktree_path: str | Path,
    base_branch: str,
) -> tuple[bool, int]:
    """Return (moved, commits_behind) for HEAD relative to base_branch (P5, read-only)."""
    wt = Path(worktree_path)
    base_ref = await _resolve_base_ref(wt, base_branch)
    # _run_git_result never raises on a non-zero rev-list; "behind" count is data, not error.
    rc, stdout, _ = await _run_git_result("rev-list", "--count", f"HEAD..{base_ref}", cwd=wt)
    if rc != 0:
        return False, 0
    try:
        behind = int(stdout.strip())
    except ValueError:
        return False, 0
    return behind > 0, behind


# TUI-SHIP-05: the harness never pushes, force-pushes, or merges — the public
# git entry only permits read-only inspection subcommands, so those operations
# are structurally rejected, not merely never called. Mutating internals (init,
# add, commit, worktree) go through the private _run_git, not this allowlist.
_RUN_GIT_ALLOWED: frozenset[str] = frozenset(
    {
        "rev-parse",
        "diff",
        "status",
        "log",
        "show",
        "rev-list",
        "ls-files",
        "cat-file",
        "symbolic-ref",
        "describe",
    }
)


async def run_git(args: list[str], *, cwd: Path, check: bool = True) -> str:
    """Run a read-only git command; return stdout.

    Only inspection subcommands in ``_RUN_GIT_ALLOWED`` are permitted (TUI-SHIP-05);
    push/force-push/merge and any other mutation raise WorktreeError. Raises
    WorktreeError if check=True and the command fails.
    """
    subcommand = next((a for a in args if not a.startswith("-")), None)
    if subcommand not in _RUN_GIT_ALLOWED:
        raise WorktreeError(
            f"git {subcommand!r} is not permitted via run_git "
            f"(read-only allowlist, TUI-SHIP-05): {' '.join(args)}"
        )
    stdout, _ = await _run_git(*args, cwd=cwd, check=check)
    return stdout


__all__ = [
    "WorktreeEntry",
    "base_has_moved",
    "commit_all",
    "diff",
    "has_pending_changes",
    "init_repo",
    "is_git_repo",
    "parse_diff_changed_files",
    "remote_has_branch",
    "repo_root",
    "resolve_base_ref",
    "run_git",
    "user_identity",
    "validate_ref_name",
    "worktree_add",
    "worktree_list",
    "worktree_remove",
]
