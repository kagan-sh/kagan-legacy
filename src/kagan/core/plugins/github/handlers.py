"""Entrypoint handlers for official GitHub plugin operations."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core.plugins.github.adapters import AppContextCoreGateway, GhCliClientAdapter
from kagan.core.plugins.github.contract import (
    GITHUB_CAPABILITY,
    GITHUB_METHOD_CONNECT_REPO,
    GITHUB_METHOD_CREATE_PR_FOR_TASK,
    GITHUB_METHOD_LINK_PR_TO_TASK,
    GITHUB_METHOD_SYNC_ISSUES,
    GITHUB_PLUGIN_ID,
    GITHUB_UI_ACTION_CONNECT_REPO_ID,
    GITHUB_UI_ACTION_CREATE_PR_ID,
    GITHUB_UI_ACTION_LINK_PR_ID,
    GITHUB_UI_ACTION_SYNC_ISSUES_ID,
    GITHUB_UI_BADGE_CONNECTION_ID,
    GITHUB_UI_FORM_CREATE_PR_ID,
    GITHUB_UI_FORM_LINK_PR_ID,
    GITHUB_UI_FORM_REPO_PICKER_ID,
)
from kagan.core.plugins.github.gh_adapter import GITHUB_CONNECTION_KEY
from kagan.core.plugins.github.models import (
    AcquireLeaseInput,
    CheckPrCiStatusInput,
    ConnectRepoInput,
    ContractProbeInput,
    CreatePrForTaskInput,
    GetLeaseStateInput,
    GetPrReviewCommentsInput,
    LinkPrToTaskInput,
    MergeGithubPrInput,
    ReconcilePrStatusInput,
    ReleaseLeaseInput,
    SyncIssuesInput,
    SyncTaskStatusInput,
    ValidateReviewTransitionInput,
)
from kagan.core.plugins.github.sync import GITHUB_SYNC_CHECKPOINT_KEY
from kagan.core.plugins.github.use_cases import (
    CI_STATUS_CHECKED,
    GH_ISSUE_REQUIRED,
    GH_NO_LINKED_PR,
    GH_NOT_CONNECTED,
    GH_PR_CHECKS_FAILED,
    GH_PR_CREATE_FAILED,
    GH_PR_MERGE_FAILED,
    GH_PR_NOT_FOUND,
    GH_PR_NUMBER_REQUIRED,
    GH_SYNC_FAILED,
    GH_TASK_REQUIRED,
    GH_WORKSPACE_REQUIRED,
    PR_MERGED,
    PR_REVIEW_COMMENTS_FETCHED,
    PR_STATUS_RECONCILED,
    TASK_STATUS_SYNCED,
    GitHubPluginUseCases,
)
from kagan.core.scalars import non_empty_str

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


_GH_CLIENT = GhCliClientAdapter()


# Local alias preserves existing call sites while using shared coercion.
_non_empty_str = non_empty_str


def _optional_str(value: object, *, field: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string")
    normalized = value.strip()
    return normalized if normalized else None


def _build_use_cases(ctx: AppContext) -> GitHubPluginUseCases:
    return GitHubPluginUseCases(AppContextCoreGateway(ctx), _GH_CLIENT)


def _parse_json_object(raw: object) -> dict[str, Any] | None:
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str) and raw.strip():
        import json

        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            return None
        return value if isinstance(value, dict) else None
    return None


def _extract_github_status(repo: object) -> tuple[str, str]:
    scripts = getattr(repo, "scripts", None) or {}
    if not isinstance(scripts, dict):
        return ("warn", "Not connected")

    connection = _parse_json_object(scripts.get(GITHUB_CONNECTION_KEY))
    if connection is None:
        raw = scripts.get(GITHUB_CONNECTION_KEY)
        if raw:
            return ("error", "Invalid metadata")
        return ("warn", "Not connected")
    if not connection.get("full_name"):
        return ("error", "Invalid metadata")

    checkpoint = _parse_json_object(scripts.get(GITHUB_SYNC_CHECKPOINT_KEY))
    if checkpoint is not None and checkpoint.get("last_sync_at"):
        return ("ok", "Connected")
    return ("info", "Sync stale")


async def handle_ui_describe(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Return declarative UI schema for GitHub operations."""
    project_id = _non_empty_str(params.get("project_id"))
    repo_id = _non_empty_str(params.get("repo_id"))
    if not project_id:
        return {
            "schema_version": "1",
            "actions": [],
            "forms": [],
            "badges": [],
        }

    repos = await ctx.api.get_project_repos(project_id)
    options = [
        {
            "label": str(getattr(repo, "display_name", None) or getattr(repo, "name", "")),
            "value": str(getattr(repo, "id", "")),
        }
        for repo in repos
        if getattr(repo, "id", None)
    ]
    repo_required = len(options) > 1

    badge_state, badge_text = ("warn", "Not connected")
    target = None
    if repos:
        if repo_id:
            target = next((repo for repo in repos if str(getattr(repo, "id", "")) == repo_id), None)
        if target is None and len(repos) == 1:
            target = repos[0]
    if target is not None:
        badge_state, badge_text = _extract_github_status(target)

    form = {
        "form_id": GITHUB_UI_FORM_REPO_PICKER_ID,
        "title": "GitHub Repo",
        "fields": [
            {
                "name": "repo_id",
                "kind": "select",
                "required": repo_required,
                "options": options,
            }
        ],
    }

    return {
        "schema_version": "1",
        "actions": [
            {
                "plugin_id": GITHUB_PLUGIN_ID,
                "action_id": GITHUB_UI_ACTION_CONNECT_REPO_ID,
                "surface": "kanban.repo_actions",
                "label": "Connect GitHub Repo",
                "command": "github connect",
                "help": "Connect the selected repo to GitHub (gh CLI required).",
                "operation": {
                    "capability": GITHUB_CAPABILITY,
                    "method": GITHUB_METHOD_CONNECT_REPO,
                },
                "form_id": form["form_id"],
                "confirm": False,
            },
            {
                "plugin_id": GITHUB_PLUGIN_ID,
                "action_id": GITHUB_UI_ACTION_SYNC_ISSUES_ID,
                "surface": "kanban.repo_actions",
                "label": "Sync GitHub Issues",
                "command": "github sync",
                "help": "Sync issues into Kagan tasks for the selected repo.",
                "operation": {"capability": GITHUB_CAPABILITY, "method": GITHUB_METHOD_SYNC_ISSUES},
                "form_id": form["form_id"],
                "confirm": False,
            },
            {
                "plugin_id": GITHUB_PLUGIN_ID,
                "action_id": GITHUB_UI_ACTION_CREATE_PR_ID,
                "surface": "kanban.task_actions",
                "label": "Create PR",
                "command": "github create pr",
                "help": "Create a pull request for the focused task.",
                "operation": {
                    "capability": GITHUB_CAPABILITY,
                    "method": GITHUB_METHOD_CREATE_PR_FOR_TASK,
                },
                "form_id": GITHUB_UI_FORM_CREATE_PR_ID,
                "confirm": False,
            },
            {
                "plugin_id": GITHUB_PLUGIN_ID,
                "action_id": GITHUB_UI_ACTION_LINK_PR_ID,
                "surface": "kanban.task_actions",
                "label": "Link PR",
                "command": "github link pr",
                "help": "Link an existing pull request to the focused task.",
                "operation": {
                    "capability": GITHUB_CAPABILITY,
                    "method": GITHUB_METHOD_LINK_PR_TO_TASK,
                },
                "form_id": GITHUB_UI_FORM_LINK_PR_ID,
                "confirm": False,
            },
        ],
        "forms": [
            form,
            {
                "form_id": GITHUB_UI_FORM_CREATE_PR_ID,
                "title": "Create Pull Request",
                "fields": [
                    {"name": "title", "kind": "text", "required": True},
                    {"name": "body", "kind": "text", "required": False},
                    {"name": "draft", "kind": "boolean"},
                ],
            },
            {
                "form_id": GITHUB_UI_FORM_LINK_PR_ID,
                "title": "Link Pull Request",
                "fields": [
                    {"name": "pr_number", "kind": "text", "required": True},
                ],
            },
        ],
        "badges": [
            {
                "plugin_id": GITHUB_PLUGIN_ID,
                "badge_id": GITHUB_UI_BADGE_CONNECTION_ID,
                "surface": "header.badges",
                "label": "GitHub",
                "state": badge_state,
                "text": badge_text,
            }
        ],
    }


