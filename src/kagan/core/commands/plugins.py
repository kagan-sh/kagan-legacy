from __future__ import annotations

from typing import TYPE_CHECKING, Any

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


__all__ = [
    "invoke_plugin_with_actionable_errors",
    "require_plugin_operation_registered",
]
