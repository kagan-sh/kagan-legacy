"""Kagan SDK client with typed async methods."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from kagan.core.domain.enums import QueueLane
from kagan.core.protocol_constants import (
    DEFAULT_EVENTS_LIMIT,
    DEFAULT_JOB_WAIT_TIMEOUT_SECONDS,
    DEFAULT_TASK_LOG_ENTRY_CHAR_LIMIT,
    DEFAULT_TASK_LOG_LIMIT,
    DEFAULT_TASK_SCRATCHPAD_CHAR_LIMIT,
)
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
    TaskWaitAnyResponse,
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


def _query_call[T: BaseModel](
    capability: str,
    method: str,
    response_model: type[T],
) -> _ModelCallSpec[T]:
    return _ModelCallSpec(capability, method, response_model)


def _request_call[T: BaseModel](
    capability: str, method: str, response_model: type[T]
) -> _ModelCallSpec[T]:
    return _ModelCallSpec(capability, method, response_model, mutating=True)


if TYPE_CHECKING:
    from kagan.core.constants import CapabilityProfile
    from kagan.core.ipc.discovery import CoreEndpoint
    from kagan.core.runtime_context import CoreRuntimeContext


_TASKS_GET_CALL = _query_call("tasks", "get", TaskResponse)
_TASKS_SEARCH_CALL = _query_call("tasks", "search", TaskListResponse)
_TASKS_CREATE_CALL = _request_call("tasks", "create", TaskCreateResponse)
_TASKS_UPDATE_CALL = _request_call("tasks", "update", TaskUpdateResponse)
_TASKS_MOVE_CALL = _request_call("tasks", "move", TaskUpdateResponse)
_TASKS_DELETE_CALL = _request_call("tasks", "delete", TaskDeleteResponse)
_TASKS_SCRATCHPAD_CALL = _query_call("tasks", "scratchpad", ScratchpadResponse)
_TASKS_CONTEXT_CALL = _query_call("tasks", "context", TaskContextResponse)
_TASKS_LOGS_CALL = _query_call("tasks", "logs", TaskLogsResponse)
_TASKS_WAIT_CALL = _request_call("tasks", "wait", TaskWaitResponse)
_TASKS_WAIT_ANY_CALL = _request_call("tasks", "wait_any", TaskWaitAnyResponse)
_REVIEW_REQUEST_CALL = _request_call("review", "request", ReviewResponse)
_REVIEW_APPROVE_CALL = _request_call("review", "approve", ReviewResponse)
_REVIEW_REJECT_CALL = _request_call("review", "reject", ReviewResponse)
_REVIEW_MERGE_CALL = _request_call("review", "merge", ReviewResponse)
_REVIEW_REBASE_CALL = _request_call("review", "rebase", ReviewResponse)
_PROJECTS_GET_CALL = _query_call("projects", "get", ProjectResponse)
_PROJECTS_LIST_CALL = _query_call("projects", "list", ProjectListResponse)
_PROJECTS_CREATE_CALL = _request_call("projects", "create", ProjectCreateResponse)
_PROJECTS_REPOS_CALL = _query_call("projects", "repos", RepoListResponse)
_PROJECTS_FIND_BY_REPO_PATH_CALL = _query_call("projects", "find_by_repo_path", ProjectResponse)
_SETTINGS_GET_CALL = _query_call("settings", "get", SettingsResponse)
_SETTINGS_UPDATE_CALL = _request_call("settings", "update", SettingsResponse)
_JOBS_SUBMIT_CALL = _request_call("jobs", "submit", JobResponse)
_JOBS_GET_CALL = _query_call("jobs", "get", JobResponse)
_JOBS_CANCEL_CALL = _request_call("jobs", "cancel", JobResponse)
_JOBS_WAIT_CALL = _request_call("jobs", "wait", JobResponse)
_JOBS_EVENTS_CALL = _query_call("jobs", "events", JobListResponse)
_SESSIONS_ATTACH_CALL = _query_call("sessions", "attach", SessionResponse)
_SESSIONS_EXISTS_CALL = _query_call("sessions", "exists", SessionExistsResponse)
_SESSIONS_KILL_CALL = _request_call("sessions", "kill", SessionResponse)
_WORKSPACES_LIST_CALL = _query_call("workspaces", "list", WorkspaceListResponse)
_AUDIT_LIST_CALL = _query_call("audit", "list", AuditListResponse)
_DIAGNOSTICS_INSTRUMENTATION_CALL = _query_call(
    "diagnostics", "instrumentation", DiagnosticsResponse
)
_PLUGINS_INVOKE_CALL = _request_call("plugins", "invoke", PluginInvokeResponse)
_AUTOMATION_QUEUE_MESSAGE_CALL = _request_call("automation", "queue_message", QueueMessageResponse)
_AUTOMATION_TAKE_QUEUED_MESSAGE_CALL = _request_call(
    "automation", "take_queued_message", QueueMessageResponse
)
_AUTOMATION_GET_EXECUTION_CALL = _query_call("automation", "get_execution", ExecutionResponse)
_AUTOMATION_GET_LATEST_EXECUTION_CALL = _query_call(
    "automation", "get_latest_execution_for_task", ExecutionResponse
)
_AUTOMATION_COUNT_EXECUTIONS_CALL = _query_call(
    "automation", "count_executions_for_task", ExecutionCountResponse
)
_AUTOMATION_DECIDE_STARTUP_CALL = _query_call(
    "automation", "decide_startup", StartupDecisionResponse
)
_AUTOMATION_GET_RUNTIME_VIEW_CALL = _query_call(
    "automation", "get_runtime_view", RuntimeViewResponse
)
_AUTOMATION_QUEUE_STATUS_CALL = _query_call("automation", "get_queue_status", QueueStatusResponse)
_AUTOMATION_DISPATCH_RUNTIME_SESSION_CALL = _request_call(
    "automation", "dispatch_runtime_session", RuntimeStateResponse
)
_AUTOMATION_RECONCILE_CALL = _request_call(
    "automation", "reconcile_running_tasks", RuntimeReconcileResponse
)
_AUTOMATION_RUNNING_TASK_IDS_CALL = _query_call(
    "automation", "get_running_task_ids", TaskIdsResponse
)
_WORKSPACES_GET_DIFF_CALL = _query_call("workspaces", "get_workspace_diff", WorkspaceDiffResponse)
_WORKSPACES_GET_COMMIT_LOG_CALL = _query_call(
    "workspaces", "get_workspace_commit_log", WorkspaceCommitLogResponse
)
_WORKSPACES_GET_DIFF_STATS_CALL = _query_call(
    "workspaces", "get_workspace_diff_stats", WorkspaceDiffStatsResponse
)
_WORKSPACES_REBASE_CALL = _request_call("workspaces", "rebase_workspace", WorkspaceRebaseResponse)
_WORKSPACES_MERGE_REPO_CALL = _request_call("workspaces", "merge_repo", WorkspaceMergeResponse)
_WORKSPACES_GET_ALL_DIFFS_CALL = _query_call("workspaces", "get_all_diffs", AllDiffsResponse)
_WORKSPACES_GET_REPO_DIFF_CALL = _query_call("workspaces", "get_repo_diff", RepoDiffResponse)
_TASKS_PREPARE_AUTO_OUTPUT_CALL = _query_call("tasks", "prepare_auto_output", AutoOutputResponse)
_TASKS_RECOVER_STALE_AUTO_OUTPUT_CALL = _query_call(
    "tasks", "recover_stale_auto_output", AutoOutputResponse
)
_PROJECTS_UPDATE_REPO_DEFAULT_BRANCH_CALL = _request_call(
    "projects", "update_repo_default_branch", RepoUpdateResponse
)
_PLUGINS_UI_CATALOG_CALL = _query_call("plugins", "plugin_ui_catalog", PluginUiCatalogResponse)
_PLUGINS_UI_INVOKE_CALL = _request_call("plugins", "plugin_ui_invoke", PluginUiInvokeResponse)


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
        runtime_context: CoreRuntimeContext | None = None,
    ) -> None:
        resolved_client_version = get_kagan_version() if client_version is None else client_version
        self._transport = transport or SDKTransport(
            endpoint=endpoint,
            runtime_context=runtime_context,
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
        **overrides: Any,
    ) -> T:
        raw = (
            await self._request(spec.capability, spec.method, params)
            if spec.mutating
            else await self._query(spec.capability, spec.method, params)
        )
        return _build(spec.response_model, raw, **overrides)

    async def tasks_get(self, task_id: str) -> TaskResponse:
        return await self._call_model(_TASKS_GET_CALL, {"task_id": task_id})

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
        return await self._call_model(_TASKS_SEARCH_CALL, {"query": query})

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
        return await self._call_model(_TASKS_CREATE_CALL, params)

    async def tasks_update(self, task_id: str, **fields: Any) -> TaskUpdateResponse:
        params: dict[str, Any] = {"task_id": task_id}
        params.update(fields)
        return await self._call_model(_TASKS_UPDATE_CALL, params)

    async def tasks_move(self, task_id: str, status: str) -> TaskUpdateResponse:
        return await self._call_model(_TASKS_MOVE_CALL, {"task_id": task_id, "status": status})

    async def tasks_delete(self, task_id: str) -> TaskDeleteResponse:
        return await self._call_model(_TASKS_DELETE_CALL, {"task_id": task_id})

    async def tasks_scratchpad(
        self,
        task_id: str,
        content_char_limit: int = DEFAULT_TASK_SCRATCHPAD_CHAR_LIMIT,
    ) -> ScratchpadResponse:
        return await self._call_model(
            _TASKS_SCRATCHPAD_CALL,
            {"task_id": task_id, "content_char_limit": content_char_limit},
        )

    async def tasks_update_scratchpad(self, task_id: str, content: str) -> TaskUpdateResponse:
        result = await self._request(
            "tasks",
            "update_scratchpad",
            {"task_id": task_id, "content": content},
        )
        return _build(TaskUpdateResponse, result, code=result.get("code", "SCRATCHPAD_UPDATED"))

    async def tasks_context(self, task_id: str) -> TaskContextResponse:
        return await self._call_model(_TASKS_CONTEXT_CALL, {"task_id": task_id})

    async def tasks_logs(
        self,
        task_id: str,
        limit: int = DEFAULT_TASK_LOG_LIMIT,
        offset: int = 0,
        content_char_limit: int = DEFAULT_TASK_LOG_ENTRY_CHAR_LIMIT,
    ) -> TaskLogsResponse:
        return await self._call_model(
            _TASKS_LOGS_CALL,
            {
                "task_id": task_id,
                "limit": limit,
                "offset": offset,
                "content_char_limit": content_char_limit,
            },
        )

    async def tasks_wait(
        self,
        task_id: str,
        timeout_seconds: float = DEFAULT_JOB_WAIT_TIMEOUT_SECONDS,
        wait_for_status: list[str] | None = None,
        from_updated_at: str | None = None,
    ) -> TaskWaitResponse:
        params: dict[str, Any] = {"task_id": task_id, "timeout_seconds": timeout_seconds}
        if wait_for_status is not None:
            params["wait_for_status"] = wait_for_status
        if from_updated_at is not None:
            params["from_updated_at"] = from_updated_at
        return await self._call_model(_TASKS_WAIT_CALL, params)

    async def tasks_wait_any(
        self,
        timeout_seconds: float = DEFAULT_JOB_WAIT_TIMEOUT_SECONDS,
    ) -> TaskWaitAnyResponse:
        return await self._call_model(_TASKS_WAIT_ANY_CALL, {"timeout_seconds": timeout_seconds})

    async def review_request(self, task_id: str, summary: str = "") -> ReviewResponse:
        return await self._call_model(
            _REVIEW_REQUEST_CALL,
            {"task_id": task_id, "summary": summary},
        )

    async def review_approve(self, task_id: str) -> ReviewResponse:
        return await self._call_model(_REVIEW_APPROVE_CALL, {"task_id": task_id})

    async def review_reject(
        self,
        task_id: str,
        feedback: str = "",
        action: str = "reopen",
    ) -> ReviewResponse:
        return await self._call_model(
            _REVIEW_REJECT_CALL,
            {"task_id": task_id, "feedback": feedback, "action": action},
        )

    async def review_merge(self, task_id: str) -> ReviewResponse:
        return await self._call_model(_REVIEW_MERGE_CALL, {"task_id": task_id})

    async def review_rebase(self, task_id: str, base_branch: str | None = None) -> ReviewResponse:
        params: dict[str, Any] = {"task_id": task_id}
        if base_branch is not None:
            params["base_branch"] = base_branch
        return await self._call_model(_REVIEW_REBASE_CALL, params)

    async def projects_get(self, project_id: str) -> ProjectResponse:
        return await self._call_model(_PROJECTS_GET_CALL, {"project_id": project_id})

    async def projects_list(self, limit: int = 10) -> ProjectListResponse:
        return await self._call_model(_PROJECTS_LIST_CALL, {"limit": limit})

    async def projects_create(
        self,
        name: str,
        description: str = "",
        repo_paths: list[str] | None = None,
    ) -> ProjectCreateResponse:
        params: dict[str, Any] = {"name": name, "description": description}
        if repo_paths:
            params["repo_paths"] = repo_paths
        return await self._call_model(_PROJECTS_CREATE_CALL, params)

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
        return await self._call_model(_PROJECTS_REPOS_CALL, {"project_id": project_id})

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
        return await self._call_model(_PROJECTS_FIND_BY_REPO_PATH_CALL, {"repo_path": repo_path})

    async def settings_get(self) -> SettingsResponse:
        return await self._call_model(_SETTINGS_GET_CALL, {}, success=True)

    async def settings_update(self, fields: dict[str, Any]) -> SettingsResponse:
        return await self._call_model(_SETTINGS_UPDATE_CALL, {"fields": fields})

    async def jobs_submit(
        self,
        task_id: str,
        action: str,
        arguments: dict[str, Any] | None = None,
    ) -> JobResponse:
        params: dict[str, Any] = {"task_id": task_id, "action": action}
        if arguments:
            params["arguments"] = arguments
        return await self._call_model(_JOBS_SUBMIT_CALL, params)

    async def jobs_get(self, job_id: str, task_id: str) -> JobResponse:
        return await self._call_model(_JOBS_GET_CALL, {"job_id": job_id, "task_id": task_id})

    async def jobs_cancel(self, job_id: str, task_id: str) -> JobResponse:
        return await self._call_model(_JOBS_CANCEL_CALL, {"job_id": job_id, "task_id": task_id})

    async def jobs_wait(
        self,
        job_id: str,
        task_id: str,
        timeout_seconds: float = DEFAULT_JOB_WAIT_TIMEOUT_SECONDS,
    ) -> JobResponse:
        return await self._call_model(
            _JOBS_WAIT_CALL,
            {"job_id": job_id, "task_id": task_id, "timeout_seconds": timeout_seconds},
        )

    async def jobs_events(
        self,
        job_id: str,
        task_id: str,
        limit: int = DEFAULT_EVENTS_LIMIT,
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
        return await self._call_model(_SESSIONS_ATTACH_CALL, {"task_id": task_id}, task_id=task_id)

    async def sessions_exists(self, task_id: str) -> SessionExistsResponse:
        return await self._call_model(_SESSIONS_EXISTS_CALL, {"task_id": task_id})

    async def sessions_kill(self, task_id: str) -> SessionResponse:
        return await self._call_model(_SESSIONS_KILL_CALL, {"task_id": task_id}, task_id=task_id)

    async def workspaces_list(self, task_id: str | None = None) -> WorkspaceListResponse:
        params: dict[str, Any] = {}
        if task_id is not None:
            params["task_id"] = task_id
        return await self._call_model(_WORKSPACES_LIST_CALL, params)

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
        limit: int = DEFAULT_EVENTS_LIMIT,
        cursor: str | None = None,
    ) -> AuditListResponse:
        params: dict[str, Any] = {"limit": limit}
        if capability is not None:
            params["capability"] = capability
        if cursor is not None:
            params["cursor"] = cursor
        return await self._call_model(_AUDIT_LIST_CALL, params)

    async def diagnostics_instrumentation(self) -> DiagnosticsResponse:
        return await self._call_model(_DIAGNOSTICS_INSTRUMENTATION_CALL, {})

    async def plugins_invoke(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> PluginInvokeResponse:
        return await self._call_model(
            _PLUGINS_INVOKE_CALL,
            {"capability": capability, "method": method, "params": params or {}},
        )

    async def queue_message(
        self,
        session_id: str,
        content: str,
        lane: QueueLane = QueueLane.IMPLEMENTATION,
        author: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QueueMessageResponse:
        params: dict[str, Any] = {"session_id": session_id, "content": content, "lane": lane}
        if author is not None:
            params["author"] = author
        if metadata is not None:
            params["metadata"] = metadata
        return await self._call_model(_AUTOMATION_QUEUE_MESSAGE_CALL, params)

    async def get_queue_status(
        self,
        session_id: str,
        lane: QueueLane = QueueLane.IMPLEMENTATION,
    ) -> QueueStatusResponse:
        return await self._call_model(
            _AUTOMATION_QUEUE_STATUS_CALL,
            {"session_id": session_id, "lane": lane},
            lane=lane,
        )

    async def get_queued_messages(
        self,
        session_id: str,
        lane: QueueLane = QueueLane.IMPLEMENTATION,
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
        lane: QueueLane = QueueLane.IMPLEMENTATION,
    ) -> QueueMessageResponse:
        return await self._call_model(
            _AUTOMATION_TAKE_QUEUED_MESSAGE_CALL,
            {"session_id": session_id, "lane": lane},
        )

    async def remove_queued_message(
        self,
        session_id: str,
        index: int,
        lane: QueueLane = QueueLane.IMPLEMENTATION,
    ) -> BoolResponse:
        result = await self._request(
            "automation",
            "remove_queued_message",
            {"session_id": session_id, "index": index, "lane": lane},
        )
        return BoolResponse(value=result.get("success", False), message=result.get("message", ""))

    async def get_execution(self, execution_id: str) -> ExecutionResponse:
        return await self._call_model(
            _AUTOMATION_GET_EXECUTION_CALL,
            {"execution_id": execution_id},
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
        return await self._call_model(_AUTOMATION_GET_LATEST_EXECUTION_CALL, {"task_id": task_id})

    async def count_executions_for_task(self, task_id: str) -> ExecutionCountResponse:
        return await self._call_model(_AUTOMATION_COUNT_EXECUTIONS_CALL, {"task_id": task_id})

    async def decide_startup(self, cwd: str) -> StartupDecisionResponse:
        return await self._call_model(_AUTOMATION_DECIDE_STARTUP_CALL, {"cwd": cwd})

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
        return await self._call_model(_AUTOMATION_DISPATCH_RUNTIME_SESSION_CALL, params)

    def get_runtime_state(self) -> RuntimeStateResponse:
        return RuntimeStateResponse(project_id=None, repo_id=None)

    async def get_runtime_view(self, task_id: str) -> RuntimeViewResponse:
        return await self._call_model(_AUTOMATION_GET_RUNTIME_VIEW_CALL, {"task_id": task_id})

    async def is_automation_running(self, task_id: str) -> BoolResponse:
        result = await self._query("automation", "is_automation_running", {"task_id": task_id})
        return BoolResponse(value=result.get("is_running", False))

    async def reconcile_running_tasks(self, task_ids: list[str]) -> RuntimeReconcileResponse:
        return await self._call_model(_AUTOMATION_RECONCILE_CALL, {"task_ids": task_ids})

    async def get_running_task_ids(self) -> TaskIdsResponse:
        return await self._call_model(_AUTOMATION_RUNNING_TASK_IDS_CALL, {})

    async def get_workspace_diff(self, task_id: str, base_branch: str) -> WorkspaceDiffResponse:
        return await self._call_model(
            _WORKSPACES_GET_DIFF_CALL,
            {"task_id": task_id, "base_branch": base_branch},
        )

    async def get_workspace_commit_log(
        self,
        task_id: str,
        base_branch: str,
    ) -> WorkspaceCommitLogResponse:
        return await self._call_model(
            _WORKSPACES_GET_COMMIT_LOG_CALL,
            {"task_id": task_id, "base_branch": base_branch},
        )

    async def get_workspace_diff_stats(
        self,
        task_id: str,
        base_branch: str,
    ) -> WorkspaceDiffStatsResponse:
        return await self._call_model(
            _WORKSPACES_GET_DIFF_STATS_CALL,
            {"task_id": task_id, "base_branch": base_branch},
        )

    async def rebase_workspace(self, task_id: str, base_branch: str) -> WorkspaceRebaseResponse:
        return await self._call_model(
            _WORKSPACES_REBASE_CALL,
            {"task_id": task_id, "base_branch": base_branch},
        )

    async def abort_workspace_rebase(self, task_id: str) -> BoolResponse:
        result = await self._request("workspaces", "abort_workspace_rebase", {"task_id": task_id})
        return BoolResponse(value=result.get("success", False))

    async def get_all_diffs(self, workspace_id: str) -> AllDiffsResponse:
        return await self._call_model(
            _WORKSPACES_GET_ALL_DIFFS_CALL,
            {"workspace_id": workspace_id},
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
        return await self._call_model(_WORKSPACES_MERGE_REPO_CALL, params)

    async def get_repo_diff(self, workspace_id: str, repo_id: str) -> RepoDiffResponse:
        return await self._call_model(
            _WORKSPACES_GET_REPO_DIFF_CALL,
            {"workspace_id": workspace_id, "repo_id": repo_id},
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
        return await self._call_model(_TASKS_PREPARE_AUTO_OUTPUT_CALL, {"task_id": task_id})

    async def recover_stale_auto_output(self, task_id: str) -> AutoOutputResponse:
        return await self._call_model(_TASKS_RECOVER_STALE_AUTO_OUTPUT_CALL, {"task_id": task_id})

    async def update_repo_default_branch(
        self,
        repo_id: str,
        branch: str,
        mark_configured: bool = False,
    ) -> RepoUpdateResponse:
        return await self._call_model(
            _PROJECTS_UPDATE_REPO_DEFAULT_BRANCH_CALL,
            {"repo_id": repo_id, "branch": branch, "mark_configured": mark_configured},
        )

    async def plugin_ui_catalog(
        self,
        project_id: str,
        repo_id: str | None = None,
    ) -> PluginUiCatalogResponse:
        params: dict[str, Any] = {"project_id": project_id}
        if repo_id is not None:
            params["repo_id"] = repo_id
        return await self._call_model(_PLUGINS_UI_CATALOG_CALL, params)

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
        return await self._call_model(_PLUGINS_UI_INVOKE_CALL, params)


__all__ = ["KaganSDK"]
