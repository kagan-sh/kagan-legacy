"""Core-backed TUI API adapter.

Provides CoreBackedApi which wraps KaganSDK with result-unwrapping logic
used by TUI screens, and CoreBackedContext which bundles app-level state.

Uses canonical Project and Repo models from SDK for attribute access (.id, .path).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from kagan.core.config import KaganConfig
    from kagan.sdk import KaganSDK


@dataclass(frozen=True, slots=True)
class WorkspaceView:
    """Workspace shape consumed by TUI screens/widgets."""

    id: str
    project_id: str | None
    task_id: str | None
    branch_name: str
    path: str
    status: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


def _value_from(source: object, key: str) -> object:
    if isinstance(source, dict):
        return source.get(key)
    return getattr(source, key, None)


def _normalize_optional_text(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _normalize_status(value: object) -> str | None:
    if value is None:
        return None
    enum_value = getattr(value, "value", None)
    if isinstance(enum_value, str):
        normalized = enum_value.strip()
        return normalized or None
    return _normalize_optional_text(value)


def _normalize_workspace_view(workspace: object) -> WorkspaceView:
    workspace_id = _normalize_optional_text(_value_from(workspace, "id"))
    if workspace_id is None:
        # Some payloads use workspace_id instead of id.
        workspace_id = _normalize_optional_text(_value_from(workspace, "workspace_id"))

    return WorkspaceView(
        id=workspace_id or "",
        project_id=_normalize_optional_text(_value_from(workspace, "project_id")),
        task_id=_normalize_optional_text(_value_from(workspace, "task_id")),
        branch_name=_normalize_optional_text(_value_from(workspace, "branch_name")) or "",
        path=_normalize_optional_text(_value_from(workspace, "path")) or "",
        status=_normalize_status(_value_from(workspace, "status")),
        created_at=_normalize_optional_text(_value_from(workspace, "created_at")),
        updated_at=_normalize_optional_text(_value_from(workspace, "updated_at")),
    )


def _normalize_dict_list(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def _normalize_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text:
            normalized.append(text)
    return normalized


def _normalize_plugin_ui_catalog(payload: object) -> dict[str, Any]:
    catalog: dict[str, Any] = {
        "schema_version": _normalize_optional_text(_value_from(payload, "schema_version")) or "1",
        "actions": _normalize_dict_list(_value_from(payload, "actions")),
        "forms": _normalize_dict_list(_value_from(payload, "forms")),
        "badges": _normalize_dict_list(_value_from(payload, "badges")),
    }
    diagnostics = _normalize_str_list(_value_from(payload, "diagnostics"))
    if diagnostics:
        catalog["diagnostics"] = diagnostics
    return catalog


def _normalize_refresh_payload(value: object) -> dict[str, bool] | None:
    if not isinstance(value, dict):
        return None
    normalized: dict[str, bool] = {}
    for key, raw in value.items():
        if not isinstance(key, str):
            continue
        cleaned_key = key.strip()
        if not cleaned_key:
            continue
        normalized[cleaned_key] = bool(raw)
    return normalized or None


def _normalize_plugin_ui_invoke(payload: object) -> dict[str, Any]:
    data = _value_from(payload, "data")
    response: dict[str, Any] = {
        "ok": bool(_value_from(payload, "ok")),
        "code": _normalize_optional_text(_value_from(payload, "code")) or "",
        "message": _normalize_optional_text(_value_from(payload, "message")) or "",
        "data": data if isinstance(data, dict) else None,
    }
    refresh = _normalize_refresh_payload(_value_from(payload, "refresh"))
    if refresh is not None:
        response["refresh"] = refresh
    return response


class CoreBackedApi:
    """API adapter that forwards calls to core via KaganSDK.

    Wraps KaganSDK with result-unwrapping, error handling, and stub methods
    that TUI screens depend on.
    """

    def __init__(self, sdk: KaganSDK) -> None:
        self._sdk = sdk

    def is_agent_available(self) -> bool:
        return True

    def get_agent_status_message(self) -> str | None:
        return None

    def refresh_agent_health(self) -> None:
        return None

    async def create_task(
        self,
        title: str,
        description: str = "",
        *,
        project_id: str | None = None,
        created_by: str | None = None,
        **fields: Any,
    ):
        result = await self._sdk.tasks_create(
            title=title,
            description=description,
            project_id=project_id,
            created_by=created_by,
            **fields,
        )
        if not result.success:
            raise TypeError(f"Failed to create task: {result.message}")
        task_result = await self._sdk.tasks_get(result.task_id)
        return task_result.task

    async def get_task(self, task_id: str):
        result = await self._sdk.tasks_get(task_id)
        return result.task

    async def list_tasks(
        self,
        *,
        project_id: str | None = None,
        status: str | None = None,
        filter: str | None = None,
    ):
        result = await self._sdk.tasks_list(
            project_id=project_id,
            status=status or filter,
        )
        return result.tasks

    async def search_tasks(self, query: str):
        result = await self._sdk.tasks_search(query)
        return result.tasks

    async def update_task(self, task_id: str, **fields: Any):
        result = await self._sdk.tasks_update(task_id, **fields)
        if result.success:
            return await self.get_task(task_id)
        return None

    async def move_task(self, task_id: str, status: str):
        result = await self._sdk.tasks_move(task_id, status)
        if result.success:
            return await self.get_task(task_id)
        return None

    async def delete_task(self, task_id: str):
        result = await self._sdk.tasks_delete(task_id)
        return result.success, result.message

    async def get_scratchpad(self, task_id: str):
        result = await self._sdk.tasks_scratchpad(task_id)
        return result.content

    async def update_scratchpad(self, task_id: str, content: str):
        result = await self._sdk.tasks_update_scratchpad(task_id, content)
        return result.success

    async def open_project(self, project_id: str):
        result = await self._sdk.projects_open(project_id)
        if result.project:
            return result.project
        raise TypeError(f"Failed to open project: {project_id}")

    async def create_project(
        self,
        name: str,
        *,
        description: str = "",
        repo_paths: list[str] | None = None,
    ):
        result = await self._sdk.projects_create(name, description, repo_paths)
        return result.project_id if result.success else ""

    async def add_repo(
        self,
        project_id: str,
        repo_path: str,
        *,
        is_primary: bool = False,
    ):
        result = await self._sdk.projects_add_repo(project_id, repo_path, is_primary)
        return result.repo_id if result.success else ""

    async def get_project(self, project_id: str):
        result = await self._sdk.projects_get(project_id)
        return result.project

    async def list_projects(self, *, limit: int = 10):
        result = await self._sdk.projects_list(limit)
        return result.projects

    async def get_project_repos(self, project_id: str):
        result = await self._sdk.projects_repos(project_id)
        return result.repos

    async def get_project_repo_details(self, project_id: str):
        result = await self._sdk.projects_repos(project_id)
        return result.repos

    async def find_project_by_repo_path(self, repo_path: str | Path):
        result = await self._sdk.projects_find_by_repo_path(str(repo_path))
        return result.project

    async def update_repo_default_branch(
        self,
        repo_id: str,
        branch: str,
        *,
        mark_configured: bool = False,
    ):
        result = await self._sdk.update_repo_default_branch(repo_id, branch, mark_configured)
        return result

    async def get_settings(self):
        result = await self._sdk.settings_get()
        return result.settings

    async def update_settings(self, fields: dict[str, object]):
        result = await self._sdk.settings_update(fields)
        return result.success, result.message or "", result.updated, result.settings

    async def invoke_plugin(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ):
        result = await self._sdk.plugins_invoke(capability, method, params)
        return result.result or {}

    async def plugin_ui_catalog(
        self,
        *,
        project_id: str,
        repo_id: str | None = None,
    ):
        result = await self._sdk.plugin_ui_catalog(project_id, repo_id)
        return _normalize_plugin_ui_catalog(result)

    async def plugin_ui_invoke(
        self,
        *,
        project_id: str,
        plugin_id: str,
        action_id: str,
        repo_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ):
        result = await self._sdk.plugin_ui_invoke(
            project_id,
            plugin_id,
            action_id,
            repo_id,
            inputs,
        )
        return _normalize_plugin_ui_invoke(result)

    async def submit_job(
        self,
        task_id: str,
        action: str,
        *,
        arguments: dict[str, Any] | None = None,
    ):
        result = await self._sdk.jobs_submit(task_id, action, arguments)
        return result

    async def wait_job(
        self,
        job_id: str,
        *,
        task_id: str,
        timeout_seconds: float | None = None,
    ):
        result = await self._sdk.jobs_wait(job_id, task_id, timeout_seconds or 30.0)
        return result

    async def cancel_job(self, job_id: str, *, task_id: str):
        result = await self._sdk.jobs_cancel(job_id, task_id)
        return result

    async def create_session(
        self,
        task_id: str,
        *,
        worktree_path: Path | None = None,
        reuse_if_exists: bool = True,
    ):
        result = await self._sdk.sessions_create(
            task_id, reuse_if_exists, str(worktree_path) if worktree_path else None
        )
        return result

    async def attach_session(self, task_id: str):
        result = await self._sdk.sessions_attach(task_id)
        return result.success

    async def session_exists(self, task_id: str):
        result = await self._sdk.sessions_exists(task_id)
        return result.exists

    async def kill_session(self, task_id: str):
        await self._sdk.sessions_kill(task_id)

    async def get_workspace_path(self, task_id: str):
        path = await self._sdk.get_workspace_path(task_id)
        return Path(path) if path else None

    async def get_task_workspace_path(self, task_id: str):
        return await self.get_workspace_path(task_id)

    async def provision_workspace(self, *, task_id: str, repos: list[Any]):
        return await self._sdk.get_workspace_path(task_id)

    async def list_workspaces(self, *, task_id: str | None = None):
        result = await self._sdk.workspaces_list(task_id)
        return [_normalize_workspace_view(workspace) for workspace in result.workspaces]

    async def get_workspace_repos(self, workspace_id: str):
        return []

    async def get_repo_diff(self, workspace_id: str, repo_id: str):
        result = await self._sdk.get_repo_diff(workspace_id, repo_id)
        return result

    async def cleanup_orphan_workspaces(self, valid_task_ids: set[str]):
        result = await self._sdk.cleanup_orphan_workspaces(list(valid_task_ids))
        return result

    async def cleanup_workspace_artifacts(
        self,
        valid_workspace_ids: set[str],
        *,
        prune_worktrees: bool = True,
        gc_branches: bool = True,
    ):
        del valid_workspace_ids, prune_worktrees, gc_branches
        return None

    async def get_workspace_diff(self, task_id: str, *, base_branch: str):
        result = await self._sdk.get_workspace_diff(task_id, base_branch)
        return result.diff

    async def get_workspace_commit_log(self, task_id: str, *, base_branch: str):
        result = await self._sdk.get_workspace_commit_log(task_id, base_branch)
        return result.commits

    async def get_workspace_diff_stats(self, task_id: str, *, base_branch: str):
        result = await self._sdk.get_workspace_diff_stats(task_id, base_branch)
        return result.stats

    async def rebase_workspace(self, task_id: str, base_branch: str):
        result = await self._sdk.rebase_workspace(task_id, base_branch)
        return result.success, result.message, result.conflict_files

    async def abort_workspace_rebase(self, task_id: str):
        await self._sdk.abort_workspace_rebase(task_id)

    async def merge_repo(
        self,
        workspace_id: str,
        repo_id: str,
        *,
        strategy,
        pr_title: str | None = None,
        pr_body: str | None = None,
        commit_message: str | None = None,
    ):
        result = await self._sdk.merge_repo(
            workspace_id,
            repo_id,
            strategy.value if hasattr(strategy, "value") else str(strategy),
            pr_title,
            pr_body,
            commit_message,
        )
        return result

    async def has_no_changes(self, task):
        task_id = task.id if hasattr(task, "id") else task
        result = await self._sdk.has_no_changes(task_id)
        return result.value

    async def close_exploratory(self, task):
        task_id = task.id if hasattr(task, "id") else task
        result = await self._sdk.close_exploratory(task_id)
        return result.value, result.message

    async def merge_task_direct(self, task):
        task_id = task.id if hasattr(task, "id") else task
        result = await self._sdk.merge_task_direct(task_id)
        return result.value, result.message

    async def apply_rejection_feedback(
        self,
        task,
        feedback: str | None,
        action: str,
    ):
        task_id = task.id if hasattr(task, "id") else task
        result = await self._sdk.apply_rejection_feedback(task_id, feedback, action)
        if result.task:
            return result.task
        return None

    async def get_all_diffs(self, workspace_id: str):
        result = await self._sdk.get_all_diffs(workspace_id)
        return result.diffs

    async def queue_message(
        self,
        session_id: str,
        content: str,
        *,
        lane: str = "implementation",
        author: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        return await self._sdk.queue_message(session_id, content, lane, author, metadata)

    async def get_queue_status(self, session_id: str, *, lane: str = "implementation"):
        result = await self._sdk.get_queue_status(session_id, lane)

        class Status:
            has_queued = result.has_queued

        return Status()

    async def get_queued_messages(
        self,
        session_id: str,
        *,
        lane: str = "implementation",
    ):
        result = await self._sdk.get_queued_messages(session_id, lane)
        return result.messages

    async def take_queued_message(self, session_id: str, *, lane: str = "implementation"):
        return await self._sdk.take_queued_message(session_id, lane)

    async def remove_queued_message(
        self,
        session_id: str,
        index: int,
        *,
        lane: str = "implementation",
    ):
        result = await self._sdk.remove_queued_message(session_id, index, lane)
        return result.value

    async def save_planner_draft(
        self,
        *,
        project_id: str,
        repo_id: str | None = None,
        tasks_json: list[dict[str, Any]],
        todos_json: list[dict[str, Any]] | None = None,
    ):
        return await self._sdk.save_planner_draft(project_id, tasks_json, repo_id, todos_json)

    async def list_pending_planner_drafts(
        self,
        project_id: str,
        *,
        repo_id: str | None = None,
    ):
        result = await self._sdk.list_pending_planner_drafts(project_id, repo_id)
        return result.drafts

    async def update_planner_draft_status(self, proposal_id: str, status):
        status_value = status.value if hasattr(status, "value") else str(status)
        return await self._sdk.update_planner_draft_status(proposal_id, status_value)

    async def get_execution(self, execution_id: str):
        result = await self._sdk.get_execution(execution_id)
        return result.execution

    async def get_execution_log_entries(self, execution_id: str):
        result = await self._sdk.get_execution_log_entries(execution_id)
        return result.entries

    async def get_latest_execution_for_task(self, task_id: str):
        result = await self._sdk.get_latest_execution_for_task(task_id)
        return result.execution

    async def count_executions_for_task(self, task_id: str):
        result = await self._sdk.count_executions_for_task(task_id)
        return result.count

    async def decide_startup(self, cwd: Path):
        result = await self._sdk.decide_startup(str(cwd))

        class Decision:
            should_open_project = result.should_open_project
            project_id = result.project_id
            preferred_repo_id = result.preferred_repo_id
            preferred_path = Path(result.preferred_path) if result.preferred_path else None
            suggest_cwd = result.suggest_cwd
            cwd_path = result.cwd_path
            cwd_is_git_repo = result.cwd_is_git_repo

        return Decision()

    async def dispatch_runtime_session(
        self,
        event,
        *,
        project_id: str | None = None,
        repo_id: str | None = None,
    ):
        event_value = event.value if hasattr(event, "value") else str(event)
        return await self._sdk.dispatch_runtime_session(event_value, project_id, repo_id)

    @property
    def runtime_state(self):
        return self._sdk.get_runtime_state()

    def get_runtime_view(self, task_id: str):
        return None

    def get_running_task_ids(self):
        return set()

    def is_automation_running(self, task_id: str):
        return False

    async def reconcile_running_tasks(self, task_ids: list[str]):
        return await self._sdk.reconcile_running_tasks(task_ids)

    async def resolve_task_base_branch(self, task):
        task_id = task.id if hasattr(task, "id") else task
        result = await self._sdk.resolve_task_base_branch(task_id)
        return result.branch

    async def prepare_auto_output(self, task):
        task_id = task.id if hasattr(task, "id") else task
        return await self._sdk.prepare_auto_output(task_id)

    async def recover_stale_auto_output(self, task):
        task_id = task.id if hasattr(task, "id") else task
        return await self._sdk.recover_stale_auto_output(task_id)


@dataclass
class CoreBackedContext:
    """Minimal app context used by TUI screens when attached to core."""

    config: KaganConfig
    config_path: Path
    db_path: Path
    api: CoreBackedApi
    sdk: KaganSDK
    active_project_id: str | None = None
    active_repo_id: str | None = None

    async def close(self) -> None:
        if self.sdk:
            await self.sdk.close()
        return None
