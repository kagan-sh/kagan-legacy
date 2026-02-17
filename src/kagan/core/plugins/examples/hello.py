"""Hello-world plugin demonstrating the full SDK lifecycle.

This example registers one operation and one policy hook, plus optional
lifecycle hooks (on_core_startup / on_core_shutdown).  Use it as a
reference when building your first plugin.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from kagan.core.plugins.sdk import (
    PluginCapabilityProvider,
    PluginCapabilitySpec,
    PluginManifest,
    PluginOperation,
    PluginPolicyContext,
    PluginPolicyDecision,
    PluginRegistrationApi,
)
from kagan.core.policy import CapabilityProfile

if TYPE_CHECKING:
    from kagan.core.bootstrap import AppContext


class HelloPlugin(PluginCapabilityProvider):
    """Minimal 'hello world' plugin for learning and scaffold validation."""

    manifest = PluginManifest(
        id="example.hello",
        name="Hello Plugin",
        version="0.1.0",
        entrypoint="kagan.core.plugins.examples.hello:HelloPlugin",
        description="Hello-world example plugin demonstrating the full SDK lifecycle.",
    )

    @property
    def capabilities(self) -> tuple[PluginCapabilitySpec, ...]:
        return (
            PluginCapabilitySpec(
                capability="hello",
                methods=("greet",),
            ),
        )

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability="hello",
                method="greet",
                handler=_greet_handler,
                minimum_profile=CapabilityProfile.VIEWER,
                mutating=False,
                description="Return a greeting message.",
            )
        )
        api.register_policy_hook(
            plugin_id=self.manifest.id,
            capability="hello",
            method="greet",
            hook=_greet_policy_hook,
        )

    # -- Optional lifecycle hooks (PluginLifecycle protocol) --

    async def on_core_startup(self, ctx: AppContext) -> None:
        """Called after core context initialization."""

    async def on_core_shutdown(self, ctx: AppContext) -> None:
        """Called during core teardown."""


async def _greet_handler(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    del ctx
    name = params.get("name", "World")
    return {
        "success": True,
        "plugin_id": HelloPlugin.manifest.id,
        "message": f"Hello, {name}!",
    }


def _greet_policy_hook(context: PluginPolicyContext) -> PluginPolicyDecision | None:
    if context.params.get("blocked") is True:
        return PluginPolicyDecision(
            allowed=False,
            code="PLUGIN_POLICY_DENIED",
            message=f"Plugin '{context.plugin_id}' denied: blocked=true",
        )
    return None


__all__ = ["HelloPlugin"]
