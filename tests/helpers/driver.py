"""DSL layer: KaganDriver — domain-language API for acceptance tests.

This is Layer 2 in the 4-layer test architecture:
    Test Cases → DSL (KaganDriver) → Protocol Driver (CoreDriver) → System Under Test

KaganDriver speaks the language of the problem domain — "create a task",
"run the agent", "approve the review". It delegates all system interaction
to the underlying protocol driver (CoreDriver for now, McpDriver later).

Tests ONLY use KaganDriver. They never touch services or drivers directly.
"""

from pathlib import Path
from typing import Any

from kagan.core import KaganCore, TaskStatus
from kagan.core.enums import Priority
from tests.helpers.core_driver import CoreDriver, ProjectView, RepoView, TaskView
from tests.helpers.fake_agent import FakeAgentFactory


class KaganDriver:
    """Domain-language test driver — the test's single point of contact.

    Usage:
        driver = await KaganDriver.boot(tmp_path)
        await driver.create_project("My Project")
        await driver.add_repo(repo_path)
        task = await driver.create_task("Implement feature X")
        assert task.status == TaskStatus.BACKLOG
        await driver.teardown()
    """

    def __init__(
        self,
        driver: CoreDriver,
        agent_factory: FakeAgentFactory,
        *,
        _ctx: KaganCore | None = None,
    ) -> None:
        self._driver = driver
        self._agents = agent_factory
        self._ctx = _ctx
        self._tmp_path: Path | None = None

    @classmethod
    async def boot(cls, tmp_path: Path) -> "KaganDriver":
        """Create a fresh Kagan board in tmp_path. Caller must call teardown()."""
        db_path = tmp_path / "kagan.db"
        factory = FakeAgentFactory()
        client = KaganCore(db_path=db_path)
        await client.settings.set({"ui.tui_tutorial_seen": "true"})
        core_driver = CoreDriver(client)
        driver = cls(core_driver, factory, _ctx=client)
        driver._tmp_path = tmp_path
        return driver

    async def teardown(self) -> None:
        """Close the app context and release resources."""
        if self._ctx is not None:
            self._ctx.close()
            self._ctx = None

    # ======================================================================
    # Agent response configuration (WHAT the agent will do)
    # ======================================================================

    def agent_will_complete(self) -> None:
        """Configure the next agent run to signal COMPLETE."""
        self._agents.set_next_response("<complete/>")

    def agent_will_block(self, reason: str = "Needs clarification") -> None:
        """Configure the next agent run to signal BLOCKED."""
        self._agents.set_next_response(f'<blocked reason="{reason}"/>')

    def agent_will_continue(self) -> None:
        """Configure the next agent run to signal CONTINUE."""
        self._agents.set_next_response("<continue/>")

    def agent_will_respond(self, response: str) -> None:
        """Configure a custom agent response (for advanced signal testing)."""
        self._agents.set_next_response(response)

    def agent_will_stream(self, chunks: list[str]) -> None:
        """Configure the next agent run to yield chunks in sequence."""
        self._agents.set_next_stream(chunks)

    # ======================================================================
    # Project operations
    # ======================================================================

    async def create_project(
        self,
        name: str = "Test Project",
        repo_path: str | None = None,
        description: str | None = None,
    ) -> str:
        """Create a project, optionally linking a git repo. Returns project_id."""
        repo_paths: list[str | Path] | None = [repo_path] if repo_path else None
        return await self._driver.create_project(
            name, repo_paths=repo_paths, description=description
        )

    async def add_repo(self, repo_path: str | Path) -> str:
        """Add a repo to the active project."""
        return await self._driver.add_repo(repo_path)

    async def open_project(self, project_id: str) -> None:
        """Switch to an existing project."""
        await self._driver.open_project(project_id)

    async def get_project(self, project_id: str) -> ProjectView | None:
        """Get a project by ID."""
        return await self._driver.get_project(project_id)

    async def get_project_repos(self, project_id: str) -> list[RepoView]:
        """Get repos linked to a project."""
        return await self._driver.get_project_repos(project_id)

    async def find_project_by_repo_path(self, repo_path: str | Path) -> ProjectView | None:
        """Find project containing the given repo path."""
        return await self._driver.find_project_by_repo_path(repo_path)

    async def list_projects(self) -> list[ProjectView]:
        """List all projects."""
        return await self._driver.list_projects()

    async def delete_project(self, project_id: str) -> None:
        """Delete a project and all its associated data."""
        await self._driver.delete_project(project_id)

    # ======================================================================
    # Task CRUD
    # ======================================================================

    async def create_task(
        self,
        title: str = "Test Task",
        description: str = "",
        *,
        priority: Priority = Priority.MEDIUM,
        acceptance_criteria: list[str] | None = None,
        base_branch: str | None = None,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> TaskView:
        """Create a task in the current project."""
        return await self._driver.create_task(
            title,
            description,
            priority=priority,
            acceptance_criteria=acceptance_criteria,
            base_branch=base_branch,
            agent_backend=agent_backend,
            launcher=launcher,
        )

    async def get_task(self, task_id: str) -> TaskView:
        """Fetch a task by ID."""
        return await self._driver.get_task(task_id)

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
        return await self._driver.update_task(
            task_id,
            title=title,
            description=description,
            priority=priority,
            acceptance_criteria=acceptance_criteria,
            base_branch=base_branch,
            agent_backend=agent_backend,
            launcher=launcher,
            status=status,
        )

    async def delete_task(self, task_id: str) -> bool:
        """Delete a task."""
        return await self._driver.delete_task(task_id)

    async def list_tasks(
        self,
        *,
        status: TaskStatus | None = None,
    ) -> list[TaskView]:
        """List tasks, optionally filtered by status."""
        return await self._driver.list_tasks(status=status)

    async def search_tasks(self, query: str) -> list[TaskView]:
        """Search tasks by text."""
        return await self._driver.search_tasks(query)

    async def task_get_context(self, task_id: str) -> dict[str, object]:
        """Get task context (task, workspace, linked tasks)."""
        return await self._driver.task_get_context(task_id)

    async def task_wait(
        self,
        task_id: str,
        *,
        timeout_seconds: float = 10.0,
        wait_for_status: list[str] | None = None,
    ) -> dict[str, object]:
        """Wait for task status change or timeout."""
        return await self._driver.task_wait(
            task_id,
            timeout_seconds=timeout_seconds,
            wait_for_status=wait_for_status,
        )

    async def move_task(self, task_id: str, to_status: TaskStatus) -> TaskView:
        """Move a task to a new status column."""
        return await self._driver.move_task(task_id, to_status)

    # ======================================================================
    # Scratchpad
    # ======================================================================

    async def get_scratchpad(self, task_id: str) -> str:
        """Read the task's scratchpad."""
        return await self._driver.get_scratchpad(task_id)

    async def list_notes(self, task_id: str) -> list[str]:
        return await self._driver.list_notes(task_id)

    async def annotate(self, task_id: str, note: str) -> None:
        """Append a note to the task's scratchpad."""
        await self._driver.update_scratchpad(task_id, note)

    # ======================================================================
    # Automation lifecycle (composite operations)
    # ======================================================================

    async def run_task(
        self,
        task_id: str,
        *,
        agent_backend: str | None = None,
        launcher: str | None = None,
    ) -> Any | None:
        return await self._driver.run_task(
            task_id,
            agent_backend=agent_backend,
            launcher=launcher,
        )

    async def cancel_task(self, task_id: str) -> bool:
        return await self._driver.cancel_task(task_id)

    async def run_detached_to_completion(
        self,
        task_id: str,
        *,
        timeout: float = 10.0,
    ) -> TaskView:
        session = await self._driver.run_task(task_id)
        if session is None:
            return await self._driver.get_task(task_id)
        return await self._driver.wait_for_detached_complete(task_id, timeout=timeout)

    # ======================================================================
    # Review
    # ======================================================================

    async def approve(
        self,
        task_id: str,
        feedback: str = "Approved",
    ) -> TaskView:
        """Approve a task in REVIEW status → DONE."""
        return await self._driver.review_approve(task_id, feedback=feedback)

    async def reject(
        self,
        task_id: str,
        feedback: str = "Needs changes",
        *,
        to_status: TaskStatus = TaskStatus.IN_PROGRESS,
    ) -> TaskView:
        """Reject a task in REVIEW → back to IN_PROGRESS (or BACKLOG)."""
        return await self._driver.review_reject(task_id, feedback=feedback, to_status=to_status)

    async def close_exploratory(self, task_id: str) -> dict[str, object]:
        """Close exploratory task with no changes, moving to DONE."""
        return await self._driver.close_exploratory(task_id)

    # ======================================================================
    # Settings
    # ======================================================================

    async def settings_get(self) -> dict[str, object]:
        """Get current settings as structured response."""
        return await self._driver.settings_get()

    async def settings_update(self, fields: dict[str, object]) -> dict[str, object]:
        """Update settings. Returns API response."""
        return await self._driver.settings_update(fields)

    async def set_setting(self, section: str, key: str, value: object) -> None:
        """Change a configuration setting in-memory."""
        await self._driver.update_setting(section, key, value)

    async def get_config(self) -> object:
        """Get the current config."""
        return await self._driver.get_config()

    # ======================================================================
    # Audit
    # ======================================================================

    async def audit_list(
        self,
        *,
        capability: str | None = None,
        limit: int = 20,
        cursor: str | None = None,
    ) -> dict[str, object]:
        """List recent audit events."""
        return await self._driver.audit_list(
            capability=capability,
            limit=limit,
            cursor=cursor,
        )

    # ======================================================================
    # Workspace operations
    # ======================================================================

    async def provision_workspace(
        self,
        task_id: str,
        *,
        branch_name: str | None = None,
    ) -> str:
        """Provision a workspace for a task."""
        return await self._driver.provision_workspace(task_id, branch_name=branch_name)

    async def get_workspace_path(self, task_id: str) -> str | None:
        """Get the workspace path for a task."""
        path = await self._driver.get_workspace_path(task_id)
        return str(path) if path else None

    async def list_workspaces(self, *, task_id: str | None = None) -> list[dict[str, object]]:
        """List workspaces, optionally filtered by task."""
        return await self._driver.list_workspaces(task_id=task_id)

    async def get_workspace_diff(
        self,
        task_id: str,
        *,
        base_branch: str | None = None,
    ) -> dict[str, object]:
        """Get diff for a task's workspace."""
        return await self._driver.get_workspace_diff(task_id, base_branch=base_branch)

    async def task_get_logs(
        self,
        task_id: str,
        *,
        limit: int | None = None,
        offset: int = 0,
    ) -> dict[str, object]:
        """Get paginated execution logs for a task."""
        return await self._driver.task_get_logs(task_id, limit=limit, offset=offset)

    async def set_repo_default_branch(
        self, repo_id: str, branch: str, *, mark_configured: bool = False
    ) -> dict[str, object]:
        """Update a repo's default branch."""
        return await self._driver.set_repo_default_branch(
            repo_id=repo_id, branch=branch, mark_configured=mark_configured
        )

    async def merge_task(self, task_id: str) -> dict[str, object]:
        """Merge task branch and move to DONE."""
        return await self._driver.merge_task(task_id)

    async def commit_in_workspace(
        self, task_id: str, relative_path: str, content: str, *, message: str = "feat: add file"
    ) -> bool:
        """Write and commit a file in the task's workspace. Controls git state via DSL."""
        from tests.helpers.helpers import commit_file

        path = await self.get_workspace_path(task_id)
        if not path:
            return False
        return await commit_file(Path(path), relative_path, content, message=message)

    async def detach_task(self, task_id: str) -> dict[str, Any]:
        return await self._driver.detach_task(task_id)

    async def wait_for_status(
        self,
        task_id: str,
        status: TaskStatus,
        *,
        timeout: float = 10.0,
    ) -> TaskView:
        """Wait for a task to reach the given status."""
        import asyncio

        async def _poll_status() -> TaskView:
            """Poll until status matches or timeout."""
            deadline = asyncio.get_event_loop().time() + timeout
            while asyncio.get_event_loop().time() < deadline:
                task = await self.get_task(task_id)
                if task.status == status:
                    return task
                await asyncio.sleep(0)  # Yield control without timing dependency
            return await self.get_task(task_id)

        return await asyncio.wait_for(_poll_status(), timeout=timeout + 1)

    @property
    def tmp_path(self) -> Path:
        """Temporary directory used for this driver (set after boot)."""
        if self._tmp_path is None:
            raise RuntimeError("Driver not booted; tmp_path unavailable")
        return self._tmp_path

    @property
    def agent_factory(self) -> FakeAgentFactory:
        """Access the FakeAgentFactory for assertions."""
        return self._agents

    @property
    def last_agent_prompt(self) -> str | None:
        """The most recent prompt sent to any agent."""
        if self._agents.all_calls:
            return self._agents.all_calls[-1].prompt
        return None

    @property
    def agent_call_count(self) -> int:
        """Total number of agent prompts across all runs."""
        return len(self._agents.all_calls)


__all__ = [
    "KaganDriver",
]
