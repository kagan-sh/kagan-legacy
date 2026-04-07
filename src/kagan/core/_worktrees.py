import asyncio
import contextlib
import os
import re
import shutil
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import TYPE_CHECKING, cast

from loguru import logger
from platformdirs import user_state_dir
from sqlalchemy import Engine
from sqlmodel import select

from kagan.core import git
from kagan.core._db_helpers import _add_and_refresh, _db_async, _db_sync, _setting_branch
from kagan.core._settings import get_settings
from kagan.core.enums import BranchRefStrategy
from kagan.core.errors import MultiRepoUnsupportedError, SessionError, WorktreeError
from kagan.core.git import DiffStats
from kagan.core.models import Repository, Task, Worktree

if TYPE_CHECKING:
    from kagan.core.client import KaganCore


# Regex for valid task ID format (UUID-like)
_TASK_ID_PATTERN = re.compile(r"^[a-zA-Z0-9_-]+$")


# ── Helpers ──────────────────────────────────────────────────────────


def _normalize_base_ref_strategy(value: str | None) -> BranchRefStrategy:
    """Validate and normalize a raw strategy setting to a known enum value."""
    if value is None:
        return BranchRefStrategy.LOCAL_IF_AHEAD
    normalized = value.strip().lower()
    try:
        return BranchRefStrategy(normalized)
    except ValueError:
        return BranchRefStrategy.LOCAL_IF_AHEAD


def _worktree_base_dir() -> Path:
    """Get the base directory for worktrees."""
    override = os.environ.get("KAGAN_WORKTREE_BASE")
    if override:
        return Path(override)
    return Path(user_state_dir("kagan", "kagan")) / "worktrees"


def _resolve_worktree_path(task_id: str) -> Path:
    """Resolve task_id to a safe worktree path, preventing path traversal.

    Args:
        task_id: Task identifier to validate and resolve.

    Returns:
        Resolved Path within the worktree base directory.

    Raises:
        ValueError: If task_id contains path traversal attempts or invalid characters.
        WorktreeError: If resolved path would escape the base directory.
    """
    # Validate task_id format - only alphanumeric, underscore, hyphen
    if not _TASK_ID_PATTERN.match(task_id):
        raise ValueError(
            f"Invalid task_id format: {task_id!r}. "
            "Task IDs must contain only letters, numbers, underscores, and hyphens."
        )

    base = _worktree_base_dir().resolve()

    # CWE-367: Verify the base directory itself is not a symlink
    if base.is_symlink():
        raise WorktreeError(f"Worktree base directory is a symlink, refusing to use it: {base}")

    worktree = (base / task_id).resolve()

    # Ensure the resolved path is within the base directory
    try:
        worktree.relative_to(base)
    except ValueError as exc:
        logger.warning(
            "Worktree path escapes base directory", task_id=task_id, worktree=str(worktree)
        )
        raise WorktreeError(f"Worktree path escapes base directory: {task_id}") from exc

    return worktree


def _check_disk_space(path: Path, min_bytes: int = 100 * 1024 * 1024) -> None:
    """Require at least `min_bytes` (default 100 MB) free before creating a worktree."""
    try:
        usage = shutil.disk_usage(path)
        if usage.free < min_bytes:
            raise WorktreeError(
                f"Insufficient disk space: {usage.free // (1024 * 1024)} MB free, "
                f"need at least {min_bytes // (1024 * 1024)} MB"
            )
    except OSError:
        pass  # If we can't check, proceed anyway


def _get_repo_sync(engine: Engine, repo_id: str) -> Repository | None:
    """Fetch a repository by ID (synchronous DB call)."""

    def op(s) -> Repository | None:
        return cast("Repository | None", s.get(Repository, repo_id))

    return _db_sync(engine, op)


async def _resolve_ref_strategy(engine: Engine) -> BranchRefStrategy:
    """Read the configured branch-ref resolution strategy from settings."""
    settings = await get_settings(engine)
    return _normalize_base_ref_strategy(settings.get("worktree_base_ref_strategy"))


