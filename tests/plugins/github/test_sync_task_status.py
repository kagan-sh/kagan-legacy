"""Tests for sync_task_status_to_issue use case."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from kagan.core.plugins.github.application.use_cases import (
    GH_SYNC_FAILED,
    GH_TASK_REQUIRED,
    TASK_STATUS_SYNCED,
    GitHubPluginUseCases,
)
from kagan.core.plugins.github.domain.models import SyncTaskStatusInput
from kagan.core.plugins.github.gh_adapter import GITHUB_CONNECTION_KEY
from kagan.core.plugins.github.sync import GITHUB_ISSUE_MAPPING_KEY


def _connected_repo(task_id: str = "task-1", issue_number: int = 42) -> SimpleNamespace:
    return SimpleNamespace(
        id="repo-1",
        path="/tmp/repo",
        scripts={
            GITHUB_CONNECTION_KEY: json.dumps({"owner": "acme", "repo": "widgets"}),
            GITHUB_ISSUE_MAPPING_KEY: json.dumps(
                {
                    "issue_to_task": {str(issue_number): task_id},
                    "task_to_issue": {task_id: issue_number},
                }
            ),
        },
    )


def _gh_client(*, gh_path: str = "/usr/bin/gh") -> MagicMock:
    client = MagicMock()
    client.resolve_gh_cli_path.return_value = (gh_path, None)
    # Default: all operations succeed
    client.run_gh_issue_close.return_value = (True, None)
    client.run_gh_issue_reopen.return_value = (True, None)
    client.run_gh_issue_label_add.return_value = (True, None)
    client.run_gh_issue_label_remove.return_value = (True, None)
    return client


def _core_gateway(repo: SimpleNamespace) -> MagicMock:
    gw = MagicMock()
    gw.get_project_repos = _async_return([repo])
    return gw


def _async_return(value: object) -> MagicMock:
    """Create a coroutine-mock that returns *value*."""
    m = MagicMock()
    f = _make_coro(value)
    m.side_effect = lambda *a, **kw: f()
    return m


async def _make_coro_inner(value: object) -> object:
    return value


def _make_coro(value: object):
    async def coro(*_a: object, **_kw: object) -> object:
        return value

    return coro


# ---------------------------------------------------------------------------
# Validation edge cases
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_missing_task_id_returns_error() -> None:
    repo = _connected_repo()
    uc = GitHubPluginUseCases(_core_gateway(repo), _gh_client())

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id=None, project_id="proj-1", to_status="DONE")
    )

    assert result["success"] is False
    assert result["code"] == GH_TASK_REQUIRED


@pytest.mark.asyncio()
async def test_missing_project_id_returns_error() -> None:
    repo = _connected_repo()
    uc = GitHubPluginUseCases(_core_gateway(repo), _gh_client())

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id="task-1", project_id=None, to_status="DONE")
    )

    assert result["success"] is False


@pytest.mark.asyncio()
async def test_invalid_status_returns_error() -> None:
    repo = _connected_repo()
    uc = GitHubPluginUseCases(_core_gateway(repo), _gh_client())

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id="task-1", project_id="proj-1", to_status="INVALID")
    )

    assert result["success"] is False
    assert result["code"] == "GH_STATUS_INVALID"


# ---------------------------------------------------------------------------
# No linked issue
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_no_linked_issue_returns_success_with_no_actions() -> None:
    repo = SimpleNamespace(
        id="repo-1",
        path="/tmp/repo",
        scripts={
            GITHUB_CONNECTION_KEY: json.dumps({"owner": "acme", "repo": "widgets"}),
            GITHUB_ISSUE_MAPPING_KEY: json.dumps({"issue_to_task": {}, "task_to_issue": {}}),
        },
    )
    uc = GitHubPluginUseCases(_core_gateway(repo), _gh_client())

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id="task-99", project_id="proj-1", to_status="DONE")
    )

    assert result["success"] is True
    assert "no linked github issue" in result["message"].lower()


# ---------------------------------------------------------------------------
# DONE status: close + kagan:done label + remove others
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_done_closes_issue_and_manages_labels() -> None:
    repo = _connected_repo()
    gh = _gh_client()
    uc = GitHubPluginUseCases(_core_gateway(repo), gh)

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id="task-1", project_id="proj-1", to_status="DONE")
    )

    assert result["success"] is True
    assert result["code"] == TASK_STATUS_SYNCED
    assert result["issue_number"] == 42
    assert result["to_status"] == "DONE"

    # Close was called
    gh.run_gh_issue_close.assert_called_once()
    # Reopen was NOT called
    gh.run_gh_issue_reopen.assert_not_called()
    # kagan:done label added
    gh.run_gh_issue_label_add.assert_called_once()
    add_args = gh.run_gh_issue_label_add.call_args
    assert add_args[0][3] == "kagan:done"  # 4th positional arg = label
    # Other two labels removed
    remove_labels = sorted(call[0][3] for call in gh.run_gh_issue_label_remove.call_args_list)
    assert remove_labels == ["kagan:in-progress", "kagan:review"]


# ---------------------------------------------------------------------------
# IN_PROGRESS status: reopen + kagan:in-progress label
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_in_progress_reopens_issue_and_manages_labels() -> None:
    repo = _connected_repo()
    gh = _gh_client()
    uc = GitHubPluginUseCases(_core_gateway(repo), gh)

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id="task-1", project_id="proj-1", to_status="IN_PROGRESS")
    )

    assert result["success"] is True
    assert result["code"] == TASK_STATUS_SYNCED

    # Reopen was called (not close)
    gh.run_gh_issue_reopen.assert_called_once()
    gh.run_gh_issue_close.assert_not_called()
    # kagan:in-progress label added
    add_args = gh.run_gh_issue_label_add.call_args
    assert add_args[0][3] == "kagan:in-progress"
    # Other two removed
    remove_labels = sorted(call[0][3] for call in gh.run_gh_issue_label_remove.call_args_list)
    assert remove_labels == ["kagan:done", "kagan:review"]


# ---------------------------------------------------------------------------
# REVIEW status: reopen + kagan:review label
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_review_reopens_issue_and_manages_labels() -> None:
    repo = _connected_repo()
    gh = _gh_client()
    uc = GitHubPluginUseCases(_core_gateway(repo), gh)

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id="task-1", project_id="proj-1", to_status="REVIEW")
    )

    assert result["success"] is True
    assert result["code"] == TASK_STATUS_SYNCED

    gh.run_gh_issue_reopen.assert_called_once()
    gh.run_gh_issue_close.assert_not_called()
    add_args = gh.run_gh_issue_label_add.call_args
    assert add_args[0][3] == "kagan:review"
    remove_labels = sorted(call[0][3] for call in gh.run_gh_issue_label_remove.call_args_list)
    assert remove_labels == ["kagan:done", "kagan:in-progress"]


# ---------------------------------------------------------------------------
# BACKLOG status: no close/reopen, remove all kagan labels
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_backlog_removes_all_status_labels() -> None:
    repo = _connected_repo()
    gh = _gh_client()
    uc = GitHubPluginUseCases(_core_gateway(repo), gh)

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id="task-1", project_id="proj-1", to_status="BACKLOG")
    )

    assert result["success"] is True
    # No close or reopen
    gh.run_gh_issue_close.assert_not_called()
    gh.run_gh_issue_reopen.assert_not_called()
    # No label added (BACKLOG has no target label)
    gh.run_gh_issue_label_add.assert_not_called()
    # All three labels removed
    remove_labels = sorted(call[0][3] for call in gh.run_gh_issue_label_remove.call_args_list)
    assert remove_labels == ["kagan:done", "kagan:in-progress", "kagan:review"]


# ---------------------------------------------------------------------------
# gh CLI unavailable
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_gh_cli_unavailable_returns_sync_failed() -> None:
    repo = _connected_repo()
    gh = _gh_client()
    gh.resolve_gh_cli_path.return_value = (
        None,
        {"message": "gh not found"},
    )
    uc = GitHubPluginUseCases(_core_gateway(repo), gh)

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id="task-1", project_id="proj-1", to_status="DONE")
    )

    assert result["success"] is False
    assert result["code"] == GH_SYNC_FAILED


# ---------------------------------------------------------------------------
# Close failure is reported in label_errors
# ---------------------------------------------------------------------------


@pytest.mark.asyncio()
async def test_close_failure_reported_in_label_errors() -> None:
    repo = _connected_repo()
    gh = _gh_client()
    gh.run_gh_issue_close.return_value = (False, "permission denied")
    uc = GitHubPluginUseCases(_core_gateway(repo), gh)

    result = await uc.sync_task_status_to_issue(
        SyncTaskStatusInput(task_id="task-1", project_id="proj-1", to_status="DONE")
    )

    # Still succeeds overall (best-effort)
    assert result["success"] is True
    assert any("close failed" in e for e in result["label_errors"])
