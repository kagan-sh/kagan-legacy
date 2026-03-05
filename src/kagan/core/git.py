"""Async git worktree operations for kagan.core — raises WorktreeError / MergeConflictError."""

import asyncio
import os
import re
from pathlib import Path

from loguru import logger

from kagan.core.errors import MergeConflictError, WorktreeError
from kagan.runtime_env import build_sanitized_subprocess_environment

# Default git identity for Kagan agent commits.
KAGAN_AGENT_NAME = "Kagan Agent"
KAGAN_AGENT_EMAIL = "info@kagan.sh"

# Timeout constants for git operations (in seconds)
TIMEOUT_DEFAULT = 30.0  # Regular operations
TIMEOUT_FETCH = 120.0  # Fetch/pull operations
TIMEOUT_CLONE = 300.0  # Clone operations


async def _run_git(
    *args: str,
    cwd: Path,
    check: bool = True,
    timeout: float = TIMEOUT_DEFAULT,
) -> tuple[str, str]:
    """Run a git command, returning (stdout, stderr). Raises WorktreeError on failure."""
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
        cmd = " ".join(args)
        raise WorktreeError(f"git command timed out after {timeout}s: git {cmd}") from None
    stdout = stdout_bytes.decode(errors="replace").strip()
    stderr = stderr_bytes.decode(errors="replace").strip()
    if check and proc.returncode != 0:
        cmd = " ".join(args)
        logger.warning("git {} failed (rc={})", cmd, proc.returncode)
        detail = stderr or stdout or "unknown git error"
        raise WorktreeError(f"git {cmd} failed (rc={proc.returncode}): {detail}")
    return stdout, stderr


async def _run_git_result(
    *args: str,
    cwd: Path,
    timeout: float = TIMEOUT_DEFAULT,
) -> tuple[int, str, str]:
    """Run a git command, returning (returncode, stdout, stderr). Never raises."""
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
        cmd = " ".join(args)
        logger.warning("git {} timed out after {}s", cmd, timeout)
        return 1, "", f"git command timed out after {timeout}s: git {cmd}"
    stdout = stdout_bytes.decode(errors="replace").strip()
    stderr = stderr_bytes.decode(errors="replace").strip()
    rc = proc.returncode if proc.returncode is not None else 1
    if rc != 0:
        cmd = " ".join(args)
        logger.warning("git {} failed (rc={})", cmd, rc)
    return rc, stdout, stderr


async def worktree_add(
    repo_path: str | Path,
    worktree_path: str | Path,
    *,
    branch: str,
    base: str = "main",
) -> None:
    """Create a new git worktree at worktree_path on a new branch from base."""
    repo = Path(repo_path)
    wt = Path(worktree_path)
    wt.parent.mkdir(parents=True, exist_ok=True)
    await _run_git("worktree", "add", "-b", branch, str(wt), base, cwd=repo)


async def is_git_repo(repo_path: str | Path) -> bool:
    repo = Path(repo_path)
    stdout, _ = await _run_git("rev-parse", "--git-dir", cwd=repo, check=False)
    return bool(stdout)


async def current_branch(repo_path: str | Path) -> str | None:
    repo = Path(repo_path)
    stdout, _ = await _run_git("symbolic-ref", "--quiet", "--short", "HEAD", cwd=repo, check=False)
    return stdout or None


async def get_system_git_identity() -> tuple[str, str]:
    """Get the system-configured git user identity.

    Checks environment variables first (GIT_AUTHOR_NAME, GIT_COMMITTER_NAME,
    GIT_AUTHOR_EMAIL, GIT_COMMITTER_EMAIL), then falls back to git config.
    Returns (name, email) tuple with Kagan Agent defaults as final fallback.
    """
    env_name = os.environ.get("GIT_AUTHOR_NAME") or os.environ.get("GIT_COMMITTER_NAME")
    env_email = os.environ.get("GIT_AUTHOR_EMAIL") or os.environ.get("GIT_COMMITTER_EMAIL")

    name = env_name or ""
    email = env_email or ""

    try:
        if not name:
            stdout, _ = await _run_git("config", "--get", "user.name", cwd=Path.cwd(), check=False)
            name = stdout.strip()
        if not email:
            stdout, _ = await _run_git("config", "--get", "user.email", cwd=Path.cwd(), check=False)
            email = stdout.strip()
    except WorktreeError:
        pass

    return name or KAGAN_AGENT_NAME, email or KAGAN_AGENT_EMAIL


