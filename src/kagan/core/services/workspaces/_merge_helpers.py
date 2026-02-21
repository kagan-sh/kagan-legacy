"""Internal merge-ops and DB helpers extracted from service.py.

WorkspaceInternalsMixin provides helper methods used by
WorkspaceServiceImpl. It expects the same instance attributes.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from sqlmodel import col, select

from kagan.core.adapters.db.session import get_session
from kagan.core.adapters.process import ProcessExecutionError, ProcessRetryPolicy, run_exec_checked
from kagan.core.services.workspaces.constants import (
    WORKSPACE_MERGE_FAILURE_MESSAGE_MAX_CHARS,
    WORKSPACE_MERGE_OVERLAP_PREVIEW_FILE_COUNT,
    WORKSPACE_MERGE_REBASE_HINT_CAP,
    WORKSPACE_MERGE_RISK_COMMIT_THRESHOLD,
    WORKSPACE_MERGE_RISK_FILE_THRESHOLD,
    WORKSPACE_MERGE_RISK_OVERLAP_SCORE,
    WORKSPACE_MERGE_RISK_REPO_CHANGE_THRESHOLD,
)

if TYPE_CHECKING:
    from kagan.core.adapters.db.schema import Repo, WorkspaceRepo
    from kagan.core.adapters.db.schema import Workspace as DbWorkspace
    from kagan.core.adapters.db.session import AsyncSessionFactory
    from kagan.core.adapters.git.worktrees import GitWorktreeProtocol
    from kagan.core.services.types import TaskLike
    from kagan.core.services.workspaces.service import MergeResult, MergeRisk


class WorkspaceInternalsMixin:
    """Mixin containing internal helpers for WorkspaceServiceImpl.

    Expects the following instance attributes (set by WorkspaceServiceImpl):
    - ``_session_factory``: AsyncSessionFactory
    - ``_git``: GitWorktreeProtocol
    - ``_merge_worktrees_dir``: Path
    - ``_rebase_first_hints``: dict[str, int]
    """

    _session_factory: AsyncSessionFactory
    _git: GitWorktreeProtocol
    _merge_worktrees_dir: Path
    _rebase_first_hints: dict[str, int]

    # ------------------------------------------------------------------
    # Merge risk & heuristics
    # ------------------------------------------------------------------

    @staticmethod
    def _is_remote_target(target_branch: str) -> bool:
        return target_branch.startswith("origin/") or target_branch.startswith("refs/remotes/")

    @staticmethod
    def _summarize_failures(
        failures: list[MergeResult],
        *,
        overlap_files: tuple[str, ...] = (),
    ) -> str:
        message = "; ".join(f"{result.repo_name}: {result.message}" for result in failures)
        hints: list[str] = []
        has_conflicts = any(
            (result.conflict_files and len(result.conflict_files) > 0)
            or "conflict" in result.message.lower()
            for result in failures
        )
        if has_conflicts:
            hints.append("Tip: run review rebase, resolve conflicts, then merge again")
        if overlap_files:
            preview = ", ".join(overlap_files[:WORKSPACE_MERGE_OVERLAP_PREVIEW_FILE_COUNT])
            suffix = (
                "..." if len(overlap_files) > WORKSPACE_MERGE_OVERLAP_PREVIEW_FILE_COUNT else ""
            )
            hints.append(f"Potential overlap with base changes: {preview}{suffix}")
        if hints:
            message = f"{message}. {' '.join(hints)}"
        return message[:WORKSPACE_MERGE_FAILURE_MESSAGE_MAX_CHARS]

    @staticmethod
    def _should_retry_after_rebase(failures: list[MergeResult]) -> bool:
        return all("rebase required" in result.message.lower() for result in failures)

    async def _assess_merge_risk(
        self,
        task: TaskLike,
        workspace_id: str,
        base_branch: str,
    ) -> MergeRisk:
        from kagan.core.services.workspaces.service import MergeRisk

        repos = await self.get_workspace_repos(workspace_id)  # type: ignore[attr-defined]
        changed_repo_count = sum(1 for repo in repos if repo.get("has_changes"))
        commits = await self.get_commit_log(task.id, base_branch)  # type: ignore[attr-defined]
        changed_files = await self.get_files_changed(task.id, base_branch)  # type: ignore[attr-defined]
        base_changed_files = await self.get_files_changed_on_base(  # type: ignore[attr-defined]
            task.id, base_branch
        )
        overlap_files = tuple(sorted(set(changed_files).intersection(base_changed_files)))

        score = 0
        if changed_repo_count > WORKSPACE_MERGE_RISK_REPO_CHANGE_THRESHOLD:
            score += 1
        if len(commits) >= WORKSPACE_MERGE_RISK_COMMIT_THRESHOLD:
            score += 1
        if len(changed_files) >= WORKSPACE_MERGE_RISK_FILE_THRESHOLD:
            score += 1
        if overlap_files:
            score += WORKSPACE_MERGE_RISK_OVERLAP_SCORE

        return MergeRisk(
            score=score,
            overlap_files=overlap_files,
            commit_count=len(commits),
            changed_repo_count=changed_repo_count,
            changed_file_count=len(changed_files),
        )

    def _should_rebase_before_merge(self, base_branch: str, risk: MergeRisk) -> bool:
        if self._rebase_first_hints.get(base_branch, 0) > 0:
            return True
        return risk.high

    def _note_rebase_hint(self, base_branch: str) -> None:
        self._rebase_first_hints[base_branch] = min(
            self._rebase_first_hints.get(base_branch, 0) + 1,
            WORKSPACE_MERGE_REBASE_HINT_CAP,
        )

    def _cooldown_rebase_hint(self, base_branch: str) -> None:
        hint = self._rebase_first_hints.get(base_branch, 0)
        if hint <= 1:
            self._rebase_first_hints.pop(base_branch, None)
            return
        self._rebase_first_hints[base_branch] = hint - 1

    # ------------------------------------------------------------------
    # PR creation
    # ------------------------------------------------------------------

    async def _create_pr(
        self,
        repo_path: str,
        branch: str,
        target: str,
        title: str,
        body: str,
    ) -> str:
        """Create PR using gh CLI."""
        retry_policy = ProcessRetryPolicy(
            max_attempts=2,
            delay_seconds=0.2,
            retry_on_timeout=True,
            retry_on_nonzero=False,
            retry_on_oserror=True,
        )
        try:
            result = await run_exec_checked(
                "gh",
                "pr",
                "create",
                "--repo",
                repo_path,
                "--head",
                branch,
                "--base",
                target,
                "--title",
                title,
                "--body",
                body,
                retry_policy=retry_policy,
            )
        except ProcessExecutionError as exc:
            raise RuntimeError(f"Failed to create PR: {exc}") from exc
        return result.stdout_text().strip()

    # ------------------------------------------------------------------
    # Internal merge-ops helpers
    # ------------------------------------------------------------------

    async def _ensure_merge_worktree(
        self, repo_id: str, base_branch: str, workspace: DbWorkspace
    ) -> Path:
        merge_path = self._merge_worktrees_dir / repo_id
        merge_path.parent.mkdir(parents=True, exist_ok=True)

        if merge_path.exists():
            return merge_path

        worktree_path = await self.get_agent_working_dir(workspace.id)  # type: ignore[attr-defined]
        repo_root = self._resolve_repo_root(worktree_path)
        await self._git.run_git(
            "worktree",
            "add",
            "-B",
            self._merge_branch_name(repo_id),
            str(merge_path),
            base_branch,
            cwd=repo_root,
        )
        return merge_path

    async def _reset_merge_worktree(self, merge_path: Path, base_branch: str) -> Path:
        await self._git.run_git("fetch", "origin", base_branch, cwd=merge_path, check=False)

        base_ref = base_branch
        if await self._ref_exists(f"refs/remotes/origin/{base_branch}", cwd=merge_path):
            base_ref = f"origin/{base_branch}"

        await self._git.run_git(
            "checkout",
            self._merge_branch_name(merge_path.name),
            cwd=merge_path,
        )
        await self._git.run_git("reset", "--hard", base_ref, cwd=merge_path)
        return merge_path

    async def _ref_exists(self, ref: str, cwd: Path) -> bool:
        stdout, _ = await self._git.run_git(
            "rev-parse",
            "--verify",
            "--quiet",
            ref,
            cwd=cwd,
            check=False,
        )
        return bool(stdout.strip())

    async def _merge_in_progress(self, cwd: Path) -> bool:
        stdout, _ = await self._git.run_git(
            "rev-parse",
            "-q",
            "--verify",
            "MERGE_HEAD",
            cwd=cwd,
            check=False,
        )
        return bool(stdout.strip())

    async def _rebase_in_progress(self, cwd: Path) -> bool:
        stdout, _ = await self._git.run_git(
            "rev-parse",
            "-q",
            "--verify",
            "REBASE_HEAD",
            cwd=cwd,
            check=False,
        )
        if stdout.strip():
            return True

        for path_name in ("rebase-apply", "rebase-merge"):
            path_out, _ = await self._git.run_git(
                "rev-parse",
                "--git-path",
                path_name,
                cwd=cwd,
                check=False,
            )
            if path_out.strip() and Path(path_out.strip()).exists():
                return True

        return False

    async def _collect_rebase_conflicts(self, cwd: Path, repo_name: str) -> list[str]:
        stdout, _ = await self._git.run_git(
            "diff",
            "--name-only",
            "--diff-filter=U",
            cwd=cwd,
            check=False,
        )
        files = [line.strip() for line in stdout.splitlines() if line.strip()]
        if not files:
            status_out, _ = await self._git.run_git("status", "--porcelain", cwd=cwd, check=False)
            files = []
            for line in status_out.splitlines():
                if line.startswith(("UU ", "AA ", "DD ", "AU ", "UA ", "DU ", "UD ")):
                    files.append(line[3:].strip())

        return [f"{repo_name}:{path}" for path in files]

    def _resolve_repo_root(self, worktree_path: Path) -> Path:
        git_file = worktree_path / ".git"
        if not git_file.exists():
            return worktree_path
        content = git_file.read_text().strip()
        if not content.startswith("gitdir:"):
            return worktree_path
        git_dir = content.split(":", 1)[1].strip()
        return Path(git_dir).parent.parent.parent

    async def _has_remote(self, cwd: Path) -> bool:
        """Check if repo has an origin remote."""
        stdout, _ = await self._git.run_git("remote", cwd=cwd, check=False)
        return "origin" in {r.strip() for r in stdout.splitlines() if r.strip()}

    def _merge_branch_name(self, repo_id: str) -> str:
        return f"kagan/merge-worktree-{repo_id[:8]}"

    # ------------------------------------------------------------------
    # Internal DB helpers
    # ------------------------------------------------------------------

    async def _get_workspace_repo_rows(self, workspace_id: str) -> list[tuple[WorkspaceRepo, Repo]]:
        from kagan.core.adapters.db.schema import Repo, WorkspaceRepo

        async with get_session(self._session_factory) as session:
            result = await session.execute(
                select(WorkspaceRepo, Repo)
                .join(Repo)
                .where(WorkspaceRepo.workspace_id == workspace_id)
                .order_by(col(WorkspaceRepo.created_at).asc())
            )
            rows = result.all()
            return [(row[0], row[1]) for row in rows]

    async def _get_workspace(self, workspace_id: str) -> DbWorkspace | None:
        from kagan.core.adapters.db.schema import Workspace

        async with get_session(self._session_factory) as session:
            return await session.get(Workspace, workspace_id)

    async def _get_latest_workspace_for_task(self, task_id: str) -> DbWorkspace | None:
        from kagan.core.adapters.db.schema import Workspace

        async with get_session(self._session_factory) as session:
            result = await session.execute(
                select(Workspace)
                .where(Workspace.task_id == task_id)
                .order_by(col(Workspace.created_at).desc())
            )
            return result.scalars().first()

    async def _get_primary_workspace_repo(self, workspace_id: str) -> WorkspaceRepo | None:
        from kagan.core.adapters.db.schema import (
            ProjectRepo,
            Workspace,
            WorkspaceRepo,
        )

        async with get_session(self._session_factory) as session:
            workspace = await session.get(Workspace, workspace_id)
            if workspace is None:
                return None

            result = await session.execute(
                select(WorkspaceRepo)
                .join(
                    ProjectRepo,
                    col(ProjectRepo.repo_id) == col(WorkspaceRepo.repo_id),
                )
                .where(WorkspaceRepo.workspace_id == workspace_id)
                .where(ProjectRepo.project_id == workspace.project_id)
                .order_by(
                    col(ProjectRepo.is_primary).desc(),
                    col(ProjectRepo.display_order).asc(),
                    col(WorkspaceRepo.created_at).asc(),
                )
            )
            primary = result.scalars().first()
            if primary:
                return primary

            result = await session.execute(
                select(WorkspaceRepo)
                .where(WorkspaceRepo.workspace_id == workspace_id)
                .order_by(col(WorkspaceRepo.created_at).asc())
            )
            return result.scalars().first()


__all__ = ["WorkspaceInternalsMixin"]
