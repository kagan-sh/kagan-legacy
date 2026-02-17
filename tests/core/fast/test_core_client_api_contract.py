from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from kagan.sdk import KaganSDK
from kagan.tui.core_client_api import CoreBackedApi


def _make_mock_sdk():
    sdk = MagicMock(spec=KaganSDK)
    sdk.tasks_create = AsyncMock()
    sdk.tasks_get = AsyncMock()
    sdk.tasks_list = AsyncMock()
    sdk.tasks_search = AsyncMock()
    sdk.tasks_update = AsyncMock()
    sdk.tasks_move = AsyncMock()
    sdk.tasks_delete = AsyncMock()
    sdk.tasks_scratchpad = AsyncMock()
    sdk.projects_open = AsyncMock()
    sdk.projects_create = AsyncMock()
    sdk.projects_add_repo = AsyncMock()
    sdk.projects_get = AsyncMock()
    sdk.projects_list = AsyncMock()
    sdk.projects_repos = AsyncMock()
    sdk.projects_find_by_repo_path = AsyncMock()
    sdk.update_repo_default_branch = AsyncMock()
    sdk.settings_get = AsyncMock()
    sdk.settings_update = AsyncMock()
    sdk.plugins_invoke = AsyncMock()
    sdk.jobs_submit = AsyncMock()
    sdk.jobs_wait = AsyncMock()
    sdk.jobs_cancel = AsyncMock()
    sdk.sessions_create = AsyncMock()
    sdk.sessions_attach = AsyncMock()
    sdk.sessions_exists = AsyncMock()
    sdk.sessions_kill = AsyncMock()
    sdk.workspaces_list = AsyncMock()
    sdk.get_workspace_path = AsyncMock()
    sdk.get_repo_diff = AsyncMock()
    sdk.cleanup_orphan_workspaces = AsyncMock()
    sdk.get_workspace_diff = AsyncMock()
    sdk.get_workspace_commit_log = AsyncMock()
    sdk.get_workspace_diff_stats = AsyncMock()
    sdk.rebase_workspace = AsyncMock()
    sdk.abort_workspace_rebase = AsyncMock()
    sdk.merge_repo = AsyncMock()
    sdk.has_no_changes = AsyncMock()
    sdk.close_exploratory = AsyncMock()
    sdk.merge_task_direct = AsyncMock()
    sdk.apply_rejection_feedback = AsyncMock()
    sdk.get_all_diffs = AsyncMock()
    sdk.queue_message = AsyncMock()
    sdk.get_queue_status = AsyncMock()
    sdk.get_queued_messages = AsyncMock()
    sdk.take_queued_message = AsyncMock()
    sdk.remove_queued_message = AsyncMock()
    sdk.save_planner_draft = AsyncMock()
    sdk.list_pending_planner_drafts = AsyncMock()
    sdk.update_planner_draft_status = AsyncMock()
    sdk.get_execution = AsyncMock()
    sdk.get_execution_log_entries = AsyncMock()
    sdk.get_latest_execution_for_task = AsyncMock()
    sdk.count_executions_for_task = AsyncMock()
    sdk.decide_startup = AsyncMock()
    sdk.dispatch_runtime_session = AsyncMock()
    sdk.get_runtime_state = MagicMock()
    sdk.reconcile_running_tasks = AsyncMock()
    sdk.resolve_task_base_branch = AsyncMock()
    sdk.prepare_auto_output = AsyncMock()
    sdk.recover_stale_auto_output = AsyncMock()
    return sdk


@pytest.mark.asyncio
async def test_core_backed_api_wait_job_returns_job_response():
    sdk = _make_mock_sdk()
    sdk.jobs_wait = AsyncMock(
        return_value=MagicMock(
            success=True,
            job_id="job-1",
            task_id="task-1",
            action="start_agent",
            status="completed",
        )
    )
    api = CoreBackedApi(sdk)

    result = await api.wait_job("job-1", task_id="task-1", timeout_seconds=30.0)

    assert result.job_id == "job-1"
    sdk.jobs_wait.assert_called_once_with("job-1", "task-1", 30.0)


