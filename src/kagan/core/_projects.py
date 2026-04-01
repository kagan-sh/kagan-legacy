import builtins
import contextlib
from collections.abc import Awaitable, Callable
from pathlib import Path
from typing import TYPE_CHECKING, cast

from loguru import logger
from sqlalchemy import Engine
from sqlalchemy.exc import IntegrityError
from sqlmodel import select

from kagan.core import git
from kagan.core._db_helpers import (
    _add_and_refresh,
    _db_async,
    _delete_task_children,
    _setting_branch,
    _setting_enabled,
)
from kagan.core._settings import get_settings
from kagan.core.errors import (
    KaganError,
    MultiRepoUnsupportedError,
    NotFoundError,
    SessionError,
    WorktreeError,
)
from kagan.core.models import Project, Repository, Task

if TYPE_CHECKING:
    from kagan.core.client import KaganCore


# ── Module-level functions (canonical API) ────────────────────────────


async def create_project(
    engine: Engine,
    name: str,
    *,
    repo_paths: list[str] | None = None,
    cancel_session: Callable[[str], Awaitable[None]] | None = None,
    cleanup_worktree: Callable[[str], Awaitable[None]] | None = None,
) -> Project:
    project = Project(name=name)
    project = await _db_async(engine, lambda s: _add_and_refresh(s, project))
    logger.debug("Project created id={}", project.id)
    if repo_paths:
        try:
            for path in repo_paths:
                await add_repo(engine, project.id, path)
        except (SessionError, WorktreeError, OSError):
            with contextlib.suppress(NotFoundError):
                await delete_project(
                    engine,
                    project.id,
                    cancel_session=cancel_session,
                    cleanup_worktree=cleanup_worktree,
                )
            raise
    return project


async def get_project(engine: Engine, project_id: str) -> Project:
    project = await _db_async(engine, lambda s: s.get(Project, project_id))
    if project is None:
        raise NotFoundError("Project", project_id)
    return project


async def list_projects(engine: Engine) -> list[Project]:
    return await _db_async(engine, lambda s: list(s.exec(select(Project)).all()))


async def delete_project(
    engine: Engine,
    project_id: str,
    *,
    cancel_session: Callable[[str], Awaitable[None]] | None = None,
    cleanup_worktree: Callable[[str], Awaitable[None]] | None = None,
    active_project_id: str | None = None,
) -> bool:
    """Delete a project and its associated data.

    Returns True if the active project was cleared (caller should update state).
    """
    await get_project(engine, project_id)

    # Pre-delete cleanup
    # Collect task IDs for this project
    task_ids: list[str] = await _db_async(
        engine,
        lambda s: [t.id for t in s.exec(select(Task).where(Task.project_id == project_id)).all()],
    )

    # Cancel running sessions
    if cancel_session is not None:
        for tid in task_ids:
            try:
                await cancel_session(tid)
            except (KaganError, OSError):
                logger.warning(
                    "Failed to cancel session during project cleanup task_id={}",
                    tid,
                    exc_info=True,
                )

    # Clean up git worktrees
    if cleanup_worktree is not None:
        for tid in task_ids:
            try:
                await cleanup_worktree(tid)
            except (WorktreeError, OSError, RuntimeError):
                logger.warning(
                    "Failed to cleanup worktree during project cleanup task_id={}",
                    tid,
                    exc_info=True,
                )

    # DB transaction: delete remaining rows
    def op(s):
        tasks = list(s.exec(select(Task).where(Task.project_id == project_id)).all())
        for task in tasks:
            _delete_task_children(s, task.id)
            s.delete(task)
        for repo in s.exec(select(Repository).where(Repository.project_id == project_id)).all():
            s.delete(repo)
        project = s.get(Project, project_id)
        if project:
            s.delete(project)

    await _db_async(engine, op, commit=True)

    cleared_active = active_project_id == project_id
    if cleared_active:
        logger.info("Active project cleared after deleting project {}", project_id)
    return cleared_active


