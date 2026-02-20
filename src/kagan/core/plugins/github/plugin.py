"""Bundled official GitHub plugin registration entrypoint."""

from __future__ import annotations

import asyncio
import logging
from importlib import import_module
from typing import Any, Final, cast

from kagan.core.plugins.github.contract import (
    GITHUB_CAPABILITY,
    GITHUB_CONTRACT_PROBE_METHOD,
    GITHUB_METHOD_ACQUIRE_LEASE,
    GITHUB_METHOD_CHECK_CI,
    GITHUB_METHOD_CONNECT_REPO,
    GITHUB_METHOD_CREATE_PR_FOR_TASK,
    GITHUB_METHOD_GET_LEASE_STATE,
    GITHUB_METHOD_GET_PR_REVIEW_COMMENTS,
    GITHUB_METHOD_LINK_PR_TO_TASK,
    GITHUB_METHOD_MERGE_PR,
    GITHUB_METHOD_RECONCILE_PR_STATUS,
    GITHUB_METHOD_RELEASE_LEASE,
    GITHUB_METHOD_SYNC_ISSUES,
    GITHUB_METHOD_SYNC_TASK_STATUS,
    GITHUB_METHOD_VALIDATE_REVIEW_TRANSITION,
    GITHUB_PLUGIN_ID,
)
from kagan.core.plugins.sdk import (
    PLUGIN_UI_DESCRIBE_METHOD,
    McpToolSchema,
    PluginCapabilityProvider,
    PluginCapabilitySpec,
    PluginManifest,
    PluginOperation,
    PluginRegistrationApi,
    PluginRegistry,
)
from kagan.core.policy import CapabilityProfile

log = logging.getLogger(__name__)

_GITHUB_DECLARED_METHODS: Final[tuple[str, ...]] = tuple(
    sorted(
        (
            GITHUB_CONTRACT_PROBE_METHOD,
            GITHUB_METHOD_CHECK_CI,
            GITHUB_METHOD_CONNECT_REPO,
            GITHUB_METHOD_CREATE_PR_FOR_TASK,
            GITHUB_METHOD_GET_PR_REVIEW_COMMENTS,
            GITHUB_METHOD_LINK_PR_TO_TASK,
            GITHUB_METHOD_MERGE_PR,
            GITHUB_METHOD_RECONCILE_PR_STATUS,
            GITHUB_METHOD_SYNC_ISSUES,
            GITHUB_METHOD_SYNC_TASK_STATUS,
            GITHUB_METHOD_ACQUIRE_LEASE,
            GITHUB_METHOD_RELEASE_LEASE,
            GITHUB_METHOD_GET_LEASE_STATE,
            GITHUB_METHOD_VALIDATE_REVIEW_TRANSITION,
            PLUGIN_UI_DESCRIBE_METHOD,
        )
    )
)


class GitHubPluginError(RuntimeError):
    """Base class for GitHub plugin runtime failures."""


class GitHubPluginModuleLoadError(GitHubPluginError):
    """Raised when the plugin handler module cannot be imported."""


class GitHubPluginHandlerResolutionError(GitHubPluginError):
    """Raised when a declared plugin handler cannot be resolved."""


class GitHubPluginHandlerExecutionError(GitHubPluginError):
    """Raised when a resolved plugin handler fails at runtime."""


def _plugin_handlers_module() -> Any:
    """Load handler module lazily to avoid eager plugin side effects."""
    module_name = "kagan.core.plugins.github.handlers"
    try:
        return import_module(module_name)
    except ImportError as exc:
        msg = f"GitHub plugin handlers module could not be imported: {module_name}"
        raise GitHubPluginModuleLoadError(msg) from exc


