"""Kagan SDK client with typed async methods."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.sdk._transport import SDKTransport
from kagan.sdk._types import (
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

if TYPE_CHECKING:
    from kagan.core.constants import CapabilityProfile
    from kagan.core.ipc.discovery import CoreEndpoint


class KaganSDK:
    """Typed async Python API for Kagan.

    Provides a clean interface over IPC for all Kagan operations.
    All methods return typed response objects.

    Usage::

        async with KaganSDK() as sdk:
            tasks = await sdk.tasks.list()
            for task in tasks.tasks:
                print(task["title"])
    """

    def __init__(
        self,
        transport: SDKTransport | None = None,
        *,
        session_id: str = "sdk-session",
        session_origin: str = "sdk",
        client_version: str = "0.0.0",
        capability_profile: CapabilityProfile | str = "operator",
        endpoint: CoreEndpoint | None = None,
    ) -> None:
        self._transport = transport or SDKTransport(
            endpoint=endpoint,
            session_id=session_id,
            session_origin=session_origin,
            client_version=client_version,
            capability_profile=capability_profile,
        )

    async def __aenter__(self) -> KaganSDK:
        await self._transport.connect()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self._transport.close()

    @property
    def is_connected(self) -> bool:
        """Whether the SDK is currently connected."""
        return self._transport.is_connected

    async def connect(self) -> None:
        """Connect to the Kagan core."""
        await self._transport.connect()

    async def close(self) -> None:
        """Close the connection to the Kagan core."""
        await self._transport.close()

    async def _request(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a request to the core."""
        return await self._transport.request(capability, method, params)

    async def _query(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make a query to the core."""
        return await self._transport.query(capability, method, params)

    # -------------------------------------------------------------------------
    # Task operations
    # -------------------------------------------------------------------------

    async def tasks_get(self, task_id: str) -> TaskResponse:
        """Get a single task by ID."""
        result = await self._query("tasks", "get", {"task_id": task_id})
        return TaskResponse(
            found=result.get("found", False),
            task=result.get("task"),
        )

    async def tasks_list(
        self,
        project_id: str | None = None,
        status: str | None = None,
        include_scratchpad: bool = False,
        exclude_task_ids: list[str] | None = None,
    ) -> TaskListResponse:
        """List tasks with optional filters."""
        params: dict[str, Any] = {}
        if project_id is not None:
            params["project_id"] = project_id
        if status is not None:
            params["filter"] = status
        if include_scratchpad:
            params["include_scratchpad"] = True
        if exclude_task_ids:
            params["exclude_task_ids"] = exclude_task_ids
        result = await self._query("tasks", "list", params)
        return TaskListResponse(
            tasks=result.get("tasks", []),
            count=result.get("count", 0),
        )

    async def tasks_search(self, query: str) -> TaskListResponse:
        """Search tasks by text query."""
        result = await self._query("tasks", "search", {"query": query})
        return TaskListResponse(
            tasks=result.get("tasks", []),
            count=result.get("count", 0),
        )

    async def tasks_create(
        self,
        title: str,
        description: str = "",
        project_id: str | None = None,
        created_by: str | None = None,
        **fields: Any,
    ) -> TaskCreateResponse:
        """Create a new task."""
        params: dict[str, Any] = {"title": title, "description": description}
        if project_id is not None:
            params["project_id"] = project_id
        if created_by is not None:
            params["created_by"] = created_by
        params.update(fields)
        result = await self._request("tasks", "create", params)
        return TaskCreateResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            title=result.get("title", ""),
            status=result.get("status", ""),
        )

    async def tasks_update(
        self,
        task_id: str,
        **fields: Any,
    ) -> TaskUpdateResponse:
        """Update task fields."""
        params: dict[str, Any] = {"task_id": task_id}
        params.update(fields)
        result = await self._request("tasks", "update", params)
        return TaskUpdateResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            code=result.get("code", ""),
            message=result.get("message"),
            hint=result.get("hint"),
        )

    async def tasks_move(
        self,
        task_id: str,
        status: str,
    ) -> TaskUpdateResponse:
        """Move a task to a new status."""
        result = await self._request("tasks", "move", {"task_id": task_id, "status": status})
        return TaskUpdateResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            code=result.get("code", ""),
            message=result.get("message"),
            hint=result.get("hint"),
        )

    async def tasks_delete(self, task_id: str) -> TaskDeleteResponse:
        """Delete a task."""
        result = await self._request("tasks", "delete", {"task_id": task_id})
        return TaskDeleteResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            message=result.get("message", ""),
        )

    async def tasks_scratchpad(
        self,
        task_id: str,
        content_char_limit: int = 16_000,
    ) -> ScratchpadResponse:
        """Get a task's scratchpad content."""
        result = await self._query(
            "tasks",
            "scratchpad",
            {"task_id": task_id, "content_char_limit": content_char_limit},
        )
        return ScratchpadResponse(
            task_id=result.get("task_id", ""),
            content=result.get("content", ""),
            truncated=result.get("truncated", False),
        )

    async def tasks_update_scratchpad(
        self,
        task_id: str,
        content: str,
    ) -> TaskUpdateResponse:
        """Append to task scratchpad."""
        result = await self._request(
            "tasks",
            "update_scratchpad",
            {"task_id": task_id, "content": content},
        )
        return TaskUpdateResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            code=result.get("code", "SCRATCHPAD_UPDATED"),
        )

    async def tasks_context(self, task_id: str) -> TaskContextResponse:
        """Get task context for AI tools."""
        result = await self._query("tasks", "context", {"task_id": task_id})
        return TaskContextResponse(
            task_id=result.get("task_id", ""),
            project_id=result.get("project_id", ""),
            title=result.get("title", ""),
            description=result.get("description", ""),
            status=result.get("status", ""),
            acceptance_criteria=result.get("acceptance_criteria"),
            scratchpad=result.get("scratchpad", ""),
            workspace_id=result.get("workspace_id"),
            workspace_branch=result.get("workspace_branch"),
            workspace_path=result.get("workspace_path"),
            repos=result.get("repos", []),
            repo_count=result.get("repo_count", 0),
            linked_tasks=result.get("linked_tasks", []),
        )

    async def tasks_logs(
        self,
        task_id: str,
        limit: int = 5,
        offset: int = 0,
        content_char_limit: int = 6_000,
    ) -> TaskLogsResponse:
        """Get task execution logs."""
        result = await self._query(
            "tasks",
            "logs",
            {
                "task_id": task_id,
                "limit": limit,
                "offset": offset,
                "content_char_limit": content_char_limit,
            },
        )
        return TaskLogsResponse(
            task_id=result.get("task_id", ""),
            logs=result.get("logs", []),
            count=result.get("count", 0),
            total_runs=result.get("total_runs", 0),
            returned_runs=result.get("returned_runs", 0),
            offset=result.get("offset", 0),
            limit=result.get("limit", 0),
            has_more=result.get("has_more", False),
            next_offset=result.get("next_offset"),
            truncated=result.get("truncated", False),
        )

    async def tasks_wait(
        self,
        task_id: str,
        timeout_seconds: float = 30.0,
        wait_for_status: list[str] | None = None,
        from_updated_at: str | None = None,
    ) -> TaskWaitResponse:
        """Wait for task status change."""
        params: dict[str, Any] = {
            "task_id": task_id,
            "timeout_seconds": timeout_seconds,
        }
        if wait_for_status is not None:
            params["wait_for_status"] = wait_for_status
        if from_updated_at is not None:
            params["from_updated_at"] = from_updated_at
        result = await self._request("tasks", "wait", params)
        return TaskWaitResponse(
            changed=result.get("changed", False),
            timed_out=result.get("timed_out", False),
            task_id=result.get("task_id", ""),
            previous_status=result.get("previous_status"),
            current_status=result.get("current_status"),
            changed_at=result.get("changed_at"),
            task=result.get("task"),
            code=result.get("code", ""),
            message=result.get("message"),
        )

    # -------------------------------------------------------------------------
    # Review operations
    # -------------------------------------------------------------------------

    async def review_request(self, task_id: str, summary: str = "") -> ReviewResponse:
        """Mark task ready for review."""
        result = await self._request("review", "request", {"task_id": task_id, "summary": summary})
        return ReviewResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            status=result.get("status", ""),
            code=result.get("code", ""),
            message=result.get("message"),
            hint=result.get("hint"),
        )

    async def review_approve(self, task_id: str) -> ReviewResponse:
        """Approve a task review."""
        result = await self._request("review", "approve", {"task_id": task_id})
        return ReviewResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            status=result.get("status", ""),
            code=result.get("code", ""),
            message=result.get("message"),
        )

    async def review_reject(
        self,
        task_id: str,
        feedback: str = "",
        action: str = "reopen",
    ) -> ReviewResponse:
        """Reject a task review with feedback."""
        result = await self._request(
            "review",
            "reject",
            {"task_id": task_id, "feedback": feedback, "action": action},
        )
        return ReviewResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            status=result.get("status", ""),
            code=result.get("code", ""),
        )

    async def review_merge(self, task_id: str) -> ReviewResponse:
        """Merge a reviewed task."""
        result = await self._request("review", "merge", {"task_id": task_id})
        return ReviewResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            code=result.get("code", ""),
            message=result.get("message"),
        )

    async def review_rebase(
        self,
        task_id: str,
        base_branch: str | None = None,
    ) -> ReviewResponse:
        """Rebase a reviewed task."""
        params: dict[str, Any] = {"task_id": task_id}
        if base_branch is not None:
            params["base_branch"] = base_branch
        result = await self._request("review", "rebase", params)
        return ReviewResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", ""),
            code=result.get("code", ""),
            message=result.get("message"),
        )

    # -------------------------------------------------------------------------
    # Project operations
    # -------------------------------------------------------------------------

    async def projects_get(self, project_id: str) -> ProjectResponse:
        """Get a project by ID."""
        result = await self._query("projects", "get", {"project_id": project_id})
        return ProjectResponse(
            found=result.get("found", False),
            project=result.get("project"),
        )

    async def projects_list(self, limit: int = 10) -> ProjectListResponse:
        """List recent projects."""
        result = await self._query("projects", "list", {"limit": limit})
        return ProjectListResponse(
            projects=result.get("projects", []),
            count=result.get("count", 0),
        )

    async def projects_create(
        self,
        name: str,
        description: str = "",
        repo_paths: list[str] | None = None,
    ) -> ProjectCreateResponse:
        """Create a new project."""
        params: dict[str, Any] = {"name": name, "description": description}
        if repo_paths:
            params["repo_paths"] = repo_paths
        result = await self._request("projects", "create", params)
        return ProjectCreateResponse(
            success=result.get("success", False),
            project_id=result.get("project_id", ""),
            name=result.get("name", ""),
            description=result.get("description", ""),
            repo_count=result.get("repo_count", 0),
        )

    async def projects_open(self, project_id: str) -> ProjectResponse:
        """Open/switch to a project."""
        result = await self._request("projects", "open", {"project_id": project_id})
        return ProjectResponse(
            found=result.get("success", False),
            project={"project_id": result.get("project_id"), "name": result.get("name")},
        )

    async def projects_repos(self, project_id: str) -> RepoListResponse:
        """Get all repos for a project."""
        result = await self._query("projects", "repos", {"project_id": project_id})
        return RepoListResponse(
            repos=result.get("repos", []),
            count=result.get("count", 0),
        )

    async def projects_add_repo(
        self,
        project_id: str,
        repo_path: str,
        is_primary: bool = False,
    ) -> ProjectResponse:
        """Add a repository to a project."""
        result = await self._request(
            "projects",
            "add_repo",
            {"project_id": project_id, "repo_path": repo_path, "is_primary": is_primary},
        )
        return ProjectResponse(
            found=result.get("success", False),
            project={
                "project_id": result.get("project_id"),
                "repo_id": result.get("repo_id"),
                "repo_path": result.get("repo_path"),
            },
        )

    async def projects_find_by_repo_path(self, repo_path: str) -> ProjectResponse:
        """Find a project containing a repository."""
        result = await self._query("projects", "find_by_repo_path", {"repo_path": repo_path})
        return ProjectResponse(
            found=result.get("found", False),
            project=result.get("project"),
        )

    # -------------------------------------------------------------------------
    # Settings operations
    # -------------------------------------------------------------------------

    async def settings_get(self) -> SettingsResponse:
        """Get admin-exposed settings."""
        result = await self._query("settings", "get", {})
        return SettingsResponse(
            success=True,
            settings=result.get("settings", {}),
        )

    async def settings_update(self, fields: dict[str, Any]) -> SettingsResponse:
        """Update allowlisted settings fields."""
        result = await self._request("settings", "update", {"fields": fields})
        return SettingsResponse(
            success=result.get("success", False),
            settings=result.get("settings", {}),
            message=result.get("message"),
            updated=result.get("updated", {}),
        )

    # -------------------------------------------------------------------------
    # Job operations
    # -------------------------------------------------------------------------

    async def jobs_submit(
        self,
        task_id: str,
        action: str,
        arguments: dict[str, Any] | None = None,
    ) -> JobResponse:
        """Submit a job."""
        params: dict[str, Any] = {"task_id": task_id, "action": action}
        if arguments:
            params["arguments"] = arguments
        result = await self._request("jobs", "submit", params)
        return JobResponse(
            success=result.get("success", False),
            job_id=result.get("job_id", ""),
            task_id=result.get("task_id", ""),
            action=result.get("action", ""),
            status=result.get("status", ""),
            code=result.get("code", ""),
            created_at=result.get("created_at", ""),
            updated_at=result.get("updated_at", ""),
        )

    async def jobs_get(self, job_id: str, task_id: str) -> JobResponse:
        """Get a job."""
        result = await self._query("jobs", "get", {"job_id": job_id, "task_id": task_id})
        return JobResponse(
            success=result.get("success", False),
            job_id=result.get("job_id", ""),
            task_id=result.get("task_id", ""),
            action=result.get("action", ""),
            status=result.get("status", ""),
            code=result.get("code", ""),
            created_at=result.get("created_at", ""),
            updated_at=result.get("updated_at", ""),
        )

    async def jobs_cancel(self, job_id: str, task_id: str) -> JobResponse:
        """Cancel a job."""
        result = await self._request("jobs", "cancel", {"job_id": job_id, "task_id": task_id})
        return JobResponse(
            success=result.get("success", False),
            job_id=result.get("job_id", ""),
            task_id=result.get("task_id", ""),
            action=result.get("action", ""),
            status=result.get("status", ""),
            message=result.get("message"),
            code=result.get("code", ""),
            created_at=result.get("created_at", ""),
            updated_at=result.get("updated_at", ""),
        )

    async def jobs_wait(
        self,
        job_id: str,
        task_id: str,
        timeout_seconds: float = 30.0,
    ) -> JobResponse:
        """Wait for a job to complete."""
        result = await self._request(
            "jobs",
            "wait",
            {"job_id": job_id, "task_id": task_id, "timeout_seconds": timeout_seconds},
        )
        return JobResponse(
            success=result.get("success", False),
            job_id=result.get("job_id", ""),
            task_id=result.get("task_id", ""),
            action=result.get("action", ""),
            status=result.get("status", ""),
            code=result.get("code", ""),
            created_at=result.get("created_at", ""),
            updated_at=result.get("updated_at", ""),
        )

    async def jobs_events(
        self,
        job_id: str,
        task_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> JobListResponse:
        """List job events."""
        result = await self._query(
            "jobs",
            "events",
            {"job_id": job_id, "task_id": task_id, "limit": limit, "offset": offset},
        )
        return JobListResponse(
            success=result.get("success", False),
            job_id=result.get("job_id", ""),
            task_id=result.get("task_id", ""),
            events=result.get("events", []),
            total_events=result.get("total_events", 0),
            returned_events=result.get("returned_events", 0),
            offset=result.get("offset", 0),
            limit=result.get("limit", 0),
            has_more=result.get("has_more", False),
            next_offset=result.get("next_offset"),
        )

    # -------------------------------------------------------------------------
    # Session operations
    # -------------------------------------------------------------------------

    async def sessions_create(
        self,
        task_id: str,
        reuse_if_exists: bool = True,
        worktree_path: str | None = None,
    ) -> SessionResponse:
        """Create or reuse a session for a task."""
        params: dict[str, Any] = {"task_id": task_id, "reuse_if_exists": reuse_if_exists}
        if worktree_path is not None:
            params["worktree_path"] = worktree_path
        result = await self._request("sessions", "create", params)
        return SessionResponse(
            success=result.get("success", False),
            task_id=result.get("task_id", task_id),
            message=result.get("message", ""),
            session_name=result.get("session_name"),
            worktree_path=result.get("worktree_path"),
            backend=result.get("backend"),
            already_exists=result.get("already_exists", False),
        )

    async def sessions_attach(self, task_id: str) -> SessionResponse:
        """Attach to a task session."""
        result = await self._query("sessions", "attach", {"task_id": task_id})
        return SessionResponse(
            success=result.get("success", False),
            task_id=task_id,
            message=result.get("message", ""),
        )

    async def sessions_exists(self, task_id: str) -> SessionExistsResponse:
        """Check session existence."""
        result = await self._query("sessions", "exists", {"task_id": task_id})
        return SessionExistsResponse(
            task_id=result.get("task_id", ""),
            exists=result.get("exists", False),
            session_name=result.get("session_name", ""),
            backend=result.get("backend"),
            worktree_path=result.get("worktree_path"),
            prompt_path=result.get("prompt_path"),
        )

    async def sessions_kill(self, task_id: str) -> SessionResponse:
        """Terminate a session."""
        result = await self._request("sessions", "kill", {"task_id": task_id})
        return SessionResponse(
            success=result.get("success", False),
            task_id=task_id,
            message=result.get("message", ""),
        )

    # -------------------------------------------------------------------------
    # Workspace operations
    # -------------------------------------------------------------------------

    async def workspaces_list(self, task_id: str | None = None) -> WorkspaceListResponse:
        """List workspaces."""
        params: dict[str, Any] = {}
        if task_id is not None:
            params["task_id"] = task_id
        result = await self._query("workspaces", "list", params)
        return WorkspaceListResponse(
            workspaces=result.get("workspaces", []),
            count=result.get("count", 0),
        )

    # -------------------------------------------------------------------------
    # Audit operations
    # -------------------------------------------------------------------------

    async def audit_list(
        self,
        capability: str | None = None,
        limit: int = 50,
        cursor: str | None = None,
    ) -> AuditListResponse:
        """List recent audit events."""
        params: dict[str, Any] = {"limit": limit}
        if capability is not None:
            params["capability"] = capability
        if cursor is not None:
            params["cursor"] = cursor
        result = await self._query("audit", "list", params)
        return AuditListResponse(
            events=result.get("events", []),
            count=result.get("count", 0),
            truncated=result.get("truncated", False),
        )

    # -------------------------------------------------------------------------
    # Diagnostics operations
    # -------------------------------------------------------------------------

    async def diagnostics_instrumentation(self) -> DiagnosticsResponse:
        """Get diagnostics instrumentation snapshot."""
        result = await self._query("diagnostics", "instrumentation", {})
        return DiagnosticsResponse(
            instrumentation=result.get("instrumentation", {}),
        )

    # -------------------------------------------------------------------------
    # Plugin operations
    # -------------------------------------------------------------------------

    async def plugins_invoke(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> PluginInvokeResponse:
        """Invoke a plugin operation."""
        result = await self._request(
            "plugins",
            "invoke",
            {"capability": capability, "method": method, "params": params or {}},
        )
        return PluginInvokeResponse(
            success=result.get("success", False),
            result=result.get("result"),
            error=result.get("error"),
        )

    # -------------------------------------------------------------------------
    # Queue operations
    # -------------------------------------------------------------------------

    async def queue_message(
        self,
        session_id: str,
        content: str,
        lane: str = "implementation",
        author: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QueueMessageResponse:
        """Queue a message to a session lane."""
        params: dict[str, Any] = {
            "session_id": session_id,
            "content": content,
            "lane": lane,
        }
        if author is not None:
            params["author"] = author
        if metadata is not None:
            params["metadata"] = metadata
        result = await self._request("automation", "queue_message", params)
        return QueueMessageResponse(
            success=result.get("success", False),
            message=result.get("message", ""),
        )

    async def get_queue_status(
        self,
        session_id: str,
        lane: str = "implementation",
    ) -> QueueStatusResponse:
        """Get the status of a queue."""
        result = await self._query(
            "automation",
            "get_queue_status",
            {"session_id": session_id, "lane": lane},
        )
        return QueueStatusResponse(
            has_queued=result.get("has_queued", False),
            lane=lane,
        )

    async def get_queued_messages(
        self,
        session_id: str,
        lane: str = "implementation",
    ) -> QueueListResponse:
        """Get queued messages for a session lane."""
        result = await self._query(
            "automation",
            "get_queued_messages",
            {"session_id": session_id, "lane": lane},
        )
        messages = result.get("messages", []) if isinstance(result.get("messages"), list) else []
        return QueueListResponse(
            messages=messages,
            count=len(messages),
        )

    async def take_queued_message(
        self,
        session_id: str,
        lane: str = "implementation",
    ) -> QueueMessageResponse:
        """Take the next message from the queue."""
        result = await self._request(
            "automation",
            "take_queued_message",
            {"session_id": session_id, "lane": lane},
        )
        return QueueMessageResponse(
            success=result.get("success", False),
            message=result.get("message", ""),
        )

    async def remove_queued_message(
        self,
        session_id: str,
        index: int,
        lane: str = "implementation",
    ) -> BoolResponse:
        """Remove a message from the queue by index."""
        result = await self._request(
            "automation",
            "remove_queued_message",
            {"session_id": session_id, "index": index, "lane": lane},
        )
        return BoolResponse(
            value=result.get("success", False),
            message=result.get("message", ""),
        )

    # -------------------------------------------------------------------------
    # Planner draft operations
    # -------------------------------------------------------------------------

    async def save_planner_draft(
        self,
        project_id: str,
        tasks_json: list[dict[str, Any]],
        repo_id: str | None = None,
        todos_json: list[dict[str, Any]] | None = None,
    ) -> PlannerDraftResponse:
        """Save a planner draft."""
        params: dict[str, Any] = {
            "project_id": project_id,
            "tasks_json": tasks_json,
        }
        if repo_id is not None:
            params["repo_id"] = repo_id
        if todos_json is not None:
            params["todos_json"] = todos_json
        result = await self._request("automation", "save_planner_draft", params)
        return PlannerDraftResponse(
            success=result.get("success", False),
            message=result.get("message", ""),
        )

    async def list_pending_planner_drafts(
        self,
        project_id: str,
        repo_id: str | None = None,
    ) -> PlannerDraftListResponse:
        """List pending planner drafts."""
        params: dict[str, Any] = {"project_id": project_id}
        if repo_id is not None:
            params["repo_id"] = repo_id
        result = await self._query("automation", "list_pending_planner_drafts", params)
        drafts = result.get("drafts", []) if isinstance(result.get("drafts"), list) else []
        return PlannerDraftListResponse(
            drafts=drafts,
            count=len(drafts),
        )

    async def update_planner_draft_status(
        self,
        proposal_id: str,
        status: str,
    ) -> PlannerDraftResponse:
        """Update planner draft status."""
        result = await self._request(
            "automation",
            "update_planner_draft_status",
            {"proposal_id": proposal_id, "status": status},
        )
        return PlannerDraftResponse(
            success=result.get("success", False),
            message=result.get("message", ""),
        )

    # -------------------------------------------------------------------------
    # Execution operations
    # -------------------------------------------------------------------------

    async def get_execution(self, execution_id: str) -> ExecutionResponse:
        """Get an execution by ID."""
        result = await self._query("automation", "get_execution", {"execution_id": execution_id})
        return ExecutionResponse(
            execution=result.get("execution"),
        )

    async def get_execution_log_entries(
        self,
        execution_id: str,
    ) -> ExecutionLogResponse:
        """Get execution log entries."""
        result = await self._query(
            "automation",
            "get_execution_log_entries",
            {"execution_id": execution_id},
        )
        entries = result.get("entries", []) if isinstance(result.get("entries"), list) else []
        return ExecutionLogResponse(
            entries=entries,
            count=len(entries),
        )

    async def get_latest_execution_for_task(self, task_id: str) -> ExecutionResponse:
        """Get the latest execution for a task."""
        result = await self._query(
            "automation",
            "get_latest_execution_for_task",
            {"task_id": task_id},
        )
        return ExecutionResponse(
            execution=result.get("execution"),
        )

    async def count_executions_for_task(self, task_id: str) -> ExecutionCountResponse:
        """Count executions for a task."""
        result = await self._query(
            "automation",
            "count_executions_for_task",
            {"task_id": task_id},
        )
        return ExecutionCountResponse(
            count=result.get("count", 0),
        )

    # -------------------------------------------------------------------------
    # Runtime operations
    # -------------------------------------------------------------------------

    async def decide_startup(self, cwd: str) -> StartupDecisionResponse:
        """Decide startup configuration based on current working directory."""
        result = await self._query("automation", "decide_startup", {"cwd": cwd})
        return StartupDecisionResponse(
            project_id=result.get("project_id"),
            preferred_repo_id=result.get("preferred_repo_id"),
            preferred_path=result.get("preferred_path"),
            suggest_cwd=result.get("suggest_cwd", False),
            cwd_path=result.get("cwd_path"),
            cwd_is_git_repo=result.get("cwd_is_git_repo", False),
            should_open_project=result.get("should_open_project", False),
        )

    async def dispatch_runtime_session(
        self,
        event: str,
        project_id: str | None = None,
        repo_id: str | None = None,
    ) -> RuntimeStateResponse:
        """Dispatch a runtime session event."""
        params: dict[str, Any] = {"event": event}
        if project_id is not None:
            params["project_id"] = project_id
        if repo_id is not None:
            params["repo_id"] = repo_id
        result = await self._request("automation", "dispatch_runtime_session", params)
        return RuntimeStateResponse(
            project_id=result.get("project_id"),
            repo_id=result.get("repo_id"),
        )

    def get_runtime_state(self) -> RuntimeStateResponse:
        """Get the current runtime state."""
        return RuntimeStateResponse(
            project_id=None,
            repo_id=None,
        )

    async def get_runtime_view(self, task_id: str) -> RuntimeViewResponse:
        """Get runtime view for a task."""
        result = await self._query("automation", "get_runtime_view", {"task_id": task_id})
        return RuntimeViewResponse(
            view=result.get("view"),
        )

    async def is_automation_running(self, task_id: str) -> BoolResponse:
        """Check if automation is running for a task."""
        result = await self._query("automation", "is_automation_running", {"task_id": task_id})
        return BoolResponse(
            value=result.get("is_running", False),
        )

    async def reconcile_running_tasks(self, task_ids: list[str]) -> TaskIdsResponse:
        """Reconcile running tasks."""
        result = await self._request(
            "automation",
            "reconcile_running_tasks",
            {"task_ids": task_ids},
        )
        task_ids_list = (
            result.get("task_ids", []) if isinstance(result.get("task_ids"), list) else []
        )
        return TaskIdsResponse(
            task_ids=task_ids_list,
        )

    async def get_running_task_ids(self) -> TaskIdsResponse:
        """Get IDs of running tasks."""
        result = await self._query("automation", "get_running_task_ids", {})
        task_ids = result.get("task_ids", []) if isinstance(result.get("task_ids"), list) else []
        return TaskIdsResponse(
            task_ids=task_ids,
        )

    # -------------------------------------------------------------------------
    # Workspace diff operations
    # -------------------------------------------------------------------------

    async def get_workspace_diff(
        self,
        task_id: str,
        base_branch: str,
    ) -> WorkspaceDiffResponse:
        """Get workspace diff."""
        result = await self._query(
            "workspaces",
            "get_workspace_diff",
            {"task_id": task_id, "base_branch": base_branch},
        )
        return WorkspaceDiffResponse(
            diff=result.get("diff", ""),
        )

    async def get_workspace_commit_log(
        self,
        task_id: str,
        base_branch: str,
    ) -> WorkspaceCommitLogResponse:
        """Get workspace commit log."""
        result = await self._query(
            "workspaces",
            "get_workspace_commit_log",
            {"task_id": task_id, "base_branch": base_branch},
        )
        commits = result.get("commits", []) if isinstance(result.get("commits"), list) else []
        return WorkspaceCommitLogResponse(
            commits=commits,
        )

    async def get_workspace_diff_stats(
        self,
        task_id: str,
        base_branch: str,
    ) -> WorkspaceDiffStatsResponse:
        """Get workspace diff stats."""
        result = await self._query(
            "workspaces",
            "get_workspace_diff_stats",
            {"task_id": task_id, "base_branch": base_branch},
        )
        return WorkspaceDiffStatsResponse(
            stats=result.get("stats", ""),
        )

    async def rebase_workspace(
        self,
        task_id: str,
        base_branch: str,
    ) -> WorkspaceRebaseResponse:
        """Rebase workspace."""
        result = await self._request(
            "workspaces",
            "rebase_workspace",
            {"task_id": task_id, "base_branch": base_branch},
        )
        conflict_files = (
            result.get("conflict_files", [])
            if isinstance(result.get("conflict_files"), list)
            else []
        )
        return WorkspaceRebaseResponse(
            success=result.get("success", False),
            message=result.get("message", ""),
            conflict_files=conflict_files,
        )

    async def abort_workspace_rebase(self, task_id: str) -> BoolResponse:
        """Abort workspace rebase."""
        result = await self._request(
            "workspaces",
            "abort_workspace_rebase",
            {"task_id": task_id},
        )
        return BoolResponse(
            value=result.get("success", False),
        )

    async def get_all_diffs(self, workspace_id: str) -> AllDiffsResponse:
        """Get all diffs for a workspace."""
        result = await self._query(
            "workspaces",
            "get_all_diffs",
            {"workspace_id": workspace_id},
        )
        diffs = result.get("diffs", []) if isinstance(result.get("diffs"), list) else []
        return AllDiffsResponse(
            diffs=diffs,
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
        """Merge a repo in workspace."""
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
        result = await self._request("workspaces", "merge_repo", params)
        return WorkspaceMergeResponse(
            success=result.get("success", False),
            message=result.get("message", ""),
            pr_url=result.get("pr_url"),
        )

    async def get_repo_diff(
        self,
        workspace_id: str,
        repo_id: str,
    ) -> RepoDiffResponse:
        """Get repo diff."""
        result = await self._query(
            "workspaces",
            "get_repo_diff",
            {"workspace_id": workspace_id, "repo_id": repo_id},
        )
        files = result.get("files", []) if isinstance(result.get("files"), list) else []
        return RepoDiffResponse(
            repo_id=result.get("repo_id", ""),
            repo_name=result.get("repo_name", ""),
            files=files,
        )

    async def get_workspace_path(self, task_id: str) -> str:
        """Get workspace path for a task."""
        result = await self._query(
            "workspaces",
            "get_workspace_path",
            {"task_id": task_id},
        )
        return result.get("path", "")

    async def cleanup_orphan_workspaces(self, valid_task_ids: list[str]) -> list[str]:
        """Clean up orphan workspaces."""
        result = await self._request(
            "workspaces",
            "cleanup_orphan_workspaces",
            {"valid_task_ids": valid_task_ids},
        )
        cleaned = result.get("cleaned", []) if isinstance(result.get("cleaned"), list) else []
        return cleaned

    # -------------------------------------------------------------------------
    # Task operations (additional)
    # -------------------------------------------------------------------------

    async def has_no_changes(self, task_id: str) -> BoolResponse:
        """Check if task has no changes."""
        result = await self._query("tasks", "has_no_changes", {"task_id": task_id})
        return BoolResponse(
            value=result.get("has_no_changes", False),
        )

    async def close_exploratory(self, task_id: str) -> BoolResponse:
        """Close exploratory task."""
        result = await self._request("tasks", "close_exploratory", {"task_id": task_id})
        return BoolResponse(
            value=result.get("success", False),
            message=result.get("message", ""),
        )

    async def merge_task_direct(self, task_id: str) -> BoolResponse:
        """Merge task directly."""
        result = await self._request("tasks", "merge_task_direct", {"task_id": task_id})
        return BoolResponse(
            value=result.get("success", False),
            message=result.get("message", ""),
        )

    async def apply_rejection_feedback(
        self,
        task_id: str,
        feedback: str | None = None,
        action: str = "reopen",
    ) -> TaskResponse:
        """Apply rejection feedback to task."""
        params: dict[str, Any] = {"task_id": task_id, "action": action}
        if feedback is not None:
            params["feedback"] = feedback
        result = await self._request("tasks", "apply_rejection_feedback", params)
        return TaskResponse(
            found=result.get("found", False),
            task=result.get("task"),
        )

    async def resolve_task_base_branch(self, task_id: str) -> TaskBaseBranchResponse:
        """Resolve task base branch."""
        result = await self._query("tasks", "resolve_task_base_branch", {"task_id": task_id})
        return TaskBaseBranchResponse(
            branch=result.get("branch", "main"),
        )

    async def prepare_auto_output(self, task_id: str) -> AutoOutputResponse:
        """Prepare auto output for task."""
        result = await self._query("tasks", "prepare_auto_output", {"task_id": task_id})
        return AutoOutputResponse(
            can_open_output=result.get("can_open_output", False),
            execution_id=result.get("execution_id"),
            is_running=result.get("is_running", False),
            output_mode=result.get("output_mode", ""),
        )

    async def recover_stale_auto_output(self, task_id: str) -> AutoOutputResponse:
        """Recover stale auto output for task."""
        result = await self._query("tasks", "recover_stale_auto_output", {"task_id": task_id})
        return AutoOutputResponse(
            can_open_output=result.get("can_open_output", False),
            execution_id=result.get("execution_id"),
            is_running=result.get("is_running", False),
            output_mode=result.get("output_mode", ""),
        )

    # -------------------------------------------------------------------------
    # Repo operations
    # -------------------------------------------------------------------------

    async def update_repo_default_branch(
        self,
        repo_id: str,
        branch: str,
        mark_configured: bool = False,
    ) -> RepoUpdateResponse:
        """Update repo default branch."""
        result = await self._request(
            "projects",
            "update_repo_default_branch",
            {"repo_id": repo_id, "branch": branch, "mark_configured": mark_configured},
        )
        return RepoUpdateResponse(
            success=result.get("success", False),
            repo_id=result.get("repo_id", ""),
        )

    # -------------------------------------------------------------------------
    # Plugin UI operations
    # -------------------------------------------------------------------------

    async def plugin_ui_catalog(
        self,
        project_id: str,
        repo_id: str | None = None,
    ) -> PluginUiCatalogResponse:
        """Get plugin UI catalog."""
        params: dict[str, Any] = {"project_id": project_id}
        if repo_id is not None:
            params["repo_id"] = repo_id
        result = await self._query("plugins", "plugin_ui_catalog", params)
        return PluginUiCatalogResponse(
            schema_version=result.get("schema_version", ""),
            actions=result.get("actions", []),
            forms=result.get("forms", []),
            badges=result.get("badges", []),
        )

    async def plugin_ui_invoke(
        self,
        project_id: str,
        plugin_id: str,
        action_id: str,
        repo_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> PluginUiInvokeResponse:
        """Invoke plugin UI action."""
        params: dict[str, Any] = {
            "project_id": project_id,
            "plugin_id": plugin_id,
            "action_id": action_id,
        }
        if repo_id is not None:
            params["repo_id"] = repo_id
        if inputs is not None:
            params["inputs"] = inputs
        result = await self._request("plugins", "plugin_ui_invoke", params)
        return PluginUiInvokeResponse(
            ok=result.get("ok", False),
            code=result.get("code", ""),
            message=result.get("message", ""),
            data=result.get("data"),
        )


__all__ = ["KaganSDK"]
