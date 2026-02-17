"""Tests for plugin SDK scaffold contracts and core wiring."""

from __future__ import annotations

import json
import sys
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, cast

import pytest
from pydantic import ValidationError

from kagan.core.bootstrap import create_app_context
from kagan.core.commands import build_command_router
from kagan.core.host import CoreHost
from kagan.core.ipc.contracts import CoreRequest
from kagan.core.plugins.examples import register_example_plugins
from kagan.core.plugins.github import (
    GITHUB_CANONICAL_METHODS,
    GITHUB_CANONICAL_METHODS_SCOPE,
    GITHUB_CAPABILITY,
    GITHUB_CONTRACT_PROBE_METHOD,
    GITHUB_CONTRACT_VERSION,
    GITHUB_METHOD_ACQUIRE_LEASE,
    GITHUB_METHOD_CHECK_CI,
    GITHUB_METHOD_CONNECT_REPO,
    GITHUB_METHOD_CREATE_PR_FOR_TASK,
    GITHUB_METHOD_GET_LEASE_STATE,
    GITHUB_METHOD_GET_PR_REVIEW_COMMENTS,
    GITHUB_METHOD_LINK_PR_TO_TASK,
    GITHUB_METHOD_MERGE_PR,
    GITHUB_METHOD_RECONCILE_PR_STATUS,
    GITHUB_METHOD_RELEASE_LEASE,
    GITHUB_METHOD_SYNC_ISSUES,
    GITHUB_METHOD_SYNC_TASK_STATUS,
    GITHUB_METHOD_VALIDATE_REVIEW_TRANSITION,
    GITHUB_PLUGIN_ID,
    RESERVED_GITHUB_CAPABILITY,
    GitHubPlugin,
    GitHubPluginHandlerResolutionError,
    GitHubPluginModuleLoadError,
    register_github_plugin,
)
from kagan.core.plugins.sdk import (
    PLUGIN_UI_DESCRIBE_METHOD,
    JsonPluginManifestLoader,
    PluginCapabilityProvider,
    PluginCapabilitySpec,
    PluginLifecycle,
    PluginManifest,
    PluginOperation,
    PluginRegistrationApi,
    PluginRegistry,
)
from kagan.version import get_kagan_version

if TYPE_CHECKING:
    from pathlib import Path


class _InvalidManifestPlugin:
    manifest = {
        "id": "example.invalid_manifest",
        "name": "Invalid Manifest Plugin",
        "version": "0.1.0",
        "entrypoint": "kagan.core.plugins.examples.invalid:Plugin",
    }

    def register(self, api: PluginRegistrationApi) -> None:
        del api


class _NoOperationPlugin:
    manifest = PluginManifest(
        id="example.no_operation",
        name="No Operation Plugin",
        version="0.1.0",
        entrypoint="kagan.core.plugins.examples.no_operation:Plugin",
        description="Conformance test plugin without operations.",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        del api


class _FailingAfterRegisterPlugin:
    manifest = PluginManifest(
        id="example.rollback",
        name="Rollback Plugin",
        version="0.1.0",
        entrypoint="kagan.core.plugins.examples.rollback:Plugin",
        description="Conformance test plugin to verify rollback semantics.",
    )

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability="plugins",
                method="rollback_probe",
                handler=_rollback_probe,
            )
        )
        msg = "registration failed after operation"
        raise RuntimeError(msg)


class _SimplePlugin:
    def __init__(
        self,
        *,
        plugin_id: str,
        capability: str = "plugins",
        method: str = "noop",
    ) -> None:
        self.manifest = PluginManifest(
            id=plugin_id,
            name=f"{plugin_id} Plugin",
            version="0.1.0",
            entrypoint=f"kagan.core.plugins.examples.{plugin_id}:Plugin",
            description="Simple plugin fixture.",
        )
        self._capability = capability
        self._method = method

    def register(self, api: PluginRegistrationApi) -> None:
        api.register_operation(
            PluginOperation(
                plugin_id=self.manifest.id,
                capability=self._capability,
                method=self._method,
                handler=_rollback_probe,
            )
        )


class _CapabilityContractPlugin(_SimplePlugin):
    @property
    def capabilities(self) -> tuple[PluginCapabilitySpec, ...]:
        return (
            PluginCapabilitySpec(
                capability=self._capability,
                methods=(self._method,),
            ),
        )