def _make_handler_dispatch(
    handler_name: str,
    *,
    include_ctx: bool,
) -> Any:
    async def _dispatch(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
        handlers_module = _plugin_handlers_module()
        try:
            handler = getattr(handlers_module, handler_name)
        except AttributeError as exc:
            msg = f"GitHub plugin handler '{handler_name}' is not defined"
            raise GitHubPluginHandlerResolutionError(msg) from exc
        if not callable(handler):
            msg = f"GitHub plugin handler '{handler_name}' is not callable"
            raise GitHubPluginHandlerResolutionError(msg)
        if not include_ctx:
            del ctx
            try:
                result = handler(params)
            except Exception as exc:  # quality-allow-broad-except
                msg = f"GitHub plugin handler '{handler_name}' failed"
                raise GitHubPluginHandlerExecutionError(msg) from exc
        else:
            try:
                result = await cast("Any", handler)(ctx, params)
            except Exception as exc:  # quality-allow-broad-except
                msg = f"GitHub plugin handler '{handler_name}' failed"
                raise GitHubPluginHandlerExecutionError(msg) from exc
        if not isinstance(result, dict):
            msg = f"GitHub plugin handler '{handler_name}' returned non-object payload"
            raise GitHubPluginHandlerExecutionError(msg)
        return result

    return _dispatch


_contract_probe = _make_handler_dispatch("build_contract_probe_payload", include_ctx=False)
_connect_repo = _make_handler_dispatch("handle_connect_repo", include_ctx=True)
_sync_issues = _make_handler_dispatch("handle_sync_issues", include_ctx=True)
_acquire_lease = _make_handler_dispatch("handle_acquire_lease", include_ctx=True)
_release_lease = _make_handler_dispatch("handle_release_lease", include_ctx=True)
_get_lease_state = _make_handler_dispatch("handle_get_lease_state", include_ctx=True)
_create_pr_for_task = _make_handler_dispatch("handle_create_pr_for_task", include_ctx=True)
_link_pr_to_task = _make_handler_dispatch("handle_link_pr_to_task", include_ctx=True)
_reconcile_pr_status = _make_handler_dispatch("handle_reconcile_pr_status", include_ctx=True)
_validate_review_transition = _make_handler_dispatch(
    "handle_validate_review_transition",
    include_ctx=True,
)
_sync_task_status = _make_handler_dispatch("handle_sync_task_status", include_ctx=True)
_check_ci_status = _make_handler_dispatch("handle_check_ci_status", include_ctx=True)
_merge_pr = _make_handler_dispatch("handle_merge_pr", include_ctx=True)
_get_pr_review_comments = _make_handler_dispatch(
    "handle_get_pr_review_comments",
    include_ctx=True,
)
_ui_describe = _make_handler_dispatch("handle_ui_describe", include_ctx=True)


class GitHubPlugin(PluginCapabilityProvider):
    """Official bundled GitHub plugin with a stable contract probe.

    Implements ``PluginLifecycle`` to register an event handler for
    ``TaskStatusChanged`` that syncs task status to linked GitHub issues.
    """

    manifest = PluginManifest(
        id=GITHUB_PLUGIN_ID,
        name="Official GitHub Plugin",
        version="0.1.0",
        entrypoint="kagan.core.plugins.github.plugin:GitHubPlugin",
        description="Bundled GitHub plugin with stable contract probe semantics.",
    )

    @property
    def capabilities(self) -> tuple[PluginCapabilitySpec, ...]:
        return (
            PluginCapabilitySpec(
                capability=GITHUB_CAPABILITY,
                methods=_GITHUB_DECLARED_METHODS,
            ),
        )

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_CONTRACT_PROBE_METHOD,
                handler=_contract_probe,
                minimum_profile=CapabilityProfile.PAIR_WORKER,
                mutating=False,
                description="Return the canonical GitHub plugin operation contract.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_contract_probe",
                    description=(
                        "Probe the GitHub plugin contract for verification (V1 contract). "
                        "Returns plugin metadata including contract version and "
                        "canonical methods."
                    ),
                    parameters={"echo": {"type": "string", "description": "Optional echo value"}},
                    response_schema={
                        "plugin_id": {"type": "string"},
                        "contract_version": {"type": "string"},
                        "capability": {"type": "string"},
                        "method": {"type": "string"},
                        "canonical_methods": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                        "echo": {"type": "string"},
                    },
                    annotations="read_only",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_CONNECT_REPO,
                handler=_connect_repo,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=True,
                description="Connect a repo to GitHub with preflight checks.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_connect_repo",
                    description=(
                        "Connect a repository to GitHub with preflight checks "
                        "(V1 contract). Performs preflight verification and "
                        "persists GitHub connection metadata."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "repo_id": {
                            "type": "string",
                            "description": "Optional repo ID (required for multi-repo)",
                        },
                    },
                    response_schema={
                        "connection": {
                            "type": "object",
                            "properties": {
                                "full_name": {"type": "string"},
                                "owner": {"type": "string"},
                                "repo": {"type": "string"},
                                "default_branch": {"type": "string"},
                                "visibility": {"type": "string"},
                                "connected_at": {"type": "string"},
                            },
                        },
                    },
                    annotations="mutating",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_SYNC_ISSUES,
                handler=_sync_issues,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=True,
                description="Sync GitHub issues to Kagan task projections.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_sync_issues",
                    description=(
                        "Sync GitHub issues to Kagan task projections (V1 contract). "
                        "Fetches issues from GitHub and creates/updates "
                        "corresponding tasks."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "repo_id": {
                            "type": "string",
                            "description": "Optional repo ID (required for multi-repo)",
                        },
                    },
                    response_schema={
                        "stats": {
                            "type": "object",
                            "properties": {
                                "total": {"type": "integer"},
                                "inserted": {"type": "integer"},
                                "updated": {"type": "integer"},
                                "reopened": {"type": "integer"},
                                "closed": {"type": "integer"},
                                "no_change": {"type": "integer"},
                                "errors": {"type": "integer"},
                            },
                        },
                    },
                    annotations="mutating",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_ACQUIRE_LEASE,
                handler=_acquire_lease,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=True,
                description="Acquire a lease on a GitHub issue for the current instance.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_acquire_lease",
                    description=(
                        "Acquire a lease on a GitHub issue for multi-instance coordination. "
                        "Prevents concurrent work on the same issue."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "repo_id": {
                            "type": "string",
                            "description": "Optional repo ID (required for multi-repo)",
                        },
                        "issue_number": {
                            "type": "integer",
                            "description": "GitHub issue number to acquire lease for",
                            "required": True,
                        },
                        "force_takeover": {
                            "type": "boolean",
                            "description": ("Force takeover of an existing lease (default: false)"),
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "holder": {"type": "object"},
                    },
                    annotations="mutating",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_RELEASE_LEASE,
                handler=_release_lease,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=True,
                description="Release a lease on a GitHub issue.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_release_lease",
                    description=("Release a previously acquired lease on a GitHub issue."),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "repo_id": {
                            "type": "string",
                            "description": "Optional repo ID (required for multi-repo)",
                        },
                        "issue_number": {
                            "type": "integer",
                            "description": "GitHub issue number to release lease for",
                            "required": True,
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                    },
                    annotations="mutating",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_GET_LEASE_STATE,
                handler=_get_lease_state,
                minimum_profile=CapabilityProfile.PAIR_WORKER,
                mutating=False,
                description="Get the current lease state for a GitHub issue.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_get_lease_state",
                    description=(
                        "Get the current lease state for a GitHub issue. "
                        "Returns lock status, holder info, and whether current "
                        "instance can acquire."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "repo_id": {
                            "type": "string",
                            "description": "Optional repo ID (required for multi-repo)",
                        },
                        "issue_number": {
                            "type": "integer",
                            "description": "GitHub issue number to check lease state for",
                            "required": True,
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "state": {"type": "object"},
                    },
                    annotations="read_only",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_CREATE_PR_FOR_TASK,
                handler=_create_pr_for_task,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=True,
                description="Create a PR for a task and link it.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_create_pr_for_task",
                    description=(
                        "Create a GitHub pull request from a task's workspace branch "
                        "and link it to the task."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "repo_id": {
                            "type": "string",
                            "description": "Optional repo ID (required for multi-repo)",
                        },
                        "task_id": {
                            "type": "string",
                            "description": "Task ID to create PR for",
                            "required": True,
                        },
                        "title": {
                            "type": "string",
                            "description": "PR title (defaults to task title)",
                        },
                        "body": {
                            "type": "string",
                            "description": "PR body/description (defaults to task description)",
                        },
                        "draft": {
                            "type": "boolean",
                            "description": "Create as draft PR (default: false)",
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "pr": {
                            "type": "object",
                            "properties": {
                                "number": {"type": "integer"},
                                "url": {"type": "string"},
                                "state": {"type": "string"},
                                "is_draft": {"type": "boolean"},
                            },
                        },
                    },
                    annotations="mutating",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_LINK_PR_TO_TASK,
                handler=_link_pr_to_task,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=True,
                description="Link an existing PR to a task.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_link_pr_to_task",
                    description=(
                        "Link an existing GitHub pull request to a Kagan task by PR number."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "repo_id": {
                            "type": "string",
                            "description": "Optional repo ID (required for multi-repo)",
                        },
                        "task_id": {
                            "type": "string",
                            "description": "Task ID to link PR to",
                            "required": True,
                        },
                        "pr_number": {
                            "type": "integer",
                            "description": "GitHub PR number to link",
                            "required": True,
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "pr": {
                            "type": "object",
                            "properties": {
                                "number": {"type": "integer"},
                                "url": {"type": "string"},
                                "state": {"type": "string"},
                            },
                        },
                    },
                    annotations="mutating",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_RECONCILE_PR_STATUS,
                handler=_reconcile_pr_status,
                minimum_profile=CapabilityProfile.PAIR_WORKER,
                mutating=True,
                description="Reconcile the PR status for a task from GitHub.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_reconcile_pr_status",
                    description=(
                        "Fetch the latest PR state from GitHub and apply board "
                        "transitions. MERGED -> task DONE, CLOSED -> task IN_PROGRESS."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "repo_id": {
                            "type": "string",
                            "description": "Optional repo ID (required for multi-repo)",
                        },
                        "task_id": {
                            "type": "string",
                            "description": "Task ID to reconcile PR status for",
                            "required": True,
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "pr": {"type": "object"},
                        "task": {"type": "object"},
                    },
                    annotations="mutating",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_CHECK_CI,
                handler=_check_ci_status,
                minimum_profile=CapabilityProfile.PAIR_WORKER,
                mutating=False,
                description="Check CI status on the linked GitHub PR for a task.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_check_ci_status",
                    description=(
                        "Check CI/check-run status on the GitHub PR linked to a task. "
                        "Returns per-check results and an overall summary. "
                        "CI failures are informational (warn, not hard-block)."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "task_id": {
                            "type": "string",
                            "description": "Task ID whose linked PR to check",
                            "required": True,
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "checks": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "summary": {"type": "object"},
                    },
                    annotations="read_only",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_MERGE_PR,
                handler=_merge_pr,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=True,
                description="Merge the GitHub PR linked to a task.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_merge_pr",
                    description=(
                        "Merge the GitHub pull request linked to a task. "
                        "Supports merge, squash, and rebase methods. "
                        "Handles already-merged, conflict, and missing-PR cases."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "task_id": {
                            "type": "string",
                            "description": "Task ID whose linked PR to merge",
                            "required": True,
                        },
                        "merge_method": {
                            "type": "string",
                            "description": (
                                "Merge strategy: merge, squash, or rebase (default: merge)"
                            ),
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "pr": {"type": "object"},
                    },
                    annotations="mutating",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_GET_PR_REVIEW_COMMENTS,
                handler=_get_pr_review_comments,
                minimum_profile=CapabilityProfile.PAIR_WORKER,
                mutating=False,
                description="Fetch PR review comments for the PR linked to a task.",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_get_pr_review_comments",
                    description=(
                        "Fetch review comments from the GitHub PR linked to a task. "
                        "Returns inline code review comments with file path, "
                        "line number, author, and body."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "task_id": {
                            "type": "string",
                            "description": "Task ID whose linked PR to fetch comments for",
                            "required": True,
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "pr_number": {"type": "integer"},
                        "comments": {
                            "type": "array",
                            "items": {"type": "object"},
                        },
                        "total": {"type": "integer"},
                    },
                    annotations="read_only",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_VALIDATE_REVIEW_TRANSITION,
                handler=_validate_review_transition,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=False,
                description="Validate REVIEW transition guardrails for GitHub-connected repos.",
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=GITHUB_METHOD_SYNC_TASK_STATUS,
                handler=_sync_task_status,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=True,
                description="Sync task status to GitHub issue (close/reopen + labels).",
                mcp_tool_schema=McpToolSchema(
                    tool_name="kagan_github_sync_task_status",
                    description=(
                        "Sync a Kagan task's status to its linked GitHub issue. "
                        "Closes/reopens the issue and manages kagan:* status labels."
                    ),
                    parameters={
                        "project_id": {
                            "type": "string",
                            "description": "Required project ID",
                            "required": True,
                        },
                        "task_id": {
                            "type": "string",
                            "description": "Task ID to sync status for",
                            "required": True,
                        },
                        "to_status": {
                            "type": "string",
                            "description": (
                                "Target task status (BACKLOG, IN_PROGRESS, REVIEW, DONE)"
                            ),
                            "required": True,
                        },
                    },
                    response_schema={
                        "success": {"type": "boolean"},
                        "code": {"type": "string"},
                        "message": {"type": "string"},
                        "issue_number": {"type": "integer"},
                        "actions": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    annotations="mutating",
                ),
            )
        )
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=GITHUB_CAPABILITY,
                method=PLUGIN_UI_DESCRIBE_METHOD,
                handler=_ui_describe,
                minimum_profile=CapabilityProfile.VIEWER,
                mutating=False,
                description=(
                    "Provide declarative TUI UI schema contributions for GitHub operations."
                ),
            )
        )

    # -- PluginLifecycle protocol --

    async def on_core_startup(self, ctx: Any) -> None:
        """Register event handler for TaskStatusChanged to sync to GitHub issues."""
        from kagan.core.events import TaskStatusChanged

        def _on_task_status_changed(event: Any) -> None:
            if not isinstance(event, TaskStatusChanged):
                return

            task_id = event.task_id
            to_status = event.to_status

            # Resolve project_id for the task so we can find the repo mapping.
            # Fire-and-forget: schedule async work, log errors, never block.
            async def _sync() -> None:
                try:
                    task = await ctx.api.get_task(task_id)
                    if task is None:
                        return
                    project_id = getattr(task, "project_id", None)
                    if not project_id:
                        return

                    result = await _sync_task_status(
                        ctx,
                        {
                            "task_id": task_id,
                            "project_id": project_id,
                            "to_status": to_status.value
                            if hasattr(to_status, "value")
                            else str(to_status),
                        },
                    )
                    if result.get("success"):
                        actions = result.get("actions", [])
                        if actions:
                            log.info(
                                "GitHub sync for task %s: %s",
                                task_id,
                                ", ".join(actions),
                            )
                    else:
                        log.warning(
                            "GitHub sync for task %s failed: %s",
                            task_id,
                            result.get("message", "unknown"),
                        )

                    # Auto-create draft PR when transitioning to REVIEW
                    to_status_str = (
                        to_status.value if hasattr(to_status, "value") else str(to_status)
                    )
                    if to_status_str == "REVIEW":
                        try:
                            from kagan.core.plugins.github.adapters import (
                                AppContextCoreGateway,
                                GhCliClientAdapter,
                            )
                            from kagan.core.plugins.github.models import AutoCreateReviewPrInput
                            from kagan.core.plugins.github.use_cases import GitHubPluginUseCases

                            use_cases = GitHubPluginUseCases(
                                AppContextCoreGateway(ctx),
                                GhCliClientAdapter(),
                            )
                            await use_cases.auto_create_review_pr(
                                AutoCreateReviewPrInput(
                                    task_id=task_id,
                                    project_id=project_id,
                                )
                            )
                        except Exception:  # quality-allow-broad-except
                            log.warning(
                                "Auto PR creation failed for task %s",
                                task_id,
                                exc_info=True,
                            )
                except Exception:  # quality-allow-broad-except
                    log.exception("GitHub status sync failed for task %s", task_id)

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_sync())
            except RuntimeError:
                log.debug("No event loop for GitHub status sync of task %s", task_id)

        ctx.event_bus.add_handler(_on_task_status_changed, TaskStatusChanged)
        self._status_handler = _on_task_status_changed

    async def on_core_shutdown(self, ctx: Any) -> None:
        """Remove event handler on shutdown."""
        handler = getattr(self, "_status_handler", None)
        if handler is not None:
            ctx.event_bus.remove_handler(handler)
            self._status_handler = None


def register_github_plugin(registry: PluginRegistry) -> None:
    """Register bundled official GitHub plugin operations."""
    registry.register_plugin(GitHubPlugin())


__all__ = [
    "GitHubPlugin",
    "GitHubPluginError",
    "GitHubPluginHandlerExecutionError",
    "GitHubPluginHandlerResolutionError",
    "GitHubPluginModuleLoadError",
    "register_github_plugin",
]
