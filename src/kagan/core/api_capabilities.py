from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

from kagan.core.config import KaganConfig
from kagan.core.domain.enums import QueueLane
from kagan.core.settings import exposed_settings_snapshot, normalize_settings_updates

if TYPE_CHECKING:
    from pathlib import Path

    from kagan.core.bootstrap import AppContext
    from kagan.core.services.automation.runner import QueuedMessage as QueueMessage
    from kagan.core.services.automation.runner import QueueStatus
    from kagan.core.services.jobs import JobEvent, JobRecord
    from kagan.core.services.workspaces import RepoWorkspaceInput


@dataclass(frozen=True, slots=True)
class ProjectCapabilityFacade:
    """Narrow project facade used to keep KaganAPI orchestration readable."""

    project_service: Any

    async def open_project(self, project_id: str) -> Any:
        return await self.project_service.open_project(project_id)

    async def create_project(
        self,
        *,
        name: str,
        repo_paths: list[str] | None,
        description: str,
    ) -> str:
        return await self.project_service.create_project(
            name=name,
            repo_paths=repo_paths,
            description=description,
        )

    async def add_repo_to_project(
        self,
        *,
        project_id: str,
        repo_path: str,
        is_primary: bool,
    ) -> str:
        return await self.project_service.add_repo_to_project(
            project_id=project_id,
            repo_path=repo_path,
            is_primary=is_primary,
        )

    async def get_project(self, project_id: str) -> Any:
        return await self.project_service.get_project(project_id)

    async def list_recent_projects(self, *, limit: int) -> list[Any]:
        return await self.project_service.list_recent_projects(limit=limit)

    async def get_project_repos(self, project_id: str) -> list[Any]:
        return await self.project_service.get_project_repos(project_id)

    async def get_project_repo_details(self, project_id: str) -> list[dict]:
        return await self.project_service.get_project_repo_details(project_id)

    async def find_project_by_repo_path(self, repo_path: str | Path) -> Any:
        return await self.project_service.find_project_by_repo_path(repo_path)

    async def update_repo_default_branch(
        self,
        repo_id: str,
        branch: str,
        *,
        mark_configured: bool,
    ) -> Any:
        return await self.project_service.update_repo_default_branch(
            repo_id,
            branch,
            mark_configured=mark_configured,
        )


@dataclass(frozen=True, slots=True)
class WorkspaceCapabilityFacade:
    """Narrow workspace facade used to keep KaganAPI orchestration readable."""

    workspace_service: Any

    async def get_task_workspace_path(self, task_id: str) -> Path | None:
        return await self.workspace_service.get_task_workspace_path(task_id)

    async def provision_workspace(self, task_id: str, repos: list[RepoWorkspaceInput]) -> str:
        return await self.workspace_service.provision(task_id, repos)

    async def list_workspaces(self, *, task_id: str | None = None) -> list[Any]:
        return await self.workspace_service.list_workspaces(task_id=task_id)

    async def get_workspace_repos(self, workspace_id: str) -> list[dict[str, Any]]:
        return await self.workspace_service.get_workspace_repos(workspace_id)

    async def cleanup_orphaned_workspaces(self, valid_task_ids: set[str]) -> list[str]:
        return await self.workspace_service.cleanup_orphaned_workspaces(valid_task_ids)

    async def cleanup_workspace_artifacts(
        self,
        valid_workspace_ids: set[str],
        *,
        prune_worktrees: bool = True,
        gc_branches: bool = True,
    ) -> Any:
        return await self.workspace_service.cleanup_workspace_artifacts(
            valid_workspace_ids,
            prune_worktrees=prune_worktrees,
            gc_branches=gc_branches,
        )

    async def cleanup_stale_done_workspaces(self, *, older_than_days: int) -> int:
        return await self.workspace_service.archive_stale_done_task_workspaces(
            older_than_days=older_than_days
        )