def build_contract_probe_payload(params: dict[str, Any]) -> dict[str, Any]:
    """Return a stable, machine-readable contract response for probe calls."""
    request = ContractProbeInput(echo=params.get("echo"))
    return GitHubPluginUseCases.build_contract_probe_payload(request)


async def handle_connect_repo(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Connect a repository to GitHub with preflight checks."""
    request = ConnectRepoInput(
        project_id=_non_empty_str(params.get("project_id")),
        repo_id=_non_empty_str(params.get("repo_id")),
    )
    return await _build_use_cases(ctx).connect_repo(request)


async def handle_sync_issues(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Sync GitHub issues to Kagan task projections."""
    request = SyncIssuesInput(
        project_id=_non_empty_str(params.get("project_id")),
        repo_id=_non_empty_str(params.get("repo_id")),
    )
    return await _build_use_cases(ctx).sync_issues(request)


async def handle_acquire_lease(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Acquire a lease on a GitHub issue for the current Kagan instance."""
    request = AcquireLeaseInput(
        project_id=_non_empty_str(params.get("project_id")),
        repo_id=_non_empty_str(params.get("repo_id")),
        issue_number=params.get("issue_number"),
        force_takeover=bool(params.get("force_takeover", False)),
    )
    return await _build_use_cases(ctx).acquire_lease(request)


async def handle_release_lease(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Release a lease on a GitHub issue."""
    request = ReleaseLeaseInput(
        project_id=_non_empty_str(params.get("project_id")),
        repo_id=_non_empty_str(params.get("repo_id")),
        issue_number=params.get("issue_number"),
    )
    return await _build_use_cases(ctx).release_lease(request)


async def handle_get_lease_state(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Get the current lease state for a GitHub issue."""
    request = GetLeaseStateInput(
        project_id=_non_empty_str(params.get("project_id")),
        repo_id=_non_empty_str(params.get("repo_id")),
        issue_number=params.get("issue_number"),
    )
    return await _build_use_cases(ctx).get_lease_state(request)


async def handle_create_pr_for_task(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Create a PR for a task and link it."""
    request = CreatePrForTaskInput(
        project_id=_non_empty_str(params.get("project_id")),
        repo_id=_non_empty_str(params.get("repo_id")),
        task_id=_non_empty_str(params.get("task_id")),
        title=_optional_str(params.get("title"), field="title"),
        body=_optional_str(params.get("body"), field="body"),
        draft=bool(params.get("draft", False)),
    )
    return await _build_use_cases(ctx).create_pr_for_task(request)


async def handle_link_pr_to_task(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Link an existing PR to a task."""
    request = LinkPrToTaskInput(
        project_id=_non_empty_str(params.get("project_id")),
        repo_id=_non_empty_str(params.get("repo_id")),
        task_id=_non_empty_str(params.get("task_id")),
        pr_number=params.get("pr_number"),
    )
    return await _build_use_cases(ctx).link_pr_to_task(request)


async def handle_reconcile_pr_status(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Reconcile PR status for a task and apply deterministic board transitions."""
    request = ReconcilePrStatusInput(
        project_id=_non_empty_str(params.get("project_id")),
        repo_id=_non_empty_str(params.get("repo_id")),
        task_id=_non_empty_str(params.get("task_id")),
    )
    return await _build_use_cases(ctx).reconcile_pr_status(request)


async def handle_validate_review_transition(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Validate REVIEW transition guardrails for GitHub-connected repos."""
    request = ValidateReviewTransitionInput(
        task_id=_non_empty_str(params.get("task_id")),
        project_id=_non_empty_str(params.get("project_id")),
    )
    return await _build_use_cases(ctx).validate_review_transition(request)


async def handle_sync_task_status(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Sync Kagan task status to the linked GitHub issue."""
    request = SyncTaskStatusInput(
        task_id=_non_empty_str(params.get("task_id")),
        project_id=_non_empty_str(params.get("project_id")),
        to_status=_non_empty_str(params.get("to_status")),
    )
    return await _build_use_cases(ctx).sync_task_status_to_issue(request)


async def handle_check_ci_status(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Check CI status on the linked GitHub PR for a task."""
    request = CheckPrCiStatusInput(
        project_id=_non_empty_str(params.get("project_id")),
        task_id=_non_empty_str(params.get("task_id")),
    )
    return await _build_use_cases(ctx).check_pr_ci_status(request)


async def handle_merge_pr(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    """Merge the GitHub PR linked to a task."""
    request = MergeGithubPrInput(
        project_id=_non_empty_str(params.get("project_id")),
        task_id=_non_empty_str(params.get("task_id")),
        merge_method=_non_empty_str(params.get("merge_method")) or "merge",
    )
    return await _build_use_cases(ctx).merge_github_pr(request)


async def handle_get_pr_review_comments(
    ctx: AppContext,
    params: dict[str, Any],
) -> dict[str, Any]:
    """Fetch PR review comments for the PR linked to a task."""
    request = GetPrReviewCommentsInput(
        project_id=_non_empty_str(params.get("project_id")),
        task_id=_non_empty_str(params.get("task_id")),
    )
    return await _build_use_cases(ctx).get_pr_review_comments(request)


__all__ = [
    "CI_STATUS_CHECKED",
    "GH_ISSUE_REQUIRED",
    "GH_NOT_CONNECTED",
    "GH_NO_LINKED_PR",
    "GH_PR_CHECKS_FAILED",
    "GH_PR_CREATE_FAILED",
    "GH_PR_MERGE_FAILED",
    "GH_PR_NOT_FOUND",
    "GH_PR_NUMBER_REQUIRED",
    "GH_SYNC_FAILED",
    "GH_TASK_REQUIRED",
    "GH_WORKSPACE_REQUIRED",
    "PR_MERGED",
    "PR_REVIEW_COMMENTS_FETCHED",
    "PR_STATUS_RECONCILED",
    "TASK_STATUS_SYNCED",
    "build_contract_probe_payload",
    "handle_acquire_lease",
    "handle_check_ci_status",
    "handle_connect_repo",
    "handle_create_pr_for_task",
    "handle_get_lease_state",
    "handle_get_pr_review_comments",
    "handle_link_pr_to_task",
    "handle_merge_pr",
    "handle_reconcile_pr_status",
    "handle_release_lease",
    "handle_sync_issues",
    "handle_sync_task_status",
    "handle_ui_describe",
    "handle_validate_review_transition",
]
