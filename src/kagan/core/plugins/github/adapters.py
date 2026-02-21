"""GitHub plugin adapters: core gateway and gh CLI client."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core.plugins.github.gh_adapter import (
    GH_CLI_NOT_AVAILABLE,
    GhIssue,
    GhPullRequest,
    GhRepoView,
    PreflightError,
    build_connection_metadata,
    parse_gh_issue_list,
    resolve_gh_cli,
    run_gh_api_pr_review_comments,
    run_gh_auth_status,
    run_gh_issue_close,
    run_gh_issue_label_add,
    run_gh_issue_label_remove,
    run_gh_issue_list,
    run_gh_issue_reopen,
    run_gh_pr_checks,
    run_gh_pr_create,
    run_gh_pr_merge,
    run_gh_pr_view,
    run_git_push_branch,
    run_preflight_checks,
)
from kagan.core.plugins.github.lease import (
    LeaseAcquireResult,
    LeaseReleaseResult,
    LeaseState,
    acquire_lease,
    get_lease_state,
    release_lease,
)

if TYPE_CHECKING:
    from kagan.core.adapters.db.schema import Project, Repo, Task, Workspace
    from kagan.core.bootstrap import AppContext


class AppContextCoreGateway:
    """Bridge from GitHub use cases to core services."""

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx

    async def get_project(self, project_id: str) -> Project | None:
        return await self._ctx.project_service.get_project(project_id)

    async def get_project_repos(self, project_id: str) -> list[Repo]:
        return await self._ctx.project_service.get_project_repos(project_id)

    async def get_task(self, task_id: str) -> Task | None:
        return await self._ctx.task_service.get_task(task_id)

    async def create_task(self, *, title: str, description: str, project_id: str) -> Task:
        return await self._ctx.task_service.create_task(
            title=title,
            description=description,
            project_id=project_id,
        )

    async def update_task_fields(self, task_id: str, **fields: Any) -> None:
        await self._ctx.task_service.update_fields(task_id, **fields)

    async def list_workspaces(self, *, task_id: str) -> list[Workspace]:
        return await self._ctx.workspace_service.list_workspaces(task_id=task_id)

    async def get_workspace_repos(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self._ctx.workspace_service.get_workspace_repos(workspace_id)

    async def update_repo_scripts(self, repo_id: str, updates: dict[str, str]) -> None:
        await self._ctx.project_service.update_repo_script_values(repo_id, updates)

    def is_auto_commit_changes_enabled(self) -> bool:
        general = getattr(getattr(self._ctx, "config", None), "general", None)
        return bool(getattr(general, "auto_commit_changes", False))


class GhCliClientAdapter:
    """Adapter that executes GitHub operations via gh CLI."""

    def build_connection_metadata(
        self,
        repo_view: GhRepoView,
        username: str | None = None,
    ) -> dict[str, Any]:
        return build_connection_metadata(repo_view, username=username)

    def run_preflight_checks(
        self,
        repo_path: str,
    ) -> tuple[GhRepoView | None, PreflightError | None]:
        return run_preflight_checks(repo_path)

    def resolve_gh_cli_path(self) -> tuple[str | None, dict[str, Any] | None]:
        cli_info = resolve_gh_cli()
        if not cli_info.available or not cli_info.path:
            return None, {
                "success": False,
                "code": GH_CLI_NOT_AVAILABLE,
                "message": "GitHub CLI (gh) is not available",
                "hint": "Install gh CLI: https://cli.github.com/",
            }
        return cli_info.path, None

    def run_gh_auth_username(self, gh_path: str) -> str | None:
        auth_status = run_gh_auth_status(gh_path)
        return auth_status.username if auth_status.authenticated else None

    def run_gh_issue_list(
        self,
        gh_path: str,
        repo_path: str,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        return run_gh_issue_list(gh_path, repo_path, state="all")

    def parse_issue_list(self, raw_issues: list[dict[str, Any]]) -> list[GhIssue]:
        return parse_gh_issue_list(raw_issues)

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
        return run_gh_pr_create(
            gh_path,
            repo_path,
            head_branch=head_branch,
            base_branch=base_branch,
            title=title,
            body=body,
            draft=draft,
        )

    def run_git_push_branch(
        self,
        repo_path: str,
        branch: str,
    ) -> str | None:
        return run_git_push_branch(repo_path, branch)

    def run_gh_pr_view(
        self,
        gh_path: str,
        repo_path: str,
        pr_number: int,
    ) -> tuple[GhPullRequest | None, str | None]:
        return run_gh_pr_view(gh_path, repo_path, pr_number)

    def run_gh_issue_close(
        self,
        gh_path: str,
        repo_path: str,
        issue_number: int,
    ) -> tuple[bool, str | None]:
        return run_gh_issue_close(gh_path, repo_path, issue_number)

    def run_gh_issue_reopen(
        self,
        gh_path: str,
        repo_path: str,
        issue_number: int,
    ) -> tuple[bool, str | None]:
        return run_gh_issue_reopen(gh_path, repo_path, issue_number)

    def run_gh_issue_label_add(
        self,
        gh_path: str,
        repo_path: str,
        issue_number: int,
        label: str,
    ) -> tuple[bool, str | None]:
        return run_gh_issue_label_add(gh_path, repo_path, issue_number, label)

    def run_gh_issue_label_remove(
        self,
        gh_path: str,
        repo_path: str,
        issue_number: int,
        label: str,
    ) -> tuple[bool, str | None]:
        return run_gh_issue_label_remove(gh_path, repo_path, issue_number, label)

    def acquire_lease(
        self,
        gh_path: str,
        repo_path: str,
        owner: str,
        repo_name: str,
        issue_number: int,
        *,
        github_user: str | None,
        force_takeover: bool,
    ) -> LeaseAcquireResult:
        return acquire_lease(
            gh_path,
            repo_path,
            owner,
            repo_name,
            issue_number,
            github_user=github_user,
            force_takeover=force_takeover,
        )

    def release_lease(
        self,
        gh_path: str,
        repo_path: str,
        owner: str,
        repo_name: str,
        issue_number: int,
    ) -> LeaseReleaseResult:
        return release_lease(
            gh_path,
            repo_path,
            owner,
            repo_name,
            issue_number,
        )

    def get_lease_state(
        self,
        gh_path: str,
        repo_path: str,
        owner: str,
        repo_name: str,
        issue_number: int,
    ) -> tuple[LeaseState | None, str | None]:
        return get_lease_state(
            gh_path,
            repo_path,
            owner,
            repo_name,
            issue_number,
        )

    def run_gh_pr_checks(
        self,
        gh_path: str,
        repo_path: str,
        pr_number: int,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        return run_gh_pr_checks(gh_path, repo_path, pr_number)

    def run_gh_pr_merge(
        self,
        gh_path: str,
        repo_path: str,
        pr_number: int,
        *,
        merge_method: str = "merge",
    ) -> tuple[bool, str | None]:
        return run_gh_pr_merge(gh_path, repo_path, pr_number, merge_method=merge_method)

    def run_gh_api_pr_review_comments(
        self,
        gh_path: str,
        repo_path: str,
        owner: str,
        repo: str,
        pr_number: int,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        return run_gh_api_pr_review_comments(gh_path, repo_path, owner, repo, pr_number)


__all__ = ["AppContextCoreGateway", "GhCliClientAdapter"]