async def add_repo(engine: Engine, project_id: str, repo_path: str) -> Repository:
    await get_project(engine, project_id)
    resolved_path = Path(repo_path).expanduser().resolve()
    normalized_path = str(resolved_path)

    existing_repo = await _db_async(
        engine,
        lambda s: s.exec(select(Repository).where(Repository.path == normalized_path)).first(),
    )
    if existing_repo is not None:
        if existing_repo.project_id == project_id:
            return existing_repo
        linked_project = await _db_async(engine, lambda s: s.get(Project, existing_repo.project_id))
        project_label = (
            linked_project.name if linked_project is not None else existing_repo.project_id
        )
        raise SessionError(
            None,
            f"Repository path {normalized_path} is already linked to project {project_label!r}.",
        )

    settings = await get_settings(engine)
    default_base_branch = _setting_branch(settings, "default_base_branch", default="main")
    auto_init_git_repo = _setting_enabled(settings, "auto_init_git_repo", default=True)
    auto_init_git_initial_commit = _setting_enabled(
        settings,
        "auto_init_git_initial_commit",
        default=True,
    )

    repo_exists = resolved_path.exists() and await git.is_git_repo(resolved_path)
    if not repo_exists:
        if not auto_init_git_repo:
            raise SessionError(
                None,
                f"Repo path {resolved_path!s} is not a git repository and auto init is disabled.",
            )
        user_name, user_email = await git.get_git_user_identity(settings)
        await git.init_repo(
            resolved_path,
            initial_branch=default_base_branch,
            create_initial_commit=auto_init_git_initial_commit,
            user_name=user_name,
            user_email=user_email,
        )

    detected_branch = await git.current_branch(resolved_path) or default_base_branch
    name = resolved_path.name
    repo = Repository(
        project_id=project_id,
        name=name,
        path=normalized_path,
        default_branch=detected_branch,
    )
    try:
        return await _db_async(engine, lambda s: _add_and_refresh(s, repo))
    except IntegrityError as exc:
        if "repos.path" not in str(exc):
            raise
        existing_repo = await _db_async(
            engine,
            lambda s: s.exec(select(Repository).where(Repository.path == normalized_path)).first(),
        )
        if existing_repo is not None and existing_repo.project_id == project_id:
            return existing_repo
        linked_project = await _db_async(
            engine,
            lambda s: (
                s.get(Project, existing_repo.project_id) if existing_repo is not None else None
            ),
        )
        project_label = (
            linked_project.name
            if linked_project is not None
            else existing_repo.project_id
            if existing_repo is not None
            else "unknown"
        )
        raise SessionError(
            None,
            f"Repository path {normalized_path} is already linked to project {project_label!r}.",
        ) from exc


async def list_repos(engine: Engine, project_id: str) -> builtins.list[Repository]:
    stmt = select(Repository).where(Repository.project_id == project_id)
    return await _db_async(engine, lambda s: list(s.exec(stmt).all()))


async def set_repo_default_branch(
    engine: Engine, project_id: str, repo_id: str, branch: str
) -> Repository:
    await get_project(engine, project_id)

    def op(s):
        repo = s.get(Repository, repo_id)
        if repo is None:
            return None
        repo.default_branch = branch
        s.add(repo)
        s.commit()
        s.refresh(repo)
        return repo

    repo = await _db_async(engine, op)
    if repo is None:
        raise NotFoundError("Repository", repo_id)
    return repo


async def find_project_by_repo(engine: Engine, repo_path: str) -> Project | None:
    normalized_repo_path = str(Path(repo_path).expanduser().resolve())

    def op(s) -> Project | None:
        repo = s.exec(select(Repository).where(Repository.path == normalized_repo_path)).first()
        if repo is None or repo.project_id is None:
            return None
        return cast("Project | None", s.get(Project, repo.project_id))

    return await _db_async(engine, op)


async def find_project_by_name(engine: Engine, name: str) -> Project | None:
    return await _db_async(
        engine,
        lambda s: s.exec(select(Project).where(Project.name == name)).first(),
    )