async def get_git_user_identity(settings: dict[str, str]) -> tuple[str, str]:
    """Resolve git identity based on settings.

    Three modes controlled by ``git_user_mode`` setting:
    - ``kagan_agent`` (default): Uses Kagan Agent <info@kagan.sh>.
    - ``system_default``: Uses the system git config / env vars.
    - ``custom``: Uses ``git_user_name`` / ``git_user_email`` from settings.
    """
    mode = settings.get("git_user_mode", "kagan_agent")

    if mode == "system_default":
        return await get_system_git_identity()

    if mode == "custom":
        name = settings.get("git_user_name", "").strip()
        email = settings.get("git_user_email", "").strip()
        return name or KAGAN_AGENT_NAME, email or KAGAN_AGENT_EMAIL

    # default: kagan_agent
    return KAGAN_AGENT_NAME, KAGAN_AGENT_EMAIL


async def init_repo(
    repo_path: str | Path,
    *,
    initial_branch: str = "main",
    create_initial_commit: bool = True,
    user_name: str = KAGAN_AGENT_NAME,
    user_email: str = KAGAN_AGENT_EMAIL,
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
        "-c",
        f"user.name={user_name}",
        "-c",
        f"user.email={user_email}",
        "commit",
        "--allow-empty",
        "-m",
        "chore: initial commit",
        cwd=repo,
    )


async def resolve_worktree_base(
    repo_path: str | Path,
    *,
    preferred_branch: str,
    strategy: str,
    refresh_remote: bool = False,
) -> str:
    repo = Path(repo_path)

    # Fetch from origin before resolving (kagan2 sync-on-start pattern).
    # Skipped for "local" strategy which never consults the remote.
    if refresh_remote and strategy != "local" and await _has_remote(repo, "origin"):
        await _run_git(
            "fetch", "origin", preferred_branch, cwd=repo, check=False, timeout=TIMEOUT_FETCH
        )

    local_exists = await _has_local_branch(repo, preferred_branch)
    remote_exists = await _has_remote_branch(repo, preferred_branch)
    remote_ref = f"origin/{preferred_branch}"

    if strategy == "remote":
        if remote_exists:
            return remote_ref
        if local_exists:
            return preferred_branch
    elif strategy == "local":
        if local_exists:
            return preferred_branch
        if remote_exists:
            return remote_ref
    else:
        if local_exists and remote_exists:
            if await _is_local_ahead_of_origin(repo, preferred_branch):
                return preferred_branch
            return remote_ref
        if local_exists:
            return preferred_branch
        if remote_exists:
            return remote_ref

    branch = await current_branch(repo)
    return branch or preferred_branch


async def worktree_remove(repo_path: str | Path, worktree_path: str | Path) -> None:
    """Remove a git worktree and prune stale refs; safe when path does not exist."""
    wt = Path(worktree_path)
    if not wt.exists():
        return
    repo = Path(repo_path)
    await _run_git("worktree", "remove", str(wt), "--force", cwd=repo, check=False)
    await _run_git("worktree", "prune", cwd=repo, check=False)


async def worktree_list(repo_path: str | Path) -> list[dict]:
    """List all worktrees; returns dicts with 'path' and 'branch' keys."""
    repo = Path(repo_path)
    stdout, _ = await _run_git("worktree", "list", "--porcelain", cwd=repo)
    worktrees: list[dict] = []
    current: dict = {}
    for line in stdout.splitlines():
        if line.startswith("worktree "):
            if current:
                worktrees.append(current)
            current = {"path": line[9:].strip(), "branch": None}
        elif line.startswith("branch "):
            ref = line[7:].strip()
            # Strip refs/heads/ prefix for readability
            current["branch"] = ref.removeprefix("refs/heads/")
        elif line == "" and current:
            worktrees.append(current)
            current = {}
    if current:
        worktrees.append(current)
    return worktrees


async def diff(
    worktree_path: str | Path,
    *,
    base_branch: str,
    strategy: str = "local_if_ahead",
) -> str:
    """Return the unified diff between worktree HEAD and base_branch."""
    wt = Path(worktree_path)
    base_ref = await _resolve_base_ref(wt, base_branch, strategy=strategy)
    stdout, _ = await _run_git("diff", f"{base_ref}..HEAD", cwd=wt)
    return stdout


