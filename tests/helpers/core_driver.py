"""Protocol driver: CoreDriver — translates DSL operations to KaganCore service calls.

This is Layer 3 in the 4-layer test architecture:
    Test Cases → DSL (KaganDriver) → Protocol Driver (CoreDriver) → System Under Test

The CoreDriver is the "how" — it knows which services to call, in what order,
and with what parameters. Tests never touch it directly; they use KaganDriver.

A future McpDriver could translate the same DSL operations into MCP tool calls,
proving that both interfaces behave identically.
"""

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from sqlmodel import Session, select

from kagan.core import (
    AgentRole,
    KaganCore,
    NotFoundError,
    Priority,
    SessionStatus,
    TaskStatus,
    db_async,
)
from kagan.core import (
    Session as AgentSession,
)
from kagan.core.models import Repository, Worktree


def _safe_criteria_texts(task: Any) -> list[str]:
    """Extract criteria texts from a Task ORM object, handling detached instances."""
    from sqlalchemy.orm.exc import DetachedInstanceError

    try:
        criteria = getattr(task, "criteria", None) or []
        return [c.text for c in sorted(criteria, key=lambda c: c.ordinal)]
    except DetachedInstanceError:
        return []


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
    priority: Priority
    agent_backend: str | None
    base_branch: str | None
    acceptance_criteria: list[str]
    project_id: str
    launcher: str | None = None
    repo_id: str | None = None


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


