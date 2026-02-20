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
        return all(c.passed for c in self.checks)

    @property
    def pass_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def fail_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)

    def _add(self, name: str, ok: bool, msg: str) -> None:
        self.checks.append(ConformanceCheckResult(name=name, passed=ok, message=msg))


class _CaptureApi(PluginRegistrationApi):
    """Captures operations during conformance checking without side effects."""

    def __init__(self) -> None:
        self.operations: list[PluginOperation] = []

    def register_operation(self, operation: PluginOperation) -> None:
        self.operations.append(operation)


def _is_async_2arg(handler: Any) -> bool:
    if not callable(handler) or not inspect.iscoroutinefunction(handler):
        return False
    params = [p for p in inspect.signature(handler).parameters.values() if p.name != "self"]
    return len(params) == 2


def _ok(condition: bool, pass_msg: str, fail_msg: str) -> str:
    return pass_msg if condition else fail_msg


class PluginConformanceRunner:
    """Validates a plugin instance against the Kagan plugin SDK contract."""

    def check(self, plugin: Any) -> ConformanceReport:
        """Run all conformance checks against a plugin instance."""
        manifest = getattr(plugin, "manifest", None)
        pid = manifest.id if isinstance(manifest, PluginManifest) else "<unknown>"
        r = ConformanceReport(plugin_id=pid)

        # Protocol checks
        has_m = hasattr(plugin, "manifest")
        r._add("plugin_has_manifest", has_m, _ok(has_m, "has 'manifest' attribute", "missing"))
        has_reg = hasattr(plugin, "register") and callable(getattr(plugin, "register", None))
        r._add("plugin_has_register", has_reg, _ok(has_reg, "has 'register' method", "missing"))
        if has_reg:
            n = len(list(inspect.signature(plugin.register).parameters.keys()))
            r._add(
                "register_signature",
                n == 1,
                _ok(
                    n == 1,
                    "register(api) signature is correct",
                    f"should accept 1 parameter, got {n}",
                ),
            )
        if not r.passed:
            return r

        # Manifest checks
        is_model = isinstance(manifest, PluginManifest)
        r._add(
            "manifest_type",
            is_model,
            _ok(
                is_model, "Manifest is a PluginManifest instance", f"got {type(manifest).__name__}"
            ),
        )
        if is_model:
            id_ok = bool(_PLUGIN_ID_PATTERN.fullmatch(manifest.id))
            r._add(
                "manifest_id_pattern",
                id_ok,
                _ok(
                    id_ok,
                    f"Plugin ID '{manifest.id}' matches required pattern",
                    f"must match {_PLUGIN_ID_PATTERN.pattern}",
                ),
            )
            has_req = bool(manifest.name and manifest.version and manifest.entrypoint)
            r._add(
                "manifest_required_fields",
                has_req,
                _ok(has_req, "has all required fields", "missing name, version, or entrypoint"),
            )

        # Registration checks
        api = _CaptureApi()
        try:
            plugin.register(api)
            r._add("register_executes", True, "register() completed without errors")
        except Exception as exc:
            r._add("register_executes", False, f"register() raised {type(exc).__name__}: {exc}")
            return r
        r._add(
            "registers_operations",
            bool(api.operations),
            f"Plugin registered {len(api.operations)} operation(s)"
            if api.operations
            else "Plugin must register at least one operation",
        )
        for op in api.operations:
            pfx = f"operation_{op.capability}_{op.method}"
            ok = op.plugin_id == pid
            r._add(
                f"{pfx}_plugin_id", ok, _ok(ok, "matches manifest", f"'{op.plugin_id}' != '{pid}'")
            )
            ok = bool(_CAPABILITY_PATTERN.fullmatch(op.capability))
            cap_pat = _CAPABILITY_PATTERN.pattern
            r._add(
                f"{pfx}_capability_pattern",
                ok,
                _ok(ok, f"'{op.capability}' matches", f"must match {cap_pat}"),
            )
            ok = bool(_METHOD_PATTERN.fullmatch(op.method))
            meth_pat = _METHOD_PATTERN.pattern
            r._add(
                f"{pfx}_method_pattern",
                ok,
                _ok(ok, f"'{op.method}' matches", f"must match {meth_pat}"),
            )
            ok = _is_async_2arg(op.handler)
            r._add(
                f"{pfx}_handler_signature",
                ok,
                _ok(ok, "correct async (ctx, params) signature", "invalid handler signature"),
            )

        # Capability contract checks
        if not isinstance(plugin, PluginCapabilityProvider):
            r._add("capability_contract", True, "PluginCapabilityProvider not declared (skipped)")
        else:
            try:
                specs = plugin.capabilities
            except Exception as exc:
                r._add(
                    "capability_contract", False, f"capabilities raised {type(exc).__name__}: {exc}"
                )
                return r
            is_tuple = isinstance(specs, tuple)
            r._add(
                "capability_contract_type",
                is_tuple,
                _ok(is_tuple, "returns a tuple", f"got {type(specs).__name__}"),
            )
            if is_tuple:
                valid = all(
                    isinstance(s, PluginCapabilitySpec)
                    and bool(_CAPABILITY_PATTERN.fullmatch(s.capability))
                    and s.methods
                    and all(_METHOD_PATTERN.fullmatch(m) for m in s.methods)
                    for s in specs
                )
                r._add(
                    "capability_specs_valid",
                    valid,
                    _ok(valid, "All specs valid", "invalid capability specs"),
                )

        # Lifecycle checks
        if not isinstance(plugin, PluginLifecycle):
            r._add("lifecycle", True, "PluginLifecycle not implemented (skipped)")
        else:
            for name, attr in [("startup", "on_core_startup"), ("shutdown", "on_core_shutdown")]:
                ok = hasattr(plugin, attr) and inspect.iscoroutinefunction(getattr(plugin, attr))
                r._add(
                    f"lifecycle_{name}", ok, _ok(ok, f"{attr} is async", f"{attr} must be async")
                )

        return r

    def check_full_registration(self, plugin: Any) -> ConformanceReport:
        """Run conformance checks including full PluginRegistry registration."""
        report = self.check(plugin)
        if not report.passed:
            return report
        registry = PluginRegistry()
        try:
            registry.register_plugin(plugin)
            report._add(
                "full_registry_registration",
                True,
                "Plugin registered successfully through PluginRegistry",
            )
        except (TypeError, ValueError) as exc:
            report._add(
                "full_registry_registration", False, f"PluginRegistry.register_plugin failed: {exc}"
            )
        return report


__all__ = [
    "ConformanceCheckResult",
    "ConformanceReport",
    "PluginConformanceRunner",
]