@pytest.mark.asyncio
async def test_core_backed_api_invoke_plugin_forwards_params():
    sdk = _make_mock_sdk()
    sdk.plugins_invoke = AsyncMock(
        return_value=MagicMock(
            success=True,
            result={"success": True, "stats": {"inserted": 3}},
        )
    )
    api = CoreBackedApi(sdk)

    result = await api.invoke_plugin(
        "kagan_github", "sync_issues", {"project_id": "project-1", "repo_id": "repo-1"}
    )

    assert result["success"] is True
    sdk.plugins_invoke.assert_called_once()


@pytest.mark.asyncio
async def test_core_backed_api_move_task_returns_task_on_success():
    sdk = _make_mock_sdk()
    sdk.tasks_move = AsyncMock(return_value=MagicMock(success=True))
    sdk.tasks_get = AsyncMock(return_value=MagicMock(task={"id": "task-1", "title": "Test"}))
    api = CoreBackedApi(sdk)

    result = await api.move_task("task-1", "in_progress")

    assert result is not None


@pytest.mark.asyncio
async def test_core_backed_api_update_task_returns_task_on_success():
    sdk = _make_mock_sdk()
    sdk.tasks_update = AsyncMock(return_value=MagicMock(success=True))
    sdk.tasks_get = AsyncMock(return_value=MagicMock(task={"id": "task-1", "title": "Updated"}))
    api = CoreBackedApi(sdk)

    result = await api.update_task("task-1", title="Updated")

    assert result is not None


@pytest.mark.asyncio
async def test_core_backed_api_provision_workspace_returns_path():
    sdk = _make_mock_sdk()
    sdk.get_workspace_path = AsyncMock(return_value="/path/to/workspace")
    api = CoreBackedApi(sdk)

    result = await api.provision_workspace(
        task_id="task-1",
        repos=[{"repo_id": "repo-1", "repo_path": "/tmp/repo-1", "target_branch": "main"}],
    )

    assert result == "/path/to/workspace"


@pytest.mark.asyncio
async def test_core_backed_api_has_no_changes_returns_bool():
    sdk = _make_mock_sdk()
    sdk.has_no_changes = AsyncMock(return_value=MagicMock(value=False))
    api = CoreBackedApi(sdk)

    result = await api.has_no_changes("task-1")

    assert result is False


@pytest.mark.asyncio
async def test_core_backed_api_delete_task_returns_tuple():
    sdk = _make_mock_sdk()
    sdk.tasks_delete = AsyncMock(return_value=MagicMock(success=False, message="Not found"))
    api = CoreBackedApi(sdk)

    deleted, _message = await api.delete_task("task-1")

    assert deleted is False


@pytest.mark.asyncio
async def test_core_backed_api_get_scratchpad_returns_content():
    sdk = _make_mock_sdk()
    sdk.tasks_scratchpad = AsyncMock(return_value=MagicMock(content="scratchpad content"))
    api = CoreBackedApi(sdk)

    result = await api.get_scratchpad("task-1")

    assert result == "scratchpad content"


@pytest.mark.asyncio
async def test_core_backed_api_list_projects_returns_list():
    sdk = _make_mock_sdk()
    sdk.projects_list = AsyncMock(return_value=MagicMock(projects=[{"id": "proj-1"}], count=1))
    api = CoreBackedApi(sdk)

    projects = await api.list_projects()

    assert len(projects) == 1


@pytest.mark.asyncio
async def test_core_backed_api_runtime_fallback_helpers():
    sdk = _make_mock_sdk()
    api = CoreBackedApi(sdk)

    assert api.is_automation_running("missing-task") is False
    assert api.refresh_agent_health() is None
    assert api.is_agent_available is True
    assert api.get_agent_status_message() is None
    assert api.get_running_task_ids() == set()
