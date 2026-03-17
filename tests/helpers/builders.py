"""Test data builders — sensible defaults for common test shapes.

These drive the real system through KaganDriver. They are not mocks.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from kagan.core import TaskStatus, WorkMode
from kagan.core.enums import Priority

if TYPE_CHECKING:
    from pathlib import Path

    from tests.helpers.core_driver import TaskView
    from tests.helpers.driver import KaganDriver


async def make_task(
    board: KaganDriver,
    title: str = "Test task",
    *,
    status: TaskStatus = TaskStatus.BACKLOG,
    execution_mode: WorkMode = WorkMode.AUTO,
    description: str = "",
    priority: Priority = Priority.MEDIUM,
    acceptance_criteria: list[str] | None = None,
    base_branch: str | None = None,
    agent_backend: str | None = None,
) -> TaskView:
    """Create a task and optionally advance it to the given status."""
    task = await board.create_task(
        title,
        description=description,
        task_type=execution_mode,
        priority=priority,
        acceptance_criteria=acceptance_criteria,
        base_branch=base_branch,
        agent_backend=agent_backend,
    )
    if status != TaskStatus.BACKLOG:
        task = await board.move_task(task.id, status)
    return task


async def make_task_in_progress(
    board: KaganDriver,
    title: str = "In-progress task",
    **kwargs: object,
) -> TaskView:
    """Create a task, provision its workspace, and move to IN_PROGRESS."""
    task = await make_task(board, title, status=TaskStatus.IN_PROGRESS, **kwargs)  # type: ignore[arg-type]
    await board.provision_workspace(task.id)
    return await board.get_task(task.id)


async def make_project_with_repo(
    board: KaganDriver,
    tmp_path: Path,
    *,
    project_name: str = "Test Project",
    base_branch: str = "main",
) -> tuple[str, Path]:
    """Create a project with a git repo. Returns (project_id, repo_path)."""
    from tests.helpers.helpers import make_git_repo

    repo_path = tmp_path / "repo"
    await make_git_repo(repo_path, base_branch=base_branch)
    project_id = await board.create_project(project_name, repo_path=str(repo_path))
    return project_id, repo_path


__all__ = [
    "make_project_with_repo",
    "make_task",
    "make_task_in_progress",
]
