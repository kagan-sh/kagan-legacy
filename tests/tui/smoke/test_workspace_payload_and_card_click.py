from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from kagan.sdk._types import PluginUiCatalogResponse, PluginUiInvokeResponse
from kagan.tui._api_adapter import CoreBackedApi, WorkspaceView
from kagan.tui.app import KaganApp, resolve_tui_mouse_enabled
from kagan.tui.ui.widgets.card import TaskCard


class _FakeWorkspaceSdk:
    async def workspaces_list(self, task_id: str | None = None) -> SimpleNamespace:
        del task_id
        return SimpleNamespace(
            workspaces=[
                {
                    "id": "ws-1",
                    "project_id": "proj-1",
                    "task_id": "task-1",
                    "branch_name": "task-abc",
                    "path": "/tmp/ws-1",
                    "status": "active",
                },
                {
                    "workspace_id": "ws-2",
                    "task_id": "task-2",
                    "branch_name": "task-def",
                    "path": "/tmp/ws-2",
                    "status": SimpleNamespace(value="archived"),
                },
            ]
        )


class _FakeWorkspaceCleanupSdk:
    def __init__(self) -> None:
        self.received_task_ids: list[set[str]] = []

    async def cleanup_orphan_workspaces(self, valid_task_ids: list[str]) -> list[str]:
        self.received_task_ids.append(set(valid_task_ids))
        return ["ws-cleaned"]


@pytest.mark.asyncio
async def test_list_workspaces_normalizes_dict_payloads_to_workspace_views() -> None:
    api = CoreBackedApi(_FakeWorkspaceSdk())

    workspaces = await api.list_workspaces()

    assert all(isinstance(item, WorkspaceView) for item in workspaces)
    assert [item.id for item in workspaces] == ["ws-1", "ws-2"]
    assert workspaces[0].branch_name == "task-abc"
    assert workspaces[1].status == "archived"


@pytest.mark.asyncio
async def test_workspace_cleanup_calls_sdk_method() -> None:
    sdk = _FakeWorkspaceCleanupSdk()
    api = CoreBackedApi(sdk)

    cleaned = await api.cleanup_orphan_workspaces({"task-1", "task-2"})

    assert cleaned == ["ws-cleaned"]
    assert sdk.received_task_ids == [{"task-1", "task-2"}]


class _JanitorApiStub:
    def __init__(self) -> None:
        self.received_ids: set[str] | None = None

    async def list_workspaces(self) -> list[object]:
        return [
            {"id": "ws-dict"},
            {"workspace_id": "ws-alias"},
            SimpleNamespace(id="ws-object"),
            SimpleNamespace(id=""),
        ]

    async def cleanup_workspace_artifacts(self, valid_workspace_ids: set[str]):
        self.received_ids = set(valid_workspace_ids)
        return SimpleNamespace(total_cleaned=0, worktrees_pruned=0, branches_deleted=[])


@pytest.mark.asyncio
async def test_run_janitor_handles_workspace_dict_payloads_without_crashing() -> None:
    app = KaganApp(db_path=":memory:")
    api_stub = _JanitorApiStub()
    app._ctx = SimpleNamespace(api=api_stub)

    await app._run_janitor()

    assert api_stub.received_ids == {"ws-dict", "ws-alias", "ws-object"}


def test_task_card_double_click_does_not_emit_selected_message() -> None:
    task_stub = SimpleNamespace(id="task-123")
    card = TaskCard(task_stub)

    with (
        patch.object(TaskCard, "focus", autospec=True) as focus_mock,
        patch.object(TaskCard, "post_message", autospec=True) as post_message_mock,
    ):
        card.on_click(SimpleNamespace(chain=2))

    focus_mock.assert_called_once_with(card)
    post_message_mock.assert_not_called()


def test_resolve_tui_mouse_enabled_defaults_to_true(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAGAN_TUI_MOUSE", raising=False)
    assert resolve_tui_mouse_enabled() is True


@pytest.mark.parametrize("value", ["0", "false", "no", "off", " OFF "])
def test_resolve_tui_mouse_enabled_honors_disable_values(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("KAGAN_TUI_MOUSE", value)
    assert resolve_tui_mouse_enabled() is False


class _FakePluginUiSdk:
    async def plugin_ui_catalog(
        self,
        project_id: str,
        repo_id: str | None = None,
    ) -> PluginUiCatalogResponse:
        del project_id, repo_id
        return PluginUiCatalogResponse(
            schema_version="1",
            actions=[
                {
                    "plugin_id": "official.github",
                    "action_id": "sync_issues",
                    "surface": "kanban.repo_actions",
                }
            ],
            forms=[{"plugin_id": "official.github", "form_id": "github_repo_picker"}],
            badges=[{"plugin_id": "official.github", "badge_id": "connection"}],
            diagnostics=["sample diagnostic"],
        )

    async def plugin_ui_invoke(
        self,
        project_id: str,
        plugin_id: str,
        action_id: str,
        repo_id: str | None = None,
        inputs: dict[str, object] | None = None,
    ) -> PluginUiInvokeResponse:
        del project_id, plugin_id, action_id, repo_id, inputs
        return PluginUiInvokeResponse(
            ok=True,
            code="OK",
            message="Invoked",
            data={"success": True},
            refresh={"repo": True, "tasks": False, "sessions": True},
        )


@pytest.mark.asyncio
async def test_plugin_ui_catalog_normalizes_sdk_response_to_dict_payload() -> None:
    api = CoreBackedApi(_FakePluginUiSdk())

    payload = await api.plugin_ui_catalog(project_id="proj-1", repo_id="repo-1")

    assert payload["schema_version"] == "1"
    assert payload["actions"] == [
        {
            "plugin_id": "official.github",
            "action_id": "sync_issues",
            "surface": "kanban.repo_actions",
        }
    ]
    assert payload["forms"] == [{"plugin_id": "official.github", "form_id": "github_repo_picker"}]
    assert payload["badges"] == [{"plugin_id": "official.github", "badge_id": "connection"}]
    assert payload["diagnostics"] == ["sample diagnostic"]


@pytest.mark.asyncio
async def test_plugin_ui_invoke_normalizes_sdk_response_to_dict_payload() -> None:
    api = CoreBackedApi(_FakePluginUiSdk())

    payload = await api.plugin_ui_invoke(
        project_id="proj-1",
        repo_id="repo-1",
        plugin_id="official.github",
        action_id="sync_issues",
    )

    assert payload == {
        "ok": True,
        "code": "OK",
        "message": "Invoked",
        "data": {"success": True},
        "refresh": {"repo": True, "tasks": False, "sessions": True},
    }
