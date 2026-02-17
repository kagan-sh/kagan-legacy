"""Tests for the plugin conformance test harness."""

from __future__ import annotations

from typing import Any

from kagan.core.plugins.sdk import (
    PluginCapabilitySpec,
    PluginManifest,
    PluginOperation,
    PluginRegistrationApi,
)
from kagan.core.plugins.testing import (
    PluginConformanceRunner,
)
from kagan.core.policy import CapabilityProfile

# -- Valid plugin fixtures --


async def _noop_handler(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    return {"ok": True}


class _ValidPlugin:
    manifest = PluginManifest(
        id="test.valid",
        name="Valid Test Plugin",
        version="1.0.0",
        entrypoint="test.valid:Plugin",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability="testing",
                method="ping",
                handler=_noop_handler,
                minimum_profile=CapabilityProfile.MAINTAINER,
            )
        )


class _ValidCapabilityPlugin:
    manifest = PluginManifest(
        id="test.capability",
        name="Capability Plugin",
        version="1.0.0",
        entrypoint="test.capability:Plugin",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability="testing",
                method="cap_ping",
                handler=_noop_handler,
                minimum_profile=CapabilityProfile.MAINTAINER,
            )
        )

    @property
    def capabilities(self) -> tuple[PluginCapabilitySpec, ...]:
        return (PluginCapabilitySpec(capability="testing", methods=("cap_ping",)),)


class _ValidLifecyclePlugin(_ValidPlugin):
    async def on_core_startup(self, ctx: Any) -> None:
        pass

    async def on_core_shutdown(self, ctx: Any) -> None:
        pass


# -- Invalid plugin fixtures --


class _NoManifestPlugin:
    def register(self, api: PluginRegistrationApi) -> None:
        pass


class _DictManifestPlugin:
    manifest = {"id": "test.bad", "name": "Bad"}

    def register(self, api: PluginRegistrationApi) -> None:
        pass


class _NoRegisterPlugin:
    manifest = PluginManifest(
        id="test.noreg",
        name="No Register",
        version="1.0.0",
        entrypoint="test:Plugin",
    )


class _BadIdPlugin:
    manifest = PluginManifest(
        id="test.badid_ok",
        name="Bad ID",
        version="1.0.0",
        entrypoint="test:Plugin",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id="WRONG_ID",
                capability="testing",
                method="ping",
                handler=_noop_handler,
            )
        )


class _NoOperationsPlugin:
    manifest = PluginManifest(
        id="test.noops",
        name="No Ops",
        version="1.0.0",
        entrypoint="test:Plugin",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        pass


class _SyncHandlerPlugin:
    manifest = PluginManifest(
        id="test.sync",
        name="Sync Handler",
        version="1.0.0",
        entrypoint="test:Plugin",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability="testing",
                method="sync_op",
                handler=lambda ctx, params: {"ok": True},  # type: ignore[arg-type]
            )
        )


class _BadCapabilityContractPlugin:
    manifest = PluginManifest(
        id="test.badcap",
        name="Bad Cap",
        version="1.0.0",
        entrypoint="test:Plugin",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability="testing",
                method="cap_op",
                handler=_noop_handler,
            )
        )

    @property
    def capabilities(self) -> list[str]:
        return ["not", "a", "tuple"]


class _SyncLifecyclePlugin(_ValidPlugin):
    def on_core_startup(self, ctx: Any) -> None:
        pass

    def on_core_shutdown(self, ctx: Any) -> None:
        pass


class _RegisterExplodesPlugin:
    manifest = PluginManifest(
        id="test.explodes",
        name="Explodes",
        version="1.0.0",
        entrypoint="test:Plugin",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        msg = "boom"
        raise RuntimeError(msg)


class _BadRegisterSigPlugin:
    manifest = PluginManifest(
        id="test.badsig",
        name="Bad Sig",
        version="1.0.0",
        entrypoint="test:Plugin",
    )

    def register(self, api: PluginRegistrationApi, extra: str) -> None:
        pass


# -- Tests --


class TestValidPluginPassesAllChecks:
    def test_basic_valid_plugin(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_ValidPlugin())

        assert report.passed
        assert report.plugin_id == "test.valid"
        assert report.fail_count == 0
        assert report.pass_count > 0

    def test_valid_plugin_with_capability_contract(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_ValidCapabilityPlugin())

        assert report.passed

    def test_valid_plugin_with_lifecycle(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_ValidLifecyclePlugin())

        assert report.passed
        lifecycle_checks = [c for c in report.checks if c.name.startswith("lifecycle_")]
        assert len(lifecycle_checks) == 2
        assert all(c.passed for c in lifecycle_checks)

    def test_noop_example_plugin_passes(self) -> None:
        from kagan.core.plugins.examples.noop import NoOpExamplePlugin

        runner = PluginConformanceRunner()
        report = runner.check(NoOpExamplePlugin())

        assert report.passed

    def test_full_registration_valid_plugin(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check_full_registration(_ValidPlugin())

        assert report.passed
        reg_check = [c for c in report.checks if c.name == "full_registry_registration"]
        assert len(reg_check) == 1
        assert reg_check[0].passed


class TestMissingManifestFails:
    def test_no_manifest_attribute(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_NoManifestPlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "plugin_has_manifest" for c in failed)

    def test_dict_manifest_fails_type_check(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_DictManifestPlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "manifest_type" for c in failed)


class TestMissingRegisterFails:
    def test_no_register_method(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_NoRegisterPlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "plugin_has_register" for c in failed)

    def test_bad_register_signature(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_BadRegisterSigPlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "register_signature" for c in failed)


class TestOperationValidation:
    def test_no_operations_fails(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_NoOperationsPlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "registers_operations" for c in failed)

    def test_operation_plugin_id_mismatch_fails(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_BadIdPlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any("plugin_id" in c.name for c in failed)

    def test_sync_handler_fails_signature_check(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_SyncHandlerPlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any("handler_signature" in c.name for c in failed)


class TestCapabilityContractValidation:
    def test_bad_capability_contract_type_fails(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_BadCapabilityContractPlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "capability_contract_type" for c in failed)


class TestLifecycleValidation:
    def test_sync_lifecycle_methods_fail(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_SyncLifecyclePlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "lifecycle_startup" for c in failed)
        assert any(c.name == "lifecycle_shutdown" for c in failed)


class TestRegisterExecution:
    def test_register_raises_is_caught(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_RegisterExplodesPlugin())

        assert not report.passed
        failed = [c for c in report.checks if not c.passed]
        assert any(c.name == "register_executes" for c in failed)
        assert "RuntimeError" in failed[0].message

    def test_full_registration_with_no_ops_fails(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check_full_registration(_NoOperationsPlugin())

        assert not report.passed


class TestReportStructure:
    def test_report_counts_are_consistent(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_ValidPlugin())

        assert report.pass_count + report.fail_count == len(report.checks)

    def test_report_plugin_id_extracted(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_NoManifestPlugin())

        assert report.plugin_id == "<unknown>"

    def test_report_unknown_id_for_dict_manifest(self) -> None:
        runner = PluginConformanceRunner()
        report = runner.check(_DictManifestPlugin())

        assert report.plugin_id == "<unknown>"
