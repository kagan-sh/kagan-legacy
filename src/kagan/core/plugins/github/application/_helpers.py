"""Private helper functions extracted from use_cases.py."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any

from kagan.core.plugins.github.domain.repo_state import (
    encode_pr_mapping_update,
    load_connection_state,
    load_pr_mapping_state,
    resolve_owner_repo,
)
from kagan.core.plugins.github.gh_adapter import (
    GH_PR_MERGE_FAILED,
    GH_PR_NOT_FOUND,
    GH_PROJECT_REQUIRED,
    GH_REPO_METADATA_INVALID,
    GH_REPO_REQUIRED,
)
from kagan.core.time import utc_now

if TYPE_CHECKING:
    from kagan.core.plugins.github.adapters.core_gateway import AppContextCoreGateway
    from kagan.core.plugins.github.adapters.gh_cli_client import GhCliClientAdapter
    from kagan.core.plugins.github.sync import IssueMapping


# ── Error codes (imported from use_cases to avoid circular deps) ─────
GH_NOT_CONNECTED = "GH_NOT_CONNECTED"
GH_WORKSPACE_REQUIRED = "GH_WORKSPACE_REQUIRED"
REVIEW_GUARDRAIL_CHECK_FAILED = "REVIEW_GUARDRAIL_CHECK_FAILED"


# ── Static helpers ───────────────────────────────────────────────────


def error(code: str, message: str, hint: str) -> dict[str, Any]:
    return {"success": False, "code": code, "message": message, "hint": hint}


def repo_identifier(repo: Any) -> str:
    repo_id = repo.id if hasattr(repo, "id") else None
    if isinstance(repo_id, str) and repo_id:
        return repo_id
    repo_name = repo.name if hasattr(repo, "name") else None
    if isinstance(repo_name, str) and repo_name:
        return repo_name
    return "<unknown-repo>"


def non_empty_str(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    return normalized if normalized else None


def coerce_positive_int(
    *,
    value: object,
    field_name: str,
    invalid_code: str,
) -> tuple[int | None, dict[str, Any] | None]:
    parsed_value: int | None = None
    if isinstance(value, bool):
        parsed_value = None
    elif isinstance(value, int):
        parsed_value = value
    elif isinstance(value, str):
        raw_value = value.strip()
        if raw_value:
            try:
                parsed_value = int(raw_value)
            except ValueError:
                parsed_value = None

    if parsed_value is None or parsed_value <= 0:
        return None, error(
            invalid_code,
            f"{field_name} must be a positive integer",
            f"Provide a numeric {field_name} value like 123",
        )
    return parsed_value, None


def review_guardrail_check_failed(detail: str) -> dict[str, Any]:
    return {
        "allowed": False,
        "code": REVIEW_GUARDRAIL_CHECK_FAILED,
        "message": "REVIEW transition blocked: failed to verify GitHub guardrails.",
        "hint": f"Resolve GitHub plugin health and retry. Details: {detail}",
    }


def build_reconcile_message(pr_number: int, pr_state: str, task_changed: bool) -> str:
    """Build a human-readable reconcile result message."""
    if pr_state == "MERGED":
        if task_changed:
            return f"PR #{pr_number} merged. Task moved to DONE."
        return f"PR #{pr_number} merged. Task already DONE."
    if pr_state == "CLOSED":
        if task_changed:
            return f"PR #{pr_number} closed without merge. Task moved to IN_PROGRESS."
        return f"PR #{pr_number} closed without merge. Task status unchanged."
    return f"PR #{pr_number} is open. No task status change."


# ── Async helpers (receive gateway/client as parameters) ─────────────


async def resolve_workspace_for_repo(
    core: AppContextCoreGateway,
    *,
    task_id: str,
    repo: Any,
    workspaces: list[Any],
) -> tuple[Any | None, dict[str, Any] | None]:
    repo_id = repo.id if hasattr(repo, "id") else None
    if not isinstance(repo_id, str) or not repo_id:
        repo_label = repo_identifier(repo)
        return None, error(
            GH_REPO_REQUIRED,
            f"Repository {repo_label} has no stable repo_id",
            "Reconnect repository metadata and retry PR creation.",
        )

    matching_workspaces: list[Any] = []
    for workspace in workspaces:
        workspace_repos = await core.get_workspace_repos(workspace.id)
        for workspace_repo in workspace_repos:
            if not isinstance(workspace_repo, dict):
                continue
            workspace_repo_id = workspace_repo.get("repo_id")
            if isinstance(workspace_repo_id, str) and workspace_repo_id == repo_id:
                matching_workspaces.append(workspace)
                break

    if not matching_workspaces:
        return None, error(
            GH_WORKSPACE_REQUIRED,
            f"Task has no workspace for repo_id {repo_id}",
            "Create a workspace for this repo before creating a PR.",
        )

    if len(matching_workspaces) > 1:
        workspace_ids = ", ".join(
            str(getattr(workspace, "id", "")) for workspace in matching_workspaces
        )
        return None, error(
            GH_WORKSPACE_REQUIRED,
            f"Task has multiple workspaces for repo_id {repo_id}: {workspace_ids}",
            "Prune stale workspaces and retry PR creation.",
        )

    return matching_workspaces[0], None


async def resolve_workspace_owner_candidates(
    core: AppContextCoreGateway,
    *,
    task_id: str,
    connected_repos: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    workspaces = await core.list_workspaces(task_id=task_id)
    workspace_repo_ids: set[str] = set()
    for workspace in workspaces:
        workspace_repos = await core.get_workspace_repos(workspace.id)
        for workspace_repo in workspace_repos:
            if not isinstance(workspace_repo, dict):
                continue
            repo_id = workspace_repo.get("repo_id")
            if isinstance(repo_id, str) and repo_id:
                workspace_repo_ids.add(repo_id)

    if not workspace_repo_ids:
        return []

    owner_candidates: list[dict[str, Any]] = []
    for repo_ctx in connected_repos:
        repo = repo_ctx["repo"]
        repo_id = repo.id if hasattr(repo, "id") else None
        if isinstance(repo_id, str) and repo_id in workspace_repo_ids:
            owner_candidates.append(repo_ctx)
    return owner_candidates


async def resolve_connect_target(
    core: AppContextCoreGateway,
    project_id: str | None,
    repo_id: str | None,
) -> tuple[Any | None, dict[str, Any] | None]:
    project_id = non_empty_str(project_id)
    repo_id = non_empty_str(repo_id)
    if not project_id:
        return None, error(
            GH_PROJECT_REQUIRED,
            "project_id is required",
            "Provide a valid project_id parameter",
        )

    project = await core.get_project(project_id)
    if not project:
        return None, error(
            GH_PROJECT_REQUIRED,
            f"Project not found: {project_id}",
            "Verify the project_id exists",
        )

    repos = await core.get_project_repos(project_id)
    if not repos:
        return None, error(
            GH_REPO_REQUIRED,
            "Project has no repositories",
            "Add a repository to the project first",
        )

    if len(repos) == 1:
        target_repo = repos[0]
        target_repo_id = target_repo.id if hasattr(target_repo, "id") else None
        if repo_id and repo_id != target_repo_id:
            expected = target_repo_id if isinstance(target_repo_id, str) else "<unknown>"
            return None, error(
                GH_REPO_REQUIRED,
                f"Repo not found in project: {repo_id}",
                f"Project has a single repo ({expected}). Use that repo_id or omit repo_id.",
            )
        return target_repo, None

    if not repo_id:
        return None, error(
            GH_REPO_REQUIRED,
            "repo_id required for multi-repo projects",
            f"Project has {len(repos)} repos. Specify repo_id explicitly.",
        )

    target_repo = next((repo for repo in repos if repo.id == repo_id), None)
    if target_repo is None:
        return None, error(
            GH_REPO_REQUIRED,
            f"Repo not found in project: {repo_id}",
            "Verify the repo_id belongs to this project",
        )

    return target_repo, None


def resolve_connected_repo_context(
    repo: Any,
    *,
    require_owner_repo: bool = False,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    connection_state = load_connection_state(repo.scripts)
    if not connection_state.raw_value:
        return None, error(
            GH_NOT_CONNECTED,
            "Repository is not connected to GitHub",
            "Run connect_repo first to establish GitHub connection",
        )

    connection = connection_state.normalized
    if connection is None:
        return None, error(
            GH_REPO_METADATA_INVALID,
            "Stored GitHub connection metadata is invalid",
            "Reconnect the repository using connect_repo.",
        )

    context: dict[str, Any] = {"connection": connection}
    if require_owner_repo:
        owner_repo = resolve_owner_repo(connection)
        if owner_repo is None:
            return None, error(
                GH_REPO_METADATA_INVALID,
                "Stored GitHub connection metadata is incomplete",
                "Reconnect the repository to refresh owner/repo metadata.",
            )
        owner, repo_name = owner_repo
        context["owner"] = owner
        context["repo_name"] = repo_name

    return context, None


async def load_mapped_tasks(
    core: AppContextCoreGateway,
    mapping: IssueMapping,
) -> dict[str, dict[str, Any]]:
    tasks: dict[str, dict[str, Any]] = {}
    for task_id in mapping.task_to_issue:
        task = await core.get_task(task_id)
        if task:
            tasks[task_id] = {
                "title": task.title,
                "status": task.status,
                "task_type": task.task_type,
            }
    return tasks


async def persist_pr_link(
    core: AppContextCoreGateway,
    repo: Any,
    task_id: str,
    pr_data: Any,
) -> None:
    pr_mapping = load_pr_mapping_state(repo.scripts)
    pr_mapping.link_pr(
        task_id=task_id,
        pr_number=pr_data.number,
        pr_url=pr_data.url,
        pr_state=pr_data.state,
        head_branch=pr_data.head_branch,
        base_branch=pr_data.base_branch,
        linked_at=utc_now().isoformat(),
    )
    await core.update_repo_scripts(repo.id, encode_pr_mapping_update(pr_mapping))


# ── PR operation helpers ─────────────────────────────────────────────

# Error codes used by PR operations (defined here to avoid circular imports)
GH_TASK_REQUIRED = "GH_TASK_REQUIRED"
GH_NO_LINKED_PR = "GH_NO_LINKED_PR"
GH_SYNC_FAILED = "GH_SYNC_FAILED"
PR_MERGED = "PR_MERGED"
PR_REVIEW_COMMENTS_FETCHED = "PR_REVIEW_COMMENTS_FETCHED"


async def merge_github_pr(
    core: AppContextCoreGateway,
    gh: GhCliClientAdapter,
    *,
    task_id_raw: str | None,
    project_id_raw: str | None,
    merge_method_raw: str | None,
) -> dict[str, Any]:
    """Merge the GitHub PR linked to a task."""
    task_id = non_empty_str(task_id_raw)
    project_id = non_empty_str(project_id_raw)
    if not task_id:
        return error(
            GH_TASK_REQUIRED,
            "task_id is required",
            "Provide the task ID to merge the PR for",
        )
    if not project_id:
        return error(
            GH_PROJECT_REQUIRED,
            "project_id is required",
            "Provide the project_id",
        )

    merge_method = merge_method_raw or "merge"
    if merge_method not in ("merge", "squash", "rebase"):
        return error(
            GH_PR_MERGE_FAILED,
            f"Invalid merge_method: {merge_method}",
            "Use one of: merge, squash, rebase",
        )

    try:
        repos = await core.get_project_repos(project_id)
    except Exception as exc:
        return error(
            GH_PR_MERGE_FAILED,
            f"Failed to fetch project repos: {exc}",
            "Check project_id is valid",
        )

    if not repos:
        return error(
            GH_NO_LINKED_PR,
            "No repos in project",
            "Add a repository to the project first",
        )

    for repo in repos:
        connection_state = load_connection_state(repo.scripts)
        if not connection_state.raw_value:
            continue
        if connection_state.normalized is None:
            continue

        pr_mapping = load_pr_mapping_state(repo.scripts)
        pr_link = pr_mapping.get_pr(task_id)
        if pr_link is None:
            continue

        # Check if PR is already merged
        if pr_link.pr_state == "MERGED":
            return {
                "success": True,
                "code": PR_MERGED,
                "message": (f"PR #{pr_link.pr_number} is already merged"),
                "pr_number": pr_link.pr_number,
                "already_merged": True,
            }

        gh_path, gh_error = gh.resolve_gh_cli_path()
        if gh_error is not None:
            return gh_error
        assert gh_path is not None

        # Verify current PR state from GitHub
        pr_data, view_error = await asyncio.to_thread(
            gh.run_gh_pr_view,
            gh_path,
            repo.path,
            pr_link.pr_number,
        )
        if view_error or pr_data is None:
            return {
                "success": False,
                "code": GH_PR_NOT_FOUND,
                "message": (f"Failed to fetch PR #{pr_link.pr_number}: {view_error or 'no data'}"),
                "hint": "Check network connectivity and GitHub access",
            }

        if pr_data.state == "MERGED":
            pr_mapping.update_pr_state(task_id, "MERGED")
            await core.update_repo_scripts(repo.id, encode_pr_mapping_update(pr_mapping))
            return {
                "success": True,
                "code": PR_MERGED,
                "message": (f"PR #{pr_link.pr_number} is already merged"),
                "pr_number": pr_link.pr_number,
                "already_merged": True,
            }

        if pr_data.state == "CLOSED":
            return {
                "success": False,
                "code": GH_PR_MERGE_FAILED,
                "message": (f"PR #{pr_link.pr_number} is closed and cannot be merged"),
                "hint": "Reopen the PR before attempting to merge",
            }

        success, merge_err = await asyncio.to_thread(
            gh.run_gh_pr_merge,
            gh_path,
            repo.path,
            pr_link.pr_number,
            merge_method=merge_method,
        )
        if not success:
            return {
                "success": False,
                "code": GH_PR_MERGE_FAILED,
                "message": (f"Failed to merge PR #{pr_link.pr_number}: {merge_err}"),
                "hint": ("Check for merge conflicts, required reviews, or branch protection rules"),
            }

        # Update stored PR state
        pr_mapping.update_pr_state(task_id, "MERGED")
        await core.update_repo_scripts(repo.id, encode_pr_mapping_update(pr_mapping))

        return {
            "success": True,
            "code": PR_MERGED,
            "message": (f"Merged PR #{pr_link.pr_number} via {merge_method}"),
            "pr_number": pr_link.pr_number,
            "merge_method": merge_method,
            "already_merged": False,
        }

    return error(
        GH_NO_LINKED_PR,
        f"Task {task_id} has no linked PR",
        "Use create_pr_for_task or link_pr_to_task first",
    )


async def get_pr_review_comments(
    core: AppContextCoreGateway,
    gh: GhCliClientAdapter,
    *,
    task_id_raw: str | None,
    project_id_raw: str | None,
) -> dict[str, Any]:
    """Fetch PR review comments for the PR linked to a task."""
    task_id = non_empty_str(task_id_raw)
    project_id = non_empty_str(project_id_raw)
    if not task_id:
        return error(
            GH_TASK_REQUIRED,
            "task_id is required",
            "Provide the task ID to fetch PR review comments for",
        )
    if not project_id:
        return error(
            GH_PROJECT_REQUIRED,
            "project_id is required",
            "Provide the project_id",
        )

    try:
        repos = await core.get_project_repos(project_id)
    except Exception as exc:
        return error(
            GH_SYNC_FAILED,
            f"Failed to fetch project repos: {exc}",
            "Check project_id is valid",
        )

    if not repos:
        return error(
            GH_NO_LINKED_PR,
            "No repos in project",
            "Add a repository to the project first",
        )

    for repo in repos:
        connection_state = load_connection_state(repo.scripts)
        if not connection_state.raw_value:
            continue
        connection = connection_state.normalized
        if connection is None:
            continue

        pr_mapping = load_pr_mapping_state(repo.scripts)
        pr_link = pr_mapping.get_pr(task_id)
        if pr_link is None:
            continue

        owner_repo = resolve_owner_repo(connection)
        if owner_repo is None:
            continue
        owner, repo_name = owner_repo

        gh_path, gh_error = gh.resolve_gh_cli_path()
        if gh_error is not None:
            return gh_error
        assert gh_path is not None

        comments, fetch_err = await asyncio.to_thread(
            gh.run_gh_api_pr_review_comments,
            gh_path,
            repo.path,
            owner,
            repo_name,
            pr_link.pr_number,
        )
        if fetch_err:
            return {
                "success": False,
                "code": GH_SYNC_FAILED,
                "message": (
                    f"Failed to fetch review comments for PR #{pr_link.pr_number}: {fetch_err}"
                ),
                "hint": "Check gh CLI authentication and network connectivity",
            }

        comment_list = comments or []
        return {
            "success": True,
            "code": PR_REVIEW_COMMENTS_FETCHED,
            "message": (
                f"Fetched {len(comment_list)} review comment(s) for PR #{pr_link.pr_number}"
            ),
            "pr_number": pr_link.pr_number,
            "comments": comment_list,
            "total": len(comment_list),
        }

    return error(
        GH_NO_LINKED_PR,
        f"Task {task_id} has no linked PR",
        "Use create_pr_for_task or link_pr_to_task first",
    )


__all__ = [
    "build_reconcile_message",
    "coerce_positive_int",
    "error",
    "get_pr_review_comments",
    "load_mapped_tasks",
    "merge_github_pr",
    "non_empty_str",
    "persist_pr_link",
    "repo_identifier",
    "resolve_connect_target",
    "resolve_connected_repo_context",
    "resolve_workspace_for_repo",
    "resolve_workspace_owner_candidates",
    "review_guardrail_check_failed",
]
