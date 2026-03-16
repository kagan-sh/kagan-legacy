"""Protocol driver: CoreDriver — translates DSL operations to KaganCore service calls.

This is Layer 3 in the 4-layer test architecture:
    Test Cases → DSL (KaganDriver) → Protocol Driver (CoreDriver) → System Under Test

The CoreDriver is the "how" — it knows which services to call, in what order,
and with what parameters. Tests never touch it directly; they use KaganDriver.

A future McpDriver could translate the same DSL operations into MCP tool calls,
proving that both interfaces behave identically.
"""

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from kagan.core import (
    KaganCore,
    NotFoundError,
    Priority,
    TaskStatus,
    WorkMode,
)
from kagan.core.models import Repository, Worktree

# ---------------------------------------------------------------------------
# Result types (protocol-independent DTOs for test assertions)
# ---------------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class TaskView:
    """Flattened task view for test assertions."""

    id: str
    title: str
    description: str
    status: TaskStatus
    execution_mode: WorkMode
    priority: Priority
    agent_backend: str | None
    base_branch: str | None
    acceptance_criteria: list[str]
    project_id: str
    launcher: str | None = None


@dataclass(frozen=True, slots=True)
class ProjectView:
    """Flattened project view for test assertions."""

    id: str
    name: str
    description: str


@dataclass(frozen=True, slots=True)
class RepoView:
    """Flattened repo view for test assertions."""

    id: str
    path: str
    default_branch: str | None


# ---------------------------------------------------------------------------
# CoreDriver
# ---------------------------------------------------------------------------