async def diff_stats(
    worktree_path: str | Path,
    *,
    base_branch: str,
    strategy: str = "local_if_ahead",
) -> dict:
    """Return diff statistics: {'files', 'insertions', 'deletions'}."""
    wt = Path(worktree_path)
    base_ref = await _resolve_base_ref(wt, base_branch, strategy=strategy)
    stdout, _ = await _run_git("diff", "--stat", f"{base_ref}..HEAD", cwd=wt)
    if not stdout:
        return {"files": 0, "insertions": 0, "deletions": 0}
    summary = stdout.splitlines()[-1]
    return {
        "files": _extract_number(summary, "file"),
        "insertions": _extract_number(summary, "insertion"),
        "deletions": _extract_number(summary, "deletion"),
    }


async def show_commit_diff(repo_path: str | Path, *, commit_sha: str) -> str:
    repo = Path(repo_path)
    stdout, _ = await _run_git(
        "show",
        "--format=",
        "--patch",
        commit_sha,
        cwd=repo,
    )
    return stdout


async def merge(
    repo_path: str | Path,
    *,
    branch: str,
    target_branch: str,
    commit_message: str,
    user_name: str = KAGAN_AGENT_NAME,
    user_email: str = KAGAN_AGENT_EMAIL,
) -> str:
    """Squash-merge branch into target_branch.

    Squashes all commits from branch into a single commit on target_branch,
    then updates the branch ref to the squash SHA so follow-up work can
    continue from the merged state without conflicts (kagan2 / vibe-kanban
    pattern).

    Returns the SHA of the squash commit.
    Raises MergeConflictError on merge conflicts.
    Raises WorktreeError on any other merge failure (e.g. untracked files
    in the working tree that would be overwritten, permission errors, etc.).
    """
    repo = Path(repo_path)
    current, _ = await _run_git("rev-parse", "--abbrev-ref", "HEAD", cwd=repo)
    await _run_git("checkout", target_branch, cwd=repo)
    try:
        returncode, stdout, stderr = await _run_git_result("merge", "--squash", branch, cwd=repo)
        # Check conflicts first — a partial squash leaves UU/AA/DD markers.
        conflict_files = await _collect_conflict_files(repo)
        if conflict_files:
            await _abort_merge(repo)
            raise MergeConflictError(
                f"Merge conflict between {branch} and {target_branch}",
                conflict_files=conflict_files,
            )
        # Non-conflict failure (e.g. untracked files blocking the squash,
        # permission errors).  These never enter a conflicted state.
        if returncode != 0:
            await _abort_merge(repo)
            detail = stderr or stdout or "unknown merge error"
            raise WorktreeError(f"git merge failed (rc={returncode}): {detail}")
        # If there's nothing staged after the squash the branches are already
        # in sync — return current HEAD without creating an empty commit.
        status_out, _ = await _run_git("status", "--porcelain", cwd=repo, check=False)
        if not status_out.strip():
            head_sha, _ = await _run_git("rev-parse", "HEAD", cwd=repo)
            return head_sha.strip()
        # Commit with explicit agent identity so the repo's local config is
        # left untouched (mirrors commit_all / kagan2 squash pattern).
        await _run_git(
            "-c",
            f"user.name={user_name}",
            "-c",
            f"user.email={user_email}",
            "-c",
            "commit.gpgsign=false",
            "commit",
            "-m",
            commit_message,
            cwd=repo,
        )
        head_sha, _ = await _run_git("rev-parse", "HEAD", cwd=repo)
        squash_sha = head_sha.strip()
        # Update the task branch ref to the squash commit so that follow-up
        # work can continue from the merged state without conflicts.
        await _run_git("update-ref", f"refs/heads/{branch}", squash_sha, cwd=repo, check=False)
        return squash_sha
    finally:
        if current and current != target_branch:
            await _run_git("checkout", current, cwd=repo, check=False)


async def rebase(worktree_path: str | Path, *, target_branch: str) -> None:
    """Rebase the worktree's current branch onto target_branch."""
    wt = Path(worktree_path)
    await _run_git("rebase", target_branch, cwd=wt)