class _CapabilityMismatchPlugin(_SimplePlugin):
    @property
    def capabilities(self) -> tuple[PluginCapabilitySpec, ...]:
        return (
            PluginCapabilitySpec(
                capability=self._capability,
                methods=("missing_method",),
            ),
        )


class _LifecycleRecordingPlugin(_SimplePlugin, PluginLifecycle):
    def __init__(self, *, plugin_id: str, events: list[str]) -> None:
        super().__init__(plugin_id=plugin_id, method=f"{plugin_id.replace('.', '_')}_noop")
        self._events = events

    async def on_core_startup(self, ctx: Any) -> None:
        del ctx
        self._events.append(f"start:{self.manifest.id}")

    async def on_core_shutdown(self, ctx: Any) -> None:
        del ctx
        self._events.append(f"stop:{self.manifest.id}")


class _CtorArgsPlugin:
    def __init__(self, required_arg: str) -> None:
        self.required_arg = required_arg


async def _rollback_probe(ctx: Any, params: dict[str, Any]) -> dict[str, Any]:
    del ctx
    del params
    return {"success": True}


def _write_minimal_config(config_path: Path) -> None:
    config_path.write_text(
        "[general]\nauto_review = false\n"
        'default_worker_agent = "claude"\n\n'
        "[agents.claude]\n"
        'identity = "claude.ai"\nname = "Claude"\nshort_name = "claude"\n'
        'run_command."*" = "echo"\ninteractive_command."*" = "echo"\nactive = true\n',
        encoding="utf-8",
    )


def test_when_manifest_loader_reads_valid_manifest_then_expected_fields_are_loaded(
    tmp_path: Path,
) -> None:
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text(
        json.dumps(
            {
                "id": "example.sample",
                "name": "Sample Plugin",
                "version": "0.1.0",
                "entrypoint": "kagan.core.plugins.examples.sample:Plugin",
                "description": "Sample",
            }
        ),
        encoding="utf-8",
    )

    manifest = JsonPluginManifestLoader().load(manifest_path)

    assert manifest.id == "example.sample"
    assert manifest.entrypoint == "kagan.core.plugins.examples.sample:Plugin"


def test_when_manifest_payload_contains_unknown_fields_then_validation_fails() -> None:
    with pytest.raises(ValidationError):
        PluginManifest.model_validate(
            {
                "id": "example.bad",
                "name": "Bad Plugin",
                "version": "0.1.0",
                "entrypoint": "kagan.core.plugins.examples.bad:Plugin",
                "unexpected": "field",
            }
        )


def test_when_manifest_loader_returns_non_manifest_then_registry_rejects_loader_contract(
    tmp_path: Path,
) -> None:
    class _BadLoader:
        def load(self, manifest_path: Path) -> dict[str, str]:
            del manifest_path
            return {}

    registry = PluginRegistry()
    manifest_path = tmp_path / "plugin.json"
    manifest_path.write_text("{}", encoding="utf-8")

    with pytest.raises(TypeError, match="must return PluginManifest"):
        registry.load_manifest(manifest_path, loader=_BadLoader())


def test_when_registering_example_plugins_then_noop_operation_is_exposed() -> None:
    registry = PluginRegistry()
    register_example_plugins(registry)

    operation = registry.resolve_operation("plugins", "noop_ping")
    assert operation is not None
    assert operation.plugin_id == "example.noop"
    assert operation.mutating is False


def test_when_plugin_manifest_is_not_plugin_manifest_model_then_registration_is_rejected() -> None:
    registry = PluginRegistry()

    with pytest.raises(TypeError, match="Plugin manifest must be an instance of PluginManifest"):
        registry.register_plugin(cast("Any", _InvalidManifestPlugin()))


def test_when_plugin_registers_no_operations_then_registry_rolls_back_manifest() -> None:
    registry = PluginRegistry()

    with pytest.raises(ValueError, match="must register at least one operation"):
        registry.register_plugin(_NoOperationPlugin())

    assert registry.registered_manifests() == ()


def test_when_plugin_registration_raises_after_operation_then_registry_rolls_back_all_changes() -> (
    None
):
    registry = PluginRegistry()

    with pytest.raises(RuntimeError, match="registration failed after operation"):
        registry.register_plugin(_FailingAfterRegisterPlugin())

    assert registry.registered_manifests() == ()
    assert registry.resolve_operation("plugins", "rollback_probe") is None


