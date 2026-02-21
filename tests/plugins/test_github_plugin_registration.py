from __future__ import annotations

from dataclasses import dataclass, field

from kagan.core.plugins.github import plugin as github_plugin
from kagan.core.plugins.github.contract import (
    GITHUB_CAPABILITY,
    GITHUB_CONTRACT_PROBE_METHOD,
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
)
from kagan.core.plugins.sdk import PLUGIN_UI_DESCRIBE_METHOD, PluginOperation
from kagan.core.policy import CapabilityProfile


@dataclass
class _RegistrationApiStub:
    operations: list[PluginOperation] = field(default_factory=list)

    def register_operation(self, operation: PluginOperation) -> None:
        self.operations.append(operation)


def test_github_plugin_registers_all_declared_methods() -> None:
    plugin = github_plugin.GitHubPlugin()
    api = _RegistrationApiStub()

    plugin.register(api)

    registered_methods = tuple(sorted(operation.method for operation in api.operations))
    declared_methods = plugin.capabilities[0].methods

    assert registered_methods == declared_methods
    assert all(operation.plugin_id == plugin.manifest.id for operation in api.operations)
    assert all(operation.capability == GITHUB_CAPABILITY for operation in api.operations)


def test_github_plugin_registration_metadata_remains_stable() -> None:
    plugin = github_plugin.GitHubPlugin()
    api = _RegistrationApiStub()

    plugin.register(api)

    operations_by_method = {operation.method: operation for operation in api.operations}
    expected = {
        GITHUB_CONTRACT_PROBE_METHOD: {
            "handler": github_plugin._contract_probe,
            "minimum_profile": CapabilityProfile.PAIR_WORKER,
            "mutating": False,
            "tool_name": "kagan_github_contract_probe",
        },
        GITHUB_METHOD_CONNECT_REPO: {
            "handler": github_plugin._connect_repo,
            "minimum_profile": CapabilityProfile.MAINTAINER,
            "mutating": True,
            "tool_name": "kagan_github_connect_repo",
        },
        GITHUB_METHOD_SYNC_ISSUES: {
            "handler": github_plugin._sync_issues,
            "minimum_profile": CapabilityProfile.MAINTAINER,
            "mutating": True,
            "tool_name": "kagan_github_sync_issues",
        },
        GITHUB_METHOD_ACQUIRE_LEASE: {
            "handler": github_plugin._acquire_lease,
            "minimum_profile": CapabilityProfile.MAINTAINER,
            "mutating": True,
            "tool_name": "kagan_github_acquire_lease",
        },
        GITHUB_METHOD_RELEASE_LEASE: {
            "handler": github_plugin._release_lease,
            "minimum_profile": CapabilityProfile.MAINTAINER,
            "mutating": True,
            "tool_name": "kagan_github_release_lease",
        },
        GITHUB_METHOD_GET_LEASE_STATE: {
            "handler": github_plugin._get_lease_state,
            "minimum_profile": CapabilityProfile.PAIR_WORKER,
            "mutating": False,
            "tool_name": "kagan_github_get_lease_state",
        },
        GITHUB_METHOD_CREATE_PR_FOR_TASK: {
            "handler": github_plugin._create_pr_for_task,
            "minimum_profile": CapabilityProfile.MAINTAINER,
            "mutating": True,
            "tool_name": "kagan_github_create_pr_for_task",
        },
        GITHUB_METHOD_LINK_PR_TO_TASK: {
            "handler": github_plugin._link_pr_to_task,
            "minimum_profile": CapabilityProfile.MAINTAINER,
            "mutating": True,
            "tool_name": "kagan_github_link_pr_to_task",
        },
        GITHUB_METHOD_RECONCILE_PR_STATUS: {
            "handler": github_plugin._reconcile_pr_status,
            "minimum_profile": CapabilityProfile.PAIR_WORKER,
            "mutating": True,
            "tool_name": "kagan_github_reconcile_pr_status",
        },
        GITHUB_METHOD_CHECK_CI: {
            "handler": github_plugin._check_ci_status,
            "minimum_profile": CapabilityProfile.PAIR_WORKER,
            "mutating": False,
            "tool_name": "kagan_github_check_ci_status",
        },
        GITHUB_METHOD_MERGE_PR: {
            "handler": github_plugin._merge_pr,
            "minimum_profile": CapabilityProfile.MAINTAINER,
            "mutating": True,
            "tool_name": "kagan_github_merge_pr",
        },
        GITHUB_METHOD_GET_PR_REVIEW_COMMENTS: {
            "handler": github_plugin._get_pr_review_comments,
            "minimum_profile": CapabilityProfile.PAIR_WORKER,
            "mutating": False,
            "tool_name": "kagan_github_get_pr_review_comments",
        },
        GITHUB_METHOD_VALIDATE_REVIEW_TRANSITION: {
            "handler": github_plugin._validate_review_transition,
            "minimum_profile": CapabilityProfile.MAINTAINER,
            "mutating": False,
            "tool_name": None,
        },
        GITHUB_METHOD_SYNC_TASK_STATUS: {
            "handler": github_plugin._sync_task_status,
            "minimum_profile": CapabilityProfile.MAINTAINER,
            "mutating": True,
            "tool_name": "kagan_github_sync_task_status",
        },
        PLUGIN_UI_DESCRIBE_METHOD: {
            "handler": github_plugin._ui_describe,
            "minimum_profile": CapabilityProfile.VIEWER,
            "mutating": False,
            "tool_name": None,
        },
    }

    assert set(operations_by_method) == set(expected)

    for method, details in expected.items():
        operation = operations_by_method[method]
        assert operation.handler is details["handler"]
        assert operation.minimum_profile == details["minimum_profile"]
        assert operation.mutating is details["mutating"]

        schema = operation.mcp_tool_schema
        tool_name = details["tool_name"]
        if tool_name is None:
            assert schema is None
        else:
            assert schema is not None
            assert schema.tool_name == tool_name
