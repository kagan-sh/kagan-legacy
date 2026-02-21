"""Project and repository management.

Covers:
- Create project with optional repo path
- Resolve existing project by repo path or create if missing
- List and open projects
- Repo association with project and branch setup
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.core.adapters.db.schema import Task
from kagan.core.adapters.process import ProcessResult
from kagan.core.domain.enums import TaskStatus

if TYPE_CHECKING:
    from pathlib import Path

    import pytest

    from tests.helpers.fixtures.core import RepoWithProjectFixture


class TestProjectCreation:
    """Creating and listing projects."""

    async def test_create_project_and_retrieve(self, state_manager) -> None:
        # ensure_test_project creates a project; verify it has an ID
        project_id = state_manager.default_project_id
        assert project_id is not None
        assert isinstance(project_id, str)
        assert len(project_id) > 0

    async def test_ensure_project_is_idempotent(self, state_manager) -> None:
        id1 = await state_manager.ensure_test_project("Test Project")
        id2 = await state_manager.ensure_test_project("Test Project")
        assert id1 == id2


class TestRepoAssociation:
    """Linking repos to projects and branch setup."""

    async def test_repo_linked_to_project(self, repo_with_project: RepoWithProjectFixture) -> None:
        repos = await repo_with_project.repo_repo.list_for_project(repo_with_project.project_id)
        assert len(repos) >= 1
        assert any(str(r.path) == str(repo_with_project.repo_path) for r in repos)

    async def test_repo_default_branch_set(self, repo_with_project: RepoWithProjectFixture) -> None:
        fetched = await repo_with_project.repo_repo.get(repo_with_project.repo.id)
        assert fetched is not None
        assert fetched.default_branch == "main"
        # branch_configured is stored in scripts dict
        assert fetched.scripts.get("kagan.branch_configured") == "true"

    async def test_get_or_create_existing_repo(
        self, repo_with_project: RepoWithProjectFixture
    ) -> None:
        same_repo, created = await repo_with_project.repo_repo.get_or_create(
            repo_with_project.repo_path,
            default_branch="main",
        )
        assert same_repo.id == repo_with_project.repo.id
        assert created is False


class TestProjectScopedTasks:
    """Tasks belong to a project scope."""

    async def test_task_created_under_project(
        self, repo_with_project: RepoWithProjectFixture
    ) -> None:
        task = Task.create(
            title="Scoped task",
            project_id=repo_with_project.project_id,
            status=TaskStatus.BACKLOG,
        )
        created = await repo_with_project.task_repo.create(task)
        assert created.project_id == repo_with_project.project_id

        all_tasks = await repo_with_project.task_repo.get_all(
            project_id=repo_with_project.project_id
        )
        assert any(t.id == created.id for t in all_tasks)


class TestGitInitBootstrap:
    """Git bootstrap behavior used by project creation flows."""

    async def test_init_git_repo_uses_non_interactive_commit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from kagan.core import git_utils

        repo_path = tmp_path / "new-project"
        repo_path.mkdir()

        calls: list[tuple[str, ...]] = []

        async def fake_run_git(
            *args: str,
            repo_root: Path | None = None,
            timeout: float | None = None,
        ) -> ProcessResult:
            del repo_root, timeout
            calls.append(args)
            if args == ("--version",):
                return ProcessResult(0, b"git version 2.45.0\n", b"")
            if args == ("config", "--get", "user.name"):
                return ProcessResult(0, b"Test User\n", b"")
            if args == ("config", "--get", "user.email"):
                return ProcessResult(0, b"test@example.com\n", b"")
            if args == ("rev-parse", "--is-inside-work-tree"):
                return ProcessResult(1, b"", b"fatal: not a git repository")
            if args == ("init", "-b", "main"):
                return ProcessResult(0, b"", b"")
            if args == ("add", "-f", ".gitignore"):
                return ProcessResult(0, b"", b"")
            if args[:3] == ("-c", "commit.gpgsign=false", "commit"):
                return ProcessResult(0, b"", b"")
            return ProcessResult(0, b"", b"")

        monkeypatch.setattr(git_utils, "_run_git", fake_run_git)

        result = await git_utils.init_git_repo(repo_path, base_branch="main")

        assert result.success is True
        assert (
            "-c",
            "commit.gpgsign=false",
            "commit",
            "--no-verify",
            "-m",
            "Initial commit (kagan)",
        ) in calls

    async def test_init_git_repo_surfaces_timeout_as_error(
        self,
        monkeypatch: pytest.MonkeyPatch,
        tmp_path: Path,
    ) -> None:
        from kagan.core import git_utils

        repo_path = tmp_path / "timed-out-project"
        repo_path.mkdir()

        async def fake_run_git(
            *args: str,
            repo_root: Path | None = None,
            timeout: float | None = None,
        ) -> ProcessResult:
            del repo_root, timeout
            if args == ("--version",):
                return ProcessResult(0, b"git version 2.45.0\n", b"")
            if args == ("config", "--get", "user.name"):
                return ProcessResult(0, b"Test User\n", b"")
            if args == ("config", "--get", "user.email"):
                return ProcessResult(0, b"test@example.com\n", b"")
            if args == ("rev-parse", "--is-inside-work-tree"):
                return ProcessResult(1, b"", b"fatal: not a git repository")
            if args == ("init", "-b", "main"):
                return ProcessResult(0, b"", b"")
            if args == ("add", "-f", ".gitignore"):
                return ProcessResult(0, b"", b"")
            if args[:3] == ("-c", "commit.gpgsign=false", "commit"):
                raise TimeoutError
            return ProcessResult(0, b"", b"")

        monkeypatch.setattr(git_utils, "_run_git", fake_run_git)

        result = await git_utils.init_git_repo(repo_path, base_branch="main")

        assert result.success is False
        assert result.error is not None
        assert result.error.error_type == "commit_failed"
        assert "timed out" in (result.error.details or "").lower()