async def resolve_repo(
    engine: Engine,
    project_id: str,
    *,
    selected_repo_id: str | None = None,
) -> Repository:
    repos = await list_repos(engine, project_id)
    if not repos:
        raise SessionError(None, f"No repos linked to project {project_id!r}.")
    if selected_repo_id:
        match = next((r for r in repos if r.id == selected_repo_id), None)
        if match is not None:
            return match
    if len(repos) == 1:
        return repos[0]
    raise MultiRepoUnsupportedError(len(repos))


async def resolve_repo_path(
    engine: Engine,
    *,
    project_id: str | None = None,
    active_project_id: str | None = None,
    settings: dict[str, str] | None = None,
) -> Path | None:
    project_id = project_id or active_project_id
    if not project_id:
        return None
    repos = await list_repos(engine, project_id)
    if not repos:
        return None
    settings = settings or {}
    selected_repo_id = settings.get(f"ui.selected_repo.{project_id}")
    try:
        repo = await resolve_repo(engine, project_id, selected_repo_id=selected_repo_id)
    except (MultiRepoUnsupportedError, SessionError):
        return None
    repo_path = Path(repo.path)
    return repo_path if repo_path.is_dir() else None


# ── Thin class wrapper (backward compatibility) ──────────────────────


class Projects:
    def __init__(self, engine: Engine, client: "KaganCore") -> None:
        self._engine = engine
        self._client = client

    async def create(self, name: str, *, repo_paths: list[str] | None = None) -> Project:
        return await create_project(
            self._engine,
            name,
            repo_paths=repo_paths,
            cancel_session=self._client.tasks.sessions.cancel,
            cleanup_worktree=self._client.worktrees.cleanup,
        )

    async def get(self, project_id: str) -> Project:
        return await get_project(self._engine, project_id)

    async def list(self) -> list[Project]:
        return await list_projects(self._engine)

    async def set_active(self, project_id: str) -> None:
        """Set the active project by ID. Validates the project exists."""
        await get_project(self._engine, project_id)
        self._client.active_project_id = project_id
        self._client.tasks._active_project_id = project_id
        logger.info("Active project set to {}", project_id)

    async def set_active_project(self, project: Project) -> None:
        """Set the active project from an already-loaded Project object.

        Use this when the project was just retrieved from list() or create()
        to avoid redundant database lookups. Trusts the object is valid.
        """
        self._client.active_project_id = project.id
        self._client.tasks._active_project_id = project.id
        logger.info("Active project set to {}", project.id)

    async def delete(self, project_id: str) -> None:
        cleared = await delete_project(
            self._engine,
            project_id,
            cancel_session=self._client.tasks.sessions.cancel,
            cleanup_worktree=self._client.worktrees.cleanup,
            active_project_id=self._client.active_project_id,
        )
        if cleared:
            self._client.active_project_id = None
            self._client.tasks._active_project_id = None

    async def add_repo(self, project_id: str, repo_path: str) -> Repository:
        return await add_repo(self._engine, project_id, repo_path)

    async def repos(self, project_id: str) -> builtins.list[Repository]:
        return await list_repos(self._engine, project_id)

    async def set_repo_default_branch(
        self, project_id: str, repo_id: str, branch: str
    ) -> Repository:
        return await set_repo_default_branch(self._engine, project_id, repo_id, branch)

    async def find_by_repo(self, repo_path: str) -> Project | None:
        return await find_project_by_repo(self._engine, repo_path)

    async def find_by_name(self, name: str) -> Project | None:
        return await find_project_by_name(self._engine, name)

    async def resolve_repo(
        self,
        project_id: str,
        *,
        selected_repo_id: str | None = None,
    ) -> Repository:
        return await resolve_repo(self._engine, project_id, selected_repo_id=selected_repo_id)

    async def resolve_repo_path(
        self,
        *,
        project_id: str | None = None,
        settings: dict[str, str] | None = None,
    ) -> Path | None:
        return await resolve_repo_path(
            self._engine,
            project_id=project_id,
            active_project_id=self._client.active_project_id,
            settings=settings,
        )


__all__ = [
    "Projects",
    "add_repo",
    "create_project",
    "delete_project",
    "find_project_by_name",
    "find_project_by_repo",
    "get_project",
    "list_projects",
    "list_repos",
    "resolve_repo",
    "resolve_repo_path",
    "set_repo_default_branch",
]
