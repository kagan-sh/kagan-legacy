from __future__ import annotations

import shutil
from datetime import timedelta
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sqlmodel import col, select

from kagan.core.adapters.db.session import get_session
from kagan.core.domain.enums import TaskStatus, WorkspaceStatus
from kagan.core.time import utc_now

if TYPE_CHECKING:
    from kagan.core.adapters.db.schema import Workspace as DbWorkspace


class WorkspaceMaintenanceMixin:
    """Maintenance and janitor workflows split from WorkspaceServiceImpl."""

    def _make_janitor_result(
        self,
        *,
        worktrees_pruned: int,
        branches_deleted: list[str],
        repos_processed: list[str],
    ) -> Any:
        msg = "_make_janitor_result must be implemented by WorkspaceServiceImpl"
        raise NotImplementedError(msg)

    async def archive_stale_done_task_workspaces(self, *, older_than_days: int) -> int:
        """Archive stale DONE-task workspaces and clean up their local worktrees."""
        from kagan.core.adapters.db.schema import Task, Workspace, WorkspaceRepo

        if older_than_days < 0:
            raise ValueError("older_than_days must be non-negative")

        cutoff = utc_now() - timedelta(days=older_than_days)
        async with get_session(self._session_factory) as session:
            result = await session.execute(
                select(Task, Workspace, WorkspaceRepo)
                .join(Workspace, col(Workspace.task_id) == col(Task.id))
                .join(WorkspaceRepo, col(WorkspaceRepo.workspace_id) == col(Workspace.id))
                .where(Task.status == TaskStatus.DONE)
                .where(Task.updated_at < cutoff)
            )
            rows = result.all()
            if not rows:
                return 0

            now = utc_now()
            workspaces: dict[str, DbWorkspace] = {}
            for _task, workspace, workspace_repo in rows:
                workspaces[workspace.id] = workspace
                if workspace_repo.worktree_path:
                    await self._git.delete_worktree(workspace_repo.worktree_path)
                    workspace_repo.worktree_path = None
                    workspace_repo.updated_at = now
                    session.add(workspace_repo)

            for workspace in workspaces.values():
                if workspace.path and Path(workspace.path).exists():
                    shutil.rmtree(workspace.path, ignore_errors=True)
                if workspace.status != WorkspaceStatus.ARCHIVED:
                    workspace.status = WorkspaceStatus.ARCHIVED
                    workspace.updated_at = now
                    session.add(workspace)

            await session.commit()

        return len(workspaces)

    async def cleanup_orphaned_workspaces(self, valid_task_ids: set[str]) -> list[str]:
        from kagan.core.adapters.db.schema import Workspace

        async with get_session(self._session_factory) as session:
            result = await session.execute(select(Workspace))
            workspaces = result.scalars().all()

        cleaned: list[str] = []
        for workspace in workspaces:
            if workspace.task_id and workspace.task_id not in valid_task_ids:
                await self.release(workspace.id, cleanup=True)
                cleaned.append(workspace.id)

        return cleaned

    async def cleanup_workspace_artifacts(
        self,
        valid_workspace_ids: set[str],
        *,
        prune_worktrees: bool = True,
        gc_branches: bool = True,
    ) -> Any:
        """Run janitor cleanup for stale worktrees and orphan kagan/* branches."""
        from kagan.core.adapters.db.schema import Repo

        async with get_session(self._session_factory) as session:
            result = await session.execute(select(Repo))
            repos = list(result.scalars().all())

        total_pruned = 0
        deleted_branches: list[str] = []
        processed_repos: list[str] = []

        for repo in repos:
            if not Path(repo.path).exists():
                continue

            processed_repos.append(repo.name)

            if prune_worktrees:
                pruned = await self._git.prune_worktrees(repo.path)
                total_pruned += pruned

            if gc_branches:
                branches = await self._git.list_kagan_branches(repo.path)
                for branch in branches:
                    workspace_id = self._extract_workspace_id_from_branch(branch)
                    if workspace_id and workspace_id in valid_workspace_ids:
                        continue

                    worktree = await self._git.get_worktree_for_branch(repo.path, branch)
                    if worktree is not None:
                        continue

                    deleted = await self._git.delete_branch(repo.path, branch, force=False)
                    if deleted:
                        deleted_branches.append(f"{repo.name}:{branch}")

        return self._make_janitor_result(
            worktrees_pruned=total_pruned,
            branches_deleted=deleted_branches,
            repos_processed=processed_repos,
        )

    def _extract_workspace_id_from_branch(self, branch_name: str) -> str | None:
        """Extract workspace ID from managed branch naming conventions."""
        if not branch_name.startswith("kagan/"):
            return None

        suffix = branch_name[6:]

        if suffix.startswith("merge-worktree-"):
            return None

        return suffix if suffix else None
