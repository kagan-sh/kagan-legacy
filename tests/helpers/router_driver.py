"""Protocol driver for acceptance tests using the core command router."""

from typing import Any

from kagan.core.protocol import CommandRequestEnvelope, CommandRouter

from kagan.core import KaganCore, Priority, TaskStatus, WorkMode
from tests.helpers.core_driver import ProjectView, TaskView


class RouterDriver:
    """Drive user-facing behavior through capability/method command dispatch."""

    def __init__(self, ctx: KaganCore, router: CommandRouter) -> None:
        self._ctx = ctx
        self._router = router
        self._request_counter = 0

    async def raw_call(
        self,
        capability: str,
        method: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        """Dispatch a command and return the raw response payload."""
        self._request_counter += 1
        envelope = CommandRequestEnvelope(
            request_id=f"acc-{self._request_counter}",
            session_id="acc:test",
            capability=capability,
            method=method,
            params=params or {},
        )
        result = await self._router.dispatch(envelope, self._ctx)
        if result is None:
            raise AssertionError(f"Command not found: {capability}.{method}")
        return result

    async def _call_ok(
        self,
        capability: str,
        method: str,
        params: dict[str, object] | None = None,
    ) -> dict[str, Any]:
        raw = await self.raw_call(capability, method, params)
        if raw.get("success") is False:
            raise AssertionError(f"{capability}.{method} failed: {raw}")
        return raw

    async def create_project(
        self,
        name: str,
        *,
        repo_paths: list[str] | None = None,
        description: str | None = None,
    ) -> str:
        """Create a project and return its ID."""
        raw = await self._call_ok(
            "projects",
            "create",
            {
                "name": name,
                "repo_paths": repo_paths,
                "description": description,
            },
        )
        project_id = raw.get("id")
        if not isinstance(project_id, str) or not project_id:
            raise AssertionError(f"projects.create returned no project id: {raw}")
        return project_id

    async def open_project(self, project_id: str) -> None:
        """Open a project to make it active for the session."""
        await self._call_ok("projects", "open", {"project_id": project_id})

    async def list_projects(self, *, limit: int = 50) -> list[ProjectView]:
        """List recent projects."""
        raw = await self._call_ok("projects", "list", {"limit": limit})
        items = raw.get("items")
        if not isinstance(items, list):
            return []
        return [self._to_project_view(item) for item in items if isinstance(item, dict)]

    async def add_repo(self, project_id: str, repo_path: str, *, is_primary: bool = False) -> str:
        """Add a repository to a project and return the repo ID."""
        raw = await self._call_ok(
            "projects",
            "add_repo",
            {
                "project_id": project_id,
                "repo_path": repo_path,
                "is_primary": is_primary,
            },
        )
        repo_id = raw.get("id")
        if not isinstance(repo_id, str) or not repo_id:
            raise AssertionError(f"projects.add_repo returned no repo id: {raw}")
        return repo_id

    async def create_task(
        self,
        title: str,
        description: str = "",
        *,
        project_id: str | None = None,
        status: TaskStatus | None = None,
        priority: Priority | None = None,
        task_type: WorkMode | None = None,
        base_branch: str | None = None,
        acceptance_criteria: list[str] | None = None,
        agent_backend: str | None = None,
    ) -> TaskView:
        """Create a task through the command router."""
        raw = await self._call_ok(
            "tasks",
            "create",
            {
                "title": title,
                "description": description,
                "project_id": project_id,
                "status": status.value if status is not None else None,
                "priority": self._priority_to_input(priority),
                "task_type": task_type.value if task_type is not None else None,
                "base_branch": base_branch,
                "acceptance_criteria": acceptance_criteria,
                "agent_backend": agent_backend,
            },
        )
        task_raw = raw.get("task")
        if not isinstance(task_raw, dict):
            raise AssertionError(f"tasks.create returned no task payload: {raw}")
        return self._to_task_view(task_raw)

    async def get_task(self, task_id: str) -> TaskView:
        """Get a task by ID through the command router."""
        raw = await self._call_ok("tasks", "get", {"task_id": task_id})
        if raw.get("found") is not True or not isinstance(raw.get("item"), dict):
            raise AssertionError(f"tasks.get did not return a task: {raw}")
        return self._to_task_view(raw["item"])

    async def list_tasks(self) -> list[TaskView]:
        """List tasks."""
        raw = await self._call_ok("tasks", "list", {})
        items = raw.get("items")
        if not isinstance(items, list):
            return []
        return [self._to_task_view(item) for item in items if isinstance(item, dict)]

    async def search_tasks(self, query: str) -> list[TaskView]:
        """Search tasks by text query."""
        raw = await self._call_ok("tasks", "search", {"query": query})
        items = raw.get("items")
        if not isinstance(items, list):
            return []
        return [self._to_task_view(item) for item in items if isinstance(item, dict)]

    async def move_task(self, task_id: str, status: TaskStatus) -> dict[str, Any]:
        """Move a task to another status and return raw payload for assertions."""
        return await self.raw_call("tasks", "move", {"task_id": task_id, "status": status.value})

    async def update_task(self, task_id: str, **fields: object) -> dict[str, Any]:
        """Update a task and return raw payload for assertions."""
        return await self.raw_call("tasks", "update", {"task_id": task_id, **fields})

    async def append_scratchpad(self, task_id: str, content: str) -> dict[str, Any]:
        """Append to task scratchpad."""
        return await self.raw_call("tasks", "add_note", {"task_id": task_id, "note": content})

    async def get_task_context(self, task_id: str) -> dict[str, Any]:
        return await self._call_ok("tasks", "context", {"task_id": task_id})

    async def request_review(self, task_id: str, summary: str = "") -> dict[str, Any]:
        """Move a task to REVIEW via review request command."""
        return await self.raw_call("review", "request", {"task_id": task_id, "summary": summary})

    async def approve_review(self, task_id: str) -> dict[str, Any]:
        """Approve review metadata for a task in REVIEW."""
        return await self.raw_call("review", "approve", {"task_id": task_id})

    async def reject_review(
        self,
        task_id: str,
        *,
        feedback: str,
        action: str = "reopen",
    ) -> dict[str, Any]:
        """Reject a review and move task back for rework."""
        return await self.raw_call(
            "review",
            "reject",
            {"task_id": task_id, "feedback": feedback, "action": action},
        )

    @staticmethod
    def _priority_to_input(priority: Priority | None) -> str | None:
        if priority is None:
            return None
        return {
            Priority.LOW: "LOW",
            Priority.MEDIUM: "MEDIUM",
            Priority.HIGH: "HIGH",
        }[priority]

    @staticmethod
    def _to_project_view(raw: dict[str, Any]) -> ProjectView:
        return ProjectView(
            id=str(raw.get("id", "")),
            name=str(raw.get("name", "")),
            description=str(raw.get("description") or ""),
        )

    @staticmethod
    def _to_task_view(raw: dict[str, Any]) -> TaskView:
        priority_raw = raw.get("priority")
        if isinstance(priority_raw, int):
            priority = Priority(priority_raw)
        elif isinstance(priority_raw, str):
            normalized = priority_raw.strip().upper()
            if normalized == "MED":
                normalized = "MEDIUM"
            priority = Priority[normalized]
        else:
            priority = Priority.MEDIUM

        return TaskView(
            id=str(raw.get("id", "")),
            title=str(raw.get("title", "")),
            description=str(raw.get("description") or ""),
            status=TaskStatus(str(raw.get("status", TaskStatus.BACKLOG.value))),
            task_type=WorkMode(str(raw.get("task_type", WorkMode.AUTO.value))),
            priority=priority,
            agent_backend=(
                str(raw.get("agent_backend")) if isinstance(raw.get("agent_backend"), str) else None
            ),
            base_branch=str(raw.get("base_branch"))
            if isinstance(raw.get("base_branch"), str)
            else None,
            acceptance_criteria=list(raw.get("acceptance_criteria") or []),
            project_id=str(raw.get("project_id", "")),
        )


__all__ = ["RouterDriver"]