def test_when_registering_duplicate_plugin_id_then_second_registration_is_rejected() -> None:
    """The registry must keep the first plugin and reject duplicate IDs."""
    registry = PluginRegistry()
    first = _SimplePlugin(plugin_id="example.duplicate")
    second = _SimplePlugin(plugin_id="example.duplicate", method="noop_2")

    registry.register_plugin(first)

    with pytest.raises(ValueError, match="already registered"):
        registry.register_plugin(second)

    manifests = registry.registered_manifests()
    assert len(manifests) == 1
    assert manifests[0].id == "example.duplicate"
    assert registry.resolve_operation("plugins", "noop") is not None
    assert registry.resolve_operation("plugins", "noop_2") is None


def test_when_registering_owned_method_then_registration_is_rejected() -> None:
    """Capability/method ownership must be unique across plugins."""
    registry = PluginRegistry()
    first = _SimplePlugin(plugin_id="example.alpha", method="same_method")
    conflicting = _SimplePlugin(plugin_id="example.beta", method="same_method")

    registry.register_plugin(first)

    with pytest.raises(ValueError, match="already registered by plugin"):
        registry.register_plugin(conflicting)

    assert registry.resolve_operation("plugins", "same_method") is not None
    assert [manifest.id for manifest in registry.registered_manifests()] == ["example.alpha"]


def test_when_plugin_declares_capability_contract_then_registry_exposes_normalized_contract() -> (
    None
):
    registry = PluginRegistry()
    plugin = _CapabilityContractPlugin(
        plugin_id="example.capabilities",
        capability="plugins",
        method="capability_probe",
    )

    registry.register_plugin(plugin)

    assert registry.capabilities_for_plugin("example.capabilities") == (
        PluginCapabilitySpec(capability="plugins", methods=("capability_probe",)),
    )


def test_when_capability_contract_mismatches_registered_methods_then_registration_is_rejected() -> (
    None
):
    registry = PluginRegistry()
    plugin = _CapabilityMismatchPlugin(
        plugin_id="example.capability_mismatch",
        capability="plugins",
        method="registered_method",
    )

    with pytest.raises(ValueError, match="declares missing operations"):
        registry.register_plugin(plugin)

    assert registry.registered_manifests() == ()


@pytest.mark.asyncio()
async def test_when_plugins_define_lifecycle_hooks_then_registry_runs_deterministic_order() -> None:
    registry = PluginRegistry()
    events: list[str] = []

    registry.register_plugin(_LifecycleRecordingPlugin(plugin_id="example.beta", events=events))
    registry.register_plugin(_LifecycleRecordingPlugin(plugin_id="example.alpha", events=events))

    ctx = cast("Any", SimpleNamespace())
    await registry.start_lifecycle(ctx)
    await registry.shutdown_lifecycle(ctx)

    assert events == [
        "start:example.alpha",
        "start:example.beta",
        "stop:example.beta",
        "stop:example.alpha",
    ]


def test_when_discovery_entrypoint_targets_non_class_then_validation_error_is_deterministic() -> (
    None
):
    registry = PluginRegistry()

    with pytest.raises(ValueError, match="must reference a class"):
        registry.discover_and_register(["kagan.core.plugins.github.contract:GITHUB_CAPABILITY"])


def test_when_discovery_plugin_cannot_instantiate_then_validation_error_is_deterministic() -> None:
    registry = PluginRegistry()

    with pytest.raises(ValueError, match="could not be instantiated"):
        registry.discover_and_register(["tests.core.unit.test_plugin_sdk:_CtorArgsPlugin"])


@pytest.mark.asyncio()
async def test_when_core_host_handles_example_plugin_op_then_response_is_successful() -> None:
    registry = PluginRegistry()
    register_example_plugins(registry)

    host = CoreHost()
    host._ctx = cast("Any", SimpleNamespace(plugin_registry=registry))

    response = await host.handle_request(
        CoreRequest(
            session_id="ext:maintainer-session",
            session_profile="maintainer",
            session_origin="kagan_admin",
            client_version=get_kagan_version(),
            capability="plugins",
            method="noop_ping",
            params={"echo": "hello"},
        )
    )

    assert response.ok
    assert response.result == {
        "success": True,
        "plugin_id": "example.noop",
        "echo": "hello",
    }