async def abort_rebase(worktree_path: str | Path) -> None:
    """Abort an in-progress rebase; safe to call when no rebase is in progress."""
    wt = Path(worktree_path)
    await _run_git("rebase", "--abort", cwd=wt, check=False)


async def continue_rebase(worktree_path: str | Path) -> None:
    wt = Path(worktree_path)
    await _run_git("rebase", "--continue", cwd=wt)


async def is_rebase_in_progress(worktree_path: str | Path) -> bool:
    wt = Path(worktree_path)
    git_dir, _ = await _run_git("rev-parse", "--git-dir", cwd=wt, check=False)
    if not git_dir:
        return False
    rebase_merge = (wt / git_dir / "rebase-merge").exists()
    rebase_apply = (wt / git_dir / "rebase-apply").exists()
    return rebase_merge or rebase_apply


async def get_conflicted_files(worktree_path: str | Path) -> list[str]:
    wt = Path(worktree_path)
    return await _collect_conflict_files(wt)


async def detect_conflict_op(worktree_path: str | Path) -> str | None:
    wt = Path(worktree_path)
    git_dir, _ = await _run_git("rev-parse", "--git-dir", cwd=wt, check=False)
    if not git_dir:
        return None
    root = wt / git_dir
    if await is_rebase_in_progress(wt):
        return "rebase"
    if (root / "MERGE_HEAD").exists():
        return "merge"
    if (root / "CHERRY_PICK_HEAD").exists():
        return "cherry_pick"
    if (root / "REVERT_HEAD").exists():
        return "revert"
    return None


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


async def _resolve_base_ref(
    cwd: Path,
    base_branch: str,
    *,
    strategy: str = "local_if_ahead",
) -> str:
    """Resolve the best ref for *base_branch* according to *strategy*.

    Strategies:
        local          — prefer refs/heads/<branch>.
        remote         — prefer origin/<branch>.
        local_if_ahead — use local when it has commits ahead of origin,
                         otherwise fall back to origin/<branch>.  (default)
    """
    local_exists = await _has_local_branch(cwd, base_branch)
    remote_exists = await _has_remote_branch(cwd, base_branch)
    remote_ref = f"origin/{base_branch}"

    if strategy == "local":
        if local_exists:
            return base_branch
        if remote_exists:
            return remote_ref
        return base_branch

    if strategy == "remote":
        if remote_exists:
            return remote_ref
        return base_branch

    # local_if_ahead (default)
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


async def _has_remote(repo: Path, remote: str) -> bool:
    """Return True if the named remote (e.g. 'origin') is configured."""
    stdout, _ = await _run_git("remote", "get-url", remote, cwd=repo, check=False)
    return bool(stdout)


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


async def _abort_merge(repo: Path) -> None:
    """Abort an in-progress merge and hard-reset to a clean state.

    Safe to call even when no merge is in progress.
    """
    await _run_git("merge", "--abort", cwd=repo, check=False)
    await _run_git("reset", "--hard", cwd=repo, check=False)


async def _collect_conflict_files(repo: Path) -> list[str]:
    """Return list of files with merge conflicts."""
    stdout, _ = await _run_git("diff", "--name-only", "--diff-filter=U", cwd=repo, check=False)
    files = [line.strip() for line in stdout.splitlines() if line.strip()]
    if files:
        return files
    # Fallback: check status --porcelain for UU/AA/DD markers
    status_out, _ = await _run_git("status", "--porcelain", cwd=repo, check=False)
    return [line[3:].strip() for line in status_out.splitlines() if line[:2] in ("UU", "AA", "DD")]


def _extract_number(text: str, word: str) -> int:
    """Extract the integer before 'word' in a git stat summary line."""
    match = re.search(rf"(\d+)\s+{word}", text)
    return int(match.group(1)) if match else 0


# ---------------------------------------------------------------------------
# Commit enforcement helpers — used by agent completion to gate REVIEW transition
# ---------------------------------------------------------------------------


# Paths generated by Kagan or agent tooling — not meaningful uncommitted work.
_KAGAN_GENERATED: frozenset[str] = frozenset(
    {
        ".mcp.json",
        "opencode.json",
        ".kagan",
    }
)


def _is_kagan_generated(path: str) -> bool:
    """Return True if *path* is a Kagan/agent-generated config file."""
    basename = Path(path).name
    return basename in _KAGAN_GENERATED or path.startswith(".kagan/")


