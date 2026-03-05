import builtins
import contextlib
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
from kagan.core.errors import NotFoundError, SessionError, WorktreeError
from kagan.core.models import Project, Repository, Task

if TYPE_CHECKING:
    from kagan.core.client import KaganCore


class Projects:
    def __init__(self, engine: Engine, client: "KaganCore") -> None:
        self._engine = engine
        self._client = client

    async def create(self, name: str, *, repo_paths: list[str] | None = None) -> Project:
        project = Project(name=name)
        project = await _db_async(self._engine, lambda s: _add_and_refresh(s, project))
        logger.debug("Project created id={}", project.id)
        if repo_paths:
            try:
                for path in repo_paths:
                    await self.add_repo(project.id, path)
            except (SessionError, WorktreeError, OSError):
                with contextlib.suppress(NotFoundError):
                    await self.delete(project.id)
                raise
        return project

    async def get(self, project_id: str) -> Project:
        project = await _db_async(self._engine, lambda s: s.get(Project, project_id))
        if project is None:
            raise NotFoundError("Project", project_id)
        return project

    async def list(self) -> list[Project]:
        return await _db_async(self._engine, lambda s: list(s.exec(select(Project)).all()))

    async def set_active(self, project_id: str) -> None:
        await self.get(project_id)
        self._client.active_project_id = project_id
        self._client.tasks._active_project_id = project_id
        logger.info("Active project set to {}", project_id)

    async def delete(self, project_id: str) -> None:
        await self.get(project_id)

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

        await _db_async(self._engine, op, commit=True)

        if self._client.active_project_id == project_id:
            self._client.active_project_id = None
            self._client.tasks._active_project_id = None
            logger.info("Active project cleared after deleting project {}", project_id)

    async def add_repo(self, project_id: str, repo_path: str) -> Repository:
        await self.get(project_id)
        resolved_path = Path(repo_path).expanduser().resolve()
        normalized_path = str(resolved_path)

        existing_repo = await _db_async(
            self._engine,
            lambda s: s.exec(select(Repository).where(Repository.path == normalized_path)).first(),
        )
        if existing_repo is not None:
            if existing_repo.project_id == project_id:
                return existing_repo
            linked_project = await _db_async(
                self._engine, lambda s: s.get(Project, existing_repo.project_id)
            )
            project_label = (
                linked_project.name if linked_project is not None else existing_repo.project_id
            )
            raise SessionError(
                None,
                "Repository path "
                f"{normalized_path} is already linked to project {project_label!r}.",
            )

        settings = await self._client.settings.get()
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
                    "Repo path "
                    f"{resolved_path!s} is not a git repository and auto init is disabled.",
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
            return await _db_async(self._engine, lambda s: _add_and_refresh(s, repo))
        except IntegrityError as exc:
            if "repos.path" not in str(exc):
                raise
            existing_repo = await _db_async(
                self._engine,
                lambda s: s.exec(
                    select(Repository).where(Repository.path == normalized_path)
                ).first(),
            )
            if existing_repo is not None and existing_repo.project_id == project_id:
                return existing_repo
            linked_project = await _db_async(
                self._engine,
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
                "Repository path "
                f"{normalized_path} is already linked to project {project_label!r}.",
            ) from exc

    async def repos(self, project_id: str) -> builtins.list[Repository]:
        stmt = select(Repository).where(Repository.project_id == project_id)
        return await _db_async(self._engine, lambda s: list(s.exec(stmt).all()))

    async def set_repo_default_branch(
        self, project_id: str, repo_id: str, branch: str
    ) -> Repository:
        await self.get(project_id)

        def op(s):
            repo = s.get(Repository, repo_id)
            if repo is None:
                return None
            repo.default_branch = branch
            s.add(repo)
            s.commit()
            s.refresh(repo)
            return repo

        repo = await _db_async(self._engine, op)
        if repo is None:
            raise NotFoundError("Repository", repo_id)
        return repo

    async def find_by_repo(self, repo_path: str) -> Project | None:
        normalized_repo_path = str(Path(repo_path).expanduser().resolve())

        def op(s) -> Project | None:
            repo = s.exec(select(Repository).where(Repository.path == normalized_repo_path)).first()
            if repo is None or repo.project_id is None:
                return None
            return cast("Project | None", s.get(Project, repo.project_id))

        return await _db_async(self._engine, op)

    async def find_by_name(self, name: str) -> Project | None:
        return await _db_async(
            self._engine,
            lambda s: s.exec(select(Project).where(Project.name == name)).first(),
        )


__all__ = ["Projects"]