class CoreDriver:
    """Drives the system through direct service calls on KaganCore.

    Every method is async, returns protocol-independent DTOs, and
    raises domain errors (KaganError subclasses) on failure.
    """

    def __init__(self, ctx: KaganCore) -> None:
        self._ctx = ctx

    # -- Projects -----------------------------------------------------------

    async def create_project(
        self,
        name: str,
        repo_paths: list[str | Path] | None = None,
        description: str | None = None,
    ) -> str:
        """Create a project and return its ID."""
        str_paths = [str(p) for p in repo_paths] if repo_paths else None
        project = await self._ctx.projects.create(name, repo_paths=str_paths)
        await self._ctx.projects.set_active(project.id)
        return project.id

    async def add_repo(self, repo_path: str | Path) -> str:
        """Add a repo to the active project. Returns repo_id."""
        pid = self._ctx.active_project_id
        if pid is None:
            raise ValueError("No active project; create one first")
        repo = await self._ctx.projects.add_repo(pid, str(repo_path))
        return repo.id

    async def open_project(self, project_id: str) -> None:
        """Switch to an existing project."""
        await self._ctx.projects.set_active(project_id)

    async def list_projects(self) -> list[ProjectView]:
        """List all projects."""
        projects = await self._ctx.projects.list()
        return [
            ProjectView(
                id=p.id,
                name=p.name,
                description=p.description or "",
            )
            for p in projects
        ]

    async def get_project(self, project_id: str) -> ProjectView | None:
        """Get a project by ID."""
        try:
            project = await self._ctx.projects.get(project_id)
        except NotFoundError:
            return None
        return ProjectView(
            id=project.id,
            name=project.name,
            description=project.description or "",
        )

    async def get_project_repos(self, project_id: str) -> list[RepoView]:
        """Get repos linked to a project."""
        repos = await self._ctx.projects.repos(project_id)
        return [
            RepoView(
                id=r.id,
                path=r.path,
                default_branch=r.default_branch,
            )
            for r in repos
        ]

    async def find_project_by_repo_path(self, repo_path: str | Path) -> ProjectView | None:
        """Find project containing the given repo path."""
        project = await self._ctx.projects.find_by_repo(str(repo_path))
        if project is None:
            return None
        return ProjectView(
            id=project.id,
            name=project.name,
            description=project.description or "",
        )

    async def delete_project(self, project_id: str) -> None:
        """Delete a project and all its associated data."""
        await self._ctx.projects.delete(project_id)

    # -- Tasks --------------------------------------------------------------

    async def create_task(
        self,
        title: str,
        description: str = "",
        *,
        project_id: str | None = None,
        task_type: WorkMode = WorkMode.AUTO,
        priority: Priority = Priority.MEDIUM,
        acceptance_criteria: list[str] | None = None,
        base_branch: str | None = None,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> TaskView:
        """Create a task and return its view."""
        # If a specific project_id is requested, temporarily switch active project
        original_pid = self._ctx.active_project_id
        if project_id is not None and project_id != original_pid:
            await self._ctx.projects.set_active(project_id)

        task = await self._ctx.tasks.create(
            title,
            description=description,
            priority=priority,
            execution_mode=task_type,
            base_branch=base_branch,
            acceptance_criteria=acceptance_criteria,
            agent_backend=agent_backend,
            launcher=launcher,
        )

        # Restore original active project if we switched
        if project_id is not None and project_id != original_pid and original_pid is not None:
            await self._ctx.projects.set_active(original_pid)

        return self._to_task_view(task)

    async def get_task(self, task_id: str) -> TaskView:
        """Get a task by ID."""
        task = await self._ctx.tasks.get(task_id)
        return self._to_task_view(task)

    async def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
        project_id: str | None = None,
    ) -> list[TaskView]:
        """List tasks with optional filters."""
        if project_id is not None and project_id != self._ctx.active_project_id:
            original_pid = self._ctx.active_project_id
            await self._ctx.projects.set_active(project_id)
            tasks = await self._ctx.tasks.list(status=status)
            if original_pid is not None:
                await self._ctx.projects.set_active(original_pid)
        else:
            tasks = await self._ctx.tasks.list(status=status)
        return [self._to_task_view(t) for t in tasks]

    async def update_task(
        self,
        task_id: str,
        *,
        title: str | None = None,
        description: str | None = None,
        priority: Priority | None = None,
        task_type: WorkMode | None = None,
        acceptance_criteria: list[str] | None = None,
        base_branch: str | None = None,
        agent_backend: str | None = None,
        launcher: str | None = None,
        status: TaskStatus | None = None,
    ) -> TaskView:
        """Update task fields."""
        task = await self._ctx.tasks.update(
            task_id,
            title=title,
            description=description,
            priority=priority,
            execution_mode=task_type,
            acceptance_criteria=acceptance_criteria,
            base_branch=base_branch,
            agent_backend=agent_backend,
            launcher=launcher,
        )
        if status is not None:
            task = await self._ctx.tasks.set_status(task_id, status)
        return self._to_task_view(task)

    async def move_task(
        self, task_id: str, to_status: TaskStatus, *, allow_done: bool = False
    ) -> TaskView:
        """Move a task to a new status column."""
        if allow_done and to_status == TaskStatus.DONE:
            # DONE transitions go through review.merge()
            task = await self._ctx.reviews.merge(task_id)
        else:
            task = await self._ctx.tasks.set_status(task_id, to_status)
        return self._to_task_view(task)

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        try:
            await self._ctx.tasks.delete(task_id)
            return True
        except NotFoundError:
            return False

    async def search_tasks(self, query: str) -> list[TaskView]:
        """Search tasks by text query."""
        tasks = await self._ctx.tasks.search(query)
        return [self._to_task_view(t) for t in tasks]

    async def task_get_context(self, task_id: str) -> dict[str, Any]:
        """Get task context (task, workspace, linked tasks)."""
        return await self._ctx.tasks.build_context(task_id)

    async def task_wait(
        self,
        task_id: str,
        *,
        timeout_seconds: float = 10.0,
        wait_for_status: list[str] | None = None,
        from_updated_at: str | None = None,
    ) -> dict[str, Any]:
        """Wait for task status change or timeout."""
        target_statuses = (
            {TaskStatus(value) for value in wait_for_status} if wait_for_status else None
        )
        task, timed_out = await self._ctx.tasks.wait_for_completion(
            task_id,
            timeout=timeout_seconds,
            wait_for_status=target_statuses,
        )
        return {"task": task, "status": task.status, "timed_out": timed_out}

    # -- Scratchpad ---------------------------------------------------------

    async def get_scratchpad(self, task_id: str) -> str:
        notes = await self._ctx.tasks.list_notes(task_id)
        return "\n\n".join(note.content for note in notes)

    async def list_notes(self, task_id: str) -> list[str]:
        notes = await self._ctx.tasks.list_notes(task_id)
        return [note.content for note in notes]

    async def update_scratchpad(self, task_id: str, content: str) -> None:
        await self._ctx.tasks.add_note(task_id, content)

    # -- Automation (agent lifecycle) ---------------------------------------

    async def start_auto(self, task_id: str) -> bool:
        """Spawn an AUTO agent for a task. Returns True if started."""
        task = await self._ctx.tasks.get(task_id)
        backend = task.agent_backend or "fake"
        try:
            await self._ctx.tasks.run(task_id, agent_backend=backend)
            return True
        except Exception:
            return False

    async def stop_auto(self, task_id: str) -> bool:
        """Stop a running AUTO agent."""
        try:
            await self._ctx.tasks.cancel(task_id)
            return True
        except Exception:
            return False

    async def wait_for_auto_complete(self, task_id: str, *, timeout: float = 15.0) -> TaskView:
        """Wait for an AUTO task to finish its agent run."""
        task, _ = await self._ctx.tasks.wait_for_completion(
            task_id,
            timeout=timeout,
            wait_for_status={TaskStatus.REVIEW, TaskStatus.BACKLOG},
        )
        return self._to_task_view(task)

    # -- Review -------------------------------------------------------------

    async def review_approve(
        self,
        task_id: str,
        *,
        feedback: str = "Approved",
    ) -> TaskView:
        """Approve a task in REVIEW status, moving it to DONE."""
        await self._ctx.reviews.approve(task_id)
        task = await self._ctx.reviews.merge(task_id)
        return self._to_task_view(task)

    async def review_reject(
        self,
        task_id: str,
        *,
        feedback: str = "Needs changes",
        to_status: TaskStatus = TaskStatus.IN_PROGRESS,
    ) -> TaskView:
        """Reject a task in REVIEW, sending it back for rework."""
        task = await self._ctx.reviews.reject(task_id, feedback=feedback)
        return self._to_task_view(task)

    async def close_exploratory(self, task_id: str) -> dict[str, Any]:
        """Close exploratory task with no changes, moving to DONE."""
        task = await self._ctx.reviews.merge(task_id)
        return {"task": task, "status": task.status}

    # -- Workspaces ---------------------------------------------------------

    async def provision_workspace(
        self,
        task_id: str,
        *,
        branch_name: str | None = None,
    ) -> str:
        """Provision a workspace for a task using active project repos."""
        ws = await self._ctx.worktrees.create(task_id)
        return ws.id

    async def get_workspace_path(self, task_id: str) -> Path | None:
        """Get the workspace path for a task."""
        ws = await self._ctx.worktrees.get(task_id)
        if ws is None:
            return None
        return Path(ws.worktree_path)

    async def list_workspaces(self, *, task_id: str | None = None) -> list[dict[str, Any]]:
        """List workspaces, optionally filtered by task."""

        def _list() -> list[dict[str, Any]]:
            with Session(self._ctx._engine) as session:
                stmt = select(Worktree)
                if task_id is not None:
                    stmt = stmt.where(Worktree.task_id == task_id)
                rows = session.exec(stmt).all()
                return [
                    {
                        "id": ws.id,
                        "task_id": ws.task_id,
                        "worktree_path": ws.worktree_path,
                        "branch_name": ws.branch_name,
                    }
                    for ws in rows
                ]

        return await asyncio.to_thread(_list)

    async def get_workspace_diff(
        self,
        task_id: str,
        *,
        base_branch: str | None = None,
    ) -> dict[str, Any]:
        """Get diff for a task's workspace."""
        diff_text = await self._ctx.worktrees.diff(task_id)
        return {"diff": diff_text}

    async def task_get_logs(
        self,
        task_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, Any]:
        """Get paginated execution logs for a task."""
        events = await self._ctx.tasks.events.list(task_id, offset=offset, limit=limit or 20)
        return {"items": [{"event_type": e.event_type, "payload": e.payload} for e in events]}

    async def set_repo_default_branch(
        self, repo_id: str, branch: str, *, mark_configured: bool = False
    ) -> dict[str, Any]:
        """Update a repo's default branch."""

        def _update() -> dict[str, Any]:
            with Session(self._ctx._engine) as session:
                repo = session.get(Repository, repo_id)
                if repo is None:
                    raise NotFoundError("Repo", repo_id)
                repo.default_branch = branch
                session.add(repo)
                session.commit()
                session.refresh(repo)
                return {"id": repo.id, "default_branch": repo.default_branch}

        return await asyncio.to_thread(_update)

    async def merge_task(self, task_id: str) -> dict[str, Any]:
        """Merge task branch and move to DONE."""
        task = await self._ctx.reviews.merge(task_id)
        return {"task": task, "status": task.status}

    # -- Pair Sessions ------------------------------------------------------

    async def pair_task(
        self,
        task_id: str,
        *,
        agent_backend: str = "claude-code",
        launcher: str = "tmux",
    ) -> Any:
        """Start a PAIR session for a task. Returns session or raises."""
        return await self._ctx.tasks.pair(task_id, agent_backend=agent_backend, launcher=launcher)

    async def cancel_task(self, task_id: str) -> None:
        """Cancel a task's active session."""
        await self._ctx.tasks.cancel(task_id)

    async def end_pairing(self, task_id: str) -> dict[str, Any]:
        """End a PAIR session for a task. Returns result with status."""
        result = await self._ctx.tasks.end_pairing(task_id)
        return {
            "ready_for_review": result.get("ready_for_review", False),
            "status": result.get("status", ""),
        }

    # -- Settings -----------------------------------------------------------

    async def get_config(self) -> Any:
        """Get the current settings dict."""
        return await self._ctx.settings.get()

    async def settings_get(self) -> dict[str, Any]:
        """Get current settings as API response."""
        return await self._ctx.settings.get()

    async def settings_update(self, fields: dict[str, Any]) -> dict[str, Any]:
        """Update settings. Returns API response."""
        str_fields = {k: str(v) for k, v in fields.items()}
        await self._ctx.settings.set(str_fields)
        return await self._ctx.settings.get()

    async def update_setting(self, section: str, key: str, value: Any) -> None:
        """Update a configuration setting."""
        await self._ctx.settings.set({f"{section}.{key}": str(value)})

    # -- Audit --------------------------------------------------------------

    async def audit_list(
        self,
        *,
        capability: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, Any]:
        """List recent audit events."""
        entries = await self._ctx.audit_log.list(limit=limit)
        return {"items": [{"id": e.id, "action": e.action} for e in entries]}

    # -- Internal -----------------------------------------------------------

    @staticmethod
    def _to_task_view(task: Any) -> TaskView:
        """Convert a DB Task model to a TaskView DTO."""
        return TaskView(
            id=task.id,
            title=task.title,
            description=task.description or "",
            status=task.status if isinstance(task.status, TaskStatus) else TaskStatus(task.status),
            execution_mode=task.execution_mode
            if isinstance(task.execution_mode, WorkMode)
            else WorkMode(task.execution_mode),
            priority=task.priority
            if isinstance(task.priority, Priority)
            else Priority(task.priority),
            agent_backend=task.agent_backend,
            launcher=getattr(task, "launcher", None),
            base_branch=task.base_branch,
            acceptance_criteria=task.acceptance_criteria or [],
            project_id=task.project_id,
        )


__all__ = [
    "CoreDriver",
    "ProjectView",
    "RepoView",
    "TaskView",
]
