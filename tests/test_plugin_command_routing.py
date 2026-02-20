from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from kagan.core.commands import build_command_router


class _PluginRegistryStub:
    def __init__(self) -> None:
        self._ops: dict[tuple[str, str], object] = {
            ("kagan_github", "sync_issues"): object(),
        }

    def resolve_operation(self, capability: str, method: str) -> object | None:
        return self._ops.get((capability, method))


class _ApiStub:
    def __init__(self) -> None:
        self.invoke_calls: list[dict[str, Any]] = []
        self.catalog_calls: list[dict[str, Any]] = []
        self.ui_invoke_calls: list[dict[str, Any]] = []

    async def invoke_plugin(
        self,
        capability: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.invoke_calls.append(
            {
                "capability": capability,
                "method": method,
                "params": dict(params or {}),
            }
        )
        return {"ok": True, "code": "SYNCED"}

    async def plugin_ui_catalog(
        self,
        *,
        project_id: str,
        repo_id: str | None = None,
    ) -> dict[str, Any]:
        self.catalog_calls.append({"project_id": project_id, "repo_id": repo_id})
        return {
            "schema_version": "1",
            "actions": [{"plugin_id": "official.github", "action_id": "connect_repo"}],
            "forms": [],
            "badges": [],
        }

    async def plugin_ui_invoke(
        self,
        *,
        project_id: str,
        plugin_id: str,
        action_id: str,
        repo_id: str | None = None,
        inputs: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.ui_invoke_calls.append(
            {
                "project_id": project_id,
                "plugin_id": plugin_id,
                "action_id": action_id,
                "repo_id": repo_id,
                "inputs": dict(inputs or {}),
            }
        )
        return {
            "ok": True,
            "code": "OK",
            "message": "Invoked",
            "data": {"success": True},
            "refresh": {"repo": True, "tasks": False, "sessions": False},
        }


@pytest.mark.asyncio
async def test_plugins_commands_are_registered_and_dispatchable() -> None:
    router = build_command_router()
    api = _ApiStub()
    ctx = SimpleNamespace(api=api, plugin_registry=_PluginRegistryStub())

    assert router.has_command("plugins", "invoke") is True
    assert router.has_command("plugins", "plugin_ui_catalog") is True
    assert router.has_command("plugins", "plugin_ui_invoke") is True

    invoke_result = await router.dispatch(
        "plugins",
        "invoke",
        ctx,
        {
            "capability": "kagan_github",
            "method": "sync_issues",
            "params": {"project_id": "proj-1"},
        },
    )
    assert invoke_result == {
        "success": True,
        "result": {"ok": True, "code": "SYNCED"},
        "error": None,
    }
    assert api.invoke_calls == [
        {
            "capability": "kagan_github",
            "method": "sync_issues",
            "params": {"project_id": "proj-1"},
        }
    ]

    catalog_result = await router.dispatch(
        "plugins",
        "plugin_ui_catalog",
        ctx,
        {"project_id": "proj-1"},
    )
    assert catalog_result is not None
    assert catalog_result["actions"][0]["action_id"] == "connect_repo"
    assert api.catalog_calls == [{"project_id": "proj-1", "repo_id": None}]

    ui_invoke_result = await router.dispatch(
        "plugins",
        "plugin_ui_invoke",
        ctx,
        {
            "project_id": "proj-1",
            "plugin_id": "official.github",
            "action_id": "sync_issues",
            "inputs": {"repo_id": "repo-1"},
        },
    )
    assert ui_invoke_result is not None
    assert ui_invoke_result["ok"] is True
    assert api.ui_invoke_calls == [
        {
            "project_id": "proj-1",
            "plugin_id": "official.github",
            "action_id": "sync_issues",
            "repo_id": None,
            "inputs": {"repo_id": "repo-1"},
        }
    ]

