"""Provider-neutral plugin SDK surface for core extensions."""

from kagan.core.plugins.sdk import (
    JsonPluginManifestLoader,
    Plugin,
    PluginCapabilityProvider,
    PluginCapabilitySpec,
    PluginLifecycle,
    PluginManifest,
    PluginManifestLoader,
    PluginOperation,
    PluginOperationHandler,
    PluginPolicyContext,
    PluginPolicyDecision,
    PluginPolicyHook,
    PluginRegistrationApi,
    PluginRegistry,
)

__all__ = [
    "JsonPluginManifestLoader",
    "Plugin",
    "PluginCapabilityProvider",
    "PluginCapabilitySpec",
    "PluginLifecycle",
    "PluginManifest",
    "PluginManifestLoader",
    "PluginOperation",
    "PluginOperationHandler",
    "PluginPolicyContext",
    "PluginPolicyDecision",
    "PluginPolicyHook",
    "PluginRegistrationApi",
    "PluginRegistry",
]
