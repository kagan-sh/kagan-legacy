import asyncio
import contextlib
import os
import shutil
from pathlib import Path
from typing import TYPE_CHECKING, cast

from loguru import logger
from sqlalchemy import Engine
from sqlmodel import select

from kagan.core import git
from kagan.core._db_helpers import _add_and_refresh, _db_async, _db_sync, _setting_branch
from kagan.core.enums import BranchRefStrategy
from kagan.core.errors import SessionError, WorktreeError
from kagan.core.models import Repository, Task, Worktree

if TYPE_CHECKING:
    from kagan.core.client import KaganCore


def _normalize_base_ref_strategy(value: str | None) -> str:
    """Validate and normalize a raw strategy setting to a known enum value."""
    if value is None:
        return BranchRefStrategy.LOCAL_IF_AHEAD
    normalized = value.strip().lower()
    try:
        return BranchRefStrategy(normalized)
    except ValueError:
        return BranchRefStrategy.LOCAL_IF_AHEAD


def _worktree_base_dir() -> Path:
    override = os.environ.get("KAGAN_WORKTREE_BASE")
    if override:
        return Path(override)
    from platformdirs import user_state_dir

    return Path(user_state_dir("kagan", "kagan")) / "worktrees"


class Worktrees:
    def __init__(self, engine: Engine, client: "KaganCore") -> None:
        self._engine = engine
        self._client = client

    async def create(self, task_id: str) -> Worktree:
        task = await self._client.tasks.get(task_id)
        project_id = self._client.active_project_id
        if project_id is None:
            raise SessionError(None, "No active project.")
        repos = await self._client.projects.repos(project_id)
        if not repos:
            raise SessionError(None, f"No repos linked to project {project_id!r}.")
        repo = repos[0]

        if not await git.is_git_repo(repo.path):
            raise WorktreeError(f"Not a git repository: {repo.path}")

        branch_name = f"kagan/{task_id}"
        settings = await self._client.settings.get()
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
        worktree_path = _worktree_base_dir() / task_id
        worktree_path.parent.mkdir(parents=True, exist_ok=True)

        await git.worktree_add(
            repo.path,
            worktree_path,
            branch=branch_name,
            base=base,
        )

        ws = Worktree(
            task_id=task_id,
            repo_id=repo.id,
            worktree_path=str(worktree_path),
            branch_name=branch_name,
        )
        ws = await _db_async(self._engine, lambda s: _add_and_refresh(s, ws))
        logger.debug("Worktree provisioned for task={}", task_id)
        return ws

    async def get(self, task_id: str) -> Worktree | None:
        return await _db_async(
            self._engine,
            lambda s: s.exec(select(Worktree).where(Worktree.task_id == task_id)).first(),
        )

    async def diff(self, task_id: str) -> str:
        ws = await self.get(task_id)
        if ws is None:
            raise SessionError(None, f"No workspace for task {task_id!r}.")
        repo = await asyncio.to_thread(self._get_repo, ws.repo_id)
        base = repo.default_branch if repo else "main"
        strategy = await self._ref_strategy()
        return await git.diff(ws.worktree_path, base_branch=base, strategy=strategy)

    def _get_repo(self, repo_id: str) -> Repository | None:
        def op(s) -> Repository | None:
            return cast("Repository | None", s.get(Repository, repo_id))

        return _db_sync(self._engine, op)

    async def diff_stats(self, task_id: str) -> dict:
        ws = await self.get(task_id)
        if ws is None:
            raise SessionError(None, f"No workspace for task {task_id!r}.")
        repo = await asyncio.to_thread(self._get_repo, ws.repo_id)
        base = repo.default_branch if repo else "main"
        strategy = await self._ref_strategy()
        return await git.diff_stats(ws.worktree_path, base_branch=base, strategy=strategy)

    async def _ref_strategy(self) -> str:
        settings = await self._client.settings.get()
        return _normalize_base_ref_strategy(settings.get("worktree_base_ref_strategy"))

    async def cleanup(self, task_id: str) -> None:
        ws = await self.get(task_id)
        if ws is None:
            return
        repo = await asyncio.to_thread(self._get_repo, ws.repo_id)
        if repo:
            await git.worktree_remove(repo.path, ws.worktree_path)

        def op(s):
            for w in s.exec(select(Worktree).where(Worktree.task_id == task_id)).all():
                s.delete(w)

        await _db_async(self._engine, op, commit=True)
        if repo:
            with contextlib.suppress(WorktreeError, OSError, RuntimeError):
                await git.prune_kagan_branches(repo.path)

    async def cleanup_orphans(self) -> int:
        worktrees = await _db_async(
            self._engine,
            lambda s: list(s.exec(select(Worktree)).all()),
        )
        removed = 0
        for ws in worktrees:
            task_exists = await _db_async(
                self._engine,
                lambda s, tid=ws.task_id: s.get(Task, tid) is not None,
            )
            if not task_exists:
                repo = await asyncio.to_thread(self._get_repo, ws.repo_id)
                if repo:
                    await git.worktree_remove(repo.path, ws.worktree_path)
                with contextlib.suppress(OSError):
                    wt = Path(ws.worktree_path)
                    if wt.exists():
                        await asyncio.to_thread(shutil.rmtree, wt, ignore_errors=True)

                def del_op(s, wid=ws.id):
                    row = s.get(Worktree, wid)
                    if row:
                        s.delete(row)

                await _db_async(self._engine, del_op, commit=True)
                removed += 1
        return removed


__all__ = ["Worktrees"]