@dataclass(slots=True)
class SettingsCapabilityFacade:
    """Narrow settings facade used to isolate config mutation rules."""

    ctx: AppContext

    def snapshot(self) -> dict[str, object]:
        return exposed_settings_snapshot(self.ctx.config)

    async def update(self, fields: dict[str, object]) -> tuple[bool, str, dict[str, object]]:
        if not fields:
            return False, "fields must be a non-empty object", {}

        try:
            updates = normalize_settings_updates(fields)
        except ValueError as exc:
            return False, str(exc), {}

        config_data = self.ctx.config.model_dump(mode="python")
        for key, value in updates.items():
            section, field = key.split(".", 1)
            section_data = config_data.get(section)
            if not isinstance(section_data, dict):
                return False, f"Invalid settings section: {section}", {}
            section_data[field] = value

        try:
            next_config = KaganConfig.model_validate(config_data)
        except Exception as exc:
            return False, f"Invalid settings update: {exc}", {}

        await next_config.save(self.ctx.config_path)
        self.ctx.config = next_config
        return True, "Settings updated", updates


@dataclass(frozen=True, slots=True)
class JobCapabilityFacade:
    """Wrapper around job service operations."""

    job_service: Any

    async def submit(
        self,
        task_id: str,
        action: str,
        *,
        arguments: dict[str, Any] | None = None,
    ) -> JobRecord:
        payload: dict[str, Any] = {"task_id": task_id}
        if arguments:
            payload.update(arguments)
        return await self.job_service.submit(task_id=task_id, action=action, params=payload)

    async def cancel(self, job_id: str, *, task_id: str) -> JobRecord | None:
        return await self.job_service.cancel(job_id, task_id=task_id)

    async def wait(
        self,
        job_id: str,
        *,
        task_id: str,
        timeout_seconds: float | None = None,
    ) -> JobRecord | None:
        return await self.job_service.wait(job_id, task_id=task_id, timeout_seconds=timeout_seconds)

    async def events(self, job_id: str, *, task_id: str) -> list[JobEvent] | None:
        return await self.job_service.events(job_id, task_id=task_id)


@dataclass(frozen=True, slots=True)
class SessionCapabilityFacade:
    """Wrapper around session service operations."""

    session_service: Any

    async def attach(self, task_id: str) -> bool:
        return await self.session_service.attach_session(task_id)

    async def exists(self, task_id: str) -> bool:
        return await self.session_service.session_exists(task_id)

    async def kill(self, task_id: str) -> None:
        await self.session_service.kill_session(task_id)


@dataclass(frozen=True, slots=True)
class AutomationQueueCapabilityFacade:
    """Wrapper around automation queue operations."""

    automation_service: Any

    def is_running(self, task_id: str) -> bool:
        return self.automation_service.is_running(task_id)

    def get_running_agent(self, task_id: str) -> Any:
        return self.automation_service.get_running_agent(task_id)

    async def wait_for_running_agent(self, task_id: str, *, timeout: float = 2.0) -> Any:
        return await self.automation_service.wait_for_running_agent(task_id, timeout=timeout)

    async def start(self) -> None:
        await self.automation_service.start()

    async def queue_message(
        self,
        session_id: str,
        content: str,
        *,
        lane: QueueLane = QueueLane.IMPLEMENTATION,
        author: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> QueueMessage:
        return await self.automation_service.queue_message(
            session_id,
            content,
            lane=lane,
            author=author,
            metadata=metadata,
        )

    async def get_status(
        self,
        session_id: str,
        *,
        lane: QueueLane = QueueLane.IMPLEMENTATION,
    ) -> QueueStatus:
        return await self.automation_service.get_status(session_id, lane=lane)

    async def get_queued(
        self,
        session_id: str,
        *,
        lane: QueueLane = QueueLane.IMPLEMENTATION,
    ) -> list[QueueMessage]:
        return await self.automation_service.get_queued(session_id, lane=lane)

    async def take_queued(
        self,
        session_id: str,
        *,
        lane: QueueLane = QueueLane.IMPLEMENTATION,
    ) -> QueueMessage | None:
        return await self.automation_service.take_queued(session_id, lane=lane)

    async def remove_message(
        self,
        session_id: str,
        index: int,
        *,
        lane: QueueLane = QueueLane.IMPLEMENTATION,
    ) -> bool:
        return await self.automation_service.remove_message(session_id, index, lane=lane)


__all__ = [
    "AutomationQueueCapabilityFacade",
    "JobCapabilityFacade",
    "ProjectCapabilityFacade",
    "SessionCapabilityFacade",
    "SettingsCapabilityFacade",
    "WorkspaceCapabilityFacade",
]
