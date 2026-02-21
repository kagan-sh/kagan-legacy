"""Automation reviewer auto-commit/push policy tests."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from kagan.core.config import GeneralConfig, KaganConfig
from kagan.core.domain.enums import TaskStatus
from kagan.core.plugins.github.gh_adapter import GITHUB_CONNECTION_KEY
from kagan.core.plugins.github.sync import GITHUB_TASK_PR_MAPPING_KEY
from kagan.core.services.automation.runner import AutomationReviewer


def _build_task(*, task_id: str = "task-1") -> SimpleNamespace:
    return SimpleNamespace(
        id=task_id,
        title="Task title",
        description="Task description",
        acceptance_criteria=None,
        project_id="proj-1",
    )


def _build_repo_scripts(task_id: str) -> dict[str, str]:
    return {
        GITHUB_CONNECTION_KEY: json.dumps(
            {
                "owner": "user",
                "repo": "repo",
                "full_name": "user/repo",
                "default_branch": "main",
            }
        ),
        GITHUB_TASK_PR_MAPPING_KEY: json.dumps(
            {
                "task_to_pr": {
                    task_id: {
                        "pr_number": 123,
                        "pr_url": "https://github.com/user/repo/pull/123",
                        "pr_state": "OPEN",
                        "head_branch": "task-branch",
                        "base_branch": "main",
                        "linked_at": "2026-02-20T00:00:00Z",
                    }
                }
            }
        ),
    }


def _build_reviewer(*, auto_commit_changes: bool) -> tuple[AutomationReviewer, SimpleNamespace]:
    task = _build_task()
    scripts = _build_repo_scripts(task.id)
    workspace = SimpleNamespace(id="ws-1", branch_name="task-branch")
    repo = SimpleNamespace(id="repo-1", scripts=scripts)

    tasks = SimpleNamespace(
        update_fields=AsyncMock(),
        get_scratchpad=AsyncMock(return_value=""),
        update_scratchpad=AsyncMock(),
    )
    projects = SimpleNamespace(get_project_repos=AsyncMock(return_value=[repo]))
    workspaces = SimpleNamespace(
        _projects=projects,
        get_task_workspace_path=AsyncMock(return_value=Path("/tmp/worktree")),
        list_workspaces=AsyncMock(return_value=[workspace]),
        get_workspace_repos=AsyncMock(
            return_value=[{"repo_id": "repo-1", "worktree_path": "/tmp/worktree"}]
        ),
    )
    git = SimpleNamespace(
        has_uncommitted_changes=AsyncMock(return_value=True),
        commit_all=AsyncMock(return_value="abc123"),
        push=AsyncMock(return_value=None),
    )
    runtime_service = SimpleNamespace(
        clear_review_agent=MagicMock(),
        get=MagicMock(return_value=None),
    )
    changed = MagicMock()

    reviewer = AutomationReviewer(
        task_service=tasks,
        workspace_service=workspaces,
        config=KaganConfig(
            general=GeneralConfig(auto_review=False, auto_commit_changes=auto_commit_changes)
        ),
        execution_service=None,
        notifier=None,
        agent_factory=MagicMock(),
        git_adapter=git,
        runtime_service=runtime_service,
        get_agent_config=MagicMock(),
        apply_model_override=MagicMock(),
        set_review_agent=AsyncMock(),
        notify_task_changed=changed,
    )
    return reviewer, SimpleNamespace(task=task, tasks=tasks, git=git, changed=changed)


async def test_handle_complete_skips_commit_and_push_when_auto_commit_disabled() -> None:
    reviewer, deps = _build_reviewer(auto_commit_changes=False)

    await reviewer._handle_complete(deps.task)

    deps.git.has_uncommitted_changes.assert_not_awaited()
    deps.git.commit_all.assert_not_awaited()
    deps.git.push.assert_not_awaited()
    deps.tasks.update_fields.assert_awaited_once_with(deps.task.id, status=TaskStatus.REVIEW)
    deps.changed.assert_called_once()


async def test_handle_complete_commits_and_pushes_when_auto_commit_enabled() -> None:
    reviewer, deps = _build_reviewer(auto_commit_changes=True)

    await reviewer._handle_complete(deps.task)

    deps.git.has_uncommitted_changes.assert_awaited_once_with("/tmp/worktree")
    deps.git.commit_all.assert_awaited_once()
    deps.git.push.assert_awaited_once_with("/tmp/worktree", "task-branch")
    deps.tasks.update_fields.assert_awaited_once_with(deps.task.id, status=TaskStatus.REVIEW)
    deps.changed.assert_called_once()
