"""Workspace service with multi-repo support, diffs, and merge operations."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import shutil
from contextlib import suppress
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import col, select

from kagan.core.adapters.db.session import AsyncSessionFactory, get_required_session, get_session
from kagan.core.domain.enums import (
    MergeStatus,
    MergeType,
    RejectionAction,
    TaskStatus,
    WorkspaceStatus,
)
from kagan.core.paths import get_worktree_base_dir
from kagan.core.services.workspaces._merge_helpers import WorkspaceInternalsMixin
from kagan.core.time import utc_now

if TYPE_CHECKING:
    from kagan.core.adapters.db.schema import Task, WorkspaceRepo
    from kagan.core.adapters.db.schema import Workspace as DbWorkspace
    from kagan.core.adapters.git.operations import GitOperationsProtocol
    from kagan.core.adapters.git.worktrees import GitWorktreeProtocol
    from kagan.core.config import KaganConfig
    from kagan.core.events import EventBus
    from kagan.core.services.automation import AutomationServiceImpl
    from kagan.core.services.projects import ProjectServiceImpl
    from kagan.core.services.sessions import SessionServiceImpl
    from kagan.core.services.tasks import TaskServiceImpl
    from kagan.core.services.types import TaskLike

log = logging.getLogger(__name__)

_REJECTION_ACTION_TO_STATUS: dict[RejectionAction, TaskStatus] = {
    RejectionAction.BACKLOG: TaskStatus.BACKLOG,
    RejectionAction.IN_PROGRESS: TaskStatus.IN_PROGRESS,
}

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class RepoWorkspaceInput:
    """Input for creating a workspace repo."""

    repo_id: str
    repo_path: str
    target_branch: str


@dataclass
class JanitorResult:
    """Result of janitor cleanup operations."""

    worktrees_pruned: int
    branches_deleted: list[str]
    repos_processed: list[str]

    @property
    def total_cleaned(self) -> int:
        """Total items cleaned up."""
        return self.worktrees_pruned + len(self.branches_deleted)


@dataclass
class FileDiff:
    """A single file's diff."""

    path: str
    additions: int
    deletions: int
    status: str
    diff_content: str


@dataclass
class RepoDiff:
    """Diff for a single repo."""

    repo_id: str
    repo_name: str
    target_branch: str
    files: list[FileDiff]
    total_additions: int
    total_deletions: int


class MergeStrategy(StrEnum):
    """How to merge changes."""

    DIRECT = "direct"
    PULL_REQUEST = "pr"


@dataclass
class MergeResult:
    """Result of a merge operation."""

    repo_id: str
    repo_name: str
    strategy: MergeStrategy
    success: bool
    message: str
    pr_url: str | None = None
    commit_sha: str | None = None
    conflict_op: str | None = None
    conflict_files: list[str] | None = None


@dataclass(frozen=True)
class MergeRisk:
    """Simple risk summary used for merge gating."""

    score: int
    overlap_files: tuple[str, ...]
    commit_count: int
    changed_repo_count: int
    changed_file_count: int

    @property
    def high(self) -> bool:
        return self.score >= 2 or bool(self.overlap_files)


# ---------------------------------------------------------------------------
# Protocol
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Implementation
# ---------------------------------------------------------------------------


