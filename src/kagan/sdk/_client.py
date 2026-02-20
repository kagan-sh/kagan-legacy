"""Kagan SDK client with typed async methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from kagan.sdk._transport import SDKTransport
from kagan.sdk._types import (
    AddRepoResponse,
    AllDiffsResponse,
    AuditListResponse,
    AutoOutputResponse,
    BoolResponse,
    DiagnosticsResponse,
    ExecutionCountResponse,
    ExecutionLogResponse,
    ExecutionResponse,
    JobListResponse,
    JobResponse,
    PlannerDraftListResponse,
    PlannerDraftResponse,
    PluginInvokeResponse,
    PluginUiCatalogResponse,
    PluginUiInvokeResponse,
    Project,
    ProjectCreateResponse,
    ProjectListResponse,
    ProjectResponse,
    QueueListResponse,
    QueueMessageResponse,
    QueueStatusResponse,
    RepoDiffResponse,
    RepoListResponse,
    RepoUpdateResponse,
    ReviewResponse,
    RuntimeReconcileResponse,
    RuntimeStateResponse,
    RuntimeViewResponse,
    ScratchpadResponse,
    SessionExistsResponse,
    SessionResponse,
    SettingsResponse,
    StartupDecisionResponse,
    TaskBaseBranchResponse,
    TaskContextResponse,
    TaskCreateResponse,
    TaskDeleteResponse,
    TaskIdsResponse,
    TaskListResponse,
    TaskLogsResponse,
    TaskResponse,
    TaskUpdateResponse,
    TaskWaitResponse,
    WorkspaceCommitLogResponse,
    WorkspaceDiffResponse,
    WorkspaceDiffStatsResponse,
    WorkspaceListResponse,
    WorkspaceMergeResponse,
    WorkspaceRebaseResponse,
)
from kagan.version import get_kagan_version


def _build[T: BaseModel](cls: type[T], data: dict[str, Any], **overrides: Any) -> T:
    """Construct a frozen Pydantic response model from a wire dict.

    Merges *overrides* on top of *data* and delegates to ``model_validate``
    which handles defaults, type coercion, and extra-field ignoring via the
    model's ``ConfigDict``.
    """
    if overrides:
        data = {**data, **overrides}
    return cls.model_validate(data)


@dataclass(frozen=True, slots=True)
class _ModelCallSpec[T: BaseModel]:
    capability: str
    method: str
    response_model: type[T]
    mutating: bool = False


if TYPE_CHECKING:
    from kagan.core.constants import CapabilityProfile
    from kagan.core.ipc.discovery import CoreEndpoint


_JOBS_GET_CALL = _ModelCallSpec("jobs", "get", JobResponse)
_JOBS_CANCEL_CALL = _ModelCallSpec("jobs", "cancel", JobResponse, mutating=True)
_JOBS_WAIT_CALL = _ModelCallSpec("jobs", "wait", JobResponse, mutating=True)
_JOBS_EVENTS_CALL = _ModelCallSpec("jobs", "events", JobListResponse)
_AUTOMATION_RECONCILE_CALL = _ModelCallSpec(
    "automation",
    "reconcile_running_tasks",
    RuntimeReconcileResponse,
    mutating=True,
)
_AUTOMATION_RUNNING_TASK_IDS_CALL = _ModelCallSpec(
    "automation",
    "get_running_task_ids",
    TaskIdsResponse,
)


class KaganSDK:
    """Typed async Python API for Kagan.

    Provides a clean interface over IPC for all Kagan operations.
    All methods return typed response objects.

    Usage::

        async with KaganSDK() as sdk:
            tasks = await sdk.tasks.list()
            for task in tasks.tasks:
                print(task.title)
    """

    def __init__(
        self,
        transport: SDKTransport | None = None,
        *,
        session_id: str = "sdk-session",
        session_origin: str = "sdk",
        client_version: str | None = None,
        client_build_hash: str | None = None,
        capability_profile: CapabilityProfile | str = "operator",
        endpoint: CoreEndpoint | None = None,
    ) -> None:
        resolved_client_version = (
            get_kagan_version() if client_version is None else client_version
        )
        self._transport = transport or SDKTransport(
            endpoint=endpoint,
            session_id=session_id,
            session_origin=session_origin,
            client_version=resolved_client_version,
            client_build_hash=client_build_hash,
            capability_profile=capability_profile,
        )

    async def __aenter__(self) -> KaganSDK:
        await self._transport.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._transport.close()

    @property
    def is_connected(self) -> bool:
        return self._transport.is_connected

    async def connect(self) -> None:
        await self._transport.connect()

    async def close(self) -> None:
        await self._transport.close()

    async def _request(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._transport.request(capability, method, params)

    async def _query(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return await self._transport.query(capability, method, params)

    async def _call_model[T: BaseModel](
        self,
        spec: _ModelCallSpec[T],
        params: dict[str, Any] | None = None,
    ) -> T:
        raw = (
            await self._request(spec.capability, spec.method, params)
            if spec.mutating
            else await self._query(spec.capability, spec.method, params)
        )
        return _build(spec.response_model, raw)

    async def tasks_get(self, task_id: str) -> TaskResponse:
        return _build(TaskResponse, await self._query("tasks", "get", {"task_id": task_id}))

    async def tasks_list(
        self,
        project_id: str | None = None,
        status: str | None = None,
        include_scratchpad: bool = False,
        exclude_task_ids: list[str] | None = None,
    ) -> TaskListResponse:
        params: dict[str, Any] = {}
        if project_id is not None:
            params["project_id"] = project_id
        if status is not None:
            params["filter"] = status
        if include_scratchpad:
            params["include_scratchpad"] = True
        if exclude_task_ids:
            params["exclude_task_ids"] = exclude_task_ids
        return _build(TaskListResponse, await self._query("tasks", "list", params))

    async def tasks_search(self, query: str) -> TaskListResponse:
        return _build(TaskListResponse, await self._query("tasks", "search", {"query": query}))

    async def tasks_create(
        self,
        title: str,
        description: str = "",
        project_id: str | None = None,
        created_by: str | None = None,
        **fields: Any,
    ) -> TaskCreateResponse:
        params: dict[str, Any] = {"title": title, "description": description}
        if project_id is not None:
            params["project_id"] = project_id
        if created_by is not None:
            params["created_by"] = created_by
        params.update(fields)
        return _build(TaskCreateResponse, await self._request("tasks", "create", params))

    async def tasks_update(self, task_id: str, **fields: Any) -> TaskUpdateResponse:
        params: dict[str, Any] = {"task_id": task_id}
        params.update(fields)
        return _build(TaskUpdateResponse, await self._request("tasks", "update", params))

    async def tasks_move(self, task_id: str, status: str) -> TaskUpdateResponse:
        return _build(
            TaskUpdateResponse,
            await self._request("tasks", "move", {"task_id": task_id, "status": status}),
        )

    async def tasks_delete(self, task_id: str) -> TaskDeleteResponse:
        return _build(
            TaskDeleteResponse,
            await self._request("tasks", "delete", {"task_id": task_id}),
        )

    async def tasks_scratchpad(
        self,
        task_id: str,
        content_char_limit: int = 16_000,
    ) -> ScratchpadResponse:
        return _build(
            ScratchpadResponse,
            await self._query(
                "tasks",
                "scratchpad",
                {"task_id": task_id, "content_char_limit": content_char_limit},
            ),
        )

    async def tasks_update_scratchpad(self, task_id: str, content: str) -> TaskUpdateResponse:
        result = await self._request(
            "tasks",
            "update_scratchpad",
            {"task_id": task_id, "content": content},
        )
        return _build(TaskUpdateResponse, result, code=result.get("code", "SCRATCHPAD_UPDATED"))

    async def tasks_context(self, task_id: str) -> TaskContextResponse:
        return _build(
            TaskContextResponse,
            await self._query("tasks", "context", {"task_id": task_id}),
        )

    async def tasks_logs(
        self,
        task_id: str,
        limit: int = 5,
        offset: int = 0,
        content_char_limit: int = 6_000,
    ) -> TaskLogsResponse:
        return _build(
            TaskLogsResponse,
            await self._query(
                "tasks",
                "logs",
                {
                    "task_id": task_id,
                    "limit": limit,
                    "offset": offset,
                    "content_char_limit": content_char_limit,
                },
            ),
        )

    async def tasks_wait(
        self,
        task_id: str,
        timeout_seconds: float = 30.0,
        wait_for_status: list[str] | None = None,
        from_updated_at: str | None = None,
    ) -> TaskWaitResponse:
        params: dict[str, Any] = {"task_id": task_id, "timeout_seconds": timeout_seconds}
        if wait_for_status is not None:
            params["wait_for_status"] = wait_for_status
        if from_updated_at is not None:
            params["from_updated_at"] = from_updated_at
        return _build(TaskWaitResponse, await self._request("tasks", "wait", params))

    async def review_request(self, task_id: str, summary: str = "") -> ReviewResponse:
        return _build(
            ReviewResponse,
            await self._request("review", "request", {"task_id": task_id, "summary": summary}),
        )

    async def review_approve(self, task_id: str) -> ReviewResponse:
        return _build(
            ReviewResponse,
            await self._request("review", "approve", {"task_id": task_id}),
        )

    async def review_reject(
        self,
        task_id: str,
        feedback: str = "",
        action: str = "reopen",
    ) -> ReviewResponse:
        return _build(
            ReviewResponse,
            await self._request(
                "review",
                "reject",
                {"task_id": task_id, "feedback": feedback, "action": action},
            ),
        )

    async def review_merge(self, task_id: str) -> ReviewResponse:
        return _build(ReviewResponse, await self._request("review", "merge", {"task_id": task_id}))

    async def review_rebase(self, task_id: str, base_branch: str | None = None) -> ReviewResponse:
        params: dict[str, Any] = {"task_id": task_id}
        if base_branch is not None:
            params["base_branch"] = base_branch
        return _build(ReviewResponse, await self._request("review", "rebase", params))

    async def projects_get(self, project_id: str) -> ProjectResponse:
        return _build(
            ProjectResponse,
            await self._query("projects", "get", {"project_id": project_id}),
        )

    async def projects_list(self, limit: int = 10) -> ProjectListResponse:
        return _build(
            ProjectListResponse,
            await self._query("projects", "list", {"limit": limit}),
        )

    async def projects_create(
        self,
        name: str,
        description: str = "",
        repo_paths: list[str] | None = None,
    ) -> ProjectCreateResponse:
        params: dict[str, Any] = {"name": name, "description": description}
        if repo_paths:
            params["repo_paths"] = repo_paths
        return _build(ProjectCreateResponse, await self._request("projects", "create", params))

    async def projects_open(self, project_id: str) -> ProjectResponse:
        result = await self._request("projects", "open", {"project_id": project_id})
        project_dict = {
            "project_id": result.get("project_id", project_id),
            "name": result.get("name", ""),
            "description": result.get("description", ""),
        }
        project = Project.model_validate(project_dict)
        return ProjectResponse(found=result.get("success", False), project=project)

    async def projects_repos(self, project_id: str) -> RepoListResponse:
        return _build(
            RepoListResponse,
            await self._query("projects", "repos", {"project_id": project_id}),
        )

    async def projects_add_repo(
        self,
        project_id: str,
        repo_path: str,
        is_primary: bool = False,
    ) -> AddRepoResponse:
        result = await self._request(
            "projects",
            "add_repo",
            {"project_id": project_id, "repo_path": repo_path, "is_primary": is_primary},
        )
        return AddRepoResponse(
            success=result.get("success", False),
            project_id=result.get("project_id", project_id),
            repo_id=result.get("repo_id", ""),
            repo_path=result.get("repo_path", repo_path),
        )

    async def projects_find_by_repo_path(self, repo_path: str) -> ProjectResponse:
        return _build(
            ProjectResponse,
            await self._query("projects", "find_by_repo_path", {"repo_path": repo_path}),
        )

    async def settings_get(self) -> SettingsResponse:
        return _build(
            SettingsResponse,
            await self._query("settings", "get", {}),
            success=True,
        )

    async def settings_update(self, fields: dict[str, Any]) -> SettingsResponse:
        return _build(
            SettingsResponse,
            await self._request("settings", "update", {"fields": fields}),
        )

    async def jobs_submit(
        self,
        task_id: str,
        action: str,
        arguments: dict[str, Any] | None = None,
    ) -> JobResponse:
        params: dict[str, Any] = {"task_id": task_id, "action": action}
        if arguments:
            params["arguments"] = arguments
        return _build(JobResponse, await self._request("jobs", "submit", params))

    async def jobs_get(self, job_id: str, task_id: str) -> JobResponse:
        return await self._call_model(_JOBS_GET_CALL, {"job_id": job_id, "task_id": task_id})

    async def jobs_cancel(self, job_id: str, task_id: str) -> JobResponse:
        return await self._call_model(_JOBS_CANCEL_CALL, {"job_id": job_id, "task_id": task_id})

    async def jobs_wait(
        self,
        job_id: str,
        task_id: str,
        timeout_seconds: float = 30.0,
    ) -> JobResponse:
        return await self._call_model(
            _JOBS_WAIT_CALL,
            {"job_id": job_id, "task_id": task_id, "timeout_seconds": timeout_seconds},
        )

    async def jobs_events(
        self,
        job_id: str,
        task_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> JobListResponse:
        return await self._call_model(
            _JOBS_EVENTS_CALL,
            {"job_id": job_id, "task_id": task_id, "limit": limit, "offset": offset},
        )

    async def sessions_create(
        self,
        task_id: str,
        reuse_if_exists: bool = True,
        worktree_path: str | None = None,
    ) -> SessionResponse:
        params: dict[str, Any] = {"task_id": task_id, "reuse_if_exists": reuse_if_exists}
        if worktree_path is not None:
            params["worktree_path"] = worktree_path
        result = await self._request("sessions", "create", params)
        return _build(SessionResponse, result, task_id=result.get("task_id", task_id))

    async def sessions_attach(self, task_id: str) -> SessionResponse:
        return _build(
            SessionResponse,
            await self._query("sessions", "attach", {"task_id": task_id}),
            task_id=task_id,
        )

    async def sessions_exists(self, task_id: str) -> SessionExistsResponse:
        return _build(
            SessionExistsResponse,
            await self._query("sessions", "exists", {"task_id": task_id}),
        )

    async def sessions_kill(self, task_id: str) -> SessionResponse:
        return _build(
            SessionResponse,
            await self._request("sessions", "kill", {"task_id": task_id}),
            task_id=task_id,
        )

    async def workspaces_list(self, task_id: str | None = None) -> WorkspaceListResponse:
        params: dict[str, Any] = {}
        if task_id is not None:
            params["task_id"] = task_id
        return _build(WorkspaceListResponse, await self._query("workspaces", "list", params))

    async def workspaces_provision(
        self,
        task_id: str,
        repos: list[dict[str, str]],
    ) -> str:
        result = await self._request(
            "workspaces",
            "provision_workspace",
            {"task_id": task_id, "repos": repos},
        )
        workspace_id = result.get("workspace_id")
        return str(workspace_id) if workspace_id is not None else ""

    async def audit_list(
        self,
        capability: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> AuditListResponse:
        params: dict[str, Any] = {"limit": limit}
        if capability is not None:
            params["capability"] = capability
        if cursor is not None:
            params["cursor"] = cursor
        return _build(AuditListResponse, await self._query("audit", "list", params))

    async def diagnostics_instrumentation(self) -> DiagnosticsResponse:
        return _build(
            DiagnosticsResponse,
            await self._query("diagnostics", "instrumentation", {}),
        )

    async def plugins_invoke(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> PluginInvokeResponse:
        return _build(
            PluginInvokeResponse,
            await self._request(
                "plugins",
                "invoke",
                {"capability": capability, "method": method, "params": params or {}},
            ),
        )

    async def queue_message(
        self,
        session_id: str,
        content: str,
        lane: str = "implementation",
        author: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QueueMessageResponse:
        params: dict[str, Any] = {"session_id": session_id, "content": content, "lane": lane}
        if author is not None:
            params["author"] = author
        if metadata is not None:
            params["metadata"] = metadata
        return _build(
            QueueMessageResponse,
            await self._request("automation", "queue_message", params),
        )

    async def get_queue_status(
        self,
        session_id: str,
        lane: str = "implementation",
    ) -> QueueStatusResponse:
        result = await self._query(
            "automation",
            "get_queue_status",
            {"session_id": session_id, "lane": lane},
        )
        return _build(QueueStatusResponse, result, lane=lane)

    async def get_queued_messages(
        self,
        session_id: str,
        lane: str = "implementation",
    ) -> QueueListResponse:
        result = await self._query(
            "automation",
            "get_queued_messages",
            {"session_id": session_id, "lane": lane},
        )
        messages = result.get("messages", []) if isinstance(result.get("messages"), list) else []
        return QueueListResponse(messages=messages, count=len(messages))

    async def take_queued_message(
        self,
        session_id: str,
        lane: str = "implementation",
    ) -> QueueMessageResponse:
        return _build(
            QueueMessageResponse,
            await self._request(
                "automation",
                "take_queued_message",
                {"session_id": session_id, "lane": lane},
            ),
        )

    async def remove_queued_message(
        self,
        session_id: str,
        index: int,
        lane: str = "implementation",
    ) -> BoolResponse:
        result = await self._request(
            "automation",
            "remove_queued_message",
            {"session_id": session_id, "index": index, "lane": lane},
        )
        return BoolResponse(value=result.get("success", False), message=result.get("message", ""))

    async def save_planner_draft(
        self,
        project_id: str,
        tasks_json: list[dict[str, Any]],
        repo_id: str | None = None,
        todos_json: list[dict[str, Any]] | None = None,
    ) -> PlannerDraftResponse:
        params: dict[str, Any] = {"project_id": project_id, "tasks_json": tasks_json}
        if repo_id is not None:
            params["repo_id"] = repo_id
        if todos_json is not None:
            params["todos_json"] = todos_json
        return _build(
            PlannerDraftResponse,
            await self._request("automation", "save_planner_draft", params),
        )

    async def list_pending_planner_drafts(
        self,
        project_id: str,
        repo_id: str | None = None,
    ) -> PlannerDraftListResponse:
        params: dict[str, Any] = {"project_id": project_id}
        if repo_id is not None:
            params["repo_id"] = repo_id
        result = await self._query("automation", "list_pending_planner_drafts", params)
        drafts = result.get("drafts", []) if isinstance(result.get("drafts"), list) else []
        return PlannerDraftListResponse(drafts=drafts, count=len(drafts))

    async def update_planner_draft_status(
        self,
        proposal_id: str,
        status: str,
    ) -> PlannerDraftResponse:
        return _build(
            PlannerDraftResponse,
            await self._request(
                "automation",
                "update_planner_draft_status",
                {"proposal_id": proposal_id, "status": status},
            ),
        )

    async def get_execution(self, execution_id: str) -> ExecutionResponse:
        return _build(
            ExecutionResponse,
            await self._query("automation", "get_execution", {"execution_id": execution_id}),
        )

    async def get_execution_log_entries(self, execution_id: str) -> ExecutionLogResponse:
        result = await self._query(
            "automation",
            "get_execution_log_entries",
            {"execution_id": execution_id},
        )
        entries = result.get("entries", []) if isinstance(result.get("entries"), list) else []
        return ExecutionLogResponse(entries=entries, count=len(entries))

    async def get_latest_execution_for_task(self, task_id: str) -> ExecutionResponse:
        return _build(
            ExecutionResponse,
            await self._query("automation", "get_latest_execution_for_task", {"task_id": task_id}),
        )

    async def count_executions_for_task(self, task_id: str) -> ExecutionCountResponse:
        return _build(
            ExecutionCountResponse,
            await self._query("automation", "count_executions_for_task", {"task_id": task_id}),
        )

    async def decide_startup(self, cwd: str) -> StartupDecisionResponse:
        return _build(
            StartupDecisionResponse,
            await self._query("automation", "decide_startup", {"cwd": cwd}),
        )

    async def dispatch_runtime_session(
        self,
        event: str,
        project_id: str | None = None,
        repo_id: str | None = None,
    ) -> RuntimeStateResponse:
        params: dict[str, Any] = {"event": event}
        if project_id is not None:
            params["project_id"] = project_id
        if repo_id is not None:
            params["repo_id"] = repo_id
        return _build(
            RuntimeStateResponse,
            await self._request("automation", "dispatch_runtime_session", params),
        )

    def get_runtime_state(self) -> RuntimeStateResponse:
        return RuntimeStateResponse(project_id=None, repo_id=None)

    async def get_runtime_view(self, task_id: str) -> RuntimeViewResponse:
        return _build(
            RuntimeViewResponse,
            await self._query("automation", "get_runtime_view", {"task_id": task_id}),
        )

    async def is_automation_running(self, task_id: str) -> BoolResponse:
        result = await self._query("automation", "is_automation_running", {"task_id": task_id})
        return BoolResponse(value=result.get("is_running", False))

    async def reconcile_running_tasks(self, task_ids: list[str]) -> RuntimeReconcileResponse:
        return await self._call_model(_AUTOMATION_RECONCILE_CALL, {"task_ids": task_ids})

    async def get_running_task_ids(self) -> TaskIdsResponse:
        return await self._call_model(_AUTOMATION_RUNNING_TASK_IDS_CALL, {})

    async def get_workspace_diff(self, task_id: str, base_branch: str) -> WorkspaceDiffResponse:
        return _build(
            WorkspaceDiffResponse,
            await self._query(
                "workspaces",
                "get_workspace_diff",
                {"task_id": task_id, "base_branch": base_branch},
            ),
        )

    async def get_workspace_commit_log(
        self,
        task_id: str,
        base_branch: str,
    ) -> WorkspaceCommitLogResponse:
        return _build(
            WorkspaceCommitLogResponse,
            await self._query(
                "workspaces",
                "get_workspace_commit_log",
                {"task_id": task_id, "base_branch": base_branch},
            ),
        )

    async def get_workspace_diff_stats(
        self,
        task_id: str,
        base_branch: str,
    ) -> WorkspaceDiffStatsResponse:
        return _build(
            WorkspaceDiffStatsResponse,
            await self._query(
                "workspaces",
                "get_workspace_diff_stats",
                {"task_id": task_id, "base_branch": base_branch},
            ),
        )

    async def rebase_workspace(self, task_id: str, base_branch: str) -> WorkspaceRebaseResponse:
        return _build(
            WorkspaceRebaseResponse,
            await self._request(
                "workspaces",
                "rebase_workspace",
                {"task_id": task_id, "base_branch": base_branch},
            ),
        )

    async def abort_workspace_rebase(self, task_id: str) -> BoolResponse:
        result = await self._request("workspaces", "abort_workspace_rebase", {"task_id": task_id})
        return BoolResponse(value=result.get("success", False))

    async def get_all_diffs(self, workspace_id: str) -> AllDiffsResponse:
        return _build(
            AllDiffsResponse,
            await self._query("workspaces", "get_all_diffs", {"workspace_id": workspace_id}),
        )

    async def merge_repo(
        self,
        workspace_id: str,
        repo_id: str,
        strategy: str = "direct",
        pr_title: str | None = None,
        pr_body: str | None = None,
        commit_message: str | None = None,
    ) -> WorkspaceMergeResponse:
        params: dict[str, Any] = {
            "workspace_id": workspace_id,
            "repo_id": repo_id,
            "strategy": strategy,
        }
        if pr_title is not None:
            params["pr_title"] = pr_title
        if pr_body is not None:
            params["pr_body"] = pr_body
        if commit_message is not None:
            params["commit_message"] = commit_message
        return _build(
            WorkspaceMergeResponse,
            await self._request("workspaces", "merge_repo", params),
        )

    async def get_repo_diff(self, workspace_id: str, repo_id: str) -> RepoDiffResponse:
        return _build(
            RepoDiffResponse,
            await self._query(
                "workspaces",
                "get_repo_diff",
                {"workspace_id": workspace_id, "repo_id": repo_id},
            ),
        )

    async def get_workspace_path(self, task_id: str) -> str:
        result = await self._query("workspaces", "get_workspace_path", {"task_id": task_id})
        return result.get("path", "")

    async def cleanup_orphan_workspaces(self, valid_task_ids: list[str]) -> list[str]:
        result = await self._request(
            "workspaces",
            "cleanup_orphan_workspaces",
            {"valid_task_ids": valid_task_ids},
        )
        cleaned = result.get("cleaned", []) if isinstance(result.get("cleaned"), list) else []
        return cleaned

    async def has_no_changes(self, task_id: str) -> BoolResponse:
        result = await self._query("tasks", "has_no_changes", {"task_id": task_id})
        return BoolResponse(value=result.get("has_no_changes", False))

    async def close_exploratory(self, task_id: str) -> BoolResponse:
        result = await self._request("tasks", "close_exploratory", {"task_id": task_id})
        return BoolResponse(value=result.get("success", False), message=result.get("message", ""))

    async def merge_task_direct(self, task_id: str) -> BoolResponse:
        result = await self._request("tasks", "merge_task_direct", {"task_id": task_id})
        return BoolResponse(value=result.get("success", False), message=result.get("message", ""))

    async def apply_rejection_feedback(
        self,
        task_id: str,
        feedback: str | None = None,
        action: str = "reopen",
    ) -> TaskResponse:
        params: dict[str, Any] = {"task_id": task_id, "action": action}
        if feedback is not None:
            params["feedback"] = feedback
        result = await self._request("tasks", "apply_rejection_feedback", params)
        return _build(TaskResponse, result)

    async def resolve_task_base_branch(self, task_id: str) -> TaskBaseBranchResponse:
        result = await self._query("tasks", "resolve_task_base_branch", {"task_id": task_id})
        return TaskBaseBranchResponse(branch=result.get("branch", "main"))

    async def prepare_auto_output(self, task_id: str) -> AutoOutputResponse:
        return _build(
            AutoOutputResponse,
            await self._query("tasks", "prepare_auto_output", {"task_id": task_id}),
        )

    async def recover_stale_auto_output(self, task_id: str) -> AutoOutputResponse:
        return _build(
            AutoOutputResponse,
            await self._query("tasks", "recover_stale_auto_output", {"task_id": task_id}),
        )

    async def update_repo_default_branch(
        self,
        repo_id: str,
        branch: str,
        mark_configured: bool = False,
    ) -> RepoUpdateResponse:
        return _build(
            RepoUpdateResponse,
            await self._request(
                "projects",
                "update_repo_default_branch",
                {"repo_id": repo_id, "branch": branch, "mark_configured": mark_configured},
            ),
        )

    async def plugin_ui_catalog(
        self,
        project_id: str,
        repo_id: str | None = None,
    ) -> PluginUiCatalogResponse:
        params: dict[str, Any] = {"project_id": project_id}
        if repo_id is not None:
            params["repo_id"] = repo_id
        return _build(
            PluginUiCatalogResponse,
            await self._query("plugins", "plugin_ui_catalog", params),
        )

    async def plugin_ui_invoke(
        self,
        project_id: str,
        plugin_id: str,
        action_id: str,
        repo_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> PluginUiInvokeResponse:
        params: dict[str, Any] = {
            "project_id": project_id,
            "plugin_id": plugin_id,
            "action_id": action_id,
        }
        if repo_id is not None:
            params["repo_id"] = repo_id
        if inputs is not None:
            params["inputs"] = inputs
        return _build(
            PluginUiInvokeResponse,
            await self._request("plugins", "plugin_ui_invoke", params),
        )


__all__ = ["KaganSDK"]
