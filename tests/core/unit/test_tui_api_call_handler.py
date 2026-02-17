"""Behavior-focused tests for TUI API call dispatch validation."""

from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock

import pytest

from kagan.core.commands.plugins import tui_api_call as handle_tui_api_call
from kagan.core.plugins.sdk import PluginManifest, PluginOperation
from kagan.core.policy import CapabilityProfile
from kagan.core.services.workspaces.service import JanitorResult
from kagan.version import get_kagan_version

if TYPE_CHECKING:
    from pathlib import Path


class _UiTestPlugin:
    def __init__(
        self,
        *,
        plugin_id: str,
        capability: str,
        describe_handler,
        action_method: str = "do_thing",
        action_handler=None,
        action_mutating: bool = True,
    ) -> None:
        self.manifest = PluginManifest(
            id=plugin_id,
            name=f"Test plugin {plugin_id}",
            version="0.0.0",
            entrypoint=f"tests:{plugin_id}",
            description="Unit test plugin",
        )
        self._capability = capability
        self._describe_handler = describe_handler
        self._action_method = action_method
        self._action_handler = action_handler
        self._action_mutating = action_mutating

    def register(self, api) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=self._capability,
                method="ui_describe",
                handler=self._describe_handler,
                minimum_profile=CapabilityProfile.MAINTAINER,
                mutating=False,
            )
        )
        if self._action_handler is not None:
            api.register_operation(
                PluginOperation(
                    plugin_id=self.manifest.id,
                    capability=self._capability,
                    method=self._action_method,
                    handler=self._action_handler,
                    minimum_profile=CapabilityProfile.MAINTAINER,
                    mutating=self._action_mutating,
                )
            )