@pytest.mark.asyncio()
async def test_when_plugin_policy_hook_denies_request_then_core_host_returns_policy_error() -> None:
    registry = PluginRegistry()
    register_example_plugins(registry)

    host = CoreHost()
    host._ctx = cast("Any", SimpleNamespace(plugin_registry=registry))

    response = await host.handle_request(
        CoreRequest(
            session_id="ext:maintainer-session",
            session_profile="maintainer",
            session_origin="kagan_admin",
            client_version=get_kagan_version(),
            capability="plugins",
            method="noop_ping",
            params={"disabled": True},
        )
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "PLUGIN_POLICY_DENIED"


@pytest.mark.asyncio()
async def test_when_session_profile_is_below_plugin_minimum_then_core_host_denies_request() -> None:
    registry = PluginRegistry()
    register_example_plugins(registry)

    host = CoreHost()
    host._ctx = cast("Any", SimpleNamespace(plugin_registry=registry))

    response = await host.handle_request(
        CoreRequest(
            session_id="ext:viewer-session",
            session_profile="viewer",
            session_origin="kagan_admin",
            client_version=get_kagan_version(),
            capability="plugins",
            method="noop_ping",
        )
    )

    assert not response.ok
    assert response.error is not None
    assert response.error.code == "AUTHORIZATION_DENIED"


@pytest.mark.asyncio()
async def test_when_create_app_context_initializes_then_example_plugin_operation_is_registered(
    tmp_path: Path,
) -> None:
    config_path = tmp_path / "config.toml"
    db_path = tmp_path / "test.db"
    _write_minimal_config(config_path)

    ctx = await create_app_context(config_path=config_path, db_path=db_path)
    try:
        operation = ctx.plugin_registry.resolve_operation("plugins", "noop_ping")
        assert operation is not None
    finally:
        await ctx.close()


def test_when_registering_github_plugin_then_contract_probe_operation_is_exposed() -> None:
    registry = PluginRegistry()

    register_github_plugin(registry)

    operation = registry.resolve_operation(GITHUB_CAPABILITY, GITHUB_CONTRACT_PROBE_METHOD)
    assert operation is not None
    assert operation.plugin_id == GITHUB_PLUGIN_ID
    assert operation.mutating is False


def test_when_loading_github_plugin_then_capability_contract_is_explicit_and_complete() -> None:
    plugin = GitHubPlugin()

    assert isinstance(plugin, PluginCapabilityProvider)
    assert plugin.capabilities == (
        PluginCapabilitySpec(
            capability=GITHUB_CAPABILITY,
            methods=tuple(
                sorted(
                    (
                        GITHUB_CONTRACT_PROBE_METHOD,
                        GITHUB_METHOD_CONNECT_REPO,
                        GITHUB_METHOD_SYNC_ISSUES,
                        GITHUB_METHOD_SYNC_TASK_STATUS,
                        GITHUB_METHOD_ACQUIRE_LEASE,
                        GITHUB_METHOD_RELEASE_LEASE,
                        GITHUB_METHOD_GET_LEASE_STATE,
                        GITHUB_METHOD_CREATE_PR_FOR_TASK,
                        GITHUB_METHOD_LINK_PR_TO_TASK,
                        GITHUB_METHOD_RECONCILE_PR_STATUS,
                        GITHUB_METHOD_CHECK_CI,
                        GITHUB_METHOD_MERGE_PR,
                        GITHUB_METHOD_GET_PR_REVIEW_COMMENTS,
                        GITHUB_METHOD_VALIDATE_REVIEW_TRANSITION,
                        PLUGIN_UI_DESCRIBE_METHOD,
                    )
                )
            ),
        ),
    )


@pytest.mark.asyncio()
async def test_when_github_handlers_module_import_fails_then_typed_error_preserves_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PluginRegistry()
    register_github_plugin(registry)
    operation = registry.resolve_operation(GITHUB_CAPABILITY, GITHUB_CONTRACT_PROBE_METHOD)
    assert operation is not None

    def _raise_import(module_name: str) -> Any:
        del module_name
        raise ImportError("boom")

    monkeypatch.setattr("kagan.core.plugins.github.plugin.import_module", _raise_import)

    with pytest.raises(GitHubPluginModuleLoadError, match="could not be imported") as exc_info:
        await operation.handler(SimpleNamespace(), {})
    assert isinstance(exc_info.value.__cause__, ImportError)


@pytest.mark.asyncio()
async def test_when_github_handler_is_missing_then_typed_resolution_error_preserves_cause(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = PluginRegistry()
    register_github_plugin(registry)
    operation = registry.resolve_operation(GITHUB_CAPABILITY, GITHUB_CONTRACT_PROBE_METHOD)
    assert operation is not None

    monkeypatch.setattr(
        "kagan.core.plugins.github.plugin.import_module",
        lambda _module_name: SimpleNamespace(),
    )

    with pytest.raises(GitHubPluginHandlerResolutionError, match="is not defined") as exc_info:
        await operation.handler(SimpleNamespace(), {})
    assert isinstance(exc_info.value.__cause__, AttributeError)


def test_when_querying_operations_by_method_then_matching_operations_are_returned() -> None:
    registry = PluginRegistry()
    register_github_plugin(registry)

    operations = registry.operations_for_method("validate_review_transition")

    assert len(operations) == 1
    assert operations[0].plugin_id == GITHUB_PLUGIN_ID


def test_when_registering_conflicting_github_probe_then_registry_rejects_collision() -> None:
    registry = PluginRegistry()
    register_github_plugin(registry)
    conflicting = _SimplePlugin(
        plugin_id="example.conflict",
        capability=GITHUB_CAPABILITY,
        method=GITHUB_CONTRACT_PROBE_METHOD,
    )

    with pytest.raises(ValueError, match="already registered by plugin"):
        registry.register_plugin(conflicting)


def test_when_registering_github_plugin_then_probe_has_no_builtin_dispatch_collision() -> None:
    router = build_command_router()

    assert GITHUB_CAPABILITY != RESERVED_GITHUB_CAPABILITY
    assert not router.has_command(GITHUB_CAPABILITY, GITHUB_CONTRACT_PROBE_METHOD)


def test_when_registering_github_plugin_then_handlers_module_is_not_eagerly_imported() -> None:
    handlers_module_name = "kagan.core.plugins.github.entrypoints.plugin_handlers"
    sys.modules.pop(handlers_module_name, None)

    registry = PluginRegistry()
    register_github_plugin(registry)

    assert handlers_module_name not in sys.modules


@pytest.mark.asyncio()
async def test_core_host_github_probe_loads_handlers_and_contract_stable() -> None:
    handlers_module_name = "kagan.core.plugins.github.entrypoints.plugin_handlers"
    sys.modules.pop(handlers_module_name, None)

    registry = PluginRegistry()
    register_github_plugin(registry)

    host = CoreHost()
    host._ctx = cast("Any", SimpleNamespace(plugin_registry=registry))

    response = await host.handle_request(
        CoreRequest(
            session_id="ext:maintainer-session",
            session_profile="maintainer",
            session_origin="kagan_admin",
            client_version=get_kagan_version(),
            capability=GITHUB_CAPABILITY,
            method=GITHUB_CONTRACT_PROBE_METHOD,
            params={"echo": "hello"},
        )
    )

    assert response.ok
    assert response.result == {
        "success": True,
        "plugin_id": GITHUB_PLUGIN_ID,
        "contract_version": GITHUB_CONTRACT_VERSION,
        "capability": GITHUB_CAPABILITY,
        "method": GITHUB_CONTRACT_PROBE_METHOD,
        "canonical_methods": list(GITHUB_CANONICAL_METHODS),
        "canonical_scope": GITHUB_CANONICAL_METHODS_SCOPE,
        "reserved_official_capability": RESERVED_GITHUB_CAPABILITY,
        "echo": "hello",
    }
    assert handlers_module_name in sys.modules


@pytest.mark.asyncio()
async def test_create_app_context_registers_github_probe_without_eager_handlers_import(
    tmp_path: Path,
) -> None:
    handlers_module_name = "kagan.core.plugins.github.entrypoints.plugin_handlers"
    sys.modules.pop(handlers_module_name, None)

    config_path = tmp_path / "config.toml"
    db_path = tmp_path / "test.db"
    _write_minimal_config(config_path)

    ctx = await create_app_context(config_path=config_path, db_path=db_path)
    try:
        operation = ctx.plugin_registry.resolve_operation(
            GITHUB_CAPABILITY, GITHUB_CONTRACT_PROBE_METHOD
        )
        assert operation is not None
        assert operation.plugin_id == GITHUB_PLUGIN_ID
        assert handlers_module_name not in sys.modules
    finally:
        await ctx.close()
