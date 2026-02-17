"""GitHub plugin application use cases."""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING, Any, Final

from kagan.core.domain.enums import TaskStatus
from kagan.core.plugins.github.application import _helpers as _h
from kagan.core.plugins.github.contract import (
    GITHUB_CANONICAL_METHODS,
    GITHUB_CANONICAL_METHODS_SCOPE,
    GITHUB_CAPABILITY,
    GITHUB_CONTRACT_PROBE_METHOD,
    GITHUB_CONTRACT_VERSION,
    GITHUB_PLUGIN_ID,
    RESERVED_GITHUB_CAPABILITY,
)
from kagan.core.plugins.github.domain.repo_state import (
    encode_connection_update,
    encode_pr_mapping_update,
    encode_sync_state_update,
    load_connection_state,
    load_issue_mapping_state,
    load_lease_enforcement_state,
    load_pr_mapping_state,
    load_repo_default_mode_state,
    load_sync_checkpoint_state,
    resolve_owner_repo,
)
from kagan.core.plugins.github.gh_adapter import (
    ALREADY_CONNECTED,
    GH_PR_CHECKS_FAILED,
    GH_PR_CREATE_FAILED,
    GH_PR_NOT_FOUND,
    GH_PROJECT_REQUIRED,
)
from kagan.core.plugins.github.lease import LEASE_HELD_BY_OTHER
from kagan.core.plugins.github.sync import (
    IssueMapping,
    SyncCheckpoint,
    SyncOutcome,
    SyncResult,
    compute_issue_changes,
    filter_issues_since_checkpoint,
)
from kagan.core.time import utc_now

