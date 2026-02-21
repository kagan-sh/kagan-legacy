"""GitHub auto-PR defaults for review transitions."""

from __future__ import annotations

import json
from types import SimpleNamespace

from kagan.core.plugins.github.gh_adapter import GITHUB_CONNECTION_KEY, GhPullRequest
from kagan.core.plugins.github.models import AutoCreateReviewPrInput, CreatePrForTaskInput
from kagan.core.plugins.github.use_cases import (
    AUTO_PR_CREATED,
    AUTO_PR_SKIPPED,
    GitHubPluginUseCases,
)


class _CoreGatewayStub:
    def __init__(
        self,
        *,
        repo: SimpleNamespace,
        task: SimpleNamespace,
        auto_commit_changes_enabled: bool = True,
    ) -> None:
        self._repo = repo
        self._task = task
        self._workspace = SimpleNamespace(id="ws-1", branch_name="task-123")
        self._auto_commit_changes_enabled = auto_commit_changes_enabled

    async def get_project(self, project_id: str) -> object | None:
        return object() if project_id == "proj-1" else None

    async def get_project_repos(self, project_id: str) -> list[SimpleNamespace]:
        return [self._repo] if project_id == "proj-1" else []

    async def get_task(self, task_id: str) -> SimpleNamespace | None:
        if task_id == self._task.id:
            return self._task
        return None

    async def list_workspaces(self, *, task_id: str) -> list[SimpleNamespace]:
        if task_id == self._task.id:
            return [self._workspace]
        return []

    async def get_workspace_repos(self, workspace_id: str) -> list[dict[str, object]]:
        if workspace_id != self._workspace.id:
            return []
        return [{"repo_id": self._repo.id, "worktree_path": "/tmp/worktree"}]

    async def update_repo_scripts(self, repo_id: str, updates: dict[str, str]) -> None:
        if repo_id == self._repo.id:
            self._repo.scripts.update(updates)

    def is_auto_commit_changes_enabled(self) -> bool:
        return self._auto_commit_changes_enabled


class _GhStub:
    def __init__(self) -> None:
        self.push_calls: list[tuple[str, str]] = []
        self.pr_create_calls: list[dict[str, object]] = []

    def resolve_gh_cli_path(self) -> tuple[str | None, dict[str, object] | None]:
        return ("gh", None)

    def run_git_push_branch(self, repo_path: str, branch: str) -> str | None:
        self.push_calls.append((repo_path, branch))
        return None

    def run_gh_pr_create(
        self,
        gh_path: str,
        repo_path: str,
        *,
        head_branch: str,
        base_branch: str,
        title: str,
        body: str,
        draft: bool,
    ) -> tuple[GhPullRequest | None, str | None]:
        self.pr_create_calls.append(
            {
                "gh_path": gh_path,
                "repo_path": repo_path,
                "head_branch": head_branch,
                "base_branch": base_branch,
                "title": title,
                "body": body,
                "draft": draft,
            }
        )
        return (
            GhPullRequest(
                number=123,
                title=title,
                state="OPEN",
                url="https://github.com/user/repo/pull/123",
                head_branch=head_branch,
                base_branch=base_branch,
                is_draft=draft,
                mergeable=None,
            ),
            None,
        )


def _connected_repo() -> SimpleNamespace:
    scripts = {
        GITHUB_CONNECTION_KEY: json.dumps(
            {
                "owner": "user",
                "repo": "repo",
                "full_name": "user/repo",
                "default_branch": "main",
            }
        )
    }
    return SimpleNamespace(
        id="repo-1",
        name="repo",
        path="/tmp/repo",
        scripts=scripts,
    )


async def test_create_pr_pushes_branch_and_uses_task_base_branch() -> None:
    task = SimpleNamespace(
        id="task-1",
        title="Implement feature",
        description="Details",
        base_branch="release/1.2",
    )
    repo = _connected_repo()
    core = _CoreGatewayStub(repo=repo, task=task)
    gh = _GhStub()
    use_cases = GitHubPluginUseCases(core, gh)

    result = await use_cases.create_pr_for_task(
        CreatePrForTaskInput(
            project_id="proj-1",
            task_id=task.id,
            title=task.title,
            draft=True,
        )
    )

    assert result["success"] is True
    assert gh.push_calls == [("/tmp/worktree", "task-123")]
    assert gh.pr_create_calls[0]["base_branch"] == "release/1.2"


async def test_auto_create_review_pr_does_not_require_linked_issue() -> None:
    task = SimpleNamespace(
        id="task-2",
        title="Auto review task",
        description="",
        base_branch=None,
    )
    repo = _connected_repo()
    core = _CoreGatewayStub(repo=repo, task=task)
    gh = _GhStub()
    use_cases = GitHubPluginUseCases(core, gh)

    result = await use_cases.auto_create_review_pr(
        AutoCreateReviewPrInput(task_id=task.id, project_id="proj-1")
    )

    assert result["success"] is True
    assert result["code"] == AUTO_PR_CREATED
    assert len(gh.pr_create_calls) == 1


async def test_auto_create_review_pr_skips_when_auto_commit_disabled() -> None:
    task = SimpleNamespace(
        id="task-3",
        title="Auto review task",
        description="",
        base_branch=None,
    )
    repo = _connected_repo()
    core = _CoreGatewayStub(repo=repo, task=task, auto_commit_changes_enabled=False)
    gh = _GhStub()
    use_cases = GitHubPluginUseCases(core, gh)

    result = await use_cases.auto_create_review_pr(
        AutoCreateReviewPrInput(task_id=task.id, project_id="proj-1")
    )

    assert result["success"] is True
    assert result["code"] == AUTO_PR_SKIPPED
    assert not gh.push_calls
    assert not gh.pr_create_calls
