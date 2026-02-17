"""Consolidated SDK integration tests.

Includes core-client regressions, core-client API / runtime-cache tests,
and TUI API-boundary enforcement.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING, cast
from unittest.mock import AsyncMock, MagicMock

import pytest
from tests.helpers.wait import wait_for_screen, wait_for_widget, wait_until_async
from textual.widgets import Button, Label, Switch

from kagan.core.adapters.db.repositories import (
    ExecutionRepository,
    SessionRecordRepository,
    TaskRepository,
)
from kagan.core.domain.enums import (
    ExecutionRunReason,
    ExecutionStatus,
    SessionType,
    TaskStatus,
    TaskType,
)
from kagan.core.services.workspaces import RepoWorkspaceInput
from kagan.sdk import KaganSDK
from kagan.tui.core_client_api import CoreBackedApi
from kagan.tui.ui.modals.plugin_form import PluginFormModal
from kagan.tui.ui.modals.review_flow import ReviewModal
from kagan.tui.ui.modals.settings import SettingsModal
from kagan.tui.ui.screens.kanban import KanbanScreen
from kagan.tui.ui.screens.kanban.commands import KanbanCommandProvider
from kagan.tui.ui.widgets.card import TaskCard
from kagan.tui.ui.widgets.chat_panel import ChatPanel

if TYPE_CHECKING:
    from kagan.tui.app import KaganApp


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _wait_chat_contains(
    review: ReviewModal,
    expected_text: str,
    *,
    timeout: float = 8.0,
) -> str:
    rendered = ""

    async def _has_expected_text() -> bool:
        nonlocal rendered
        rendered = review.query_one(
            "#review-agent-output-chat", ChatPanel
        ).output.get_text_content()
        return expected_text in rendered

    await wait_until_async(
        _has_expected_text,
        timeout=timeout,
        check_interval=0.1,
        description=f"agent output to contain '{expected_text}'",
    )
    return rendered


def _make_mock_sdk():
    sdk = MagicMock(spec=KaganSDK)
    sdk.reconcile_running_tasks = AsyncMock()
    sdk.get_runtime_view = AsyncMock()
    sdk.plugins_invoke = AsyncMock()
    return sdk


# ---------------------------------------------------------------------------
# TUI API boundary enforcement
# ---------------------------------------------------------------------------

TUI_SRC = Path("src/kagan/tui")

# Services that MUST be accessed through the API boundary.
_SERVICES = (
    "task_service",
    "session_service",
    "runtime_service",
    "workspace_service",
    "job_service",
    "automation_service",
    "project_service",
    "agent_health",
    "execution_service",
    "audit_repository",
    "planner_repository",
)

# Matches direct `ctx.<service>`.
_DIRECT_ACCESS = re.compile(r"ctx\.(" + "|".join(_SERVICES) + r")\b")


def test_no_direct_service_access_in_tui() -> None:
    """TUI source files must not access services directly on ctx."""
    violations: list[str] = []
    for py_file in sorted(TUI_SRC.rglob("*.py")):
        rel = str(py_file.relative_to(TUI_SRC))
        for i, line in enumerate(py_file.read_text(encoding="utf-8").splitlines(), 1):
            # Skip comments
            stripped = line.lstrip()
            if stripped.startswith("#"):
                continue
            if _DIRECT_ACCESS.search(line):
                violations.append(f"  {rel}:{i}: {stripped}")

    assert not violations, (
        "TUI files must not access services directly on ctx. "
        "Use ctx.api.<method>() only.\n" + "\n".join(violations)
    )


# ---------------------------------------------------------------------------
# Core-client API / runtime-cache tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_reconcile_running_tasks_calls_sdk():
    sdk = _make_mock_sdk()
    sdk.reconcile_running_tasks = AsyncMock(return_value=MagicMock(task_ids=["task-1", "task-2"]))
    api = CoreBackedApi(sdk)

    await api.reconcile_running_tasks(["task-1", "task-2"])

    sdk.reconcile_running_tasks.assert_called_once_with(["task-1", "task-2"])


@pytest.mark.asyncio
async def test_get_runtime_view_returns_none():
    sdk = _make_mock_sdk()
    api = CoreBackedApi(sdk)

    result = api.get_runtime_view("task-1")

    assert result is None


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_core_backed_api_invoke_plugin_forwards_payload():
    sdk = _make_mock_sdk()
    sdk.plugins_invoke = AsyncMock(
        return_value=MagicMock(
            success=True,
            result={"successcode": "CONNECTED"},
        )
    )
    api = CoreBackedApi(sdk)

    result = await api.invoke_plugin(
        "kagan_github", "connect_repo", {"project_id": "project-1", "repo_id": "repo-1"}
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_core_backed_api_invoke_plugin_returns_empty_on_error():
    sdk = _make_mock_sdk()
    sdk.plugins_invoke = AsyncMock(return_value=MagicMock(success=False, result=None))
    api = CoreBackedApi(sdk)

    result = await api.invoke_plugin("kagan_github", "sync_issues", {"project_id": "project-1"})

    assert result == {}


# ---------------------------------------------------------------------------
# Core-client regression tests
# ---------------------------------------------------------------------------


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_settings_modal_reflects_saved_values_without_restart(e2e_app_with_tasks) -> None:
    app = cast("KaganApp", e2e_app_with_tasks)

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))

        await kanban.action_open_settings()
        settings = cast("SettingsModal", await wait_for_screen(pilot, SettingsModal, timeout=5.0))
        switch = settings.query_one("#auto-review-switch", Switch)
        updated_value = not switch.value
        switch.value = updated_value
        await pilot.pause()
        settings.query_one("#save-btn", Button).press()

        await wait_for_screen(pilot, KanbanScreen, timeout=10.0)

        await kanban.action_open_settings()
        settings = cast("SettingsModal", await wait_for_screen(pilot, SettingsModal, timeout=5.0))
        assert settings.query_one("#auto-review-switch", Switch).value is updated_value


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_kanban_resume_recovers_after_core_client_disconnect(e2e_app_with_tasks) -> None:
    app = cast("KaganApp", e2e_app_with_tasks)

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        client = app._core_client
        assert client is not None

        await client.close()
        assert not client.is_connected

        await kanban.on_screen_resume()
        tasks = await app.ctx.api.list_tasks(project_id=app.ctx.active_project_id)
        assert tasks


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_task_output_streams_incremental_logs_for_external_running_execution(
    e2e_app_with_tasks,
) -> None:
    app = cast("KaganApp", e2e_app_with_tasks)
    repo = TaskRepository(app.db_path, project_root=app.project_root)
    await repo.initialize()
    session_repo = SessionRecordRepository(repo.session_factory)
    execution_repo = ExecutionRepository(repo.session_factory)

    try:
        async with app.run_test(size=(120, 40)) as pilot:
            kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
            project_id = app.ctx.active_project_id
            assert project_id is not None

            task = await app.ctx.api.create_task(
                title="External run stream",
                description="",
                project_id=project_id,
                status=TaskStatus.IN_PROGRESS.value,
                task_type=TaskType.AUTO.value,
            )

            repo_rows = await app.ctx.api.get_project_repo_details(project_id)
            assert repo_rows
            active_repo_id = app.ctx.active_repo_id or str(repo_rows[0]["id"])
            repo_row = next(row for row in repo_rows if str(row["id"]) == active_repo_id)

            workspace_id = await app.ctx.api.provision_workspace(
                task_id=task.id,
                repos=[
                    RepoWorkspaceInput(
                        repo_id=str(repo_row["id"]),
                        repo_path=str(repo_row["path"]),
                        target_branch=str(repo_row["default_branch"]),
                    )
                ],
            )
            session_record = await session_repo.create_session_record(
                workspace_id=workspace_id,
                session_type=SessionType.SCRIPT,
                external_id=f"task:{task.id}",
            )
            execution = await execution_repo.create_execution(
                session_id=session_record.id,
                run_reason=ExecutionRunReason.CODINGAGENT,
            )
            await execution_repo.update_execution(execution.id, status=ExecutionStatus.RUNNING)

            await app.ctx.api.reconcile_running_tasks([task.id])
            await kanban._board.refresh_board()
            await wait_for_widget(pilot, f"#card-{task.id}", timeout=6.0)

            card = kanban.query_one(f"#card-{task.id}", TaskCard)
            card.focus()
            await pilot.pause()
            assert kanban.check_action("stop_agent", ()) is True
            await pilot.press("enter")
            review = cast("ReviewModal", await wait_for_screen(pilot, ReviewModal, timeout=10.0))

            await execution_repo.append_execution_log(
                execution.id,
                '{"messages":[{"type":"response","content":"external log line one"}]}',
            )
            rendered = await _wait_chat_contains(review, "external log line one")
            assert "external log line one" in rendered

            await execution_repo.append_execution_log(
                execution.id,
                '{"messages":[{"type":"response","content":"external log line two"}]}',
            )
            rendered = await _wait_chat_contains(review, "external log line two")
            assert "external log line two" in rendered
    finally:
        await repo.close()


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_github_connect_action_succeeds_and_status_is_refreshed(
    e2e_app_with_tasks,
    monkeypatch,
) -> None:
    app = cast("KaganApp", e2e_app_with_tasks)
    connected = False
    repo_option_value: str | None = None
    repo_option_value: str | None = None

    async def _plugin_ui_catalog(
        *,
        project_id: str,
        repo_id: str | None = None,
    ) -> dict[str, object]:
        del project_id, repo_id
        state = "ok" if connected else "warn"
        text = "Connected" if connected else "Not connected"
        option_value = repo_option_value or "repo-1"
        return {
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "official.github",
                    "action_id": "connect_repo",
                    "surface": "kanban.repo_actions",
                    "label": "Connect GitHub Repo",
                    "command": "github connect",
                    "operation": {"capability": "kagan_github", "method": "connect_repo"},
                    "form_id": "connect_repo_form",
                    "confirm": False,
                }
            ],
            "forms": [
                {
                    "plugin_id": "official.github",
                    "form_id": "connect_repo_form",
                    "title": "Connect GitHub Repo",
                    "fields": [
                        {
                            "name": "repo_id",
                            "kind": "select",
                            "required": False,
                            "options": [{"label": "repo-1", "value": option_value}],
                        }
                    ],
                }
            ],
            "badges": [
                {
                    "plugin_id": "official.github",
                    "badge_id": "connection",
                    "surface": "header.badges",
                    "label": "GitHub",
                    "state": state,
                    "text": text,
                }
            ],
        }

    async def _plugin_ui_invoke(
        *,
        project_id: str,
        repo_id: str | None = None,
        plugin_id: str,
        action_id: str,
        inputs: dict | None = None,
    ) -> dict[str, object]:
        del project_id, repo_id, plugin_id, action_id, inputs
        nonlocal connected
        connected = True
        return {
            "ok": True,
            "code": "CONNECTED",
            "message": "Connected",
            "data": {},
            "refresh": {"repo": True, "tasks": False, "sessions": False},
        }

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        repo_option_value = app.ctx.active_repo_id or "repo-1"
        monkeypatch.setattr(app.ctx.api, "plugin_ui_catalog", _plugin_ui_catalog)
        monkeypatch.setattr(app.ctx.api, "plugin_ui_invoke", _plugin_ui_invoke)
        await kanban.sync_header_context(kanban.header)
        await pilot.pause()
        status = kanban.header.query_one("#header-github-status", Label)
        assert "Not connected" in str(status.content)

        await kanban._refresh_plugin_ui_catalog(force=True)
        kanban.run_worker(
            kanban.invoke_plugin_ui_action("official.github", "connect_repo"),
            group="test-plugin-ui-connect",
            exclusive=True,
            exit_on_error=False,
        )
        form = cast("PluginFormModal", await wait_for_screen(pilot, PluginFormModal, timeout=5.0))
        await wait_for_widget(pilot, "#btn-submit", timeout=5.0)
        form.query_one("#btn-submit", Button).press()
        await pilot.pause()

        async def _is_connected() -> bool:
            return connected

        await wait_until_async(
            _is_connected,
            timeout=5.0,
            check_interval=0.05,
            description="plugin connect invoke to set connected flag",
        )
        await wait_for_screen(pilot, KanbanScreen, timeout=10.0)
        await pilot.pause()
        status = kanban.header.query_one("#header-github-status", Label)
        assert "Connected" in str(status.content)


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_github_connect_palette_command_schedules_worker_and_completes(
    e2e_app_with_tasks,
    monkeypatch,
) -> None:
    app = cast("KaganApp", e2e_app_with_tasks)
    connected = False

    async def _plugin_ui_catalog(
        *,
        project_id: str,
        repo_id: str | None = None,
    ) -> dict[str, object]:
        del project_id, repo_id
        option_value = repo_option_value or "repo-1"
        return {
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "official.github",
                    "action_id": "connect_repo",
                    "surface": "kanban.repo_actions",
                    "label": "Connect GitHub Repo",
                    "command": "github connect",
                    "operation": {"capability": "kagan_github", "method": "connect_repo"},
                    "form_id": "connect_repo_form",
                    "confirm": False,
                }
            ],
            "forms": [
                {
                    "plugin_id": "official.github",
                    "form_id": "connect_repo_form",
                    "title": "Connect GitHub Repo",
                    "fields": [
                        {
                            "name": "repo_id",
                            "kind": "select",
                            "required": False,
                            "options": [{"label": "repo-1", "value": option_value}],
                        }
                    ],
                }
            ],
            "badges": [],
        }

    async def _plugin_ui_invoke(
        *,
        project_id: str,
        repo_id: str | None = None,
        plugin_id: str,
        action_id: str,
        inputs: dict | None = None,
    ) -> dict[str, object]:
        del project_id, repo_id, plugin_id, action_id, inputs
        nonlocal connected
        connected = True
        return {
            "ok": True,
            "code": "CONNECTED",
            "message": "Connected",
            "data": {},
            "refresh": {"repo": True, "tasks": False, "sessions": False},
        }

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        repo_option_value = app.ctx.active_repo_id or "repo-1"
        monkeypatch.setattr(app.ctx.api, "plugin_ui_catalog", _plugin_ui_catalog)
        monkeypatch.setattr(app.ctx.api, "plugin_ui_invoke", _plugin_ui_invoke)
        await kanban._refresh_plugin_ui_catalog(force=True)

        provider = KanbanCommandProvider(kanban)
        hits = [hit async for hit in provider.search("github connect")]
        assert hits
        command_result = hits[0].command()
        assert command_result is None

        form = cast("PluginFormModal", await wait_for_screen(pilot, PluginFormModal, timeout=5.0))
        await wait_for_widget(pilot, "#btn-submit", timeout=5.0)
        form.query_one("#btn-submit", Button).press()
        await pilot.pause()

        async def _is_connected() -> bool:
            return connected

        await wait_until_async(
            _is_connected,
            timeout=5.0,
            check_interval=0.05,
            description="palette plugin connect invoke to set connected flag",
        )


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_plugin_form_validation_error_does_not_mutate_state(
    e2e_app_with_tasks,
    monkeypatch,
) -> None:
    app = cast("KaganApp", e2e_app_with_tasks)
    plugin_ui_invoke = AsyncMock()

    async def _plugin_ui_catalog(
        *,
        project_id: str,
        repo_id: str | None = None,
    ) -> dict[str, object]:
        del project_id, repo_id
        return {
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "official.github",
                    "action_id": "needs_input",
                    "surface": "kanban.repo_actions",
                    "label": "Needs Input",
                    "command": "github needs-input",
                    "operation": {"capability": "kagan_github", "method": "noop"},
                    "form_id": "needs_input_form",
                    "confirm": False,
                }
            ],
            "forms": [
                {
                    "plugin_id": "official.github",
                    "form_id": "needs_input_form",
                    "title": "Needs Input",
                    "fields": [
                        {
                            "name": "token",
                            "kind": "text",
                            "required": True,
                            "placeholder": "Required",
                        }
                    ],
                }
            ],
            "badges": [],
        }

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        monkeypatch.setattr(app.ctx.api, "plugin_ui_catalog", _plugin_ui_catalog)
        monkeypatch.setattr(app.ctx.api, "plugin_ui_invoke", plugin_ui_invoke)
        await kanban._refresh_plugin_ui_catalog(force=True)
        kanban.run_worker(
            kanban.invoke_plugin_ui_action("official.github", "needs_input"),
            group="test-plugin-ui-validation",
            exclusive=True,
            exit_on_error=False,
        )

        form = cast("PluginFormModal", await wait_for_screen(pilot, PluginFormModal, timeout=5.0))
        await wait_for_widget(pilot, "#btn-submit", timeout=5.0)
        form.query_one("#btn-submit", Button).press()
        await pilot.pause()
        assert isinstance(pilot.app.screen, PluginFormModal)

        await wait_for_widget(pilot, "#btn-cancel", timeout=5.0)
        form.query_one("#btn-cancel", Button).press()
        await pilot.pause()

        await wait_for_screen(pilot, KanbanScreen, timeout=10.0)
        plugin_ui_invoke.assert_not_awaited()


@pytest.mark.xfail(reason="Pending post-rewrite TUI stabilization")
@pytest.mark.asyncio
async def test_plugin_badges_render_from_catalog_and_update_after_invoke(
    e2e_app_with_tasks,
    monkeypatch,
) -> None:
    app = cast("KaganApp", e2e_app_with_tasks)
    badge_text = "Not connected"
    badge_state = "warn"

    async def _plugin_ui_catalog(
        *,
        project_id: str,
        repo_id: str | None = None,
    ) -> dict[str, object]:
        del project_id, repo_id
        return {
            "schema_version": "1",
            "actions": [],
            "forms": [],
            "badges": [
                {
                    "plugin_id": "official.github",
                    "badge_id": "connection",
                    "surface": "header.badges",
                    "label": "GitHub",
                    "state": badge_state,
                    "text": badge_text,
                }
            ],
        }

    async with app.run_test(size=(120, 40)) as pilot:
        kanban = cast("KanbanScreen", await wait_for_screen(pilot, KanbanScreen, timeout=10.0))
        monkeypatch.setattr(app.ctx.api, "plugin_ui_catalog", _plugin_ui_catalog)

        await kanban.sync_header_context(kanban.header)
        await pilot.pause()
        status = kanban.header.query_one("#header-github-status", Label)
        assert "Not connected" in str(status.content)

        badge_text = "Connected"
        badge_state = "ok"

        await kanban.sync_header_context(kanban.header)
        await pilot.pause()
        status = kanban.header.query_one("#header-github-status", Label)
        assert "Connected" in str(status.content)