async def has_uncommitted_changes(worktree_path: str | Path) -> bool:
    """Return True if the worktree has tracked uncommitted changes.

    Ignores untracked files (`??`) and Kagan-generated config files.
    """
    wt = Path(worktree_path)
    stdout, _ = await _run_git("status", "--porcelain", cwd=wt, check=False)
    for line in stdout.splitlines():
        if not line.strip():
            continue
        status = line[:2]
        if status == "??":  # untracked
            continue
        file_path = line[3:].strip()
        if not _is_kagan_generated(file_path):
            return True
    return False


async def has_pending_changes(worktree_path: str | Path) -> bool:
    """Return True if the worktree has any uncommitted or untracked meaningful changes.

    Ignores Kagan-generated config files.
    """
    wt = Path(worktree_path)
    stdout, _ = await _run_git("status", "--porcelain", cwd=wt, check=False)
    for line in stdout.splitlines():
        if not line.strip():
            continue
        file_path = line[3:].strip()
        if not _is_kagan_generated(file_path):
            return True
    return False


async def commit_all(
    worktree_path: str | Path,
    message: str,
    *,
    user_name: str = KAGAN_AGENT_NAME,
    user_email: str = KAGAN_AGENT_EMAIL,
) -> None:
    """Stage all tracked changes and commit with *message*.

    Uses `-c` flags for identity so the worktree's local config is untouched.
    """
    wt = Path(worktree_path)
    await _run_git("add", "-A", cwd=wt)
    await _run_git(
        "-c",
        f"user.name={user_name}",
        "-c",
        f"user.email={user_email}",
        "-c",
        "commit.gpgsign=false",
        "commit",
        "-m",
        message,
        cwd=wt,
    )
    logger.info("Auto-committed in {}: {}", wt, message)


async def has_commits_since(
    worktree_path: str | Path,
    base_branch: str,
    *,
    strategy: str = "local_if_ahead",
) -> bool:
    """Return True if the worktree has commits ahead of *base_branch*."""
    wt = Path(worktree_path)
    base_ref = await _resolve_base_ref(wt, base_branch, strategy=strategy)
    rev_count, _ = await _run_git(
        "rev-list",
        "--count",
        f"{base_ref}..HEAD",
        cwd=wt,
        check=False,
    )
    count = rev_count.strip()
    return count.isdigit() and int(count) > 0


async def prune_kagan_branches(repo_path: str | Path) -> list[str]:
    """Delete kagan/* branches that have no live worktree.

    After a squash-merge the task branch ref is updated to the squash SHA but
    the branch still exists. This cleans up orphaned kagan/* branches that no
    worktree is currently checked out on.

    Returns the list of branch names that were deleted.
    """
    repo = Path(repo_path)
    stdout, _ = await _run_git(
        "branch", "--list", "kagan/*", "--format=%(refname:short)", cwd=repo, check=False
    )
    branches = [b.strip() for b in stdout.splitlines() if b.strip()]
    if not branches:
        return []

    live_worktrees = await worktree_list(repo)
    checked_out: set[str] = {wt["branch"] for wt in live_worktrees if wt.get("branch")}

    deleted: list[str] = []
    for branch in branches:
        if branch in checked_out:
            continue
        rc, _, _ = await _run_git_result("branch", "-d", branch, cwd=repo)
        if rc != 0:
            rc, _, _ = await _run_git_result("branch", "-D", branch, cwd=repo)
        if rc == 0:
            logger.debug("Pruned kagan branch: {}", branch)
            deleted.append(branch)
    return deleted


__all__ = [
    "KAGAN_AGENT_EMAIL",
    "KAGAN_AGENT_NAME",
    "abort_rebase",
    "commit_all",
    "continue_rebase",
    "current_branch",
    "detect_conflict_op",
    "diff",
    "diff_stats",
    "get_conflicted_files",
    "get_git_user_identity",
    "get_system_git_identity",
    "has_commits_since",
    "has_pending_changes",
    "has_uncommitted_changes",
    "init_repo",
    "is_git_repo",
    "is_rebase_in_progress",
    "merge",
    "prune_kagan_branches",
    "rebase",
    "resolve_worktree_base",
    "worktree_add",
    "worktree_list",
    "worktree_remove",
]
