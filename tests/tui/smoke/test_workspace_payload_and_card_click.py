from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

import pytest

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


@pytest.mark.asyncio
async def test_list_workspaces_normalizes_dict_payloads_to_workspace_views() -> None:
    api = CoreBackedApi(_FakeWorkspaceSdk())

    workspaces = await api.list_workspaces()

    assert all(isinstance(item, WorkspaceView) for item in workspaces)
    assert [item.id for item in workspaces] == ["ws-1", "ws-2"]
    assert workspaces[0].branch_name == "task-abc"
    assert workspaces[1].status == "archived"


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

    async def run_workspace_janitor(self, valid_workspace_ids: set[str]):
        self.received_ids = set(valid_workspace_ids)
        return None


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
