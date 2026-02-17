"""Plugin conformance test harness for validating third-party plugins against the SDK contract."""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any

from kagan.core.plugins.sdk import (
    _CAPABILITY_PATTERN,
    _METHOD_PATTERN,
    _PLUGIN_ID_PATTERN,
    PluginCapabilityProvider,
    PluginCapabilitySpec,
    PluginLifecycle,
    PluginManifest,
    PluginOperation,
    PluginRegistrationApi,
    PluginRegistry,
)


@dataclass(frozen=True, slots=True)
class ConformanceCheckResult:
    """Result of a single conformance check."""

    name: str
    passed: bool
    message: str


@dataclass(slots=True)
class ConformanceReport:
    """Aggregated results from a conformance run."""

    plugin_id: str
    checks: list[ConformanceCheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(check.passed for check in self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for check in self.checks if check.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for check in self.checks if not check.passed)


class _ConformanceRegistrationApi(PluginRegistrationApi):
    """Captures operations registered during conformance checking without side effects."""

    def __init__(self) -> None:
        self.operations: list[PluginOperation] = []

    def register_operation(self, operation: PluginOperation) -> None:
        self.operations.append(operation)

    def register_policy_hook(
        self,
        *,
        plugin_id: str,
        capability: str,
        method: str,
        hook: Any,
    ) -> None:
        pass


class PluginConformanceRunner:
    """Validates a plugin instance against the Kagan plugin SDK contract.

    Usage::

        runner = PluginConformanceRunner()
        report = runner.check(my_plugin)
        assert report.passed
    """

    def check(self, plugin: Any) -> ConformanceReport:
        """Run all conformance checks against a plugin instance."""
        plugin_id = _extract_plugin_id(plugin)
        report = ConformanceReport(plugin_id=plugin_id)

        self._check_plugin_protocol(plugin, report)
        if not report.passed:
            return report

        self._check_manifest(plugin, report)
        self._check_registration(plugin, report)
        self._check_capability_contract(plugin, report)
        self._check_lifecycle(plugin, report)

        return report

    def _check_plugin_protocol(self, plugin: Any, report: ConformanceReport) -> None:
        has_manifest = hasattr(plugin, "manifest")
        report.checks.append(
            ConformanceCheckResult(
                name="plugin_has_manifest",
                passed=has_manifest,
                message="Plugin has 'manifest' attribute"
                if has_manifest
                else "Plugin missing 'manifest' attribute",
            )
        )

        has_register = hasattr(plugin, "register") and callable(getattr(plugin, "register", None))
        report.checks.append(
            ConformanceCheckResult(
                name="plugin_has_register",
                passed=has_register,
                message="Plugin has 'register' method"
                if has_register
                else "Plugin missing callable 'register' method",
            )
        )

        if has_register:
            sig = inspect.signature(plugin.register)
            params = list(sig.parameters.keys())
            # Expect (self, api) — for bound method, self is excluded
            valid_sig = len(params) == 1
            report.checks.append(
                ConformanceCheckResult(
                    name="register_signature",
                    passed=valid_sig,
                    message="register(api) signature is correct"
                    if valid_sig
                    else f"register() should accept exactly 1 parameter (api), got {len(params)}",
                )
            )

    def _check_manifest(self, plugin: Any, report: ConformanceReport) -> None:
        manifest = getattr(plugin, "manifest", None)

        is_model = isinstance(manifest, PluginManifest)
        report.checks.append(
            ConformanceCheckResult(
                name="manifest_type",
                passed=is_model,
                message="Manifest is a PluginManifest instance"
                if is_model
                else f"Manifest must be PluginManifest, got {type(manifest).__name__}",
            )
        )
        if not is_model:
            return

        id_valid = bool(_PLUGIN_ID_PATTERN.fullmatch(manifest.id))
        report.checks.append(
            ConformanceCheckResult(
                name="manifest_id_pattern",
                passed=id_valid,
                message=f"Plugin ID '{manifest.id}' matches required pattern"
                if id_valid
                else f"Plugin ID '{manifest.id}' must match {_PLUGIN_ID_PATTERN.pattern}",
            )
        )

        has_required = bool(manifest.name and manifest.version and manifest.entrypoint)
        report.checks.append(
            ConformanceCheckResult(
                name="manifest_required_fields",
                passed=has_required,
                message="Manifest has all required fields (name, version, entrypoint)"
                if has_required
                else "Manifest missing required fields: name, version, or entrypoint",
            )
        )

    def _check_registration(self, plugin: Any, report: ConformanceReport) -> None:
        api = _ConformanceRegistrationApi()
        try:
            plugin.register(api)
            register_ok = True
            register_msg = "register() completed without errors"
        except Exception as exc:
            register_ok = False
            register_msg = f"register() raised {type(exc).__name__}: {exc}"

        report.checks.append(
            ConformanceCheckResult(
                name="register_executes",
                passed=register_ok,
                message=register_msg,
            )
        )
        if not register_ok:
            return

        has_ops = len(api.operations) > 0
        report.checks.append(
            ConformanceCheckResult(
                name="registers_operations",
                passed=has_ops,
                message=f"Plugin registered {len(api.operations)} operation(s)"
                if has_ops
                else "Plugin must register at least one operation",
            )
        )

        manifest = plugin.manifest
        for op in api.operations:
            self._check_operation(op, manifest.id, report)

    def _check_operation(
        self, op: PluginOperation, plugin_id: str, report: ConformanceReport
    ) -> None:
        id_match = op.plugin_id == plugin_id
        report.checks.append(
            ConformanceCheckResult(
                name=f"operation_{op.capability}_{op.method}_plugin_id",
                passed=id_match,
                message="Operation plugin_id matches manifest"
                if id_match
                else f"Operation plugin_id '{op.plugin_id}' != manifest id '{plugin_id}'",
            )
        )

        cap_valid = bool(_CAPABILITY_PATTERN.fullmatch(op.capability))
        report.checks.append(
            ConformanceCheckResult(
                name=f"operation_{op.capability}_{op.method}_capability_pattern",
                passed=cap_valid,
                message=f"Capability '{op.capability}' matches pattern"
                if cap_valid
                else (f"Capability '{op.capability}' must match {_CAPABILITY_PATTERN.pattern}"),
            )
        )

        method_valid = bool(_METHOD_PATTERN.fullmatch(op.method))
        report.checks.append(
            ConformanceCheckResult(
                name=f"operation_{op.capability}_{op.method}_method_pattern",
                passed=method_valid,
                message=f"Method '{op.method}' matches pattern"
                if method_valid
                else f"Method '{op.method}' must match {_METHOD_PATTERN.pattern}",
            )
        )

        handler_ok = _check_handler_signature(op.handler)
        report.checks.append(
            ConformanceCheckResult(
                name=f"operation_{op.capability}_{op.method}_handler_signature",
                passed=handler_ok,
                message="Handler has correct async (ctx, params) signature"
                if handler_ok
                else "Handler must be async callable with (ctx, params) signature",
            )
        )

    def _check_capability_contract(self, plugin: Any, report: ConformanceReport) -> None:
        if not isinstance(plugin, PluginCapabilityProvider):
            report.checks.append(
                ConformanceCheckResult(
                    name="capability_contract",
                    passed=True,
                    message="Plugin does not declare PluginCapabilityProvider (optional, skipped)",
                )
            )
            return

        try:
            specs = plugin.capabilities
        except Exception as exc:
            report.checks.append(
                ConformanceCheckResult(
                    name="capability_contract",
                    passed=False,
                    message=f"capabilities property raised {type(exc).__name__}: {exc}",
                )
            )
            return

        is_tuple = isinstance(specs, tuple)
        report.checks.append(
            ConformanceCheckResult(
                name="capability_contract_type",
                passed=is_tuple,
                message="capabilities returns a tuple"
                if is_tuple
                else f"capabilities must return tuple, got {type(specs).__name__}",
            )
        )
        if not is_tuple:
            return

        all_valid = True
        for spec in specs:
            if not isinstance(spec, PluginCapabilitySpec):
                all_valid = False
                break
            if not _CAPABILITY_PATTERN.fullmatch(spec.capability):
                all_valid = False
                break
            if not spec.methods:
                all_valid = False
                break
            for method in spec.methods:
                if not _METHOD_PATTERN.fullmatch(method):
                    all_valid = False
                    break

        report.checks.append(
            ConformanceCheckResult(
                name="capability_specs_valid",
                passed=all_valid,
                message="All capability specs are valid"
                if all_valid
                else "One or more capability specs have invalid fields",
            )
        )

    def _check_lifecycle(self, plugin: Any, report: ConformanceReport) -> None:
        if not isinstance(plugin, PluginLifecycle):
            report.checks.append(
                ConformanceCheckResult(
                    name="lifecycle",
                    passed=True,
                    message="Plugin does not implement PluginLifecycle (optional, skipped)",
                )
            )
            return

        has_startup = hasattr(plugin, "on_core_startup") and inspect.iscoroutinefunction(
            plugin.on_core_startup
        )
        report.checks.append(
            ConformanceCheckResult(
                name="lifecycle_startup",
                passed=has_startup,
                message="on_core_startup is an async method"
                if has_startup
                else "on_core_startup must be an async method",
            )
        )

        has_shutdown = hasattr(plugin, "on_core_shutdown") and inspect.iscoroutinefunction(
            plugin.on_core_shutdown
        )
        report.checks.append(
            ConformanceCheckResult(
                name="lifecycle_shutdown",
                passed=has_shutdown,
                message="on_core_shutdown is an async method"
                if has_shutdown
                else "on_core_shutdown must be an async method",
            )
        )

    def check_full_registration(self, plugin: Any) -> ConformanceReport:
        """Run conformance checks including full PluginRegistry registration.

        This validates the plugin can be registered end-to-end through the real registry,
        which also validates capability contract matching against registered operations.
        """
        report = self.check(plugin)
        if not report.passed:
            return report

        registry = PluginRegistry()
        try:
            registry.register_plugin(plugin)
            report.checks.append(
                ConformanceCheckResult(
                    name="full_registry_registration",
                    passed=True,
                    message="Plugin registered successfully through PluginRegistry",
                )
            )
        except (TypeError, ValueError) as exc:
            report.checks.append(
                ConformanceCheckResult(
                    name="full_registry_registration",
                    passed=False,
                    message=f"PluginRegistry.register_plugin failed: {exc}",
                )
            )

        return report


def _extract_plugin_id(plugin: Any) -> str:
    manifest = getattr(plugin, "manifest", None)
    if isinstance(manifest, PluginManifest):
        return manifest.id
    return "<unknown>"


def _check_handler_signature(handler: Any) -> bool:
    if not callable(handler):
        return False
    if not inspect.iscoroutinefunction(handler):
        return False
    sig = inspect.signature(handler)
    params = [p for p in sig.parameters.values() if p.name != "self"]
    return len(params) == 2


__all__ = [
    "ConformanceCheckResult",
    "ConformanceReport",
    "PluginConformanceRunner",
]
