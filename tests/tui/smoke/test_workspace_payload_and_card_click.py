from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

from kagan.sdk._types import PluginUiCatalogResponse, PluginUiInvokeResponse, QueueMessageResponse
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


class _FakeProjectRepoSdk:
    async def projects_repos(self, project_id: str) -> SimpleNamespace:
        del project_id
        return SimpleNamespace(
            repos=[
                SimpleNamespace(
                    id="repo-1",
                    name="Repo One",
                    path="/tmp/repo-one",
                    default_branch="main",
                ),
                {
                    "id": "repo-2",
                    "name": "Repo Two",
                    "path": "/tmp/repo-two",
                    "default_branch": "develop",
                    "is_primary": True,
                    "display_order": 7,
                },
            ]
        )


class _FakeWorkspaceProvisionSdk:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict[str, str]]]] = []

    async def workspaces_provision(self, task_id: str, repos: list[dict[str, str]]) -> str:
        self.calls.append((task_id, repos))
        return "ws-123"


class _FakeWorkspaceCleanupSdk:
    def __init__(self) -> None:
        self.received_task_ids: list[set[str]] = []

    async def cleanup_orphan_workspaces(self, valid_task_ids: list[str]) -> list[str]:
        self.received_task_ids.append(set(valid_task_ids))
        return ["ws-cleaned"]


class _FakeRuntimeSdk:
    def __init__(self) -> None:
        self.snapshots: list[dict[str, object]] = []

    async def reconcile_running_tasks(self, task_ids: list[str]) -> SimpleNamespace:
        del task_ids
        return SimpleNamespace(tasks=list(self.snapshots), count=len(self.snapshots))


class _FakeQueueSdk:
    async def take_queued_message(
        self,
        session_id: str,
        lane: str = "implementation",
    ) -> QueueMessageResponse:
        del session_id, lane
        return QueueMessageResponse.model_validate(
            {
                "success": True,
                "message": {
                    "content": "Please include risk notes.",
                    "author": "orchestrator-overlay",
                    "metadata": {"target": "review"},
                    "queued_at": "2026-02-20T12:43:00.673142+00:00",
                },
                "code": "MESSAGE_TAKEN",
            }
        )


class _FakeQueueEmptySdk:
    async def take_queued_message(
        self,
        session_id: str,
        lane: str = "implementation",
    ) -> QueueMessageResponse:
        del session_id, lane
        return QueueMessageResponse.model_validate(
            {
                "success": True,
                "message": None,
                "code": "QUEUE_EMPTY",
            }
        )


@pytest.mark.asyncio
async def test_list_workspaces_normalizes_dict_payloads_to_workspace_views() -> None:
    api = CoreBackedApi(_FakeWorkspaceSdk())

    workspaces = await api.list_workspaces()

    assert all(isinstance(item, WorkspaceView) for item in workspaces)
    assert [item.id for item in workspaces] == ["ws-1", "ws-2"]
    assert workspaces[0].branch_name == "task-abc"
    assert workspaces[1].status == "archived"


@pytest.mark.asyncio
async def test_get_project_repo_details_normalizes_payload_shape() -> None:
    api = CoreBackedApi(_FakeProjectRepoSdk())

    repo_details = await api.get_project_repo_details("proj-1")

    assert repo_details == [
        {
            "id": "repo-1",
            "name": "Repo One",
            "path": "/tmp/repo-one",
            "default_branch": "main",
            "is_primary": False,
            "display_order": 0,
        },
        {
            "id": "repo-2",
            "name": "Repo Two",
            "path": "/tmp/repo-two",
            "default_branch": "develop",
            "is_primary": True,
            "display_order": 7,
        },
    ]


@pytest.mark.asyncio
async def test_provision_workspace_sends_repo_payload_to_sdk() -> None:
    from kagan.core.services.workspaces import RepoWorkspaceInput

    sdk = _FakeWorkspaceProvisionSdk()
    api = CoreBackedApi(sdk)

    workspace_id = await api.provision_workspace(
        task_id="task-1",
        repos=[
            RepoWorkspaceInput(
                repo_id="repo-1",
                repo_path="/tmp/repo-one",
                target_branch="main",
            ),
            {
                "repo_id": "repo-2",
                "repo_path": "/tmp/repo-two",
                "target_branch": "develop",
            },
        ],
    )

    assert workspace_id == "ws-123"
    assert sdk.calls == [
        (
            "task-1",
            [
                {
                    "repo_id": "repo-1",
                    "repo_path": "/tmp/repo-one",
                    "target_branch": "main",
                },
                {
                    "repo_id": "repo-2",
                    "repo_path": "/tmp/repo-two",
                    "target_branch": "develop",
                },
            ],
        )
    ]


