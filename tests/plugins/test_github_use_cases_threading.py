from __future__ import annotations

import threading
from types import SimpleNamespace
from typing import Any

import pytest

from kagan.core.plugins.github.gh_adapter import GITHUB_CONNECTION_KEY
from kagan.core.plugins.github.models import SyncIssuesInput
from kagan.core.plugins.github.use_cases import SYNCED, GitHubPluginUseCases


class _CoreGatewayStub:
    def __init__(self, repo: Any) -> None:
        self._repo = repo
        self.updated_scripts: list[tuple[str, dict[str, str]]] = []

    async def get_project(self, project_id: str) -> Any:
        return SimpleNamespace(id=project_id)

    async def get_project_repos(self, project_id: str) -> list[Any]:
        del project_id
        return [self._repo]

    async def get_task(self, task_id: str) -> Any | None:
        del task_id
        return None

    async def create_task(self, *, title: str, description: str, project_id: str) -> Any:
        del title, description, project_id
        raise AssertionError("sync_issues should not create tasks when issue list is empty")

    async def update_task_fields(self, task_id: str, **fields: Any) -> None:
        del task_id, fields
        raise AssertionError("sync_issues should not update tasks when issue list is empty")

    async def update_repo_scripts(self, repo_id: str, updates: dict[str, str]) -> None:
        self.updated_scripts.append((repo_id, updates))


class _GhClientStub:
    def __init__(self, event_loop_thread_id: int) -> None:
        self._event_loop_thread_id = event_loop_thread_id
        self.resolve_thread_id: int | None = None

    def resolve_gh_cli_path(self) -> tuple[str | None, dict[str, Any] | None]:
        self.resolve_thread_id = threading.get_ident()
        if self.resolve_thread_id == self._event_loop_thread_id:
            raise AssertionError("resolve_gh_cli_path must not run on the event-loop thread")
        return "/usr/bin/gh", None

    def run_gh_issue_list(
        self,
        gh_path: str,
        repo_path: str,
    ) -> tuple[list[dict[str, Any]] | None, str | None]:
        del gh_path, repo_path
        return [], None

    def parse_issue_list(self, raw_issues: list[dict[str, Any]]) -> list[Any]:
        del raw_issues
        return []


@pytest.mark.asyncio
async def test_sync_issues_resolves_gh_cli_path_off_event_loop_thread() -> None:
    event_loop_thread_id = threading.get_ident()
    repo = SimpleNamespace(
        id="repo-1",
        path="/tmp/repo-1",
        scripts={
            GITHUB_CONNECTION_KEY: {
                "owner": "acme",
                "repo": "platform",
                "full_name": "acme/platform",
                "default_branch": "main",
            }
        },
    )
    core = _CoreGatewayStub(repo)
    gh = _GhClientStub(event_loop_thread_id)
    use_cases = GitHubPluginUseCases(core, gh)  # type: ignore[arg-type]

    result = await use_cases.sync_issues(SyncIssuesInput(project_id="project-1", repo_id="repo-1"))

    assert result["success"] is True
    assert result["code"] == SYNCED
    assert gh.resolve_thread_id is not None
    assert gh.resolve_thread_id != event_loop_thread_id
    assert core.updated_scripts