async def test_tui_api_call_rejects_method_not_allowlisted(api_env) -> None:
    _, api, ctx = api_env
    ctx.api = api

    result = await handle_tui_api_call(
        ctx,
        {"method": "__getattribute__", "kwargs": {}},
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "__getattribute__"
    assert result["message"] == "Unsupported TUI API method: __getattribute__"


@pytest.mark.parametrize(
    ("repos_payload", "expected_message"),
    [
        (None, "repos must be a non-empty list"),
        ("not-a-list", "repos must be a non-empty list"),
        (
            [123],
            "Each repos item must be an object with repo_id, repo_path, and target_branch",
        ),
        (
            [{"repo_id": "repo-1", "repo_path": "/tmp/repo"}],
            "Each repos item must include non-empty repo_id, repo_path, and target_branch",
        ),
    ],
)
async def test_tui_api_call_provision_workspace_rejects_invalid_repos_payload(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
    repos_payload: object,
    expected_message: str,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    provision_workspace = AsyncMock(return_value="ws-1")
    monkeypatch.setattr(api, "provision_workspace", provision_workspace)

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "provision_workspace",
            "kwargs": {"task_id": "task-1", "repos": repos_payload},
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "provision_workspace"
    assert result["message"] == expected_message
    provision_workspace.assert_not_awaited()


async def test_tui_api_call_queue_message_rejects_invalid_lane_without_mutation(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    queue_message = AsyncMock(return_value={"ok": True})
    monkeypatch.setattr(api, "queue_message", queue_message)

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "queue_message",
            "kwargs": {
                "session_id": "session-1",
                "content": "hello",
                "lane": "invalid-lane",
            },
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "queue_message"
    assert result["message"] == "lane must be one of: implementation, review, planner"
    queue_message.assert_not_awaited()


@pytest.mark.parametrize("index", [True, "1", 1.5, None])
async def test_tui_api_call_remove_queued_message_rejects_bool_and_non_int_index(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
    index: object,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    remove_queued_message = AsyncMock(return_value=True)
    monkeypatch.setattr(api, "remove_queued_message", remove_queued_message)

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "remove_queued_message",
            "kwargs": {
                "session_id": "session-1",
                "lane": "review",
                "index": index,
            },
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "remove_queued_message"
    assert result["message"] == "index must be an integer"
    remove_queued_message.assert_not_awaited()


async def test_tui_api_call_dispatch_runtime_session_rejects_unknown_event(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    dispatch_runtime_session = AsyncMock()
    monkeypatch.setattr(api, "dispatch_runtime_session", dispatch_runtime_session)

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "dispatch_runtime_session",
            "kwargs": {"event": "unknown_event"},
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "dispatch_runtime_session"
    assert (
        result["message"]
        == "event must be one of: project_selected, repo_selected, repo_cleared, reset"
    )
    dispatch_runtime_session.assert_not_awaited()


async def test_tui_api_call_save_planner_draft_rejects_non_dict_entries(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    save_planner_draft = AsyncMock()
    monkeypatch.setattr(api, "save_planner_draft", save_planner_draft)

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "save_planner_draft",
            "kwargs": {
                "project_id": "project-1",
                "tasks_json": [{"title": "ok"}, "bad-entry"],
            },
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "save_planner_draft"
    assert result["message"] == "tasks_json items must be objects"
    save_planner_draft.assert_not_awaited()


async def test_tui_api_call_update_planner_draft_status_rejects_invalid_status(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    update_planner_draft_status = AsyncMock()
    monkeypatch.setattr(api, "update_planner_draft_status", update_planner_draft_status)

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "update_planner_draft_status",
            "kwargs": {"proposal_id": "proposal-1", "status": "invalid-status"},
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "update_planner_draft_status"
    assert result["message"] == "status must be one of: draft, approved, rejected"
    update_planner_draft_status.assert_not_awaited()


@pytest.mark.parametrize(
    "method_name", ["has_no_changes", "merge_task_direct", "close_exploratory"]
)
async def test_tui_api_call_resolve_task_methods_reject_missing_task_id(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
    method_name: str,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    method = AsyncMock()
    monkeypatch.setattr(api, method_name, method)

    result = await handle_tui_api_call(
        ctx,
        {
            "method": method_name,
            "kwargs": {},
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == method_name
    assert result["message"] == "task_id is required"
    method.assert_not_awaited()


async def test_tui_api_call_resolve_task_methods_reject_unknown_task_id(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    monkeypatch.setattr(api, "get_task", AsyncMock(return_value=None))
    has_no_changes = AsyncMock(return_value=False)
    monkeypatch.setattr(api, "has_no_changes", has_no_changes)

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "has_no_changes",
            "kwargs": {"task_id": "task-missing"},
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "has_no_changes"
    assert "Task task-missing not found" in result["message"]
    has_no_changes.assert_not_awaited()


async def test_tui_api_call_create_session_normalizes_worktree_path(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    create_session = AsyncMock(return_value={"session_name": "kagan-task-1", "backend": "tmux"})
    monkeypatch.setattr(api, "create_session", create_session)

    worktree = tmp_path / "ws" / ".." / "ws"
    result = await handle_tui_api_call(
        ctx,
        {
            "method": "create_session",
            "kwargs": {
                "task_id": "task-1",
                "reuse_if_exists": False,
                "worktree_path": str(worktree),
            },
        },
    )

    assert result["success"] is True
    assert result["method"] == "create_session"
    assert result["value"]["session_name"] == "kagan-task-1"
    create_session.assert_awaited_once_with(
        "task-1",
        worktree_path=worktree.expanduser().resolve(strict=False),
        reuse_if_exists=False,
    )


async def test_tui_api_call_run_workspace_janitor_returns_stable_user_payload(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    run_workspace_janitor = AsyncMock(
        return_value=JanitorResult(
            worktrees_pruned=2,
            branches_deleted=["feature/a"],
            repos_processed=["repo-1"],
        )
    )
    monkeypatch.setattr(api, "run_workspace_janitor", run_workspace_janitor)

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "run_workspace_janitor",
            "kwargs": {
                "valid_workspace_ids": ["ws-2", "ws-1", "ws-2"],
                "prune_worktrees": True,
                "gc_branches": True,
            },
        },
    )

    assert result["success"] is True
    assert result["method"] == "run_workspace_janitor"
    assert result["value"] == {
        "worktrees_pruned": 2,
        "branches_deleted": ["feature/a"],
        "repos_processed": ["repo-1"],
        "total_cleaned": 3,
    }
    run_workspace_janitor.assert_awaited_once_with(
        {"ws-1", "ws-2"},
        prune_worktrees=True,
        gc_branches=True,
    )


async def test_tui_api_call_rejects_unsupported_transport_value_type(
    api_env,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    get_task = AsyncMock(return_value=object())
    monkeypatch.setattr(api, "get_task", get_task)

    result = await handle_tui_api_call(
        ctx,
        {"method": "get_task", "kwargs": {"task_id": "task-1"}},
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "get_task"
    assert result["message"] == "Unsupported TUI transport value type: object"
    get_task.assert_awaited_once_with("task-1")


async def test_tui_api_call_invoke_plugin_rejects_unregistered_operation(api_env) -> None:
    _, api, ctx = api_env
    ctx.api = api

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "invoke_plugin",
            "kwargs": {"capability": "unknown_capability", "method": "unknown_method"},
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "invoke_plugin"
    assert (
        result["message"]
        == "Plugin operation is not registered: unknown_capability.unknown_method. "
        "Ensure the plugin is installed and registered, then retry."
    )


async def test_tui_api_call_rejects_removed_github_alias_method(api_env) -> None:
    _, api, ctx = api_env
    ctx.api = api

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "github_sync_issues",
            "kwargs": {"project_id": "project-1", "repo_id": "repo-1"},
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "github_sync_issues"
    assert result["message"] == "Unsupported TUI API method: github_sync_issues"


async def test_plugin_ui_catalog_rejects_invalid_project_id(api_env) -> None:
    _, api, ctx = api_env
    ctx.api = api

    result = await handle_tui_api_call(
        ctx,
        {"method": "plugin_ui_catalog", "kwargs": {"project_id": "   "}},
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "plugin_ui_catalog"
    assert result["message"] == "project_id is required"


async def test_plugin_ui_catalog_filters_non_allowlisted_plugins(api_env) -> None:
    _, api, ctx = api_env
    ctx.api = api
    ctx.config.ui.tui_plugin_ui_allowlist = ["allowed"]

    allowed_handler = AsyncMock(
        return_value={
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "allowed",
                    "action_id": "do",
                    "surface": "kanban.repo_actions",
                    "label": "Do",
                    "operation": {"capability": "allowed_cap", "method": "do_thing"},
                }
            ],
        }
    )
    denied_handler = AsyncMock(
        return_value={
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "denied",
                    "action_id": "do",
                    "surface": "kanban.repo_actions",
                    "label": "Do",
                    "operation": {"capability": "denied_cap", "method": "do_thing"},
                }
            ],
        }
    )
    ctx.plugin_registry.register_plugin(
        _UiTestPlugin(
            plugin_id="allowed",
            capability="allowed_cap",
            describe_handler=allowed_handler,
        )
    )
    ctx.plugin_registry.register_plugin(
        _UiTestPlugin(
            plugin_id="denied",
            capability="denied_cap",
            describe_handler=denied_handler,
        )
    )

    result = await handle_tui_api_call(
        ctx,
        {"method": "plugin_ui_catalog", "kwargs": {"project_id": ctx.active_project_id}},
    )

    assert result["success"] is True
    value = result["value"]
    assert isinstance(value, dict)
    actions = value.get("actions", [])
    assert isinstance(actions, list)
    assert {item["plugin_id"] for item in actions} == {"allowed"}


async def test_plugin_ui_catalog_drops_invalid_schema_objects_but_returns_valid_catalog(
    api_env,
) -> None:
    _, api, ctx = api_env
    ctx.api = api
    ctx.config.ui.tui_plugin_ui_allowlist = ["allowed"]

    handler = AsyncMock(
        return_value={
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "allowed",
                    "action_id": "ok",
                    "surface": "kanban.repo_actions",
                    "label": "OK",
                    "operation": {"capability": "allowed_cap", "method": "do_thing"},
                },
                {
                    "plugin_id": "allowed",
                    "surface": "kanban.repo_actions",
                    "label": "Missing action_id",
                    "operation": {"capability": "allowed_cap", "method": "do_thing"},
                },
            ],
        }
    )
    ctx.plugin_registry.register_plugin(
        _UiTestPlugin(
            plugin_id="allowed",
            capability="allowed_cap",
            describe_handler=handler,
        )
    )

    result = await handle_tui_api_call(
        ctx,
        {"method": "plugin_ui_catalog", "kwargs": {"project_id": ctx.active_project_id}},
    )

    assert result["success"] is True
    value = result["value"]
    assert isinstance(value, dict)
    actions = value.get("actions", [])
    assert isinstance(actions, list)
    assert [item["action_id"] for item in actions] == ["ok"]


async def test_plugin_ui_invoke_rejects_unknown_action_with_invalid_params(api_env) -> None:
    _, api, ctx = api_env
    ctx.api = api
    ctx.config.ui.tui_plugin_ui_allowlist = ["allowed"]

    describe_handler = AsyncMock(
        return_value={
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "allowed",
                    "action_id": "known",
                    "surface": "kanban.repo_actions",
                    "label": "Known",
                    "operation": {"capability": "allowed_cap", "method": "do_thing"},
                }
            ],
        }
    )
    action_handler = AsyncMock(return_value={"success": True})
    ctx.plugin_registry.register_plugin(
        _UiTestPlugin(
            plugin_id="allowed",
            capability="allowed_cap",
            describe_handler=describe_handler,
            action_handler=action_handler,
        )
    )

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "plugin_ui_invoke",
            "kwargs": {
                "project_id": ctx.active_project_id,
                "plugin_id": "allowed",
                "action_id": "missing",
            },
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "plugin_ui_invoke"
    assert result["message"] == "Unknown plugin action: allowed.missing"
    action_handler.assert_not_awaited()


async def test_plugin_ui_invoke_rejects_missing_required_form_fields(api_env) -> None:
    _, api, ctx = api_env
    ctx.api = api
    ctx.config.ui.tui_plugin_ui_allowlist = ["allowed"]

    describe_handler = AsyncMock(
        return_value={
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "allowed",
                    "action_id": "needs_form",
                    "surface": "kanban.repo_actions",
                    "label": "Needs form",
                    "operation": {"capability": "allowed_cap", "method": "do_thing"},
                    "form_id": "form-1",
                }
            ],
            "forms": [
                {
                    "form_id": "form-1",
                    "title": "Form",
                    "fields": [{"name": "repo_id", "kind": "text", "required": True}],
                }
            ],
        }
    )
    action_handler = AsyncMock(return_value={"success": True})
    ctx.plugin_registry.register_plugin(
        _UiTestPlugin(
            plugin_id="allowed",
            capability="allowed_cap",
            describe_handler=describe_handler,
            action_handler=action_handler,
        )
    )

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "plugin_ui_invoke",
            "kwargs": {
                "project_id": ctx.active_project_id,
                "plugin_id": "allowed",
                "action_id": "needs_form",
                "inputs": {},
            },
        },
    )

    assert result["success"] is False
    assert result["code"] == "INVALID_PARAMS"
    assert result["method"] == "plugin_ui_invoke"
    assert result["message"] == "Missing required input field(s): repo_id"
    action_handler.assert_not_awaited()


async def test_plugin_ui_invoke_returns_stable_error_shape_on_plugin_failure(api_env) -> None:
    _, api, ctx = api_env
    ctx.api = api
    ctx.config.ui.tui_plugin_ui_allowlist = ["allowed"]

    describe_handler = AsyncMock(
        return_value={
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "allowed",
                    "action_id": "fail",
                    "surface": "kanban.repo_actions",
                    "label": "Fail",
                    "operation": {"capability": "allowed_cap", "method": "do_thing"},
                }
            ],
        }
    )
    action_handler = AsyncMock(return_value={"success": False, "code": "BOOM", "message": "Nope"})
    ctx.plugin_registry.register_plugin(
        _UiTestPlugin(
            plugin_id="allowed",
            capability="allowed_cap",
            describe_handler=describe_handler,
            action_handler=action_handler,
        )
    )

    result = await handle_tui_api_call(
        ctx,
        {
            "method": "plugin_ui_invoke",
            "kwargs": {
                "project_id": ctx.active_project_id,
                "plugin_id": "allowed",
                "action_id": "fail",
            },
        },
    )

    assert result["success"] is True
    payload = result["value"]
    assert payload["ok"] is False
    assert payload["code"] == "BOOM"
    assert payload["message"] == "Nope"


