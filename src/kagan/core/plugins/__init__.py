"""Provider-neutral plugin SDK surface for core extensions."""

from kagan.core.plugins.sdk import (
    Plugin,
    PluginCapabilityProvider,
    PluginCapabilitySpec,
    PluginLifecycle,
    PluginManifest,
    PluginOperation,
    PluginOperationHandler,
    PluginPolicyDecision,
    PluginRegistrationApi,
    PluginRegistry,
)

__all__ = [
    "Plugin",
    "PluginCapabilityProvider",
    "PluginCapabilitySpec",
    "PluginLifecycle",
    "PluginManifest",
    "PluginOperation",
    "PluginOperationHandler",
    "PluginPolicyDecision",
    "PluginRegistrationApi",
    "PluginRegistry",
]