# ── Module-level functions (canonical API) ───────────────────────────


async def create_worktree(
    engine: Engine,
    task_id: str,
    *,
    get_task_fn: Callable[[str], Awaitable[Task]],
    get_repos_fn: Callable[[str], Awaitable[Sequence[Repository]]],
) -> Worktree:
    """Provision a git worktree for a task.

    Args:
        engine: SQLAlchemy engine for DB access.
        task_id: ID of the task to create a worktree for.
        get_task_fn: Async callable to fetch a task by ID.
        get_repos_fn: Async callable to fetch repositories for a project ID.
    """
    task = await get_task_fn(task_id)
    project_id = task.project_id
    if not project_id:
        raise SessionError(None, f"Task {task_id!r} is not linked to a project.")
    repos = await get_repos_fn(project_id)
    if not repos:
        raise SessionError(None, f"No repos linked to project {project_id!r}.")
    if task.repo_id is not None:
        repo = next((r for r in repos if r.id == task.repo_id), None)
        if repo is None:
            raise SessionError(None, f"Repo {task.repo_id!r} not found in project {project_id!r}.")
    elif len(repos) == 1:
        repo = repos[0]
    else:
        raise MultiRepoUnsupportedError(len(repos))

    if not await git.is_git_repo(repo.path):
        raise WorktreeError(f"Not a git repository: {repo.path}")

    branch_name = f"kagan/{task_id}"
    settings = await get_settings(engine)
    current_active_branch = await git.current_branch(repo.path)
    preferred_base = (
        task.base_branch
        or current_active_branch
        or repo.default_branch
        or _setting_branch(
            settings,
            "default_base_branch",
            default="main",
        )
    )
    strategy = _normalize_base_ref_strategy(settings.get("worktree_base_ref_strategy"))
    base = await git.resolve_worktree_base(
        repo.path,
        preferred_branch=preferred_base,
        strategy=strategy,
        refresh_remote=True,
    )
    worktree_path = _resolve_worktree_path(task_id)
    worktree_path.parent.mkdir(parents=True, exist_ok=True)

    # CWE-770: Ensure sufficient disk space before creating worktree
    _check_disk_space(worktree_path.parent)

    await git.worktree_add(
        repo.path,
        worktree_path,
        branch=branch_name,
        base=base,
    )

    # CWE-367: Post-creation TOCTOU re-validation — verify path is still in bounds
    base_dir = _worktree_base_dir().resolve()
    actual = worktree_path.resolve()
    if not actual.is_relative_to(base_dir):
        logger.warning(
            "Worktree path escaped base directory after creation",
            task_id=task_id,
            actual=str(actual),
            base=str(base_dir),
        )
        await git.worktree_remove(repo.path, worktree_path)
        raise WorktreeError("Worktree path escaped base directory after creation")

    ws = Worktree(
        task_id=task_id,
        repo_id=repo.id,
        worktree_path=str(worktree_path),
        branch_name=branch_name,
    )
    ws = await _db_async(engine, lambda s: _add_and_refresh(s, ws))
    logger.debug("Worktree provisioned for task={}", task_id)
    return ws


async def get_worktree(engine: Engine, task_id: str) -> Worktree | None:
    """Fetch the worktree record for a task."""
    return await _db_async(
        engine,
        lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
    )


async def get_worktree_diff(engine: Engine, task_id: str) -> str:
    """Get the diff for a task's worktree against its base branch."""
    ws = await get_worktree(engine, task_id)
    if ws is None:
        raise SessionError(None, f"No workspace for task {task_id!r}.")
    repo = await asyncio.to_thread(_get_repo_sync, engine, ws.repo_id)
    base = repo.default_branch if repo else "main"
    strategy = await _resolve_ref_strategy(engine)
    return await git.diff(ws.worktree_path, base_branch=base, strategy=strategy)


