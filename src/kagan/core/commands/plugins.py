from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core.policy import command
from kagan.core.scalars import non_empty_str

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


def require_plugin_operation_registered(
    ctx: AppContext,
    *,
    capability: str,
    method: str,
) -> None:
    plugin_registry = getattr(ctx, "plugin_registry", None)
    if plugin_registry is None:
        raise ValueError(
            f"Plugin operation is not registered: {capability}.{method}. "
            "Ensure the plugin is installed and registered, then retry."
        )

    resolve_operation = getattr(plugin_registry, "resolve_operation", None)
    if not callable(resolve_operation):
        raise ValueError("Plugin registry cannot resolve plugin operations")

    operation = resolve_operation(capability, method)
    if operation is None:
        raise ValueError(
            f"Plugin operation is not registered: {capability}.{method}. "
            "Ensure the plugin is installed and registered, then retry."
        )


async def invoke_plugin_with_actionable_errors(
    ctx: AppContext,
    *,
    capability: str,
    method: str,
    params: dict[str, Any] | None = None,
) -> dict[str, Any]:
    api = getattr(ctx, "api", None)
    if api is None:
        raise ValueError("API context is not initialized")

    try:
        return await api.invoke_plugin(capability, method, params)
    except RuntimeError as exc:
        raise ValueError(
            f"Plugin invocation failed for {capability}.{method}: {exc}. "
            "Ensure the plugin is healthy and registered, then retry."
        ) from exc


@command(
    "plugins",
    "invoke",
    profile="maintainer",
    mutating=True,
    description="Invoke a plugin operation by capability and method.",
)
async def invoke_plugin(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    capability = non_empty_str(params.get("capability"))
    if capability is None:
        raise ValueError("capability is required")

    method = non_empty_str(params.get("method"))
    if method is None:
        raise ValueError("method is required")

    raw_params = params.get("params")
    if raw_params is None:
        plugin_params: dict[str, Any] = {}
    elif isinstance(raw_params, dict):
        plugin_params = dict(raw_params)
    else:
        raise ValueError("params must be an object when provided")

    require_plugin_operation_registered(ctx, capability=capability, method=method)
    result = await invoke_plugin_with_actionable_errors(
        ctx,
        capability=capability,
        method=method,
        params=plugin_params,
    )
    return {
        "success": True,
        "result": result,
        "error": None,
    }


@command(
    "plugins",
    "plugin_ui_catalog",
    description="Return declarative plugin UI catalog for the active project/repo.",
)
async def plugin_ui_catalog(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = getattr(ctx, "api", None)
    if api is None:
        raise ValueError("API context is not initialized")

    project_id = non_empty_str(params.get("project_id"))
    if project_id is None:
        raise ValueError("project_id is required")

    repo_id = non_empty_str(params.get("repo_id"))
    return await api.plugin_ui_catalog(project_id=project_id, repo_id=repo_id)


@command(
    "plugins",
    "plugin_ui_invoke",
    profile="maintainer",
    mutating=True,
    description="Invoke a declarative plugin UI action.",
)
async def plugin_ui_invoke(ctx: AppContext, params: dict[str, Any]) -> dict[str, Any]:
    api = getattr(ctx, "api", None)
    if api is None:
        raise ValueError("API context is not initialized")

    project_id = non_empty_str(params.get("project_id"))
    if project_id is None:
        raise ValueError("project_id is required")

    plugin_id = non_empty_str(params.get("plugin_id"))
    if plugin_id is None:
        raise ValueError("plugin_id is required")

    action_id = non_empty_str(params.get("action_id"))
    if action_id is None:
        raise ValueError("action_id is required")

    repo_id = non_empty_str(params.get("repo_id"))
    raw_inputs = params.get("inputs")
    if raw_inputs is None:
        inputs: dict[str, Any] | None = None
    elif isinstance(raw_inputs, dict):
        inputs = dict(raw_inputs)
    else:
        raise ValueError("inputs must be an object when provided")

    return await api.plugin_ui_invoke(
        project_id=project_id,
        plugin_id=plugin_id,
        action_id=action_id,
        repo_id=repo_id,
        inputs=inputs,
    )


__all__ = [
    "invoke_plugin",
    "invoke_plugin_with_actionable_errors",
    "plugin_ui_catalog",
    "plugin_ui_invoke",
    "require_plugin_operation_registered",
]