if TYPE_CHECKING:
    from typing import Any, Protocol

    from kagan.core.plugins.github.adapters.core_gateway import AppContextCoreGateway
    from kagan.core.plugins.github.adapters.gh_cli_client import GhCliClientAdapter
    from kagan.core.plugins.github.domain.models import (
        AcquireLeaseInput,
        AutoCreateReviewPrInput,
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

    class GitHubCoreGateway(Protocol):
        """Port for core data and mutation operations used by GitHub use cases."""

        ...

    class GitHubClient(Protocol):
        """Port for GitHub/gh CLI operations."""

        ...


GH_NOT_CONNECTED: Final = "GH_NOT_CONNECTED"
GH_SYNC_FAILED: Final = "GH_SYNC_FAILED"
GH_ISSUE_REQUIRED: Final = "GH_ISSUE_REQUIRED"
GH_ISSUE_NUMBER_INVALID: Final = "GH_ISSUE_NUMBER_INVALID"
GH_TASK_REQUIRED: Final = "GH_TASK_REQUIRED"
GH_WORKSPACE_REQUIRED: Final = "GH_WORKSPACE_REQUIRED"
GH_REPO_REQUIRED: Final = "GH_REPO_REQUIRED"
GH_PR_NUMBER_REQUIRED: Final = "GH_PR_NUMBER_REQUIRED"
GH_PR_NUMBER_INVALID: Final = "GH_PR_NUMBER_INVALID"
GH_NO_LINKED_PR: Final = "GH_NO_LINKED_PR"
GH_PR_MERGE_FAILED: Final = "GH_PR_MERGE_FAILED"
CONNECTED: Final = "CONNECTED"
SYNCED: Final = "SYNCED"
LEASE_STATE_OK: Final = "LEASE_STATE_OK"
LEASE_STATE_ERROR: Final = "LEASE_STATE_ERROR"
PR_CREATED: Final = "PR_CREATED"
PR_LINKED: Final = "PR_LINKED"
PR_STATUS_RECONCILED: Final = "PR_STATUS_RECONCILED"
TASK_STATUS_SYNCED: Final = "TASK_STATUS_SYNCED"
CI_STATUS_CHECKED: Final = "CI_STATUS_CHECKED"
PR_MERGED: Final = "PR_MERGED"
PR_REVIEW_COMMENTS_FETCHED: Final = "PR_REVIEW_COMMENTS_FETCHED"
LEASE_ENFORCEMENT_DISABLED: Final = "LEASE_ENFORCEMENT_DISABLED"
REVIEW_BLOCKED_NO_PR: Final = "REVIEW_BLOCKED_NO_PR"
REVIEW_BLOCKED_LEASE: Final = "REVIEW_BLOCKED_LEASE"
REVIEW_GUARDRAIL_CHECK_FAILED: Final = "REVIEW_GUARDRAIL_CHECK_FAILED"
AUTO_PR_SKIPPED: Final = "AUTO_PR_SKIPPED"
AUTO_PR_CREATED: Final = "AUTO_PR_CREATED"
_SYNC_TASK_WRITE_ERRORS: Final = (ValueError, RuntimeError, LookupError)


class GitHubPluginUseCases:
    """Use-case orchestrator for official GitHub plugin operations."""

    def __init__(
        self,
        core_gateway: AppContextCoreGateway,
        gh_client: GhCliClientAdapter,
    ) -> None:
        self._core: AppContextCoreGateway = core_gateway
        self._gh: GhCliClientAdapter = gh_client

    @staticmethod
    def build_contract_probe_payload(request: ContractProbeInput) -> dict[str, Any]:
        """Return a stable, machine-readable contract response for probe calls."""
        return {
            "success": True,
            "plugin_id": GITHUB_PLUGIN_ID,
            "contract_version": GITHUB_CONTRACT_VERSION,
            "capability": GITHUB_CAPABILITY,
            "method": GITHUB_CONTRACT_PROBE_METHOD,
            "canonical_methods": list(GITHUB_CANONICAL_METHODS),
            "canonical_scope": GITHUB_CANONICAL_METHODS_SCOPE,
            "reserved_official_capability": RESERVED_GITHUB_CAPABILITY,
            "echo": request.echo,
        }

    async def connect_repo(self, request: ConnectRepoInput) -> dict[str, Any]:
        """Connect a repository to GitHub with preflight checks."""
        repo, resolve_error = await _h.resolve_connect_target(
            self._core,
            request.project_id,
            request.repo_id,
        )
        if resolve_error is not None:
            return resolve_error
        assert repo is not None

        connection_state = load_connection_state(repo.scripts)
        repairing_invalid_connection = False
        if connection_state.raw_value:
            connection_data = connection_state.normalized
            if connection_data is None:
                repairing_invalid_connection = True
            else:
                if connection_state.needs_rewrite:
                    await self._core.update_repo_scripts(
                        repo.id,
                        encode_connection_update(connection_data),
                    )

                return {
                    "success": True,
                    "code": ALREADY_CONNECTED,
                    "message": "Repository is already connected to GitHub",
                    "connection": connection_data,
                }

        repo_view, error = await asyncio.to_thread(self._gh.run_preflight_checks, repo.path)
        if error is not None:
            return {
                "success": False,
                "code": error.code,
                "message": error.message,
                "hint": error.hint,
            }

        assert repo_view is not None
        connection_metadata = self._gh.build_connection_metadata(repo_view)
        await self._core.update_repo_scripts(repo.id, encode_connection_update(connection_metadata))

        if repairing_invalid_connection:
            return {
                "success": True,
                "code": CONNECTED,
                "message": (
                    "Repaired invalid GitHub connection metadata and connected "
                    f"to {repo_view.full_name}"
                ),
                "connection": connection_metadata,
            }

        return {
            "success": True,
            "code": CONNECTED,
            "message": f"Connected to {repo_view.full_name}",
            "connection": connection_metadata,
        }

    async def sync_issues(self, request: SyncIssuesInput) -> dict[str, Any]:
        """Sync GitHub issues to Kagan task projections."""
        repo, resolve_error = await _h.resolve_connect_target(
            self._core,
            request.project_id,
            request.repo_id,
        )
        if resolve_error is not None:
            return resolve_error
        assert repo is not None

        _, connection_error = _h.resolve_connected_repo_context(repo)
        if connection_error is not None:
            return connection_error

        gh_path, gh_error = self._gh.resolve_gh_cli_path()
        if gh_error is not None:
            return gh_error
        assert gh_path is not None

        raw_issues, error = await asyncio.to_thread(self._gh.run_gh_issue_list, gh_path, repo.path)
        if error:
            return {
                "success": False,
                "code": GH_SYNC_FAILED,
                "message": f"Failed to fetch issues: {error}",
                "hint": "Check gh CLI authentication and repository access",
            }

        all_issues = self._gh.parse_issue_list(raw_issues or [])
        checkpoint = load_sync_checkpoint_state(repo.scripts)
        issues = filter_issues_since_checkpoint(all_issues, checkpoint)

        mapping = load_issue_mapping_state(repo.scripts)
        repo_default_mode = load_repo_default_mode_state(repo.scripts)
        existing_tasks = await _h.load_mapped_tasks(self._core, mapping)

        result = SyncResult()
        new_mapping = IssueMapping(
            issue_to_task=dict(mapping.issue_to_task),
            task_to_issue=dict(mapping.task_to_issue),
        )

        for issue in issues:
            action, changes = compute_issue_changes(
                issue,
                mapping,
                existing_tasks,
                repo_default_mode,
            )

            if action == "no_change" or changes is None:
                result.add_outcome(
                    SyncOutcome(
                        issue_number=issue.number,
                        action="no_change",
                        task_id=mapping.get_task_id(issue.number),
                    )
                )
                continue

            if action == "insert":
                try:
                    normalized_project_id = _h.non_empty_str(request.project_id)
                    assert normalized_project_id is not None
                    task = await self._core.create_task(
                        title=changes["title"],
                        description=changes["description"],
                        project_id=normalized_project_id,
                    )
                    update_fields: dict[str, Any] = {}
                    if changes.get("task_type"):
                        update_fields["task_type"] = changes["task_type"]
                    if changes.get("status"):
                        update_fields["status"] = changes["status"]
                    if update_fields:
                        await self._core.update_task_fields(task.id, **update_fields)
                    new_mapping.remove_by_issue(issue.number)
                    new_mapping.add_mapping(issue.number, task.id)
                    result.add_outcome(
                        SyncOutcome(issue_number=issue.number, action="insert", task_id=task.id)
                    )
                except _SYNC_TASK_WRITE_ERRORS as exc:
                    result.add_outcome(
                        SyncOutcome(issue_number=issue.number, action="insert", error=str(exc))
                    )
                continue

            task_id = mapping.get_task_id(issue.number)
            if not task_id:
                continue

            try:
                await self._core.update_task_fields(task_id, **changes)
                result.add_outcome(
                    SyncOutcome(issue_number=issue.number, action=action, task_id=task_id)
                )
            except _SYNC_TASK_WRITE_ERRORS as exc:
                result.add_outcome(
                    SyncOutcome(issue_number=issue.number, action=action, error=str(exc))
                )

        stats = {
            "total": len(issues),
            "inserted": result.inserted,
            "updated": result.updated,
            "reopened": result.reopened,
            "closed": result.closed,
            "no_change": result.no_change,
            "errors": result.errors,
        }

        mapping_changed = new_mapping.to_dict() != mapping.to_dict()
        if result.errors > 0:
            if mapping_changed:
                await self._core.update_repo_scripts(
                    repo.id,
                    encode_sync_state_update(checkpoint, new_mapping),
                )
            return {
                "success": False,
                "code": GH_SYNC_FAILED,
                "message": f"Synced {len(issues)} issues with {result.errors} per-issue errors",
                "hint": (
                    "Review failing issue mappings and retry sync after fixing task create/update "
                    "errors."
                ),
                "stats": stats,
            }

        new_checkpoint = SyncCheckpoint(
            last_sync_at=utc_now().isoformat(),
            issue_count=len(issues),
        )
        await self._core.update_repo_scripts(
            repo.id,
            encode_sync_state_update(new_checkpoint, new_mapping),
        )

        return {
            "success": True,
            "code": SYNCED,
            "message": f"Synced {len(issues)} issues",
            "stats": stats,
        }

    async def acquire_lease(self, request: AcquireLeaseInput) -> dict[str, Any]:
        """Acquire a lease on a GitHub issue for the current Kagan instance."""
        if request.issue_number is None:
            return _h.error(
                GH_ISSUE_REQUIRED,
                "issue_number is required",
                "Provide the GitHub issue number to acquire lease for",
            )
        issue_number, issue_error = _h.coerce_positive_int(
            value=request.issue_number,
            field_name="issue_number",
            invalid_code=GH_ISSUE_NUMBER_INVALID,
        )
        if issue_error is not None:
            return issue_error
        assert issue_number is not None

        repo, resolve_error = await _h.resolve_connect_target(
            self._core,
            request.project_id,
            request.repo_id,
        )
        if resolve_error is not None:
            return resolve_error
        assert repo is not None

        lease_enforced = load_lease_enforcement_state(repo.scripts)
        repo_context, connection_error = _h.resolve_connected_repo_context(
            repo,
            require_owner_repo=lease_enforced,
        )
        if connection_error is not None:
            return connection_error
        assert repo_context is not None

        if not lease_enforced:
            return {
                "success": True,
                "code": LEASE_ENFORCEMENT_DISABLED,
                "message": "Lease enforcement disabled for this repository; skipping acquire.",
                "hint": (
                    "Set kagan.github.lease_enforcement=true in repo scripts to re-enable lease "
                    "coordination."
                ),
                "holder": None,
            }

        gh_path, gh_error = self._gh.resolve_gh_cli_path()
        if gh_error is not None:
            return gh_error
        assert gh_path is not None

        github_user = await asyncio.to_thread(self._gh.run_gh_auth_username, gh_path)
        result = await asyncio.to_thread(
            self._gh.acquire_lease,
            gh_path,
            repo.path,
            str(repo_context["owner"]),
            str(repo_context["repo_name"]),
            issue_number,
            github_user=github_user,
            force_takeover=bool(request.force_takeover),
        )

        if result.success:
            return {
                "success": True,
                "code": result.code,
                "message": result.message,
                "holder": result.holder.to_dict() if result.holder else None,
            }

        response: dict[str, Any] = {
            "success": False,
            "code": result.code,
            "message": result.message,
        }
        if result.code == LEASE_HELD_BY_OTHER:
            if result.holder is not None:
                response["holder"] = result.holder.to_dict()
                response["hint"] = (
                    f"Issue #{issue_number} is locked by another instance. "
                    "Use force_takeover=true to take over the lease."
                )
            else:
                response["hint"] = (
                    "Lease holder metadata could not be verified. "
                    "Retry, or use force_takeover=true to proceed."
                )
        return response

    async def release_lease(self, request: ReleaseLeaseInput) -> dict[str, Any]:
        """Release a lease on a GitHub issue."""
        if request.issue_number is None:
            return _h.error(
                GH_ISSUE_REQUIRED,
                "issue_number is required",
                "Provide the GitHub issue number to release lease for",
            )
        issue_number, issue_error = _h.coerce_positive_int(
            value=request.issue_number,
            field_name="issue_number",
            invalid_code=GH_ISSUE_NUMBER_INVALID,
        )
        if issue_error is not None:
            return issue_error
        assert issue_number is not None

        repo, resolve_error = await _h.resolve_connect_target(
            self._core,
            request.project_id,
            request.repo_id,
        )
        if resolve_error is not None:
            return resolve_error
        assert repo is not None

        lease_enforced = load_lease_enforcement_state(repo.scripts)
        repo_context, connection_error = _h.resolve_connected_repo_context(
            repo,
            require_owner_repo=lease_enforced,
        )
        if connection_error is not None:
            return connection_error
        assert repo_context is not None

        if not lease_enforced:
            return {
                "success": True,
                "code": LEASE_ENFORCEMENT_DISABLED,
                "message": "Lease enforcement disabled for this repository; skipping release.",
            }

        gh_path, gh_error = self._gh.resolve_gh_cli_path()
        if gh_error is not None:
            return gh_error
        assert gh_path is not None

        result = await asyncio.to_thread(
            self._gh.release_lease,
            gh_path,
            repo.path,
            str(repo_context["owner"]),
            str(repo_context["repo_name"]),
            issue_number,
        )
        return {
            "success": result.success,
            "code": result.code,
            "message": result.message,
        }

    async def get_lease_state(self, request: GetLeaseStateInput) -> dict[str, Any]:
        """Get the current lease state for a GitHub issue."""
        if request.issue_number is None:
            return _h.error(
                GH_ISSUE_REQUIRED,
                "issue_number is required",
                "Provide the GitHub issue number to check lease state for",
            )
        issue_number, issue_error = _h.coerce_positive_int(
            value=request.issue_number,
            field_name="issue_number",
            invalid_code=GH_ISSUE_NUMBER_INVALID,
        )
        if issue_error is not None:
            return issue_error
        assert issue_number is not None

        repo, resolve_error = await _h.resolve_connect_target(
            self._core,
            request.project_id,
            request.repo_id,
        )
        if resolve_error is not None:
            return resolve_error
        assert repo is not None

        lease_enforced = load_lease_enforcement_state(repo.scripts)
        repo_context, connection_error = _h.resolve_connected_repo_context(
            repo,
            require_owner_repo=lease_enforced,
        )
        if connection_error is not None:
            return connection_error
        assert repo_context is not None

        if not lease_enforced:
            return {
                "success": True,
                "code": LEASE_STATE_OK,
                "state": {
                    "is_locked": False,
                    "is_held_by_current_instance": False,
                    "can_acquire": True,
                    "requires_takeover": False,
                    "holder": None,
                    "enforcement_enabled": False,
                },
            }

        gh_path, gh_error = self._gh.resolve_gh_cli_path()
        if gh_error is not None:
            return gh_error
        assert gh_path is not None

        state, error = await asyncio.to_thread(
            self._gh.get_lease_state,
            gh_path,
            repo.path,
            str(repo_context["owner"]),
            str(repo_context["repo_name"]),
            issue_number,
        )

        if error:
            return {
                "success": False,
                "code": LEASE_STATE_ERROR,
                "message": f"Failed to get lease state: {error}",
            }

        if state is None:
            return {
                "success": False,
                "code": LEASE_STATE_ERROR,
                "message": "Failed to get lease state",
            }

        return {
            "success": True,
            "code": LEASE_STATE_OK,
            "state": {
                "is_locked": state.is_locked,
                "is_held_by_current_instance": state.is_held_by_current_instance,
                "can_acquire": state.can_acquire,
                "requires_takeover": state.requires_takeover,
                "holder": state.holder.to_dict() if state.holder else None,
            },
        }

    async def sync_task_status_to_issue(
        self,
        request: SyncTaskStatusInput,
    ) -> dict[str, Any]:
        """Sync Kagan task status to linked GitHub issue (close/reopen + labels).

        Label convention: ``kagan:in-progress``, ``kagan:review``, ``kagan:done``.
        Close/reopen is authoritative; label failures are best-effort.
        """
        task_id = _h.non_empty_str(request.task_id)
        project_id = _h.non_empty_str(request.project_id)

        if not task_id:
            return _h.error(GH_TASK_REQUIRED, "task_id is required", "Provide the task_id")
        if not project_id:
            return _h.error(GH_PROJECT_REQUIRED, "project_id is required", "Provide the project_id")

        to_status_str = _h.non_empty_str(request.to_status)
        if not to_status_str:
            return _h.error(
                "GH_STATUS_REQUIRED",
                "to_status is required",
                "Provide the target task status",
            )

        try:
            to_status = TaskStatus(to_status_str)
        except ValueError:
            return _h.error(
                "GH_STATUS_INVALID",
                f"Invalid task status: {to_status_str}",
                f"Expected one of: {', '.join(s.value for s in TaskStatus)}",
            )

        try:
            repos = await self._core.get_project_repos(project_id)
        except Exception as exc:
            return _h.error(
                GH_SYNC_FAILED,
                f"Failed to fetch project repos: {exc}",
                "Check project_id is valid",
            )

        if not repos:
            return {"success": True, "message": "No repos in project", "actions": []}

        # Find connected repo with a mapping for this task
        for repo in repos:
            connection_state = load_connection_state(repo.scripts)
            if not connection_state.raw_value:
                continue
            connection = connection_state.normalized
            if connection is None:
                continue

            issue_mapping = load_issue_mapping_state(repo.scripts)
            issue_number = issue_mapping.get_issue_number(task_id)
            if issue_number is None:
                continue

            owner_repo = resolve_owner_repo(connection)
            if owner_repo is None:
                continue

            # Found the target repo + issue. Execute status sync.
            return await self._apply_status_sync(
                repo=repo,
                issue_number=issue_number,
                to_status=to_status,
            )

        # No mapped issue found — not an error, just nothing to sync.
        return {
            "success": True,
            "message": f"Task {task_id} has no linked GitHub issue",
            "actions": [],
        }

    async def _apply_status_sync(
        self,
        *,
        repo: Any,
        issue_number: int,
        to_status: TaskStatus,
    ) -> dict[str, Any]:
        """Apply close/reopen and label changes to a GitHub issue."""
        gh_path, gh_error = self._gh.resolve_gh_cli_path()
        if gh_error is not None:
            detail = (
                str(gh_error.get("message"))
                if isinstance(gh_error.get("message"), str)
                else "GitHub CLI (gh) is unavailable"
            )
            return _h.error(GH_SYNC_FAILED, detail, "Install gh CLI")

        assert gh_path is not None

        # Define label sets per status
        status_labels: dict[TaskStatus, str] = {
            TaskStatus.IN_PROGRESS: "kagan:in-progress",
            TaskStatus.REVIEW: "kagan:review",
            TaskStatus.DONE: "kagan:done",
        }
        all_kagan_labels = set(status_labels.values())
        target_label = status_labels.get(to_status)
        labels_to_remove = all_kagan_labels - ({target_label} if target_label else set())

        actions: list[str] = []
        errors: list[str] = []

        # Close/reopen logic
        if to_status == TaskStatus.DONE:
            success, error = await asyncio.to_thread(
                self._gh.run_gh_issue_close, gh_path, repo.path, issue_number
            )
            if success:
                actions.append(f"closed issue #{issue_number}")
            elif error:
                errors.append(f"close failed: {error}")
        elif to_status in (TaskStatus.IN_PROGRESS, TaskStatus.REVIEW):
            # Reopen in case the issue was previously closed
            success, error = await asyncio.to_thread(
                self._gh.run_gh_issue_reopen, gh_path, repo.path, issue_number
            )
            if success:
                actions.append(f"reopened issue #{issue_number}")
            # If reopen fails (e.g. already open), that's fine — not an error.

        # Label management (best-effort)
        if target_label:
            success, error = await asyncio.to_thread(
                self._gh.run_gh_issue_label_add,
                gh_path,
                repo.path,
                issue_number,
                target_label,
            )
            if success:
                actions.append(f"added label '{target_label}'")

        for label in sorted(labels_to_remove):
            success, error = await asyncio.to_thread(
                self._gh.run_gh_issue_label_remove,
                gh_path,
                repo.path,
                issue_number,
                label,
            )
            if success:
                actions.append(f"removed label '{label}'")

        return {
            "success": True,
            "code": "TASK_STATUS_SYNCED",
            "message": f"Synced status {to_status.value} to issue #{issue_number}",
            "issue_number": issue_number,
            "to_status": to_status.value,
            "actions": actions,
            "label_errors": errors,
        }

    async def validate_review_transition(
        self,
        request: ValidateReviewTransitionInput,
    ) -> dict[str, Any]:
        """Validate REVIEW transition guardrails for GitHub-connected repos."""
        task_id = _h.non_empty_str(request.task_id)
        project_id = _h.non_empty_str(request.project_id)
        if not task_id or not project_id:
            return {"allowed": True}

        try:
            repos = await self._core.get_project_repos(project_id)
        except Exception as exc:
            # Explicit resilience boundary: guardrail verification must fail closed.
            return _h.review_guardrail_check_failed(str(exc))

        if not repos:
            return {"allowed": True}

        connected_repos: list[dict[str, Any]] = []
        for repo in repos:
            connection_state = load_connection_state(repo.scripts)
            if not connection_state.raw_value:
                continue

            connection = connection_state.normalized
            if connection is None:
                return _h.review_guardrail_check_failed("invalid GitHub connection metadata")

            connected_repos.append(
                {
                    "repo": repo,
                    "connection": connection,
                    "pr_mapping": load_pr_mapping_state(repo.scripts),
                    "issue_mapping": load_issue_mapping_state(repo.scripts),
                    "lease_enforced": load_lease_enforcement_state(repo.scripts),
                }
            )

        if not connected_repos:
            return {"allowed": True}

        owner_candidates = [
            repo_ctx
            for repo_ctx in connected_repos
            if repo_ctx["pr_mapping"].has_pr(task_id)
            or repo_ctx["issue_mapping"].get_issue_number(task_id) is not None
        ]

        if not owner_candidates:
            try:
                owner_candidates = await _h.resolve_workspace_owner_candidates(
                    self._core,
                    task_id=task_id,
                    connected_repos=connected_repos,
                )
            except Exception as exc:
                return _h.review_guardrail_check_failed(str(exc))

        if not owner_candidates:
            # Task is not scoped to a GitHub-connected repo; skip GitHub guardrails.
            return {"allowed": True}

        missing_pr_repos: list[str] = []
        lease_conflicts: list[str] = []
        gh_path: str | None = None

        for repo_ctx in owner_candidates:
            repo = repo_ctx["repo"]
            repo_label = _h.repo_identifier(repo)
            if not repo_ctx["pr_mapping"].has_pr(task_id):
                missing_pr_repos.append(repo_label)
                continue

            issue_number = repo_ctx["issue_mapping"].get_issue_number(task_id)
            if issue_number is None or not bool(repo_ctx.get("lease_enforced", True)):
                continue

            owner_repo = resolve_owner_repo(repo_ctx["connection"])
            if owner_repo is None:
                return _h.review_guardrail_check_failed(
                    f"{repo_label}: GitHub connection metadata missing owner/repo"
                )
            owner, repo_name = owner_repo

            if gh_path is None:
                gh_path, gh_error = self._gh.resolve_gh_cli_path()
                if gh_error is not None:
                    detail = (
                        str(gh_error.get("message"))
                        if isinstance(gh_error.get("message"), str)
                        else "GitHub CLI (gh) is unavailable"
                    )
                    return _h.review_guardrail_check_failed(f"{repo_label}: {detail}")
            assert gh_path is not None

            state, error = await asyncio.to_thread(
                self._gh.get_lease_state,
                gh_path,
                repo.path,
                owner,
                repo_name,
                issue_number,
            )
            if error:
                return _h.review_guardrail_check_failed(f"{repo_label}: {error}")
            if state is None:
                return _h.review_guardrail_check_failed(
                    f"{repo_label}: lease state could not be determined"
                )
            if state.is_locked and not state.is_held_by_current_instance:
                holder_info = ""
                if state.holder:
                    holder_info = f" (held by {state.holder.instance_id})"
                lease_conflicts.append(f"{repo_label}{holder_info}")

        if missing_pr_repos:
            repo_list = ", ".join(sorted(set(missing_pr_repos)))
            return {
                "allowed": False,
                "code": REVIEW_BLOCKED_NO_PR,
                "message": (
                    "REVIEW transition blocked: no linked PR for repo(s): "
                    f"{repo_list}. Create or link PRs before requesting review."
                ),
                "hint": ("Use create_pr_for_task or link_pr_to_task with repo_id for each repo."),
            }

        if lease_conflicts:
            conflict_details = ", ".join(sorted(set(lease_conflicts)))
            return {
                "allowed": False,
                "code": REVIEW_BLOCKED_LEASE,
                "message": (
                    "REVIEW transition blocked: lease held by another instance for repo(s): "
                    f"{conflict_details}. Wait for lease release before requesting review."
                ),
                "hint": "The issue is being worked on by another Kagan instance.",
            }

        return {"allowed": True}

    async def create_pr_for_task(self, request: CreatePrForTaskInput) -> dict[str, Any]:
        """Create a PR for a task and link it."""
        if not request.task_id:
            return _h.error(
                GH_TASK_REQUIRED,
                "task_id is required",
                "Provide the task ID to create a PR for",
            )

        repo, resolve_error = await _h.resolve_connect_target(
            self._core,
            request.project_id,
            request.repo_id,
        )
        if resolve_error is not None:
            return resolve_error
        assert repo is not None

        repo_context, connection_error = _h.resolve_connected_repo_context(repo)
        if connection_error is not None:
            return connection_error
        assert repo_context is not None

        connection = repo_context["connection"]
        base_branch = connection.get("default_branch", "main")

        task = await self._core.get_task(request.task_id)
        if task is None:
            return _h.error(
                GH_TASK_REQUIRED,
                f"Task not found: {request.task_id}",
                "Verify the task_id exists",
            )

        workspaces = await self._core.list_workspaces(task_id=request.task_id)
        if not workspaces:
            return _h.error(
                GH_WORKSPACE_REQUIRED,
                "Task has no workspace",
                "Create a workspace for the task first",
            )

        workspace, workspace_error = await _h.resolve_workspace_for_repo(
            self._core,
            task_id=request.task_id,
            repo=repo,
            workspaces=workspaces,
        )
        if workspace_error is not None:
            return workspace_error
        assert workspace is not None

        head_branch = _h.non_empty_str(getattr(workspace, "branch_name", None))
        if head_branch is None:
            return _h.error(
                GH_WORKSPACE_REQUIRED,
                f"Workspace {workspace.id} has no branch name",
                "Recreate workspace for this task before creating a PR",
            )

        pr_title = request.title or task.title
        pr_body = request.body or task.description or ""

        gh_path, gh_error = self._gh.resolve_gh_cli_path()
        if gh_error is not None:
            return gh_error
        assert gh_path is not None

        pr_data, error = await asyncio.to_thread(
            self._gh.run_gh_pr_create,
            gh_path,
            repo.path,
            head_branch=head_branch,
            base_branch=base_branch,
            title=pr_title,
            body=pr_body,
            draft=bool(request.draft),
        )

        if error:
            return {
                "success": False,
                "code": GH_PR_CREATE_FAILED,
                "message": f"Failed to create PR: {error}",
                "hint": "Check that changes are pushed and the branch exists on GitHub",
            }

        if pr_data is None:
            return {
                "success": False,
                "code": GH_PR_CREATE_FAILED,
                "message": "Failed to create PR: no data returned",
            }

        assert request.task_id is not None
        await _h.persist_pr_link(self._core, repo, request.task_id, pr_data)

        return {
            "success": True,
            "code": PR_CREATED,
            "message": f"Created PR #{pr_data.number}",
            "pr": {
                "number": pr_data.number,
                "url": pr_data.url,
                "state": pr_data.state,
                "head_branch": pr_data.head_branch,
                "base_branch": pr_data.base_branch,
                "is_draft": pr_data.is_draft,
            },
        }

    async def auto_create_review_pr(
        self,
        request: AutoCreateReviewPrInput,
    ) -> dict[str, Any]:
        """Auto-create a draft PR when a task transitions to REVIEW.

        Skips silently if the task already has a linked PR or if no connected
        repo can be resolved.
        """
        task_id = _h.non_empty_str(request.task_id)
        project_id = _h.non_empty_str(request.project_id)
        if not task_id or not project_id:
            return {
                "success": True,
                "code": AUTO_PR_SKIPPED,
                "message": "Missing task_id or project_id; skipping auto PR creation",
            }

        try:
            repos = await self._core.get_project_repos(project_id)
        except Exception:  # quality-allow-broad-except
            return {
                "success": True,
                "code": AUTO_PR_SKIPPED,
                "message": "Could not fetch project repos; skipping auto PR creation",
            }

        if not repos:
            return {
                "success": True,
                "code": AUTO_PR_SKIPPED,
                "message": "No repos in project; skipping auto PR creation",
            }

        for repo in repos:
            connection_state = load_connection_state(repo.scripts)
            if not connection_state.raw_value or connection_state.normalized is None:
                continue

            issue_mapping = load_issue_mapping_state(repo.scripts)
            if issue_mapping.get_issue_number(task_id) is None:
                continue

            pr_mapping = load_pr_mapping_state(repo.scripts)
            if pr_mapping.has_pr(task_id):
                return {
                    "success": True,
                    "code": AUTO_PR_SKIPPED,
                    "message": f"Task {task_id} already has a linked PR",
                }

            task = await self._core.get_task(task_id)
            if task is None:
                return {
                    "success": True,
                    "code": AUTO_PR_SKIPPED,
                    "message": f"Task {task_id} not found; skipping auto PR creation",
                }

            from kagan.core.plugins.github.domain.models import CreatePrForTaskInput

            pr_request = CreatePrForTaskInput(
                project_id=project_id,
                repo_id=repo.id if hasattr(repo, "id") else None,
                task_id=task_id,
                title=task.title,
                body="Auto-created draft PR for review",
                draft=True,
            )
            return await self.create_pr_for_task(pr_request)

        return {
            "success": True,
            "code": AUTO_PR_SKIPPED,
            "message": (f"Task {task_id} has no linked GitHub issue; skipping auto PR creation"),
        }

    async def link_pr_to_task(self, request: LinkPrToTaskInput) -> dict[str, Any]:
        """Link an existing PR to a task."""
        if not request.task_id:
            return _h.error(
                GH_TASK_REQUIRED,
                "task_id is required",
                "Provide the task ID to link the PR to",
            )

        if request.pr_number is None:
            return _h.error(
                GH_PR_NUMBER_REQUIRED,
                "pr_number is required",
                "Provide the PR number to link",
            )
        pr_number, pr_number_error = _h.coerce_positive_int(
            value=request.pr_number,
            field_name="pr_number",
            invalid_code=GH_PR_NUMBER_INVALID,
        )
        if pr_number_error is not None:
            return pr_number_error
        assert pr_number is not None

        repo, resolve_error = await _h.resolve_connect_target(
            self._core,
            request.project_id,
            request.repo_id,
        )
        if resolve_error is not None:
            return resolve_error
        assert repo is not None

        _, connection_error = _h.resolve_connected_repo_context(repo)
        if connection_error is not None:
            return connection_error

        task = await self._core.get_task(request.task_id)
        if task is None:
            return _h.error(
                GH_TASK_REQUIRED,
                f"Task not found: {request.task_id}",
                "Verify the task_id exists",
            )

        gh_path, gh_error = self._gh.resolve_gh_cli_path()
        if gh_error is not None:
            return gh_error
        assert gh_path is not None

        pr_data, error = await asyncio.to_thread(
            self._gh.run_gh_pr_view,
            gh_path,
            repo.path,
            pr_number,
        )
        if error:
            return {
                "success": False,
                "code": GH_PR_NOT_FOUND,
                "message": f"Failed to find PR #{pr_number}: {error}",
                "hint": "Verify the PR exists and you have access to it",
            }

        if pr_data is None:
            return {
                "success": False,
                "code": GH_PR_NOT_FOUND,
                "message": f"PR #{pr_number} not found",
            }

        assert request.task_id is not None
        await _h.persist_pr_link(self._core, repo, request.task_id, pr_data)

        return {
            "success": True,
            "code": PR_LINKED,
            "message": f"Linked PR #{pr_data.number} to task {request.task_id}",
            "pr": {
                "number": pr_data.number,
                "url": pr_data.url,
                "state": pr_data.state,
                "head_branch": pr_data.head_branch,
                "base_branch": pr_data.base_branch,
                "is_draft": pr_data.is_draft,
            },
        }

    async def reconcile_pr_status(self, request: ReconcilePrStatusInput) -> dict[str, Any]:
        """Reconcile PR status for a task and apply deterministic board transitions."""
        if not request.task_id:
            return _h.error(
                GH_TASK_REQUIRED,
                "task_id is required",
                "Provide the task ID to reconcile PR status for",
            )

        repo, resolve_error = await _h.resolve_connect_target(
            self._core,
            request.project_id,
            request.repo_id,
        )
        if resolve_error is not None:
            return resolve_error
        assert repo is not None

        _, connection_error = _h.resolve_connected_repo_context(repo)
        if connection_error is not None:
            return connection_error

        pr_mapping = load_pr_mapping_state(repo.scripts)
        pr_link = pr_mapping.get_pr(request.task_id)
        if pr_link is None:
            return _h.error(
                GH_NO_LINKED_PR,
                f"Task {request.task_id} has no linked PR",
                "Use create_pr_for_task or link_pr_to_task first",
            )

        task = await self._core.get_task(request.task_id)
        if task is None:
            return _h.error(
                GH_TASK_REQUIRED,
                f"Task not found: {request.task_id}",
                "Verify the task_id exists",
            )

        gh_path, gh_error = self._gh.resolve_gh_cli_path()
        if gh_error is not None:
            return gh_error
        assert gh_path is not None

        pr_data, error = await asyncio.to_thread(
            self._gh.run_gh_pr_view,
            gh_path,
            repo.path,
            pr_link.pr_number,
        )
        if error:
            return {
                "success": False,
                "code": GH_PR_NOT_FOUND,
                "message": f"Failed to fetch PR #{pr_link.pr_number}: {error}",
                "hint": (
                    "Check network connectivity and GitHub access. Retry the reconcile operation."
                ),
            }

        if pr_data is None:
            return {
                "success": False,
                "code": GH_PR_NOT_FOUND,
                "message": f"PR #{pr_link.pr_number} not found",
                "hint": "The PR may have been deleted. Consider unlinking and creating a new PR.",
            }

        pr_state_changed = pr_data.state != pr_link.pr_state
        task_status_changed = False
        previous_task_status = task.status
        new_task_status = task.status

        if pr_state_changed:
            pr_mapping.update_pr_state(request.task_id, pr_data.state)
            await self._core.update_repo_scripts(repo.id, encode_pr_mapping_update(pr_mapping))

        if pr_data.state == "MERGED":
            if task.status != TaskStatus.DONE:
                await self._core.update_task_fields(request.task_id, status=TaskStatus.DONE)
                task_status_changed = True
                new_task_status = TaskStatus.DONE
        elif pr_data.state == "CLOSED":
            if task.status not in {TaskStatus.DONE, TaskStatus.IN_PROGRESS}:
                await self._core.update_task_fields(request.task_id, status=TaskStatus.IN_PROGRESS)
                task_status_changed = True
                new_task_status = TaskStatus.IN_PROGRESS

        return {
            "success": True,
            "code": PR_STATUS_RECONCILED,
            "message": _h.build_reconcile_message(
                pr_data.number,
                pr_data.state,
                task_status_changed,
            ),
            "pr": {
                "number": pr_data.number,
                "url": pr_data.url,
                "state": pr_data.state,
                "previous_state": pr_link.pr_state,
                "state_changed": pr_state_changed,
            },
            "task": {
                "id": request.task_id,
                "status": new_task_status.value,
                "previous_status": previous_task_status.value,
                "status_changed": task_status_changed,
            },
        }

    async def check_pr_ci_status(
        self,
        request: CheckPrCiStatusInput,
    ) -> dict[str, Any]:
        """Check CI status for the PR linked to a task."""
        task_id = _h.non_empty_str(request.task_id)
        project_id = _h.non_empty_str(request.project_id)
        if not task_id:
            return _h.error(
                GH_TASK_REQUIRED,
                "task_id is required",
                "Provide the task ID to check CI status for",
            )
        if not project_id:
            return _h.error(
                GH_PROJECT_REQUIRED,
                "project_id is required",
                "Provide the project_id",
            )

        try:
            repos = await self._core.get_project_repos(project_id)
        except Exception as exc:
            return _h.error(
                GH_PR_CHECKS_FAILED,
                f"Failed to fetch project repos: {exc}",
                "Check project_id is valid",
            )

        if not repos:
            return _h.error(
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

            gh_path, gh_error = self._gh.resolve_gh_cli_path()
            if gh_error is not None:
                return gh_error
            assert gh_path is not None

            checks, error = await asyncio.to_thread(
                self._gh.run_gh_pr_checks,
                gh_path,
                repo.path,
                pr_link.pr_number,
            )
            if error:
                return {
                    "success": False,
                    "code": GH_PR_CHECKS_FAILED,
                    "message": f"Failed to fetch CI checks for PR #{pr_link.pr_number}: {error}",
                    "hint": "Check gh CLI authentication and network connectivity",
                }

            check_list = checks or []
            all_passing = (
                all(
                    c.get("conclusion") in ("SUCCESS", "success")
                    for c in check_list
                    if c.get("state") in ("COMPLETED", "completed")
                )
                if check_list
                else True
            )

            failing = [
                c.get("name", "unknown")
                for c in check_list
                if c.get("conclusion") not in ("SUCCESS", "success", None)
                and c.get("state") in ("COMPLETED", "completed")
            ]
            pending = [
                c.get("name", "unknown")
                for c in check_list
                if c.get("state") not in ("COMPLETED", "completed")
            ]

            if all_passing and not pending:
                summary = "All CI checks passing"
            elif pending:
                summary = f"{len(pending)} check(s) pending"
                all_passing = False
            else:
                summary = f"{len(failing)} check(s) failing"

            return {
                "success": True,
                "code": CI_STATUS_CHECKED,
                "message": (f"CI status for PR #{pr_link.pr_number}: {summary}"),
                "pr_number": pr_link.pr_number,
                "checks": check_list,
                "all_passing": all_passing,
                "summary": summary,
                "failing": failing,
                "pending": pending,
            }

        return _h.error(
            GH_NO_LINKED_PR,
            f"Task {task_id} has no linked PR",
            "Use create_pr_for_task or link_pr_to_task first",
        )

    async def merge_github_pr(
        self,
        request: MergeGithubPrInput,
    ) -> dict[str, Any]:
        """Merge the GitHub PR linked to a task."""
        return await _h.merge_github_pr(
            self._core,
            self._gh,
            task_id_raw=request.task_id,
            project_id_raw=request.project_id,
            merge_method_raw=request.merge_method,
        )

    async def get_pr_review_comments(
        self,
        request: GetPrReviewCommentsInput,
    ) -> dict[str, Any]:
        """Fetch PR review comments for the PR linked to a task."""
        return await _h.get_pr_review_comments(
            self._core,
            self._gh,
            task_id_raw=request.task_id,
            project_id_raw=request.project_id,
        )


__all__ = [
    "AUTO_PR_CREATED",
    "AUTO_PR_SKIPPED",
    "CI_STATUS_CHECKED",
    "GH_ISSUE_NUMBER_INVALID",
    "GH_ISSUE_REQUIRED",
    "GH_NOT_CONNECTED",
    "GH_NO_LINKED_PR",
    "GH_PR_CREATE_FAILED",
    "GH_PR_NOT_FOUND",
    "GH_PR_NUMBER_INVALID",
    "GH_PR_NUMBER_REQUIRED",
    "GH_SYNC_FAILED",
    "GH_TASK_REQUIRED",
    "GH_WORKSPACE_REQUIRED",
    "PR_MERGED",
    "PR_REVIEW_COMMENTS_FETCHED",
    "PR_STATUS_RECONCILED",
    "TASK_STATUS_SYNCED",
    "GitHubPluginUseCases",
]
