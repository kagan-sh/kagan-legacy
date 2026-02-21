"""Core domain fixtures: database repositories, event bus, and task services."""

from __future__ import annotations

import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from kagan.core.adapters.db.repositories import RepoRepository, TaskRepository
    from kagan.core.adapters.db.schema import Repo
    from kagan.core.bootstrap import InMemoryEventBus
    from kagan.core.services.tasks import TaskServiceImpl


@dataclass(slots=True)
class RepoWithProjectFixture:
    """Shared fixture payload for a task repository linked to a git repo/project."""

    task_repo: TaskRepository
    repo_repo: RepoRepository
    project_id: str
    repo_path: Path
    repo: Repo


@pytest.fixture
async def state_manager():
    """Create a temporary task repository for testing."""
    from kagan.core.adapters.db.repositories import TaskRepository

    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        manager = TaskRepository(db_path)
        await manager.initialize()

        await manager.ensure_test_project("Test Project")
        yield manager
        await manager.close()


@pytest.fixture
def event_bus() -> InMemoryEventBus:
    """Create an in-memory event bus for service tests."""
    from kagan.core.bootstrap import InMemoryEventBus

    return InMemoryEventBus()


@pytest.fixture
def task_service(state_manager: TaskRepository, event_bus: InMemoryEventBus) -> TaskServiceImpl:
    """Create a TaskServiceImpl backed by the test repository."""
    from kagan.core.services.tasks import TaskServiceImpl

    return TaskServiceImpl(state_manager, event_bus)


@pytest.fixture
def task_factory(state_manager: TaskRepository):
    """Factory for creating DB Task objects with default project/repo IDs."""
    from kagan.core.adapters.db.schema import Task
    from kagan.core.domain.enums import TaskPriority, TaskStatus, TaskType

    def _factory(
        *,
        title: str,
        description: str = "",
        priority: TaskPriority = TaskPriority.MEDIUM,
        status: TaskStatus = TaskStatus.BACKLOG,
        task_type: TaskType = TaskType.PAIR,
        acceptance_criteria: list[str] | None = None,
        agent_backend: str | None = None,
    ) -> Task:
        project_id = state_manager.default_project_id
        if project_id is None:
            raise RuntimeError("TaskRepository defaults not initialized")
        return Task.create(
            title=title,
            description=description,
            priority=priority,
            task_type=task_type,
            status=status,
            agent_backend=agent_backend,
            acceptance_criteria=acceptance_criteria,
            project_id=project_id,
        )

    return _factory


@pytest.fixture
async def git_repo(tmp_path: Path) -> Path:
    """Create an initialized git repository for testing."""
    from tests.helpers.git import init_git_repo_with_commit

    return await init_git_repo_with_commit(tmp_path)


@pytest.fixture
async def repo_with_project(
    tmp_path: Path, git_repo: Path
) -> AsyncIterator[RepoWithProjectFixture]:
    """Create a TaskRepository with a project and linked git repo."""
    from kagan.core.adapters.db.repositories import RepoRepository, TaskRepository

    repo_path = git_repo
    db_path = tmp_path / "test.db"
    task_repo = TaskRepository(db_path, project_root=repo_path)
    await task_repo.initialize()
    project_id = await task_repo.ensure_test_project("Test Project")

    assert task_repo._session_factory is not None
    repo_repo = RepoRepository(task_repo._session_factory)
    repo, _ = await repo_repo.get_or_create(repo_path, default_branch="main")
    if repo.id:
        await repo_repo.update_default_branch(repo.id, "main", mark_configured=True)
        await repo_repo.add_to_project(project_id, repo.id, is_primary=True)

    yield RepoWithProjectFixture(
        task_repo=task_repo,
        repo_repo=repo_repo,
        project_id=project_id,
        repo_path=repo_path,
        repo=repo,
    )
    await task_repo.close()