async def get_worktree_diff_stats(engine: Engine, task_id: str) -> DiffStats:
    """Get diff statistics for a task's worktree against its base branch."""
    ws = await get_worktree(engine, task_id)
    if ws is None:
        raise SessionError(None, f"No workspace for task {task_id!r}.")
    repo = await asyncio.to_thread(_get_repo_sync, engine, ws.repo_id)
    base = repo.default_branch if repo else "main"
    strategy = await _resolve_ref_strategy(engine)
    return await git.diff_stats(ws.worktree_path, base_branch=base, strategy=strategy)


async def cleanup_worktree(engine: Engine, task_id: str) -> None:
    """Remove a task's worktree and prune leftover branches."""
    ws = await get_worktree(engine, task_id)
    if ws is None:
        return
    repo = await asyncio.to_thread(_get_repo_sync, engine, ws.repo_id)
    if repo and await git.is_git_repo(repo.path):
        await git.worktree_remove(repo.path, ws.worktree_path)

    def op(s):
        for w in s.exec(select(Worktree).where(Worktree.task_id == task_id)).all():
            s.delete(w)

    await _db_async(engine, op, commit=True)
    if repo:
        with contextlib.suppress(WorktreeError, OSError, RuntimeError):
            await git.prune_kagan_branches(repo.path)


async def cleanup_orphan_worktrees(engine: Engine) -> int:
    """Remove worktrees whose tasks no longer exist. Returns count removed."""
    worktrees = await _db_async(
        engine,
        lambda s: list(s.exec(select(Worktree)).all()),
    )
    removed = 0
    for ws in worktrees:
        task_exists = await _db_async(
            engine,
            lambda s, tid=ws.task_id: s.get(Task, tid) is not None,
        )
        if not task_exists:
            repo = await asyncio.to_thread(_get_repo_sync, engine, ws.repo_id)
            if repo and await git.is_git_repo(repo.path):
                await git.worktree_remove(repo.path, ws.worktree_path)
            with contextlib.suppress(OSError):
                wt = Path(ws.worktree_path)
                if wt.exists():
                    await asyncio.to_thread(shutil.rmtree, wt, ignore_errors=True)

            def del_op(s, wid=ws.id):
                row = s.get(Worktree, wid)
                if row:
                    s.delete(row)

            await _db_async(engine, del_op, commit=True)
            removed += 1
    return removed


# ── Thin class wrapper (backward compatibility) ─────────────────────


class Worktrees:
    def __init__(self, engine: Engine, client: "KaganCore") -> None:
        self._engine = engine
        self._client = client

    @staticmethod
    def _resolve_worktree_path(task_id: str) -> Path:
        """Resolve task_id to a safe worktree path, preventing path traversal.

        This is a static wrapper around the module-level function for testability.
        """
        return _resolve_worktree_path(task_id)

    async def create(self, task_id: str) -> Worktree:
        return await create_worktree(
            self._engine,
            task_id,
            get_task_fn=self._client.tasks.get,
            get_repos_fn=self._client.projects.repos,
        )

    async def get(self, task_id: str) -> Worktree | None:
        return await get_worktree(self._engine, task_id)

    async def diff(self, task_id: str) -> str:
        return await get_worktree_diff(self._engine, task_id)

    def _get_repo(self, repo_id: str) -> Repository | None:
        return _get_repo_sync(self._engine, repo_id)

    async def diff_stats(self, task_id: str) -> DiffStats:
        return await get_worktree_diff_stats(self._engine, task_id)

    async def cleanup(self, task_id: str) -> None:
        return await cleanup_worktree(self._engine, task_id)

    async def cleanup_orphans(self) -> int:
        return await cleanup_orphan_worktrees(self._engine)


__all__ = [
    "Worktrees",
    "cleanup_orphan_worktrees",
    "cleanup_worktree",
    "create_worktree",
    "get_worktree",
    "get_worktree_diff",
    "get_worktree_diff_stats",
]