class WorkspaceServiceImpl(WorkspaceInternalsMixin):
    """Unified implementation of workspace, diff, and merge operations."""

    _MERGE_QUIESCE_TIMEOUT_SECONDS = 5.0
    _MERGE_QUIESCE_POLL_SECONDS = 0.1

    def __init__(
        self,
        session_factory: AsyncSessionFactory,
        git_adapter: GitWorktreeProtocol,
        task_service: TaskServiceImpl,
        project_service: ProjectServiceImpl,
        *,
        sessions: SessionServiceImpl | None = None,
        automation: AutomationServiceImpl | None = None,
        config: KaganConfig | None = None,
        event_bus: EventBus | None = None,
        git_ops_adapter: GitOperationsProtocol | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._git = git_adapter
        self._tasks = task_service
        self._projects = project_service
        self._merge_worktrees_dir = get_worktree_base_dir() / "merge-worktrees"

        # Merge/diff dependencies (optional, required only for merge/diff ops)
        self._sessions = sessions
        self._automation = automation
        self._config = config
        self._events = event_bus
        self._git_ops = git_ops_adapter
        self._rebase_first_hints: dict[str, int] = {}

    def _get_workspace_base_dir(self, workspace_id: str) -> Path:
        return get_worktree_base_dir() / "worktrees" / workspace_id

    # ------------------------------------------------------------------
    # Provisioning and lifecycle
    # ------------------------------------------------------------------

    async def provision(
        self,
        task_id: str,
        repos: list[RepoWorkspaceInput],
        *,
        branch_name: str | None = None,
    ) -> str:
        """Provision a workspace with worktrees for all repos."""
        import uuid

        from kagan.core.adapters.db.schema import Workspace, WorkspaceRepo

        if not repos:
            raise ValueError("At least one repo is required to provision a workspace")

        workspace_id = uuid.uuid4().hex[:8]
        branch_name = branch_name or f"kagan/{workspace_id}"

        task = await self._tasks.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        base_dir = self._get_workspace_base_dir(workspace_id)
        base_dir.mkdir(parents=True, exist_ok=True)

        workspace = Workspace(
            id=workspace_id,
            project_id=task.project_id,
            task_id=task_id,
            path=str(base_dir),
            branch_name=branch_name,
        )

        created_paths: list[Path] = []
        workspace_repos: list[WorkspaceRepo] = []
        try:
            for repo_input in repos:
                worktree_path = base_dir / Path(repo_input.repo_path).name
                await self._git.create_worktree(
                    repo_path=repo_input.repo_path,
                    worktree_path=str(worktree_path),
                    branch_name=branch_name,
                    base_branch=repo_input.target_branch,
                )
                created_paths.append(worktree_path)

                workspace_repos.append(
                    WorkspaceRepo(
                        workspace_id=workspace_id,
                        repo_id=repo_input.repo_id,
                        target_branch=repo_input.target_branch,
                        worktree_path=str(worktree_path),
                    )
                )

            async with get_session(self._session_factory) as session:
                session.add(workspace)
                for wr in workspace_repos:
                    session.add(wr)
                await session.commit()

        except Exception:
            for path in created_paths:
                with contextlib.suppress(Exception):
                    await self._git.delete_worktree(str(path))
            shutil.rmtree(base_dir, ignore_errors=True)
            raise

        return workspace_id

    async def provision_for_project(
        self,
        task_id: str,
        project_id: str,
        *,
        branch_name: str | None = None,
    ) -> str:
        """Provision workspace using all project repos."""
        from kagan.core.adapters.db.schema import ProjectRepo, Repo

        async with get_session(self._session_factory) as session:
            result = await session.execute(
                select(ProjectRepo, Repo)
                .join(Repo)
                .where(ProjectRepo.project_id == project_id)
                .order_by(col(ProjectRepo.display_order))
            )
            project_repos = result.all()

        if not project_repos:
            raise ValueError(f"Project {project_id} has no repos")

        repos = [
            RepoWorkspaceInput(
                repo_id=repo.id,
                repo_path=repo.path,
                target_branch=repo.default_branch,
            )
            for project_repo, repo in project_repos
        ]

        return await self.provision(task_id, repos, branch_name=branch_name)

    async def release(
        self,
        workspace_id: str,
        *,
        reason: str | None = None,
        cleanup: bool = True,
    ) -> None:
        """Release workspace and clean up worktrees."""
        from kagan.core.adapters.db.schema import Workspace, WorkspaceRepo

        async with get_session(self._session_factory) as session:
            result = await session.execute(select(Workspace).where(Workspace.id == workspace_id))
            workspace = result.scalars().first()

            if not workspace:
                raise ValueError(f"Workspace {workspace_id} not found")

            if cleanup:
                result = await session.execute(
                    select(WorkspaceRepo).where(WorkspaceRepo.workspace_id == workspace_id)
                )
                workspace_repos = result.scalars().all()

                for wr in workspace_repos:
                    if wr.worktree_path and Path(wr.worktree_path).exists():
                        with contextlib.suppress(Exception):
                            await self._git.delete_worktree(wr.worktree_path)

                if workspace.path and Path(workspace.path).exists():
                    shutil.rmtree(workspace.path, ignore_errors=True)

            workspace.status = WorkspaceStatus.ARCHIVED
            workspace.updated_at = utc_now()
            session.add(workspace)
            await session.commit()

    async def get_workspace_repos(self, workspace_id: str) -> list[dict]:
        """Get all repos for a workspace with paths and status."""
        from kagan.core.adapters.db.schema import Repo, WorkspaceRepo

        async with get_session(self._session_factory) as session:
            result = await session.execute(
                select(WorkspaceRepo, Repo)
                .join(Repo)
                .where(WorkspaceRepo.workspace_id == workspace_id)
            )
            results = result.all()

        items: list[dict] = []
        for workspace_repo, repo in results:
            diff_stats = None
            has_changes = False
            if workspace_repo.worktree_path:
                has_uncommitted = await self._git.has_uncommitted_changes(
                    workspace_repo.worktree_path
                )
                diff_stats = await self._git.get_diff_stats(
                    workspace_repo.worktree_path,
                    workspace_repo.target_branch,
                )
                diff_files = int(diff_stats.get("files", 0)) if diff_stats else 0
                diff_insertions = int(diff_stats.get("insertions", 0)) if diff_stats else 0
                diff_deletions = int(diff_stats.get("deletions", 0)) if diff_stats else 0
                has_changes = bool(
                    has_uncommitted or diff_files or diff_insertions or diff_deletions
                )
            item = {
                "repo_id": repo.id,
                "repo_name": repo.name,
                "repo_path": repo.path,
                "worktree_path": workspace_repo.worktree_path,
                "target_branch": workspace_repo.target_branch,
                "has_changes": has_changes,
                "diff_stats": diff_stats,
            }
            items.append(item)

        return items

    async def get_agent_working_dir(self, workspace_id: str) -> Path:
        """Get working directory for agents (primary repo's worktree)."""
        primary_repo = await self._get_primary_workspace_repo(workspace_id)
        if primary_repo is None or not primary_repo.worktree_path:
            raise ValueError(f"Workspace {workspace_id} has no repos")
        return Path(primary_repo.worktree_path)

    async def get_workspace(self, workspace_id: str) -> DbWorkspace | None:
        workspace = await self._get_workspace(workspace_id)
        return workspace

    async def list_workspaces(
        self,
        *,
        task_id: str | None = None,
        repo_id: str | None = None,
    ) -> list[DbWorkspace]:
        from kagan.core.adapters.db.schema import Workspace, WorkspaceRepo

        async with get_session(self._session_factory) as session:
            statement = select(Workspace).order_by(col(Workspace.created_at).desc())
            if task_id is not None:
                statement = statement.where(Workspace.task_id == task_id)
            if repo_id is not None:
                statement = (
                    statement.join(WorkspaceRepo).where(WorkspaceRepo.repo_id == repo_id).distinct()
                )
            result = await session.execute(statement)
            return list(result.scalars().all())

    async def cleanup_orphans(self, valid_task_ids: set[str]) -> list[str]:
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

    async def run_janitor(
        self,
        valid_workspace_ids: set[str],
        *,
        prune_worktrees: bool = True,
        gc_branches: bool = True,
    ) -> JanitorResult:
        """Run janitor cleanup for stale worktrees and orphan kagan/* branches.

        This performs two cleanup operations:

        1. **Worktree pruning**: Runs `git worktree prune` on all project repos
           to clean up stale worktree administrative files for worktrees that
           no longer exist on disk.

        2. **Branch GC**: Deletes local `kagan/*` branches that are no longer
           associated with an active workspace. Only deletes branches that:
           - Match the `kagan/*` pattern (managed branches)
           - Are not currently checked out in any worktree
           - Do not belong to an active workspace in valid_workspace_ids

        Args:
            valid_workspace_ids: Set of workspace IDs that are still active.
                Branches matching these IDs will be preserved.
            prune_worktrees: If True, run git worktree prune on all repos.
            gc_branches: If True, delete orphaned kagan/* branches.

        Returns:
            JanitorResult with counts of cleaned items.
        """
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

        return JanitorResult(
            worktrees_pruned=total_pruned,
            branches_deleted=deleted_branches,
            repos_processed=processed_repos,
        )

    def _extract_workspace_id_from_branch(self, branch_name: str) -> str | None:
        """Extract workspace ID from a kagan branch name.

        Branch naming conventions:
        - kagan/{workspace_id} -> workspace_id
        - kagan/merge-worktree-{repo_id} -> None (merge worktrees handled separately)

        Returns None if the branch doesn't match the expected pattern.
        """
        if not branch_name.startswith("kagan/"):
            return None

        suffix = branch_name[6:]

        if suffix.startswith("merge-worktree-"):
            return None

        return suffix if suffix else None

    # ------------------------------------------------------------------
    # Git operations
    # ------------------------------------------------------------------

    async def create(self, task_id: str, base_branch: str | None = None) -> Path:
        """Create a workspace for the task and return primary worktree path."""
        task = await self._tasks.get_task(task_id)
        if task is None:
            raise ValueError(f"Task {task_id} not found")

        repos = await self._projects.get_project_repos(task.project_id)
        if not repos:
            raise ValueError(f"Project {task.project_id} has no repos")

        explicit_branch = (base_branch or "").strip()
        repo_inputs: list[RepoWorkspaceInput] = []
        for repo in repos:
            target_branch = explicit_branch or (repo.default_branch or "").strip()
            if not target_branch:
                raise ValueError(f"Repository {repo.name} has no default branch configured")
            repo_inputs.append(
                RepoWorkspaceInput(
                    repo_id=repo.id,
                    repo_path=repo.path,
                    target_branch=target_branch,
                )
            )
        workspace_id = await self.provision(task_id, repo_inputs)
        return await self.get_agent_working_dir(workspace_id)

    async def delete(self, task_id: str, *, delete_branch: bool = False) -> None:
        del delete_branch
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return
        await self.release(workspace.id, cleanup=True)

    async def get_path(self, task_id: str) -> Path | None:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return None
        return await self.get_agent_working_dir(workspace.id)

    async def get_commit_log(self, task_id: str, base_branch: str = "main") -> list[str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return []
        repo_rows = await self._get_workspace_repo_rows(workspace.id)
        commits: list[str] = []
        for workspace_repo, repo in repo_rows:
            if not workspace_repo.worktree_path:
                continue
            target_branch = workspace_repo.target_branch or base_branch
            repo_commits = await self._git.get_commit_log(
                workspace_repo.worktree_path,
                target_branch,
            )
            commits.extend([f"[{repo.name}] {commit}" for commit in repo_commits])
        return commits

    async def get_diff(self, task_id: str, base_branch: str = "main") -> str:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return ""
        repo_rows = await self._get_workspace_repo_rows(workspace.id)
        chunks: list[str] = []
        for workspace_repo, repo in repo_rows:
            if not workspace_repo.worktree_path:
                continue
            target_branch = workspace_repo.target_branch or base_branch
            diff = await self._git.get_diff(workspace_repo.worktree_path, target_branch)
            if not diff.strip():
                continue
            chunks.append(f"# === {repo.name} ({target_branch}) ===")
            chunks.append(diff.rstrip())
            chunks.append("")
        return "\n".join(chunks).strip()

    async def get_diff_stats(self, task_id: str, base_branch: str = "main") -> str:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return ""
        repo_rows = await self._get_workspace_repo_rows(workspace.id)
        summary_lines: list[str] = []
        total_files = 0
        total_insertions = 0
        total_deletions = 0
        for workspace_repo, repo in repo_rows:
            if not workspace_repo.worktree_path:
                continue
            target_branch = workspace_repo.target_branch or base_branch
            stats = await self._git.get_diff_stats(
                workspace_repo.worktree_path,
                target_branch,
            )
            files = int(stats.get("files", 0))
            insertions = int(stats.get("insertions", 0))
            deletions = int(stats.get("deletions", 0))
            total_files += files
            total_insertions += insertions
            total_deletions += deletions
            if files or insertions or deletions:
                summary_lines.append(f"{repo.name}: +{insertions} -{deletions} ({files} files)")
            else:
                summary_lines.append(f"{repo.name}: no changes")

        if not summary_lines:
            return ""
        if len(summary_lines) > 1:
            summary_lines.append(
                f"Total: +{total_insertions} -{total_deletions} ({total_files} files)"
            )
        return "\n".join(summary_lines)

    async def get_files_changed(self, task_id: str, base_branch: str = "main") -> list[str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return []
        repo_rows = await self._get_workspace_repo_rows(workspace.id)
        files: list[str] = []
        for workspace_repo, repo in repo_rows:
            if not workspace_repo.worktree_path:
                continue
            target_branch = workspace_repo.target_branch or base_branch
            repo_files = await self._git.get_files_changed(
                workspace_repo.worktree_path,
                target_branch,
            )
            files.extend([f"{repo.name}:{path}" for path in repo_files])
        return files

    # ------------------------------------------------------------------
    # Merge-ops (formerly WorkspaceMergeOpsMixin)
    # ------------------------------------------------------------------

    async def get_merge_worktree_path(self, task_id: str, base_branch: str = "main") -> Path:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            raise ValueError(f"Workspace not found for task {task_id}")
        primary_repo = await self._get_primary_workspace_repo(workspace.id)
        if primary_repo is None:
            raise ValueError(f"Workspace {workspace.id} has no repos")
        return await self._ensure_merge_worktree(primary_repo.repo_id, base_branch, workspace)

    async def prepare_merge_conflicts(
        self, task_id: str, base_branch: str = "main"
    ) -> tuple[bool, str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return False, f"Workspace not found for task {task_id}"
        branch_name = workspace.branch_name

        primary_repo = await self._get_primary_workspace_repo(workspace.id)
        if primary_repo is None:
            return False, f"Workspace {workspace.id} has no repos"
        merge_path = await self._ensure_merge_worktree(primary_repo.repo_id, base_branch, workspace)
        if await self._merge_in_progress(merge_path):
            return True, "Merge already in progress"

        try:
            await self._reset_merge_worktree(merge_path, base_branch)
            await self._git.run_git(
                "merge",
                "--squash",
                branch_name,
                cwd=merge_path,
                check=False,
            )
            status_out, _ = await self._git.run_git("status", "--porcelain", cwd=merge_path)
            if any(marker in status_out for marker in ("UU ", "AA ", "DD ")):
                return True, "Merge conflicts prepared"

            await self._git.run_git("merge", "--abort", cwd=merge_path, check=False)
            return False, "No conflicts detected"
        except Exception as exc:
            return False, f"Prepare failed: {exc}"

    async def rebase_onto_base(
        self, task_id: str, base_branch: str = "main"
    ) -> tuple[bool, str, list[str]]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return False, f"Workspace not found for task {task_id}", []

        repo_rows = await self._get_workspace_repo_rows(workspace.id)
        if not repo_rows:
            return False, f"Workspace {workspace.id} has no repos", []

        try:
            for workspace_repo, repo in repo_rows:
                if not workspace_repo.worktree_path:
                    continue
                target_branch = workspace_repo.target_branch or base_branch
                wt_path = Path(workspace_repo.worktree_path)
                has_remote = await self._has_remote(wt_path)
                if has_remote:
                    await self._git.run_git(
                        "fetch", "origin", target_branch, cwd=wt_path, check=False
                    )
                rebase_ref = f"origin/{target_branch}" if has_remote else target_branch

                if await self._rebase_in_progress(wt_path):
                    conflict_files = await self._collect_rebase_conflicts(wt_path, repo.name)
                    return (
                        False,
                        (
                            f"Rebase already in progress for {repo.name}; resolve conflicts or "
                            "abort the rebase"
                        ),
                        conflict_files,
                    )

                status_out, _ = await self._git.run_git("status", "--porcelain", cwd=wt_path)
                if status_out.strip():
                    await self._git.run_git("add", "-A", cwd=wt_path)
                    await self._git.run_git(
                        "commit",
                        "-m",
                        f"chore: adding uncommitted agent changes ({repo.name})",
                        cwd=wt_path,
                    )

                stdout, stderr = await self._git.run_git(
                    "rebase",
                    rebase_ref,
                    cwd=wt_path,
                    check=False,
                )
                if await self._rebase_in_progress(wt_path):
                    conflict_files = await self._collect_rebase_conflicts(wt_path, repo.name)
                    return (
                        False,
                        (
                            f"Rebase conflict in {repo.name} ({len(conflict_files)} file(s)); "
                            "resolve or abort"
                        ),
                        conflict_files,
                    )

                combined_output = f"{stdout}\n{stderr}".strip().lower()
                if "fatal:" in combined_output or "error:" in combined_output:
                    failure = combined_output.strip() or "rebase failed"
                    return False, f"Rebase failed in {repo.name}: {failure}", []

            return True, f"Successfully rebased onto {base_branch}", []
        except Exception as exc:
            with contextlib.suppress(Exception):
                for workspace_repo, _repo in repo_rows:
                    if not workspace_repo.worktree_path:
                        continue
                    await self._git.run_git(
                        "rebase",
                        "--abort",
                        cwd=Path(workspace_repo.worktree_path),
                        check=False,
                    )
            return False, f"Rebase failed: {exc}", []

    async def abort_rebase(self, task_id: str) -> tuple[bool, str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return False, f"Workspace not found for task {task_id}"

        repo_rows = await self._get_workspace_repo_rows(workspace.id)
        if not repo_rows:
            return False, f"Workspace {workspace.id} has no repos"

        aborted: list[str] = []
        for workspace_repo, repo in repo_rows:
            if not workspace_repo.worktree_path:
                continue
            wt_path = Path(workspace_repo.worktree_path)
            if not await self._rebase_in_progress(wt_path):
                continue
            await self._git.run_git("rebase", "--abort", cwd=wt_path, check=False)
            aborted.append(repo.name)

        if not aborted:
            return False, "No rebase in progress"

        aborted_list = ", ".join(aborted)
        return True, f"Aborted rebase in {len(aborted)} repo(s): {aborted_list}"

    async def get_files_changed_on_base(self, task_id: str, base_branch: str = "main") -> list[str]:
        workspace = await self._get_latest_workspace_for_task(task_id)
        if workspace is None:
            return []

        repo_rows = await self._get_workspace_repo_rows(workspace.id)
        try:
            files: list[str] = []
            for workspace_repo, repo in repo_rows:
                if not workspace_repo.worktree_path:
                    continue
                target_branch = workspace_repo.target_branch or base_branch
                wt_path = Path(workspace_repo.worktree_path)
                merge_base_out, _ = await self._git.run_git(
                    "merge-base",
                    "HEAD",
                    f"origin/{target_branch}",
                    cwd=wt_path,
                    check=False,
                )
                if not merge_base_out.strip():
                    continue

                merge_base = merge_base_out.strip()
                diff_out, _ = await self._git.run_git(
                    "diff",
                    "--name-only",
                    merge_base,
                    f"origin/{target_branch}",
                    cwd=wt_path,
                )
                if not diff_out.strip():
                    continue

                repo_files = [line.strip() for line in diff_out.split("\n") if line.strip()]
                files.extend([f"{repo.name}:{path}" for path in repo_files])

            return files
        except Exception:
            return []

    # ------------------------------------------------------------------
    # Diff operations (formerly DiffService)
    # ------------------------------------------------------------------

    async def get_repo_diff(self, workspace_id: str, repo_id: str) -> RepoDiff:
        """Get diff for a single repo."""
        from kagan.core.adapters.db.schema import Repo, WorkspaceRepo

        async with get_session(self._session_factory) as session:
            result = await session.execute(
                select(WorkspaceRepo, Repo)
                .join(Repo)
                .where(WorkspaceRepo.workspace_id == workspace_id)
                .where(WorkspaceRepo.repo_id == repo_id)
            )
            row = result.first()

        if not row:
            raise ValueError(f"Repo {repo_id} not found in workspace {workspace_id}")

        workspace_repo, repo = row
        if not workspace_repo.worktree_path:
            raise ValueError(f"Repo {repo_id} has no worktree for workspace {workspace_id}")
        if self._git_ops is None:
            raise RuntimeError("Workspace service missing git_ops_adapter for diff operations")
        files = await self._git_ops.get_file_diffs(
            workspace_repo.worktree_path,
            workspace_repo.target_branch,
        )

        return RepoDiff(
            repo_id=repo_id,
            repo_name=repo.name,
            target_branch=workspace_repo.target_branch,
            files=files,
            total_additions=sum(file.additions for file in files),
            total_deletions=sum(file.deletions for file in files),
        )

    async def get_all_diffs(self, workspace_id: str) -> list[RepoDiff]:
        """Get diffs for all repos in a workspace."""
        repos = await self.get_workspace_repos(workspace_id)
        diffs: list[RepoDiff] = []

        for repo in repos:
            diff = await self.get_repo_diff(workspace_id, repo["repo_id"])
            if diff.files or diff.total_additions or diff.total_deletions:
                diffs.append(diff)

        return diffs

    async def get_unified_diff(self, workspace_id: str) -> str:
        """Get unified diff across all repos for agent context."""
        diffs = await self.get_all_diffs(workspace_id)

        lines: list[str] = []
        for diff in diffs:
            lines.append(f"# === {diff.repo_name} ({diff.target_branch}) ===")
            lines.append(f"# +{diff.total_additions} -{diff.total_deletions}")
            lines.append("")
            for file in diff.files:
                lines.append(file.diff_content)
                lines.append("")

        return "\n".join(lines)

    # ------------------------------------------------------------------
    # Merge operations (formerly MergeService)
    # ------------------------------------------------------------------

    def _is_task_runtime_active(self, task_id: str) -> bool:
        assert self._automation is not None
        return self._automation.is_running(task_id) or self._automation.is_reviewing(task_id)

    async def _ensure_task_idle_before_merge(self, task_id: str) -> tuple[bool, str | None]:
        """Stop runtime activity and wait until task runtime is fully idle."""
        assert self._automation is not None
        if not self._is_task_runtime_active(task_id):
            return True, None

        with suppress(Exception):
            await self._automation.stop_task(task_id)

        loop = asyncio.get_running_loop()
        deadline = loop.time() + self._MERGE_QUIESCE_TIMEOUT_SECONDS
        while self._is_task_runtime_active(task_id):
            if loop.time() >= deadline:
                message = "Task runtime is still active; wait for agent shutdown and retry merge."
                return False, message
            await asyncio.sleep(self._MERGE_QUIESCE_POLL_SECONDS)
        return True, None

    async def _get_latest_workspace_id(self, task_id: str) -> str | None:
        workspaces = await self.list_workspaces(task_id=task_id)
        return workspaces[0].id if workspaces else None

    @staticmethod
    def _normalize_branch(value: object) -> str:
        return str(value).strip() if isinstance(value, str) else ""

    async def _resolve_base_branch(self, task: TaskLike, *, workspace_id: str) -> str:
        explicit_branch = self._normalize_branch(getattr(task, "base_branch", None))
        if explicit_branch:
            return explicit_branch

        repos = await self.get_workspace_repos(workspace_id)
        for repo in repos:
            target_branch = self._normalize_branch(repo.get("target_branch"))
            if target_branch:
                return target_branch

        raise ValueError(
            f"Task {task.id} has no base branch configured. "
            "Set task branch explicitly or sync repository branch first."
        )

    async def delete_task(self, task: TaskLike) -> tuple[bool, str]:
        """Delete task with rollback-aware error handling.

        Returns:
            Tuple of (success, message) indicating result and reason.
        """
        assert self._automation is not None
        assert self._sessions is not None
        steps_completed: list[str] = []
        try:
            if self._automation.is_running(task.id):
                await self._automation.stop_task(task.id)
            steps_completed.append("agent_stopped")

            await self._sessions.kill_session(task.id)
            steps_completed.append("session_killed")

            if await self.get_path(task.id):
                await self.delete(task.id, delete_branch=True)
            steps_completed.append("worktree_deleted")

            await self._tasks.delete_task(task.id)
            steps_completed.append("db_deleted")

            log.debug(f"Task {task.id} deleted successfully. Steps: {steps_completed}")
            return True, "Deleted successfully"
        except Exception as e:
            log.error(
                f"Delete failed for task {task.id} after steps: {steps_completed}. Error: {e}"
            )
            return False, f"Delete failed: {e}"

    async def merge_task(self, task: TaskLike) -> tuple[bool, str]:
        """Merge task changes and clean up. Returns (success, message)."""
        assert self._config is not None
        assert self._sessions is not None
        config = self._config.general

        async def _do_merge() -> tuple[bool, str]:
            idle, idle_message = await self._ensure_task_idle_before_merge(task.id)
            if not idle:
                assert idle_message is not None
                return False, f"Merge blocked: {idle_message}"

            workspace_id = await self._get_latest_workspace_id(task.id)
            if not workspace_id:
                message = (
                    f"Workspace not found for task {task.id}. "
                    "Ensure the task has a provisioned workspace before merging."
                )
                return False, message

            try:
                base_branch = await self._resolve_base_branch(task, workspace_id=workspace_id)
            except ValueError as exc:
                return False, str(exc)
            short_id = task.id.split("-")[0] if "-" in task.id else task.id[:8]
            commit_msg = f"{task.title} (kagan {short_id})"
            if task.description and task.description.strip():
                commit_msg += f"\n\n{task.description}"

            skip_unchanged = await self.has_no_changes(task, base_branch=base_branch)
            risk = await self._assess_merge_risk(task, workspace_id, base_branch)
            used_premerge_rebase = False

            if self._should_rebase_before_merge(base_branch, risk):
                try:
                    (
                        rebase_success,
                        rebase_message,
                        _conflict_files,
                    ) = await self.rebase_onto_base(task.id, base_branch)
                except RuntimeError as exc:
                    log.error("Pre-merge rebase failed for task %s: %s", task.id, exc)
                    return False, (
                        f"Pre-merge rebase failed: {exc}. "
                        "Try running 'review rebase' manually and retry merge."
                    )[:500]
                if not rebase_success:
                    return False, f"Merge blocked: {rebase_message}"[:500]
                used_premerge_rebase = True

            try:
                results = await self.merge_all(
                    workspace_id,
                    strategy=MergeStrategy.DIRECT,
                    skip_unchanged=skip_unchanged,
                    commit_message=commit_msg,
                )
            except RuntimeError as exc:
                log.error("Merge failed for task %s: %s", task.id, exc)
                return False, (
                    f"Git operation failed during merge: {exc}. Check branch state and retry."
                )[:500]
            failures = [result for result in results if not result.success]
            used_auto_rebase = False

            if failures and self._should_retry_after_rebase(failures):
                try:
                    (
                        rebase_success,
                        rebase_message,
                        _conflict_files,
                    ) = await self.rebase_onto_base(task.id, base_branch)
                except RuntimeError as exc:
                    log.error("Auto-rebase failed for task %s: %s", task.id, exc)
                    return False, (
                        f"Auto-rebase failed: {exc}. "
                        "Try running 'review rebase' manually and retry merge."
                    )[:500]
                if not rebase_success:
                    return False, f"Merge blocked: {rebase_message}"[:500]

                used_auto_rebase = True
                try:
                    results = await self.merge_all(
                        workspace_id,
                        strategy=MergeStrategy.DIRECT,
                        skip_unchanged=skip_unchanged,
                        commit_message=commit_msg,
                    )
                except RuntimeError as exc:
                    log.error("Merge after rebase failed for task %s: %s", task.id, exc)
                    return False, (
                        f"Git operation failed during merge (after rebase): {exc}. "
                        "Check branch state and retry."
                    )[:500]
                failures = [result for result in results if not result.success]

            if failures:
                return False, self._summarize_failures(failures, overlap_files=risk.overlap_files)

            assert self._sessions is not None
            await self.release(workspace_id, cleanup=False, reason="merged")
            await self._sessions.kill_session(task.id)
            await self._tasks.update_fields(
                task.id,
                status=TaskStatus.DONE,
            )
            if used_premerge_rebase or used_auto_rebase:
                self._note_rebase_hint(base_branch)
            else:
                self._cooldown_rebase_hint(base_branch)

            if used_auto_rebase:
                return True, "Merged all repos (after auto-rebase)"
            if used_premerge_rebase:
                return True, "Merged all repos (after pre-merge rebase)"
            return True, "Merged all repos"

        assert self._automation is not None
        if config.serialize_merges:
            async with self._automation.merge_lock:
                return await _do_merge()
        return await _do_merge()

    async def close_exploratory(self, task: TaskLike) -> tuple[bool, str]:
        """Close a no-change task by marking DONE and archiving its workspace."""
        assert self._automation is not None
        assert self._sessions is not None
        if self._automation.is_running(task.id):
            await self._automation.stop_task(task.id)

        await self._sessions.kill_session(task.id)

        workspace_id = await self._get_latest_workspace_id(task.id)
        if workspace_id:
            await self.release(workspace_id, cleanup=False, reason="no_changes")

        await self._tasks.update_fields(
            task.id,
            status=TaskStatus.DONE,
        )
        return True, "Closed with no changes"

    async def apply_rejection_feedback(
        self,
        task: TaskLike,
        feedback: str | None,
        action: str = "backlog",
    ) -> Task:
        """Apply rejection feedback and move the task out of REVIEW.

        State Transitions:
            - return: REVIEW -> IN_PROGRESS (manual restart)
            - backlog: REVIEW -> BACKLOG

        Returns:
            Updated task from database.
        """

        resolved_action = (
            RejectionAction.BACKLOG
            if action == RejectionAction.BACKLOG
            else RejectionAction.IN_PROGRESS
        )
        target_status = _REJECTION_ACTION_TO_STATUS[resolved_action]

        if feedback:
            timestamp = utc_now().strftime("%Y-%m-%d %H:%M")
            new_description = task.description or ""
            new_description += f"\n\n---\n**Review Feedback ({timestamp}):**\n{feedback}"

            await self._tasks.update_fields(
                task.id,
                description=new_description,
                status=target_status,
            )
        else:
            await self._tasks.update_fields(
                task.id,
                status=target_status,
            )

        refreshed_task = await self._tasks.get_task(task.id)
        assert refreshed_task is not None
        return refreshed_task

    async def has_no_changes(self, task: TaskLike, base_branch: str | None = None) -> bool:
        """Return True if the task has no commits and no diff stats."""
        workspace_id = await self._get_latest_workspace_id(task.id)
        if not workspace_id:
            return True
        repos = await self.get_workspace_repos(workspace_id)
        if any(repo.get("has_changes") for repo in repos):
            return False

        resolved_base = base_branch or await self._resolve_base_branch(
            task,
            workspace_id=workspace_id,
        )
        commits = await self.get_commit_log(task.id, resolved_base)
        return not commits

    async def merge_repo(
        self,
        workspace_id: str,
        repo_id: str,
        *,
        strategy: MergeStrategy = MergeStrategy.DIRECT,
        pr_title: str | None = None,
        pr_body: str | None = None,
        commit_message: str | None = None,
    ) -> MergeResult:
        """Merge a single repo's changes."""
        if self._events is None or self._git_ops is None:
            raise RuntimeError("Workspace service missing dependencies for per-repo operations")

        from kagan.core.adapters.db.schema import Merge, Repo, Workspace, WorkspaceRepo
        from kagan.core.events import MergeCompleted, MergeFailed, PRCreated

        async with get_required_session(
            self._session_factory,
            error_message="Workspace service missing session factory for per-repo operations",
        ) as session:
            result = await session.execute(
                select(WorkspaceRepo, Repo, Workspace)
                .join(Repo, col(WorkspaceRepo.repo_id) == col(Repo.id))
                .join(Workspace, col(WorkspaceRepo.workspace_id) == col(Workspace.id))
                .where(WorkspaceRepo.workspace_id == workspace_id)
                .where(WorkspaceRepo.repo_id == repo_id)
            )
            row = result.first()

        if not row:
            raise ValueError(f"Repo {repo_id} not found in workspace {workspace_id}")

        workspace_repo, repo, workspace = row
        if not workspace_repo.worktree_path:
            raise ValueError(f"Repo {repo_id} has no worktree for workspace {workspace_id}")

        merge_result: MergeResult | None = None
        if await self._git_ops.has_uncommitted_changes(workspace_repo.worktree_path):
            short_id = workspace.task_id[:8] if workspace.task_id else "unknown"
            await self._git_ops.commit_all(
                workspace_repo.worktree_path,
                f"chore: adding uncommitted agent changes ({short_id})",
            )
            log.info(f"Auto-committed changes before merge for repo {repo.name}")

        await self._git_ops.push(workspace_repo.worktree_path, workspace.branch_name, force=True)

        if merge_result is None and strategy == MergeStrategy.PULL_REQUEST:
            pr_url = await self._create_pr(
                repo_path=repo.path,
                branch=workspace.branch_name,
                target=workspace_repo.target_branch,
                title=pr_title or f"Merge {workspace.branch_name}",
                body=pr_body or "",
            )
            merge_result = MergeResult(
                repo_id=repo_id,
                repo_name=repo.name,
                strategy=strategy,
                success=True,
                message=f"PR created: {pr_url}",
                pr_url=pr_url,
            )
            await self._events.publish(
                PRCreated(
                    workspace_id=workspace_id,
                    repo_id=repo_id,
                    pr_url=pr_url,
                )
            )
        elif merge_result is None:
            if self._is_remote_target(workspace_repo.target_branch):
                merge_result = MergeResult(
                    repo_id=repo_id,
                    repo_name=repo.name,
                    strategy=strategy,
                    success=False,
                    message=(
                        f"Direct merge blocked for remote target {workspace_repo.target_branch}"
                    ),
                )
                await self._events.publish(
                    MergeFailed(
                        workspace_id=workspace_id,
                        repo_id=repo_id,
                        error=merge_result.message,
                    )
                )
            else:
                try:
                    git_result = await self._git_ops.merge_squash(
                        repo_path=repo.path,
                        source_branch=workspace.branch_name,
                        target_branch=workspace_repo.target_branch,
                        commit_message=commit_message,
                    )
                    if git_result.success:
                        merge_result = MergeResult(
                            repo_id=repo_id,
                            repo_name=repo.name,
                            strategy=strategy,
                            success=True,
                            message=git_result.message,
                            commit_sha=git_result.commit_sha,
                        )
                        if git_result.commit_sha:
                            await self._events.publish(
                                MergeCompleted(
                                    workspace_id=workspace_id,
                                    repo_id=repo_id,
                                    target_branch=workspace_repo.target_branch,
                                    commit_sha=git_result.commit_sha,
                                )
                            )
                    else:
                        merge_result = MergeResult(
                            repo_id=repo_id,
                            repo_name=repo.name,
                            strategy=strategy,
                            success=False,
                            message=git_result.message,
                            conflict_op=git_result.conflict.op if git_result.conflict else None,
                            conflict_files=git_result.conflict.files
                            if git_result.conflict
                            else None,
                        )
                        await self._events.publish(
                            MergeFailed(
                                workspace_id=workspace_id,
                                repo_id=repo_id,
                                error=git_result.message,
                                conflict_op=merge_result.conflict_op,
                                conflict_files=merge_result.conflict_files,
                            )
                        )
                except Exception as exc:
                    merge_result = MergeResult(
                        repo_id=repo_id,
                        repo_name=repo.name,
                        strategy=strategy,
                        success=False,
                        message=str(exc),
                    )
                    await self._events.publish(
                        MergeFailed(
                            workspace_id=workspace_id,
                            repo_id=repo_id,
                            error=str(exc),
                        )
                    )

        async with get_required_session(
            self._session_factory,
            error_message="Workspace service missing session factory for per-repo operations",
        ) as session:
            merge_type = (
                MergeType.PR if strategy == MergeStrategy.PULL_REQUEST else MergeType.DIRECT
            )
            merge_record = Merge(
                workspace_id=workspace_id,
                repo_id=repo_id,
                merge_type=merge_type,
                target_branch_name=workspace_repo.target_branch,
                merge_commit=merge_result.commit_sha if merge_type == MergeType.DIRECT else None,
                pr_url=merge_result.pr_url if merge_type == MergeType.PR else None,
                pr_status=(
                    MergeStatus.OPEN
                    if merge_type == MergeType.PR and merge_result.success
                    else MergeStatus.MERGED
                    if merge_result.success
                    else MergeStatus.CLOSED
                ),
                pr_merged_at=utc_now()
                if merge_type == MergeType.PR and merge_result.success
                else None,
                pr_merge_commit_sha=merge_result.commit_sha
                if merge_type == MergeType.PR and merge_result.success
                else None,
            )
            session.add(merge_record)
            await session.commit()

        return merge_result

    async def merge_all(
        self,
        workspace_id: str,
        *,
        strategy: MergeStrategy = MergeStrategy.DIRECT,
        skip_unchanged: bool = True,
        commit_message: str | None = None,
    ) -> list[MergeResult]:
        """Merge all repos in a workspace."""
        repos = await self.get_workspace_repos(workspace_id)
        results: list[MergeResult] = []

        for repo in repos:
            if skip_unchanged and not repo["has_changes"]:
                results.append(
                    MergeResult(
                        repo_id=repo["repo_id"],
                        repo_name=repo["repo_name"],
                        strategy=strategy,
                        success=True,
                        message="Skipped (no changes)",
                    )
                )
                continue
            results.append(
                await self.merge_repo(
                    workspace_id,
                    repo["repo_id"],
                    strategy=strategy,
                    commit_message=commit_message,
                )
            )

        return results

    async def create_pr(
        self,
        workspace_id: str,
        repo_id: str,
        *,
        title: str,
        body: str,
        draft: bool = False,
    ) -> str:
        """Create a pull request for a specific repo."""
        del draft
        result = await self.merge_repo(
            workspace_id,
            repo_id,
            strategy=MergeStrategy.PULL_REQUEST,
            pr_title=title,
            pr_body=body,
        )
        if not result.pr_url:
            raise RuntimeError("PR creation failed")
        return result.pr_url