async def test_plugin_ui_invoke_enforces_plugin_profile_policy_via_request_context(api_env) -> None:
    from kagan.core.ipc.contracts import CoreRequest
    from kagan.core.policy import (
        AuthorizationPolicy,
        RequestContext,
        SessionBinding,
        SessionNamespace,
        SessionOrigin,
        request_context,
    )

    _, api, ctx = api_env
    ctx.api = api
    ctx.config.ui.tui_plugin_ui_allowlist = ["allowed"]

    describe_handler = AsyncMock(
        return_value={
            "schema_version": "1",
            "actions": [
                {
                    "plugin_id": "allowed",
                    "action_id": "do",
                    "surface": "kanban.repo_actions",
                    "label": "Do",
                    "operation": {"capability": "allowed_cap", "method": "do_thing"},
                }
            ],
        }
    )
    action_handler = AsyncMock(return_value={"success": True})

    class _Plugin:
        manifest = PluginManifest(
            id="allowed",
            name="Allowed",
            version="0.0.0",
            entrypoint="tests",
            description="test",
        )

        def register(self, api) -> None:
            api.register_operation(
                PluginOperation(
                    plugin_id="allowed",
                    capability="allowed_cap",
                    method="ui_describe",
                    handler=describe_handler,
                    minimum_profile=CapabilityProfile.VIEWER,
                    mutating=False,
                )
            )
            api.register_operation(
                PluginOperation(
                    plugin_id="allowed",
                    capability="allowed_cap",
                    method="do_thing",
                    handler=action_handler,
                    minimum_profile=CapabilityProfile.MAINTAINER,
                    mutating=True,
                )
            )

    ctx.plugin_registry.register_plugin(_Plugin())

    binding = SessionBinding(
        policy=AuthorizationPolicy("operator"),
        origin=SessionOrigin.TUI,
        namespace=SessionNamespace.TUI,
        scope_id="",
    )
    request = CoreRequest(
        session_id="operator-session",
        session_origin="tui",
        client_version=get_kagan_version(),
        capability="tui",
        method="api_call",
        params={},
    )

    with request_context(RequestContext(request=request, binding=binding)):
        result = await handle_tui_api_call(
            ctx,
            {
                "method": "plugin_ui_invoke",
                "kwargs": {
                    "project_id": ctx.active_project_id,
                    "plugin_id": "allowed",
                    "action_id": "do",
                },
            },
        )

    assert result["success"] is True
    payload = result["value"]
    assert payload["ok"] is False
    assert payload["code"] == "AUTHORIZATION_DENIED"
    action_handler.assert_not_awaited()
