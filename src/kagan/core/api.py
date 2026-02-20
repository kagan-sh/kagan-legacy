"""Typed orchestration API for all Kagan operations.

KaganAPI wraps AppContext and exposes direct method calls
instead of stringly-typed (capability, method) dispatch. It sits at
the same level as command/query handlers and delegates to the
underlying services for each operation.

This module now contains all core API mixins directly:
- task/review operations
- project/settings/audit operations
- automation/session/job/runtime operations
- plugin dispatch and plugin UI operations
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kagan.core.api_capabilities import (
    AutomationQueueCapabilityFacade,
    JobCapabilityFacade,
    ProjectCapabilityFacade,
    SessionCapabilityFacade,
    SettingsCapabilityFacade,
    WorkspaceCapabilityFacade,
)
from kagan.core.debug_log import log as debug_log
from kagan.core.domain.enums import TaskStatus, TaskType
from kagan.core.domain.task_rules import validate_transition
from kagan.core.instrumentation import snapshot as instrumentation_snapshot
from kagan.core.plugins.sdk import (
    PLUGIN_HOOK_VALIDATE_REVIEW,
    PLUGIN_UI_DESCRIBE_METHOD,
    PluginPolicyDecision,
)
from kagan.core.plugins.ui_schema import UiCatalog, sanitize_plugin_ui_payload
from kagan.core.policy import CapabilityProfile, command, get_request_context
from kagan.core.scalars import non_empty_str
from kagan.core.services.runtime import runtime_snapshot_for_task
from kagan.core.time import utc_now

if TYPE_CHECKING:
    from collections.abc import Mapping, Sequence
    from pathlib import Path

    from kagan.core.adapters.db.schema import AuditEvent, Project, Repo, Task
    from kagan.core.bootstrap import AppContext
    from kagan.core.domain.enums import PairTerminalBackend, TaskPriority
    from kagan.core.plugins.sdk import PluginOperation, PluginRegistry
    from kagan.core.services.automation.runner import QueuedMessage, QueueLane, QueueStatus
    from kagan.core.services.jobs import JobEvent, JobRecord
    from kagan.core.services.runtime import (
        AutoOutputReadiness,
        RuntimeContextState,
        RuntimeSessionEvent,
    )
    from kagan.core.services.workspaces import MergeResult, MergeStrategy, RepoWorkspaceInput

# ── Error re-exports (canonical definitions in domain/errors.py) ──────
from kagan.core.domain.errors import (
    InvalidWorktreePathError,
    ReviewApprovalContextMissingError,
    ReviewGuardrailBlockedError,
    SessionCreateFailedError,
    SessionError,
    TaskNotFoundError,
    TaskTypeMismatchError,
    WorkspaceNotFoundError,
    task_not_found_message,
)

# ── Dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True, slots=True)
class SessionCreateResult:
    """Rich result from api.create_session()."""

    session_name: str
    already_exists: bool
    worktree_path: Path
    task: Task


logger = logging.getLogger(__name__)

_REVIEW_GUARDRAIL_TIMEOUT_SECONDS: float = 30.0

# ── Plugin UI helpers (moved from _plugin_ui.py) ─────────────────────

_DEFAULT_REFRESH_FALSE = {"repo": False, "tasks": False, "sessions": False}


# Local alias preserves existing call sites while using shared coercion.
_non_empty_str = non_empty_str


def _merge_catalogs(target: UiCatalog, incoming: UiCatalog, *, plugin_id: str) -> UiCatalog:
    diagnostics = list(target.diagnostics)
    diagnostics.extend(f"{plugin_id}: {msg}" for msg in incoming.diagnostics)
    return UiCatalog(
        schema_version=target.schema_version,
        actions=[*target.actions, *incoming.actions],
        forms=[*target.forms, *incoming.forms],
        badges=[*target.badges, *incoming.badges],
        diagnostics=diagnostics,
    )


def _sanitize_refresh(value: object) -> dict[str, bool] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, bool] = {}
    for key in ("repo", "tasks", "sessions"):
        item = value.get(key)
        if isinstance(item, bool):
            normalized[key] = item
    return normalized


def _required_fields_from_form(form: Mapping[str, Any]) -> list[str]:
    fields = form.get("fields")
    if not isinstance(fields, list):
        return []
    required: list[str] = []
    for field in fields:
        if not isinstance(field, dict):
            continue
        name = field.get("name")
        if not isinstance(name, str) or not name.strip():
            continue
        if field.get("required") is True:
            required.append(name)
    return required


def _has_required_value(value: object) -> bool:
    if value is None:
        return False
    if isinstance(value, bool):
        return True
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _resolve_session_identity() -> tuple[str, CapabilityProfile]:
    ctx = get_request_context()
    if ctx is None:
        return ("local", CapabilityProfile.MAINTAINER)
    return (ctx.request.session_id, CapabilityProfile(ctx.binding.policy.profile))


class KaganAPI:
    """Typed orchestration API for all Kagan operations.

    Wraps the existing AppContext and provides direct method calls
    instead of stringly-typed (capability, method) dispatch.
    """

    def __init__(self, ctx: AppContext) -> None:
        self._ctx = ctx
        self._projects = ProjectCapabilityFacade(ctx.project_service)
        self._workspaces = WorkspaceCapabilityFacade(ctx.workspace_service)
        self._settings = SettingsCapabilityFacade(ctx)
        self._jobs = JobCapabilityFacade(ctx.job_service)
        self._sessions = SessionCapabilityFacade(ctx.session_service)
        self._automation_queue = AutomationQueueCapabilityFacade(ctx.automation_service)

    # ── Tasks ──────────────────────────────────────────────────────────

    @command("tasks", "create", profile="operator", mutating=True, description="Create a new task.")
    async def create_task(
        self,
        title: str,
        description: str = "",
        *,
        project_id: str | None = None,
        created_by: str | None = None,
        status: TaskStatus | None = None,
        priority: TaskPriority | None = None,
        task_type: TaskType | None = None,
        terminal_backend: PairTerminalBackend | None = None,
        agent_backend: str | None = None,
        parent_id: str | None = None,
        base_branch: str | None = None,
        acceptance_criteria: list[str] | None = None,
    ) -> Task:
        """Create a new task with optional field overrides."""
        task = await self._ctx.task_service.create_task(
            title=title,
            description=description,
            project_id=project_id,
            created_by=created_by,
        )

        fields: dict[str, object] = {}
        if status is not None:
            fields["status"] = status
        if priority is not None:
            fields["priority"] = priority
        if task_type is not None:
            fields["task_type"] = task_type
        if terminal_backend is not None:
            fields["terminal_backend"] = terminal_backend
        if agent_backend is not None:
            fields["agent_backend"] = agent_backend
        if parent_id is not None:
            fields["parent_id"] = parent_id
        if base_branch is not None:
            fields["base_branch"] = base_branch
        if acceptance_criteria is not None:
            fields["acceptance_criteria"] = acceptance_criteria

        if fields:
            updated = await self._ctx.task_service.update_fields(task.id, **fields)
            if updated is not None:
                task = updated

        return task

    @command("tasks", "get", description="Get a single task by ID.")
    async def get_task(self, task_id: str) -> Task | None:
        """Get a single task by ID."""
        return await self._ctx.task_service.get_task(task_id)

    @command("tasks", "list", description="List tasks with optional project/status filter.")
    async def list_tasks(
        self,
        *,
        project_id: str | None = None,
        status: TaskStatus | None = None,
    ) -> list[Task]:
        """List tasks with optional project/status filter."""
        return await self._ctx.task_service.list_tasks(project_id=project_id, status=status)

    @command(
        "tasks", "update", profile="operator", mutating=True, description="Update task fields."
    )
    async def update_task(
        self,
        task_id: str,
        **fields: object,
    ) -> Task | None:
        """Update task fields.

        Handles task_type transitions (killing sessions or stopping agents)
        when switching between PAIR and AUTO.
        """
        current = await self._ctx.task_service.get_task(task_id)
        if current is None:
            return None

        status_value = fields.get("status")
        if status_value is not None:
            target = TaskStatus(status_value) if isinstance(status_value, str) else status_value
            validate_transition(current.status, target)

        new_task_type = fields.get("task_type")
        if isinstance(new_task_type, TaskType) and new_task_type != current.task_type:
            await self._handle_task_type_transition(
                task_id=task_id,
                current_type=current.task_type,
                new_type=new_task_type,
                fields=fields,
            )

        return await self._ctx.task_service.update_fields(task_id, **fields)

    @command(
        "tasks",
        "move",
        profile="operator",
        mutating=True,
        description="Move a task to a new status column.",
    )
    async def move_task(self, task_id: str, status: TaskStatus) -> Task | None:
        """Move a task to a new status column."""
        validate_transition(TaskStatus.BACKLOG, status)
        return await self._ctx.task_service.move(task_id, status)

    @command(
        "tasks",
        "delete",
        profile="maintainer",
        mutating=True,
        description="Delete a task.",
    )
    async def delete_task(self, task_id: str) -> tuple[bool, str]:
        """Delete a task, coordinating across services.

        Returns:
            Tuple of (success, message).
        """
        task = await self._ctx.task_service.get_task(task_id)
        if task is None:
            return False, task_not_found_message(task_id)

        return await self._ctx.workspace_service.delete_task(task)

    @command(
        "tasks",
        "update_scratchpad",
        profile="pair_worker",
        mutating=True,
        description="Append to task scratchpad.",
    )
    async def update_scratchpad(self, task_id: str, content: str) -> None:
        """Append content to a task's scratchpad."""
        existing = await self._ctx.task_service.get_scratchpad(task_id)
        updated = f"{existing}\n{content}".strip() if existing else content
        await self._ctx.task_service.update_scratchpad(task_id, updated)

    @command("tasks", "scratchpad", description="Get a task's scratchpad content.")
    async def get_scratchpad(self, task_id: str) -> str:
        """Get a task's scratchpad content."""
        return await self._ctx.task_service.get_scratchpad(task_id)

    @command("tasks", "context", description="Get task context for AI tools.")
    async def get_task_context(self, task_id: str) -> dict[str, Any]:
        """Return expanded task context for coordination and implementation.

        Collects task details, scratchpad, linked tasks, workspace info,
        and repository metadata.
        """
        task = await self._ctx.task_service.get_task(task_id)
        if task is None:
            return {"found": False, "task": None}

        scratchpad = await self._ctx.task_service.get_scratchpad(task_id)

        linked_task_ids = await self._ctx.task_service.get_task_links(task_id)
        linked_tasks: list[dict[str, Any]] = []
        for linked_task_id in linked_task_ids:
            linked = await self._ctx.task_service.get_task(linked_task_id)
            if linked is None:
                continue
            linked_tasks.append(
                {
                    "task_id": linked.id,
                    "title": linked.title,
                    "status": linked.status.value,
                    "description": linked.description,
                }
            )
        linked_tasks.sort(key=lambda item: item["task_id"])

        workspace_id: str | None = None
        workspace_branch: str | None = None
        workspace_path: str | None = None
        repos: list[dict[str, Any]] = []

        workspaces = await self._ctx.workspace_service.list_workspaces(task_id=task_id)
        if workspaces:
            workspace = workspaces[0]
            workspace_id = workspace.id
            workspace_branch = workspace.branch_name
            workspace_path = workspace.path
            try:
                workspace_repos = await self._ctx.workspace_service.get_workspace_repos(
                    workspace.id
                )
                repos = [
                    {
                        "repo_id": repo["repo_id"],
                        "name": repo["repo_name"],
                        "path": repo["repo_path"],
                        "worktree_path": repo.get("worktree_path"),
                        "target_branch": repo.get("target_branch"),
                        "has_changes": repo.get("has_changes"),
                    }
                    for repo in workspace_repos
                ]
            except (AttributeError, KeyError, LookupError, OSError, RuntimeError) as exc:
                logger.warning("API: workspace repos unavailable: %s", exc)

        if not repos:
            try:
                project_repos = await self._ctx.project_service.get_project_repos(task.project_id)
                repos = [
                    {
                        "repo_id": repo.id,
                        "name": repo.name,
                        "path": repo.path,
                        "worktree_path": None,
                        "target_branch": repo.default_branch,
                        "has_changes": None,
                    }
                    for repo in project_repos
                ]
            except (AttributeError, KeyError, LookupError, OSError, RuntimeError) as exc:
                logger.warning("API: project repos unavailable: %s", exc)

        return {
            "task_id": task.id,
            "project_id": task.project_id,
            "title": task.title,
            "description": task.description,
            "status": task.status.value,
            "acceptance_criteria": task.acceptance_criteria,
            "scratchpad": scratchpad,
            "workspace_id": workspace_id,
            "workspace_branch": workspace_branch,
            "workspace_path": workspace_path,
            "repos": repos,
            "repo_count": len(repos),
            "linked_tasks": linked_tasks,
        }

    @command("tasks", "logs", description="Return execution logs for a task.")
    async def get_task_logs(
        self,
        task_id: str,
        *,
        limit: int = 5,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Return a paginated execution-log page for a task."""
        limit = max(1, min(limit, 20))
        offset = max(0, offset)
        executions = await self._ctx.execution_service.list_executions_for_task(
            task_id,
            limit=limit,
            offset=offset,
        )
        total_runs = offset + len(executions)
        with contextlib.suppress(AttributeError, KeyError, RuntimeError):
            total_runs = max(
                total_runs,
                await self._ctx.execution_service.count_executions_for_task(task_id),
            )

        logs: list[dict[str, Any]] = []
        run_start = max(1, total_runs - offset - len(executions) + 1)
        for run_number, execution in enumerate(reversed(executions), start=run_start):
            try:
                log_entries = await self._ctx.execution_service.get_execution_log_entries(
                    execution.id
                )
                content = "\n".join(entry.logs for entry in log_entries if entry.logs).strip()
                if not content:
                    continue
                logs.append(
                    {
                        "run": run_number,
                        "content": content,
                        "created_at": execution.created_at.isoformat(),
                    }
                )
            except (AttributeError, KeyError, RuntimeError):
                pass

        next_offset = offset + len(executions)
        has_more = next_offset < total_runs
        return {
            "task_id": task_id,
            "logs": logs,
            "count": len(logs),
            "total_runs": total_runs,
            "returned_runs": len(logs),
            "offset": offset,
            "limit": limit,
            "has_more": has_more,
            "next_offset": next_offset if has_more else None,
        }

    @command("tasks", "search", description="Search tasks by text query.")
    async def search_tasks(self, query: str) -> Sequence[Task]:
        """Search tasks by text query."""
        if not query.strip():
            return []
        return await self._ctx.task_service.search(query)

    # ── Reviews ────────────────────────────────────────────────────────

    @command(
        "review",
        "request",
        profile="pair_worker",
        mutating=True,
        description="Mark task ready for review.",
    )
    async def request_review(self, task_id: str, summary: str = "") -> Task | None:
        """Move task to REVIEW status.

        For tasks in GitHub-connected repos, enforces guardrails:
        - Blocks if no linked PR exists
        - Blocks if lease is held by another instance
        """
        task = await self._ctx.task_service.get_task(task_id)
        if task is None:
            return None

        # Check REVIEW transition guardrails for GitHub-connected repos
        guardrail_result = await self._check_review_guardrails(task)
        if not guardrail_result["allowed"]:
            raise ReviewGuardrailBlockedError(
                code=str(guardrail_result.get("code", "REVIEW_BLOCKED")),
                message=str(guardrail_result.get("message", "REVIEW transition blocked")),
                hint=(
                    str(guardrail_result["hint"])
                    if isinstance(guardrail_result.get("hint"), str)
                    else None
                ),
            )

        task = await self._ctx.task_service.set_status(
            task_id, TaskStatus.REVIEW, reason="Review requested"
        )
        if task is not None:
            await self._set_latest_review_result(
                task_id,
                status="pending",
                summary=summary,
                approved=False,
            )
        return task

    async def _check_review_guardrails(self, task: Task) -> dict[str, Any]:
        """Check REVIEW transition guardrails via plugin hook operations."""
        guardrail_method = PLUGIN_HOOK_VALIDATE_REVIEW
        plugin_registry = getattr(self._ctx, "plugin_registry", None)
        if plugin_registry is None:
            return {"allowed": True}
        operations_for_method = getattr(plugin_registry, "operations_for_method", None)
        if not callable(operations_for_method):
            return {"allowed": True}
        operations = tuple(operations_for_method(guardrail_method))
        if not operations:
            return {"allowed": True}

        for operation in operations:
            plugin_id = getattr(operation, "plugin_id", "<unknown-plugin>")
            try:
                result = await asyncio.wait_for(
                    operation.handler(
                        self._ctx,
                        {
                            "task_id": task.id,
                            "project_id": task.project_id,
                        },
                    ),
                    timeout=_REVIEW_GUARDRAIL_TIMEOUT_SECONDS,
                )
            except TimeoutError as exc:
                return {
                    "allowed": False,
                    "code": "REVIEW_GUARDRAIL_TIMEOUT",
                    "message": "REVIEW transition blocked: review guardrail check timed out.",
                    "hint": (
                        "Retry, or investigate plugin health. Details: "
                        f"{plugin_id}.{guardrail_method} timed out after "
                        f"{_REVIEW_GUARDRAIL_TIMEOUT_SECONDS:.0f}s: {exc}"
                    ),
                }
            except Exception as exc:
                return {
                    "allowed": False,
                    "code": "REVIEW_GUARDRAIL_CHECK_FAILED",
                    "message": "REVIEW transition blocked: failed to verify review guardrails.",
                    "hint": (
                        "Resolve plugin health and retry. Details: "
                        f"{plugin_id}.{guardrail_method} failed: {exc}"
                    ),
                }

            if not isinstance(result, dict):
                return {
                    "allowed": False,
                    "code": "REVIEW_GUARDRAIL_CHECK_FAILED",
                    "message": "REVIEW transition blocked: failed to verify review guardrails.",
                    "hint": (
                        "Resolve plugin health and retry. Details: "
                        f"{plugin_id}.{guardrail_method} returned non-dict response."
                    ),
                }

            if not isinstance(result.get("allowed"), bool):
                return {
                    "allowed": False,
                    "code": "REVIEW_GUARDRAIL_CHECK_FAILED",
                    "message": "REVIEW transition blocked: failed to verify review guardrails.",
                    "hint": (
                        "Resolve plugin health and retry. Details: "
                        f"{plugin_id}.{guardrail_method} response missing boolean 'allowed'."
                    ),
                }

            if not bool(result["allowed"]):
                return result

        return {"allowed": True}

    @command(
        "review",
        "approve",
        profile="operator",
        mutating=True,
        description="Approve a task review.",
    )
    async def approve_task(self, task_id: str) -> Task | None:
        """Approve a task review without moving it to DONE."""
        task = await self._ctx.task_service.get_task(task_id)
        if task is None:
            return None
        if task.status is not TaskStatus.REVIEW:
            return task
        persisted = await self._set_latest_review_result(
            task_id,
            status="approved",
            summary="",
            approved=True,
        )
        if not persisted:
            raise ReviewApprovalContextMissingError(
                code="REVIEW_APPROVAL_CONTEXT_MISSING",
                message=(
                    "Cannot approve review: no execution context exists for this task. "
                    "Run or attach review execution before approving."
                ),
                hint="Create a review execution for this task, then retry approve.",
            )
        return task

    @command(
        "review",
        "reject",
        profile="operator",
        mutating=True,
        description="Reject a task review with feedback.",
    )
    async def reject_task(
        self,
        task_id: str,
        feedback: str = "",
        action: str = "reopen",
    ) -> Task | None:
        """Reject a task review with feedback."""
        task = await self._ctx.task_service.get_task(task_id)
        if task is None:
            return None
        return await self._ctx.workspace_service.apply_rejection_feedback(task, feedback, action)

    async def merge_task(self, task_id: str) -> tuple[bool, str]:
        """Merge a task's workspace into the base branch.

        Returns:
            Tuple of (success, message).
        """
        task = await self._ctx.task_service.get_task(task_id)
        if task is None:
            return False, task_not_found_message(task_id)

        if self._ctx.config.general.require_review_approval and task.status == TaskStatus.REVIEW:
            if not await self._is_latest_review_approved(task_id):
                return (
                    False,
                    "Task review must be approved before merge. "
                    "Use review_apply(action='approve') first.",
                )

        success, message = await self._ctx.workspace_service.merge_task(task)
        if not success:
            refreshed = await self._ctx.task_service.get_task(task_id)
            if refreshed is not None and refreshed.status is not TaskStatus.REVIEW:
                restored = await self._ctx.task_service.move(task_id, TaskStatus.REVIEW)
                if restored is not None:
                    message = f"{message} Task returned to REVIEW for retry."
        return success, message

    async def rebase_task(
        self, task_id: str, *, base_branch: str | None = None
    ) -> tuple[bool, str, list[str]]:
        """Rebase task worktree onto base branch.

        Returns:
            Tuple of (success, message, conflict_files).
        """
        task = await self._ctx.task_service.get_task(task_id)
        if task is None:
            return False, task_not_found_message(task_id), []

        if task.status != TaskStatus.REVIEW:
            return (
                False,
                f"Task is not in REVIEW (current: {task.status.value}). "
                "Move task to REVIEW before rebasing.",
                [],
            )

        if base_branch is not None:
            resolved_branch = base_branch.strip()
            if not resolved_branch:
                return False, "Base branch cannot be empty", []
        else:
            try:
                resolved_branch = await self.resolve_task_base_branch(task)
            except ValueError as exc:
                return False, str(exc), []

        success, message, conflict_files = await self._ctx.workspace_service.rebase_onto_base(
            task.id, resolved_branch
        )

        if success:
            return True, f"Rebased: {task.title}", []

        if not conflict_files:
            return False, f"Rebase failed: {message}", []

        await self._ctx.workspace_service.abort_rebase(task.id)

        await self._ctx.task_service.update_fields(
            task.id,
            description=(task.description or "") + "\n\n---\n_Rebase conflict detected_",
        )
        await self._ctx.task_service.move(task.id, TaskStatus.IN_PROGRESS)

        if task.task_type == TaskType.AUTO:
            refreshed = await self._ctx.task_service.get_task(task.id)
            if refreshed is not None:
                await self._ctx.automation_service.spawn_for_task(refreshed)

        return (
            False,
            f"Rebase conflict: {len(conflict_files)} file(s). Task moved to IN_PROGRESS.",
            conflict_files,
        )

    async def resolve_task_base_branch(self, task: Task) -> str:
        """Resolve effective base branch for a task.

        Resolution order:
        1. Explicit task override (`task.base_branch`)
        2. Existing workspace repo target branch
        3. Active repo default branch (or first project repo as fallback)
        """
        task_branch = (task.base_branch or "").strip()
        if task_branch:
            return task_branch

        workspaces = await self._ctx.workspace_service.list_workspaces(task_id=task.id)
        if workspaces:
            workspace_repos = await self._ctx.workspace_service.get_workspace_repos(
                workspaces[0].id
            )
            for repo in workspace_repos:
                target_branch = str(repo.get("target_branch") or "").strip()
                if target_branch:
                    return target_branch

        project_repos = await self._ctx.project_service.get_project_repos(task.project_id)
        if not project_repos:
            raise ValueError(f"Project {task.project_id} has no repositories")

        active_repo_id = self._ctx.active_repo_id
        selected_repo = None
        if active_repo_id is not None:
            selected_repo = next(
                (repo for repo in project_repos if repo.id == active_repo_id),
                None,
            )

        repo = selected_repo or project_repos[0]
        repo_branch = (repo.default_branch or "").strip()
        if repo_branch:
            return repo_branch

        repo_label = repo.display_name or repo.name
        raise ValueError(f"Repository {repo_label} has no default branch configured")

    async def _is_latest_review_approved(self, task_id: str) -> bool:
        """Check whether latest execution metadata marks review as approved."""
        execution_service = getattr(self._ctx, "execution_service", None)
        if execution_service is None:
            return False
        execution = await execution_service.get_latest_execution_for_task(task_id)
        if execution is None:
            return False
        review_result = (execution.metadata_ or {}).get("review_result")
        if not isinstance(review_result, dict):
            return False
        approved = review_result.get("approved")
        if isinstance(approved, bool):
            return approved
        status = str(review_result.get("status") or "").strip().lower()
        return status == "approved"

    async def _set_latest_review_result(
        self,
        task_id: str,
        *,
        status: str,
        summary: str,
        approved: bool,
    ) -> bool:
        """Persist review result metadata on latest task execution when available."""
        execution_service = getattr(self._ctx, "execution_service", None)
        if execution_service is None:
            return False
        execution = await execution_service.get_latest_execution_for_task(task_id)
        if execution is None:
            return False

        review_result: dict[str, object] = {
            "status": status,
            "summary": summary,
            "approved": approved,
        }
        timestamp = utc_now().isoformat()
        if status == "approved":
            review_result["completed_at"] = timestamp
        else:
            review_result["requested_at"] = timestamp

        metadata = dict(execution.metadata_ or {})
        metadata["review_result"] = review_result
        await execution_service.update_execution(execution.id, metadata=metadata)
        return True

    # ── Private helpers ────────────────────────────────────────────────

    async def _handle_task_type_transition(
        self,
        *,
        task_id: str,
        current_type: TaskType,
        new_type: TaskType,
        fields: dict[str, object],
    ) -> None:
        """Handle side effects when task_type changes between PAIR and AUTO."""
        if current_type == new_type:
            return

        if current_type == TaskType.PAIR and new_type == TaskType.AUTO:
            if await self._ctx.session_service.session_exists(task_id):
                await self._ctx.session_service.kill_session(task_id)
            fields["terminal_backend"] = None
            return

        if current_type == TaskType.AUTO and new_type == TaskType.PAIR:
            if self._ctx.automation_service.is_running(task_id):
                await self._ctx.automation_service.stop_task(task_id)

    # ── Projects ───────────────────────────────────────────────────────

    @command(
        "projects",
        "open",
        profile="maintainer",
        mutating=True,
        description="Open/switch to a project.",
    )
    async def open_project(self, project_id: str) -> Project:
        """Open/switch to a project."""
        return await self._projects.open_project(project_id)

    @command(
        "projects",
        "create",
        profile="maintainer",
        mutating=True,
        description="Create a new project with optional repositories.",
    )
    async def create_project(
        self,
        name: str,
        *,
        description: str = "",
        repo_paths: list[str | Path] | None = None,
    ) -> str:
        """Create a project and optionally attach repositories.

        Returns:
            The project ID.

        Raises:
            ValueError: If name is empty or repo_paths is not a list.
        """
        name = name.strip()
        if not name:
            msg = "Project name cannot be empty"
            raise ValueError(msg)

        if repo_paths is not None:
            if not isinstance(repo_paths, list):
                msg = "repo_paths must be a list of repository paths"
                raise ValueError(msg)
            repo_paths = [str(p).strip() for p in repo_paths if str(p).strip()]

        return await self._projects.create_project(
            name=name,
            repo_paths=repo_paths,
            description=description,
        )

    @command(
        "projects",
        "add_repo",
        profile="maintainer",
        mutating=True,
        description="Add a repository to a project.",
    )
    async def add_repo(
        self,
        project_id: str,
        repo_path: str | Path,
        *,
        is_primary: bool = False,
    ) -> str:
        """Add a repository to a project.

        Returns:
            The repo ID.

        Raises:
            ValueError: If project_id or repo_path is empty.
        """
        project_id = str(project_id).strip()
        if not project_id:
            raise ValueError("project_id cannot be empty")
        repo_path_str = str(repo_path).strip()
        if not repo_path_str:
            raise ValueError("repo_path cannot be empty")
        return await self._projects.add_repo_to_project(
            project_id=project_id,
            repo_path=repo_path_str,
            is_primary=is_primary,
        )

    @command("projects", "get", description="Get a project by ID.")
    async def get_project(self, project_id: str) -> Project | None:
        """Get a project by ID."""
        return await self._projects.get_project(project_id)

    @command("projects", "list", description="List recent projects.")
    async def list_projects(self, *, limit: int = 10) -> list[Project]:
        """List recent projects."""
        return await self._projects.list_recent_projects(limit=limit)

    @command("projects", "repos", description="Get all repos for a project.")
    async def get_project_repos(self, project_id: str) -> list[Repo]:
        """Get all repos for a project."""
        return await self._projects.get_project_repos(project_id)

    async def get_project_repo_details(self, project_id: str) -> list[dict]:
        """Get repos with junction metadata for a project."""
        return await self._projects.get_project_repo_details(project_id)

    @command(
        "projects",
        "find_by_repo_path",
        description="Find a project containing the given repository path.",
    )
    async def find_project_by_repo_path(self, repo_path: str | Path) -> Project | None:
        """Find a project containing the given repository path."""
        return await self._projects.find_project_by_repo_path(repo_path)

    async def update_repo_default_branch(
        self,
        repo_id: str,
        branch: str,
        *,
        mark_configured: bool = False,
    ) -> Repo | None:
        """Update Repo.default_branch, optionally marking branch as configured."""
        return await self._projects.update_repo_default_branch(
            repo_id,
            branch,
            mark_configured=mark_configured,
        )

    # ── Settings & Audit ───────────────────────────────────────────────

    @command("settings", "get", profile="maintainer", description="Get admin-exposed settings.")
    async def get_settings(self) -> dict[str, object]:
        """Get MCP-exposed settings snapshot."""
        return self._settings.snapshot()

    @command(
        "settings",
        "update",
        profile="maintainer",
        mutating=True,
        description="Update allowlisted settings fields.",
    )
    async def update_settings(
        self, fields: dict[str, object]
    ) -> tuple[bool, str, dict[str, object]]:
        """Update allowlisted settings fields.

        Returns:
            Tuple of (success, message, updated_fields).
        """
        return await self._settings.update(fields)

    @command("audit", "list", description="List recent audit events.")
    async def list_audit_events(
        self,
        *,
        capability: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> list[AuditEvent]:
        """List audit events with optional filtering."""
        return await self._ctx.audit_repository.list_events(
            capability=capability, limit=limit, cursor=cursor
        )

    # ── Automation ─────────────────────────────────────────────────────

    # ── Jobs ───────────────────────────────────────────────────────────

    async def submit_job(
        self,
        task_id: str,
        action: str,
        *,
        arguments: dict[str, Any] | None = None,
    ) -> JobRecord:
        """Submit an asynchronous job for a task."""
        return await self._jobs.submit(task_id, action, arguments=arguments)

    async def cancel_job(self, job_id: str, *, task_id: str) -> JobRecord | None:
        """Cancel a submitted job."""
        return await self._jobs.cancel(job_id, task_id=task_id)

    async def get_job(self, job_id: str, *, task_id: str | None = None) -> JobRecord | None:
        """Get job details, optionally verifying task ownership."""
        job = await self._ctx.job_service.get(job_id)
        if job is None:
            return None
        if task_id is not None and job.task_id != task_id:
            return None
        return job

    async def wait_job(
        self,
        job_id: str,
        *,
        task_id: str,
        timeout_seconds: float | None = None,
    ) -> JobRecord | None:
        """Wait for a job to reach terminal status."""
        return await self._jobs.wait(job_id, task_id=task_id, timeout_seconds=timeout_seconds)

    async def get_job_events(self, job_id: str, *, task_id: str) -> list[JobEvent] | None:
        """List events emitted by a submitted job."""
        return await self._jobs.events(job_id, task_id=task_id)

    # ── Sessions ───────────────────────────────────────────────────────

    async def create_session(
        self,
        task_id: str,
        *,
        worktree_path: Path | None = None,
        reuse_if_exists: bool = True,
    ) -> Any:
        """Create a PAIR session for a task.

        Returns:
            SessionCreateResult with session_name, already_exists, worktree_path, task.

        Raises:
            TaskNotFoundError: task does not exist.
            TaskTypeMismatchError: task is not PAIR type.
            WorkspaceNotFoundError: no workspace provisioned.
            InvalidWorktreePathError: provided path doesn't match expected.
            SessionCreateFailedError: backend failed to create session.
        """
        task = await self._ctx.task_service.get_task(task_id)
        if task is None:
            raise TaskNotFoundError(task_id)

        if task.task_type != TaskType.PAIR:
            raise TaskTypeMismatchError(task_id, task.task_type.value)

        expected_worktree = await self._workspaces.get_task_workspace_path(task_id)
        if expected_worktree is None:
            raise WorkspaceNotFoundError(task_id)

        resolved_worktree = expected_worktree
        if worktree_path is not None:
            provided = worktree_path.expanduser().resolve(strict=False)
            expected_resolved = expected_worktree.resolve(strict=False)
            if provided != expected_resolved:
                raise InvalidWorktreePathError(
                    task_id,
                    f"worktree_path must point to the task workspace. "
                    f"Expected: {expected_resolved}",
                )
            resolved_worktree = expected_resolved

        already_exists = await self._ctx.session_service.session_exists(task_id)
        if already_exists and not reuse_if_exists:
            await self._ctx.session_service.kill_session(task_id)
            already_exists = False

        try:
            session_name = (
                f"kagan-{task_id}"
                if already_exists
                else await self._ctx.session_service.create_session(task, resolved_worktree)
            )
        except Exception as exc:  # quality-allow-broad-except
            raise SessionCreateFailedError(task_id, exc) from exc

        return SessionCreateResult(
            session_name=session_name,
            already_exists=already_exists,
            worktree_path=resolved_worktree,
            task=task,
        )

    async def attach_session(self, task_id: str) -> bool:
        """Attach to an existing PAIR session."""
        return await self._sessions.attach(task_id)

    async def session_exists(self, task_id: str) -> bool:
        """Check if a session exists for a task."""
        return await self._sessions.exists(task_id)

    async def kill_session(self, task_id: str) -> None:
        """Kill a PAIR session."""
        await self._sessions.kill(task_id)

    # ── Automation Operations ─────────────────────────────────────────

    def is_automation_running(self, task_id: str) -> bool:
        """Check if automation is running for a task (sync)."""
        return self._automation_queue.is_running(task_id)

    def get_running_agent(self, task_id: str) -> Any:
        """Get the running agent for a task (sync)."""
        return self._automation_queue.get_running_agent(task_id)

    async def wait_for_running_agent(self, task_id: str, *, timeout: float = 2.0) -> Any:
        """Wait for a running agent to attach for a task."""
        return await self._automation_queue.wait_for_running_agent(task_id, timeout=timeout)

    async def start_automation(self) -> None:
        """Start the automation service."""
        await self._automation_queue.start()

    async def queue_message(
        self,
        session_id: str,
        content: str,
        *,
        lane: QueueLane = "implementation",
        author: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QueuedMessage:
        """Queue a follow-up message for implementation/review/planner lanes."""
        return await self._automation_queue.queue_message(
            session_id,
            content,
            lane=lane,
            author=author,
            metadata=metadata,
        )

    async def get_queue_status(
        self,
        session_id: str,
        *,
        lane: QueueLane = "implementation",
    ) -> QueueStatus:
        """Get queue status for a specific lane."""
        return await self._automation_queue.get_status(session_id, lane=lane)

    async def get_queued_messages(
        self,
        session_id: str,
        *,
        lane: QueueLane = "implementation",
    ) -> list[QueuedMessage]:
        """List queued messages without consuming them."""
        return await self._automation_queue.get_queued(session_id, lane=lane)

    async def take_queued_message(
        self,
        session_id: str,
        *,
        lane: QueueLane = "implementation",
    ) -> QueuedMessage | None:
        """Consume and return the next queued message payload for a lane."""
        return await self._automation_queue.take_queued(session_id, lane=lane)

    async def remove_queued_message(
        self,
        session_id: str,
        index: int,
        *,
        lane: QueueLane = "implementation",
    ) -> bool:
        """Remove a queued message by index from a lane."""
        return await self._automation_queue.remove_message(session_id, index, lane=lane)

    # ── Execution Operations ──────────────────────────────────────────

    async def get_execution_logs(self, execution_id: str) -> Any:
        """Return aggregated execution logs for an execution."""
        return await self._ctx.execution_service.get_execution_logs(execution_id)

    async def get_execution(self, execution_id: str) -> Any:
        """Return execution record by ID."""
        return await self._ctx.execution_service.get_execution(execution_id)

    async def get_execution_log_entries(self, execution_id: str) -> list[Any]:
        """Return ordered execution log entries for an execution."""
        return await self._ctx.execution_service.get_execution_log_entries(execution_id)

    async def get_latest_execution_for_task(self, task_id: str) -> Any:
        """Return most recent execution for a task."""
        return await self._ctx.execution_service.get_latest_execution_for_task(task_id)

    async def count_executions_for_task(self, task_id: str) -> int:
        """Return total executions for a task."""
        return await self._ctx.execution_service.count_executions_for_task(task_id)

    # ── Runtime Operations ────────────────────────────────────────────

    def get_runtime_view(self, task_id: str) -> Any:
        """Get the RuntimeTaskView for a task (in-memory projection)."""
        return self._ctx.runtime_service.get(task_id)

    def get_running_task_ids(self) -> set[str]:
        """Return the set of currently running task IDs."""
        return self._ctx.runtime_service.running_tasks()

    async def reconcile_running_tasks(self, task_ids: Sequence[str]) -> list[dict[str, Any]]:
        """Synchronize runtime task projections and return refreshed runtime snapshots."""
        unique_task_ids = tuple(dict.fromkeys(task_ids))
        if not unique_task_ids:
            return []

        await self._ctx.runtime_service.reconcile_running_tasks(unique_task_ids)
        return [
            {
                "task_id": task_id,
                "runtime": runtime_snapshot_for_task(
                    task_id=task_id,
                    runtime_service=self._ctx.runtime_service,
                ),
            }
            for task_id in unique_task_ids
        ]

    async def decide_startup(self, cwd: Path) -> Any:
        """Determine startup flow based on persisted runtime state and cwd."""
        return await self._ctx.runtime_service.decide_startup(cwd)

    async def dispatch_runtime_session(
        self,
        event: RuntimeSessionEvent,
        *,
        project_id: str | None = None,
        repo_id: str | None = None,
    ) -> RuntimeContextState:
        """Dispatch a runtime session event."""
        return await self._ctx.runtime_service.dispatch(
            event, project_id=project_id, repo_id=repo_id
        )

    @property
    def runtime_state(self) -> Any:
        """Access the current runtime session state."""
        return self._ctx.runtime_service.state

    async def prepare_auto_output(self, task: Task) -> AutoOutputReadiness:
        """Prepare AUTO output modal readiness for a task."""
        return await self._ctx.runtime_service.prepare_auto_output(task)

    async def recover_stale_auto_output(self, task: Task) -> Any:
        """Recover stale AUTO output for a task."""
        return await self._ctx.runtime_service.recover_stale_auto_output(task)

    # ── Agent health ──────────────────────────────────────────────────

    def refresh_agent_health(self) -> None:
        """Refresh agent health status."""
        self._ctx.agent_health.refresh()

    def is_agent_available(self) -> bool:
        """Check if the configured agent is available."""
        return self._ctx.agent_health.is_available()

    def get_agent_status_message(self) -> str | None:
        """Get a human-readable agent status message."""
        return self._ctx.agent_health.get_status_message()

    # ── Diffs ─────────────────────────────────────────────────────────

    async def get_all_diffs(self, workspace_id: str) -> Any:
        """Retrieve all diffs for a workspace during task review."""
        return await self._ctx.workspace_service.get_all_diffs(workspace_id)

    # ── Planner ───────────────────────────────────────────────────────

    async def save_plan_proposal(self, proposal: Any) -> Any:
        """Save a planner proposal."""
        repo = getattr(self._ctx, "planner_repository", None)
        if repo is None:
            raise RuntimeError("Planner repository not available")
        return await repo.save(proposal)

    async def get_plan_proposal(self, task_id: str) -> Any:
        """Get the latest planner proposal for a task."""
        repo = getattr(self._ctx, "planner_repository", None)
        if repo is None:
            return None
        return await repo.get_latest(task_id)

    async def save_planner_draft(
        self,
        *,
        project_id: str,
        repo_id: str | None = None,
        tasks_json: list[dict[str, Any]],
        todos_json: list[dict[str, Any]] | None = None,
    ) -> Any | None:
        """Persist a planner draft proposal."""
        repo = getattr(self._ctx, "planner_repository", None)
        if repo is None:
            return None
        return await repo.save_proposal(
            project_id=project_id,
            repo_id=repo_id,
            tasks_json=tasks_json,
            todos_json=todos_json,
        )

    async def list_pending_planner_drafts(
        self,
        project_id: str,
        *,
        repo_id: str | None = None,
    ) -> list[Any]:
        """List pending planner draft proposals for a project/repo scope."""
        repo = getattr(self._ctx, "planner_repository", None)
        if repo is None:
            return []
        return await repo.list_pending(project_id, repo_id=repo_id)

    async def update_planner_draft_status(self, proposal_id: str, status: Any) -> Any | None:
        """Update planner draft status (approved/rejected)."""
        repo = getattr(self._ctx, "planner_repository", None)
        if repo is None:
            return None
        return await repo.update_status(proposal_id, status)

    # ── Merge Operations ────────────────────────────────────────────────

    async def has_no_changes(self, task: Task) -> bool:
        """Check if a task has no uncommitted changes or new commits."""
        return await self._ctx.workspace_service.has_no_changes(task)

    async def close_exploratory(self, task: Task) -> tuple[bool, str]:
        """Close a no-change task by marking DONE and archiving its workspace."""
        return await self._ctx.workspace_service.close_exploratory(task)

    async def merge_repo(
        self,
        workspace_id: str,
        repo_id: str,
        *,
        strategy: MergeStrategy,
        pr_title: str | None = None,
        pr_body: str | None = None,
        commit_message: str | None = None,
    ) -> MergeResult:
        """Merge a single repo's changes."""
        return await self._ctx.workspace_service.merge_repo(
            workspace_id,
            repo_id,
            strategy=strategy,
            pr_title=pr_title,
            pr_body=pr_body,
            commit_message=commit_message,
        )

    async def apply_rejection_feedback(
        self, task: Task, feedback: str | None, action: str
    ) -> Task | None:
        """Apply rejection feedback and move a task out of REVIEW."""
        return await self._ctx.workspace_service.apply_rejection_feedback(task, feedback, action)

    async def merge_task_direct(self, task: Task) -> tuple[bool, str]:
        """Merge task changes directly (bypassing review-gate logic)."""
        return await self._ctx.workspace_service.merge_task(task)

    # ── Workspace Operations ──────────────────────────────────────────

    async def get_task_workspace_path(self, task_id: str) -> Path | None:
        """Get the filesystem path for a task's workspace."""
        return await self._workspaces.get_task_workspace_path(task_id)

    async def provision_workspace(self, *, task_id: str, repos: list[RepoWorkspaceInput]) -> str:
        """Provision a workspace with worktrees for all repos."""
        return await self._workspaces.provision_workspace(task_id, repos)

    async def list_workspaces(self, *, task_id: str | None = None) -> list[Any]:
        """List workspaces, optionally filtered by task."""
        return await self._workspaces.list_workspaces(task_id=task_id)

    async def get_workspace_repos(self, workspace_id: str) -> list[dict[str, Any]]:
        """List repository records for a workspace."""
        return await self._workspaces.get_workspace_repos(workspace_id)

    async def cleanup_orphaned_workspaces(self, valid_task_ids: set[str]) -> list[str]:
        """Clean up workspaces whose tasks no longer exist."""
        return await self._workspaces.cleanup_orphaned_workspaces(valid_task_ids)

    async def cleanup_workspace_artifacts(
        self,
        valid_workspace_ids: set[str],
        *,
        prune_worktrees: bool = True,
        gc_branches: bool = True,
    ) -> Any:
        """Run janitor cleanup for stale worktrees and orphan kagan/* branches.

        This performs two cleanup operations:
        1. Worktree pruning: Runs `git worktree prune` on all project repos.
        2. Branch GC: Deletes orphaned `kagan/*` branches not in valid_workspace_ids.

        Returns:
            JanitorResult with worktrees_pruned, branches_deleted, repos_processed.
        """
        return await self._workspaces.cleanup_workspace_artifacts(
            valid_workspace_ids,
            prune_worktrees=prune_worktrees,
            gc_branches=gc_branches,
        )

    async def cleanup_stale_done_workspaces(self, *, older_than_days: int) -> int:
        """Archive DONE-task workspaces older than a configured age threshold."""
        return await self._workspaces.cleanup_stale_done_workspaces(older_than_days=older_than_days)

    async def get_workspace_diff(self, task_id: str, *, base_branch: str) -> str:
        """Get the diff for a task's workspace against a base branch."""
        return await self._ctx.workspace_service.get_diff(task_id, base_branch)

    async def get_workspace_commit_log(self, task_id: str, *, base_branch: str) -> list[str]:
        """Get commit log for a task workspace against a base branch."""
        return await self._ctx.workspace_service.get_commit_log(task_id, base_branch)

    async def get_workspace_diff_stats(self, task_id: str, *, base_branch: str) -> str:
        """Get summarized diff stats for a task workspace against a base branch."""
        return await self._ctx.workspace_service.get_diff_stats(task_id, base_branch)

    async def get_repo_diff(self, workspace_id: str, repo_id: str) -> Any:
        """Get diff details for one repository in a workspace."""
        return await self._ctx.workspace_service.get_repo_diff(workspace_id, repo_id)

    async def rebase_workspace(self, task_id: str, base_branch: str) -> tuple[bool, str, list[str]]:
        """Rebase a task's workspace onto a base branch."""
        return await self._ctx.workspace_service.rebase_onto_base(task_id, base_branch)

    async def abort_workspace_rebase(self, task_id: str) -> None:
        """Abort an in-progress rebase for a task's workspace."""
        await self._ctx.workspace_service.abort_rebase(task_id)

    # ── Diagnostics ───────────────────────────────────────────────────

    @command(
        "diagnostics",
        "instrumentation",
        profile="maintainer",
        description="Return in-memory instrumentation aggregates.",
    )
    async def get_instrumentation(self) -> dict[str, Any]:
        """Return in-memory instrumentation aggregates."""
        return instrumentation_snapshot()

    # ── Plugin dispatch ───────────────────────────────────────────────

    async def invoke_plugin(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Invoke a registered plugin operation by capability and method.

        Args:
            capability: Plugin capability namespace.
            method: Operation method name.
            params: Optional parameters dict.

        Returns:
            Plugin operation result dict.

        Raises:
            RuntimeError: If plugin registry or operation is not available.
        """
        plugin_registry = getattr(self._ctx, "plugin_registry", None)
        if plugin_registry is None:
            raise RuntimeError("Plugin registry is not initialized")

        operation = plugin_registry.resolve_operation(capability, method)
        if operation is None:
            msg = f"Plugin operation not registered: {capability}.{method}"
            raise RuntimeError(msg)

        result = await operation.handler(self._ctx, params or {})
        if not isinstance(result, dict):
            msg = f"Plugin operation returned invalid payload: {capability}.{method}"
            raise RuntimeError(msg)
        return result

    # ── Plugin UI ─────────────────────────────────────────────────────

    def _plugin_registry(self) -> PluginRegistry:
        plugin_registry = getattr(self._ctx, "plugin_registry", None)
        if plugin_registry is None:
            raise RuntimeError("Plugin registry is not initialized")
        return plugin_registry

    def _plugin_ui_allowlist(self) -> set[str] | None:
        """Return the plugin UI allowlist, or ``None`` if all plugins are allowed.

        An empty configured list means "allow everything" (no restriction).
        """
        allowlist = getattr(self._ctx.config.ui, "tui_plugin_ui_allowlist", None)
        if not isinstance(allowlist, list):
            return None
        entries = {item for item in allowlist if isinstance(item, str) and item.strip()}
        return entries if entries else None

    def _evaluate_policy(
        self,
        registry: PluginRegistry,
        *,
        capability: str,
        method: str,
        params: Mapping[str, Any],
    ) -> PluginPolicyDecision | None:
        session_id, profile = _resolve_session_identity()
        return registry.evaluate_policy(
            capability=capability,
            method=method,
            session_id=session_id,
            profile=profile,
            params=params,
        )

    async def plugin_ui_catalog(
        self,
        *,
        project_id: str,
        repo_id: str | None = None,
    ) -> dict[str, Any]:
        cleaned_project_id, cleaned_repo_id = self._clean_project_repo_args(project_id, repo_id)

        allowlist = self._plugin_ui_allowlist()

        registry = self._plugin_registry()
        catalog = UiCatalog(schema_version="1", actions=[], forms=[], badges=[], diagnostics=[])
        params: dict[str, Any] = {"project_id": cleaned_project_id}
        if cleaned_repo_id is not None:
            params["repo_id"] = cleaned_repo_id

        for operation in registry.operations_for_method(PLUGIN_UI_DESCRIBE_METHOD):
            if allowlist is not None and operation.plugin_id not in allowlist:
                continue
            if operation.mutating:
                catalog = _merge_catalogs(
                    catalog,
                    UiCatalog(
                        schema_version="1",
                        actions=[],
                        forms=[],
                        badges=[],
                        diagnostics=["ui_describe must be non-mutating"],
                    ),
                    plugin_id=operation.plugin_id,
                )
                continue
            decision = self._evaluate_policy(
                registry,
                capability=operation.capability,
                method=operation.method,
                params=params,
            )
            if decision is not None and not decision.allowed:
                catalog = _merge_catalogs(
                    catalog,
                    UiCatalog(
                        schema_version="1",
                        actions=[],
                        forms=[],
                        badges=[],
                        diagnostics=[f"policy denied: {decision.code}"],
                    ),
                    plugin_id=operation.plugin_id,
                )
                continue
            result = await operation.handler(self._ctx, params)
            sanitized = sanitize_plugin_ui_payload(result, plugin_id=operation.plugin_id)
            if sanitized.diagnostics:
                debug_log.debug(
                    "[PluginUI] ui_describe diagnostics",
                    plugin=operation.plugin_id,
                    diagnostics=sanitized.diagnostics,
                )
            catalog = _merge_catalogs(catalog, sanitized, plugin_id=operation.plugin_id)

        response: dict[str, Any] = {
            "schema_version": catalog.schema_version,
            "actions": catalog.actions,
            "forms": catalog.forms,
            "badges": catalog.badges,
        }
        if catalog.diagnostics:
            response["diagnostics"] = catalog.diagnostics
        return response

    async def plugin_ui_invoke(
        self,
        *,
        project_id: str,
        plugin_id: str,
        action_id: str,
        repo_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cleaned_project_id, cleaned_repo_id = self._clean_project_repo_args(project_id, repo_id)
        cleaned_plugin_id = _non_empty_str(plugin_id)
        cleaned_action_id = _non_empty_str(action_id)
        if cleaned_plugin_id is None:
            raise ValueError("plugin_id is required")
        if cleaned_action_id is None:
            raise ValueError("action_id is required")

        allowlist = self._plugin_ui_allowlist()
        if allowlist is not None and cleaned_plugin_id not in allowlist:
            raise ValueError(f"Plugin '{cleaned_plugin_id}' is not allowlisted for TUI UI")

        if inputs is not None and not isinstance(inputs, dict):
            raise ValueError("inputs must be an object when provided")
        normalized_inputs = dict(inputs or {})

        registry = self._plugin_registry()
        describe_ops: list[PluginOperation] = [
            op
            for op in registry.operations_for_method(PLUGIN_UI_DESCRIBE_METHOD)
            if op.plugin_id == cleaned_plugin_id
        ]
        if not describe_ops:
            raise ValueError(f"Plugin '{cleaned_plugin_id}' did not register ui_describe")
        if len(describe_ops) > 1:
            raise RuntimeError(f"Plugin '{cleaned_plugin_id}' registered multiple ui_describe ops")
        describe_op = describe_ops[0]

        describe_params: dict[str, Any] = {"project_id": cleaned_project_id}
        if cleaned_repo_id is not None:
            describe_params["repo_id"] = cleaned_repo_id

        decision = self._evaluate_policy(
            registry,
            capability=describe_op.capability,
            method=describe_op.method,
            params=describe_params,
        )
        if decision is not None and not decision.allowed:
            return {
                "ok": False,
                "code": decision.code,
                "message": decision.message,
                "data": None,
                "refresh": dict(_DEFAULT_REFRESH_FALSE),
            }

        describe_payload = await describe_op.handler(self._ctx, describe_params)
        catalog = sanitize_plugin_ui_payload(describe_payload, plugin_id=cleaned_plugin_id)
        action = next(
            (item for item in catalog.actions if item.get("action_id") == cleaned_action_id),
            None,
        )
        if action is None:
            raise ValueError(f"Unknown plugin action: {cleaned_plugin_id}.{cleaned_action_id}")

        form_id = action.get("form_id")
        if isinstance(form_id, str) and form_id.strip():
            form = next(
                (
                    item
                    for item in catalog.forms
                    if item.get("form_id") == form_id and item.get("plugin_id") == cleaned_plugin_id
                ),
                None,
            )
            if form is None:
                raise ValueError(f"Action references unknown form_id: {form_id}")
            required_fields = _required_fields_from_form(form)
            effective_inputs = dict(normalized_inputs)
            effective_inputs.setdefault("project_id", cleaned_project_id)
            if cleaned_repo_id is not None:
                effective_inputs.setdefault("repo_id", cleaned_repo_id)
            missing = [
                name
                for name in required_fields
                if not _has_required_value(effective_inputs.get(name))
            ]
            if missing:
                missing_str = ", ".join(missing)
                raise ValueError(f"Missing required input field(s): {missing_str}")

        operation = action.get("operation")
        if not isinstance(operation, dict):
            raise ValueError("Action operation must be an object")
        capability = _non_empty_str(operation.get("capability"))
        method = _non_empty_str(operation.get("method"))
        if capability is None or method is None:
            raise ValueError("Action operation requires capability and method")

        plugin_operation = registry.resolve_operation(capability, method)
        if plugin_operation is None:
            return {
                "ok": False,
                "code": "PLUGIN_OPERATION_NOT_FOUND",
                "message": f"Plugin operation is not registered: {capability}.{method}",
                "data": None,
                "refresh": dict(_DEFAULT_REFRESH_FALSE),
            }
        if plugin_operation.plugin_id != cleaned_plugin_id:
            return {
                "ok": False,
                "code": "PLUGIN_OPERATION_MISMATCH",
                "message": "Action operation belongs to a different plugin",
                "data": None,
                "refresh": dict(_DEFAULT_REFRESH_FALSE),
            }

        invoke_params: dict[str, Any] = {"project_id": cleaned_project_id}
        if cleaned_repo_id is not None:
            invoke_params["repo_id"] = cleaned_repo_id
        for key in ("project_id", "plugin_id", "action_id"):
            normalized_inputs.pop(key, None)
        if "repo_id" in invoke_params:
            normalized_inputs.pop("repo_id", None)
        invoke_params.update(normalized_inputs)

        invoke_decision = self._evaluate_policy(
            registry,
            capability=plugin_operation.capability,
            method=plugin_operation.method,
            params=invoke_params,
        )
        if invoke_decision is not None and not invoke_decision.allowed:
            return {
                "ok": False,
                "code": invoke_decision.code,
                "message": invoke_decision.message,
                "data": None,
                "refresh": dict(_DEFAULT_REFRESH_FALSE),
            }

        try:
            result = await plugin_operation.handler(self._ctx, invoke_params)
        except Exception as exc:  # quality-allow-broad-except
            return {
                "ok": False,
                "code": "PLUGIN_HANDLER_ERROR",
                "message": f"Plugin handler failed: {exc}",
                "data": None,
                "refresh": dict(_DEFAULT_REFRESH_FALSE),
            }

        if not isinstance(result, dict):
            return {
                "ok": False,
                "code": "PLUGIN_INVALID_RESULT",
                "message": "Plugin handler returned invalid payload",
                "data": None,
                "refresh": dict(_DEFAULT_REFRESH_FALSE),
            }

        ok: bool
        code: str
        message: str
        if isinstance(result.get("success"), bool):
            ok = bool(result.get("success"))
            code = str(result.get("code") or ("OK" if ok else "PLUGIN_ERROR"))
            message = str(result.get("message") or ("OK" if ok else "Plugin operation failed"))
        else:
            ok = True
            code = "OK"
            message = "OK"

        default_refresh = dict(_DEFAULT_REFRESH_FALSE)
        if plugin_operation.mutating:
            default_refresh.update({"repo": True, "tasks": True})
        refresh_override = _sanitize_refresh(result.get("refresh"))
        if refresh_override:
            default_refresh.update(refresh_override)

        data = dict(result)
        data.pop("refresh", None)
        return {
            "ok": ok,
            "code": code,
            "message": message,
            "data": data,
            "refresh": default_refresh,
        }

    @staticmethod
    def _clean_project_repo_args(project_id: str, repo_id: str | None) -> tuple[str, str | None]:
        cleaned_project_id = project_id.strip()
        if not cleaned_project_id:
            raise ValueError("project_id is required")

        cleaned_repo_id: str | None = None
        if repo_id is not None:
            normalized_repo_id = repo_id.strip()
            if not normalized_repo_id:
                raise ValueError("repo_id must be a non-empty string when provided")
            cleaned_repo_id = normalized_repo_id
        return cleaned_project_id, cleaned_repo_id


__all__ = [
    "InvalidWorktreePathError",
    "KaganAPI",
    "ReviewApprovalContextMissingError",
    "ReviewGuardrailBlockedError",
    "SessionCreateFailedError",
    "SessionCreateResult",
    "SessionError",
    "TaskNotFoundError",
    "TaskTypeMismatchError",
    "WorkspaceNotFoundError",
]