@dataclass(frozen=True, slots=True)
class ChatTurnOutcome:
    """Result of a single chat turn driven through the engine."""

    user_content: str
    assistant_content: str
    terminated: bool
    events: list[Any] = field(default_factory=list)


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
        # Persist so TUI instances using the same DB auto-restore this project.
        await self._ctx.settings.set({"ui.last_project_id": project.id})
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
        priority: Priority = Priority.MEDIUM,
        acceptance_criteria: list[str] | None = None,
        base_branch: str | None = None,
        agent_backend: str | None = None,
        launcher: str | None = None,
        repo_id: str | None = None,
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
            base_branch=base_branch,
            acceptance_criteria=acceptance_criteria,
            agent_backend=agent_backend,
            launcher=launcher,
            repo_id=repo_id,
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

    async def run_task(
        self,
        task_id: str,
        *,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> Any | None:
        task = await self._ctx.tasks.get(task_id)
        backend = agent_backend or task.agent_backend or "fake"
        kwargs: dict[str, Any] = {"agent_backend": backend}
        if launcher is not None or task.launcher is not None:
            kwargs["launcher"] = launcher or task.launcher or "tmux"
            return await self._ctx.tasks.run(task_id, **kwargs)
        try:
            return await self._ctx.tasks.run(task_id, **kwargs)
        except Exception:
            return None

    async def create_agent_session(
        self,
        task_id: str,
        *,
        session_id: str | None = None,
        status: SessionStatus = SessionStatus.RUNNING,
        agent_role: AgentRole | str | None = AgentRole.WORKER,
        agent_backend: str = "test",
    ) -> str:
        """Create an agent session row for tests that need a session-bound event stream."""
        row = AgentSession(
            id=session_id,
            task_id=task_id,
            agent_backend=agent_backend,
            status=status,
            agent_role=agent_role.value if isinstance(agent_role, AgentRole) else agent_role,
        )
        created_id = row.id

        def _create(s: Session) -> AgentSession:
            s.add(row)
            return row

        await db_async(self._ctx.engine, _create, commit=True)
        return created_id

    async def cancel_task(self, task_id: str) -> bool:
        try:
            await self._ctx.tasks.cancel(task_id)
            return True
        except Exception:
            return False

    async def wait_for_detached_complete(self, task_id: str, *, timeout: float = 15.0) -> TaskView:
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

    async def detach_task(self, task_id: str) -> dict[str, Any]:
        result = await self._ctx.tasks.detach(task_id)
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

    # -- Chat sessions ------------------------------------------------------

    async def chat_create_session(
        self,
        *,
        source: str = "test",
        label: str | None = None,
        agent_backend: str | None = None,
        project_id: str | None = None,
    ) -> dict[str, Any]:
        from kagan.cli.chat._session_picker import chat_session_to_view

        row = await self._ctx.chat_sessions.create(
            source=source,
            label=label,
            agent_backend=agent_backend,
            project_id=project_id,
        )
        return chat_session_to_view(row, []).model_dump()

    async def chat_get_session(self, session_id: str) -> dict[str, Any] | None:
        from kagan.cli.chat._session_picker import chat_session_to_view

        pair = await self._ctx.chat_sessions.get_with_history(session_id)
        if pair is None:
            return None
        return chat_session_to_view(*pair).model_dump()

    async def chat_list_sessions(
        self,
        *,
        source: str | None = None,
        project_id: str | None = None,
    ) -> list[dict[str, Any]]:
        from kagan.cli.chat._session_picker import chat_session_to_view

        pairs = await self._ctx.chat_sessions.list_with_history(
            source=source, project_id=project_id
        )
        return [chat_session_to_view(row, msgs).model_dump() for row, msgs in pairs]

    async def chat_delete_session(self, session_id: str) -> bool:
        return await self._ctx.chat_sessions.delete(session_id)

    async def chat_append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        *,
        terminated: bool = False,
    ) -> Any:
        return await self._ctx.chat_sessions.append_message(
            session_id,
            role,
            content,
            terminated=terminated,
        )

    async def chat_send(
        self,
        session_id: str,
        text: str,
        *,
        agent_chunks: list[str] | None = None,
        cancel_after_chars: int | None = None,
    ) -> "ChatTurnOutcome":
        """Drive a full chat turn through ChatEngine with a ScriptedFactory.

        ``agent_chunks`` is forwarded to ``ScriptedFactory``; defaults to
        ``["ok"]`` when omitted.  If ``cancel_after_chars`` is set, the engine
        is cancelled once the in-flight partial exceeds that many characters.
        """
        from acp.schema import TextContentBlock

        from tests.helpers.chat_engine import ScriptedFactory, SuspendingFactory

        chunks = agent_chunks if agent_chunks is not None else ["ok"]
        engine = self._ctx.chat

        if cancel_after_chars is not None:
            started: asyncio.Event = asyncio.Event()
            factory: Any = SuspendingFactory(
                first_chunk=chunks[0] if chunks else "x", started=started
            )
        else:
            factory = ScriptedFactory(chunks=chunks)

        user_msg = await engine.push_user(session_id, text)

        events: list[Any] = []

        async def _consume() -> None:
            async for ev in engine.stream_assistant(
                session_id,
                prompt_blocks=[TextContentBlock(type="text", text=text)],
                acp_factory=factory,
            ):
                events.append(ev)

        if cancel_after_chars is not None:
            consumer = asyncio.create_task(_consume())
            await asyncio.wait_for(started.wait(), timeout=5.0)
            # Wait until enough chars accumulated.
            for _ in range(200):
                status = engine.turn_status(session_id)
                if status.partial_chars >= cancel_after_chars:
                    break
                await asyncio.sleep(0)
            await engine.cancel(session_id)
            await asyncio.wait_for(consumer, timeout=5.0)
        else:
            await asyncio.wait_for(_consume(), timeout=10.0)

        from kagan.core.events import AssistantMessagePersisted

        persisted = next(
            (e for e in reversed(events) if isinstance(e, AssistantMessagePersisted)), None
        )
        assistant_content = persisted.content if persisted else ""
        terminated = persisted.terminated if persisted else False
        return ChatTurnOutcome(
            user_content=user_msg.content,
            assistant_content=assistant_content,
            terminated=terminated,
            events=events,
        )

    async def chat_history(self, session_id: str) -> list[Any]:
        """Return ChatMessage rows for a session via the engine."""
        return await self._ctx.chat.history(session_id)

    async def chat_event_log(self, session_id: str, outcome: "ChatTurnOutcome") -> list[Any]:
        """Return the events list from a ChatTurnOutcome (for sequence assertions)."""
        return list(outcome.events)

    async def chat_cancel_in_flight(self, session_id: str) -> Any:
        """Cancel any in-flight turn for ``session_id``."""
        return await self._ctx.chat.cancel(session_id)

    async def chat_switch_session(self, new_session_id: str) -> None:
        """Detach engine state for ``new_session_id`` (simulates session switch)."""
        await self._ctx.chat.detach(new_session_id)

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
            priority=task.priority
            if isinstance(task.priority, Priority)
            else Priority(task.priority),
            agent_backend=task.agent_backend,
            launcher=getattr(task, "launcher", None),
            base_branch=task.base_branch,
            acceptance_criteria=_safe_criteria_texts(task),
            project_id=task.project_id,
            repo_id=getattr(task, "repo_id", None),
        )


__all__ = [
    "ChatTurnOutcome",
    "CoreDriver",
    "ProjectView",
    "RepoView",
    "TaskView",
]