@pytest.mark.asyncio
async def test_workspace_cleanup_calls_sdk_method() -> None:
    sdk = _FakeWorkspaceCleanupSdk()
    api = CoreBackedApi(sdk)

    cleaned = await api.cleanup_orphaned_workspaces({"task-1", "task-2"})

    assert cleaned == ["ws-cleaned"]
    assert sdk.received_task_ids == [{"task-1", "task-2"}]


@pytest.mark.asyncio
async def test_runtime_reconcile_updates_runtime_cache_for_sync_getters() -> None:
    sdk = _FakeRuntimeSdk()
    sdk.snapshots = [
        {"task_id": "task-1", "runtime": {"is_running": True, "is_blocked": False}},
        {"task_id": "task-2", "runtime": {"is_running": False, "is_blocked": True}},
    ]
    api = CoreBackedApi(sdk)

    await api.reconcile_running_tasks(["task-1", "task-2"])

    assert api.get_running_task_ids() == {"task-1"}
    assert api.is_automation_running("task-1") is True
    assert api.is_automation_running("task-2") is False
    assert api.get_runtime_view("task-2") == {"is_running": False, "is_blocked": True}

    sdk.snapshots = [{"task_id": "task-1", "runtime": {"is_running": False}}]
    await api.reconcile_running_tasks(["task-1", "task-2"])

    assert api.get_running_task_ids() == set()
    assert api.get_runtime_view("task-2") is None


@pytest.mark.asyncio
async def test_take_queued_message_returns_payload_object_from_sdk_response() -> None:
    api = CoreBackedApi(_FakeQueueSdk())

    queued = await api.take_queued_message("task-1", lane="review")

    assert queued is not None
    assert queued.content == "Please include risk notes."
    assert queued.author == "orchestrator-overlay"


@pytest.mark.asyncio
async def test_take_queued_message_returns_none_when_queue_empty() -> None:
    api = CoreBackedApi(_FakeQueueEmptySdk())

    queued = await api.take_queued_message("task-1", lane="review")

    assert queued is None


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


class _StartupMaintenanceApiStub:
    def __init__(self) -> None:
        self.list_tasks_calls = 0

    async def list_tasks(self, project_id: str | None = None) -> list[SimpleNamespace]:
        del project_id
        self.list_tasks_calls += 1
        return [SimpleNamespace(id="task-1"), SimpleNamespace(id="task-2")]


@pytest.mark.asyncio
async def test_run_startup_maintenance_reuses_single_task_snapshot(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    app = KaganApp(db_path=":memory:")
    api_stub = _StartupMaintenanceApiStub()
    app._ctx = SimpleNamespace(api=api_stub, active_project_id="proj-1")

    worktree_seen_ids: list[set[str]] = []
    session_seen_ids: list[set[str]] = []
    janitor_calls: list[None] = []

    async def _fake_reconcile_worktrees(*, valid_task_ids: set[str] | None = None) -> None:
        assert valid_task_ids is not None
        worktree_seen_ids.append(set(valid_task_ids))

    async def _fake_reconcile_sessions(*, valid_task_ids: set[str] | None = None) -> None:
        assert valid_task_ids is not None
        session_seen_ids.append(set(valid_task_ids))

    async def _fake_run_janitor() -> None:
        janitor_calls.append(None)

    monkeypatch.setattr(app, "_reconcile_worktrees", _fake_reconcile_worktrees)
    monkeypatch.setattr(app, "_reconcile_sessions", _fake_reconcile_sessions)
    monkeypatch.setattr(app, "_run_janitor", _fake_run_janitor)

    await app._run_startup_maintenance()

    assert api_stub.list_tasks_calls == 1
    assert worktree_seen_ids == [{"task-1", "task-2"}]
    assert session_seen_ids == [{"task-1", "task-2"}]
    assert len(janitor_calls) == 1


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
