"""MCP access: capability profiles and tool catalog.

Covers:
- Capability profiles (viewer, planner, pair_worker, operator, maintainer)
- Profile hierarchy restricts tool access
- Read-only mode enforcement
- AuthorizationPolicy enforce raises AuthorizationError with code/profile
- Full profile hierarchy: each level is a strict superset of the one below
- Session binding: get_binding resolves profile/origin/namespace
- enforce_task_scope blocks cross-task mutations
"""

from __future__ import annotations

import pytest

from kagan.core.ipc.contracts import CoreRequest
from kagan.core.policy import (
    CAPABILITY_PROFILES,
    AuthorizationError,
    AuthorizationPolicy,
    CapabilityProfile,
    SessionBinding,
    SessionBindingError,
    SessionNamespace,
    SessionOrigin,
    apply_profile_ceiling,
    enforce_task_scope,
    get_binding,
    profile_rank,
    resolve_mcp_capability,
)


class TestCapabilityProfileHierarchy:
    """Profiles are hierarchical: viewer < planner < pair_worker < operator < maintainer."""

    def test_all_profiles_are_defined(self) -> None:
        expected = {"viewer", "planner", "pair_worker", "operator", "maintainer"}
        actual = {p.value for p in CapabilityProfile}
        assert actual == expected

    def test_maintainer_has_most_methods(self) -> None:
        maintainer_methods = CAPABILITY_PROFILES[CapabilityProfile.MAINTAINER]
        viewer_methods = CAPABILITY_PROFILES[CapabilityProfile.VIEWER]
        assert len(maintainer_methods) > len(viewer_methods)

    def test_viewer_methods_subset_of_maintainer(self) -> None:
        viewer = CAPABILITY_PROFILES[CapabilityProfile.VIEWER]
        maintainer = CAPABILITY_PROFILES[CapabilityProfile.MAINTAINER]
        assert viewer.issubset(maintainer)

    def test_planner_superset_of_viewer(self) -> None:
        viewer = CAPABILITY_PROFILES[CapabilityProfile.VIEWER]
        planner = CAPABILITY_PROFILES[CapabilityProfile.PLANNER]
        assert viewer.issubset(planner)


class TestCapabilityProfileRankOrdering:
    """Canonical rank helpers preserve profile precedence semantics."""

    def test_profile_rank_is_monotonic_by_privilege(self) -> None:
        ordered_profiles = [
            CapabilityProfile.VIEWER,
            CapabilityProfile.PLANNER,
            CapabilityProfile.PAIR_WORKER,
            CapabilityProfile.OPERATOR,
            CapabilityProfile.MAINTAINER,
        ]
        ranks = [profile_rank(profile) for profile in ordered_profiles]
        assert ranks == sorted(ranks)

    def test_apply_profile_ceiling_caps_requested_profile(self) -> None:
        assert (
            apply_profile_ceiling(
                CapabilityProfile.MAINTAINER,
                ceiling_profile=CapabilityProfile.PAIR_WORKER,
            )
            == CapabilityProfile.PAIR_WORKER
        )

    def test_apply_profile_ceiling_accepts_string_profiles(self) -> None:
        assert (
            apply_profile_ceiling("viewer", ceiling_profile="maintainer")
            == CapabilityProfile.VIEWER
        )


class TestAuthorizationPolicy:
    """Policy enforces profile-based access control."""

    def test_viewer_cannot_create_tasks(self) -> None:
        policy = AuthorizationPolicy(CapabilityProfile.VIEWER)
        assert policy.check("tasks", "create") is False

    def test_maintainer_can_create_tasks(self) -> None:
        policy = AuthorizationPolicy(CapabilityProfile.MAINTAINER)
        assert policy.check("tasks", "create") is True

    def test_viewer_can_list_tasks(self) -> None:
        policy = AuthorizationPolicy(CapabilityProfile.VIEWER)
        assert policy.check("tasks", "list") is True

    def test_enforce_raises_for_unauthorized(self) -> None:
        policy = AuthorizationPolicy(CapabilityProfile.VIEWER)
        with pytest.raises(AuthorizationError):
            policy.enforce("tasks", "create")


class TestAuthorizationPolicyHierarchy:
    """Each profile is a strict superset of the one below it."""

    _ORDERED_PROFILES = [
        CapabilityProfile.VIEWER,
        CapabilityProfile.PLANNER,
        CapabilityProfile.PAIR_WORKER,
        CapabilityProfile.OPERATOR,
        CapabilityProfile.MAINTAINER,
    ]

    def test_each_profile_is_strict_superset_of_lower(self) -> None:
        for i in range(1, len(self._ORDERED_PROFILES)):
            lower = CAPABILITY_PROFILES[self._ORDERED_PROFILES[i - 1]]
            higher = CAPABILITY_PROFILES[self._ORDERED_PROFILES[i]]
            assert lower.issubset(higher), (
                f"{self._ORDERED_PROFILES[i].value} is not a superset of "
                f"{self._ORDERED_PROFILES[i - 1].value}"
            )
            assert len(higher) > len(lower), (
                f"{self._ORDERED_PROFILES[i].value} has same size as "
                f"{self._ORDERED_PROFILES[i - 1].value}"
            )

    def test_enforce_raises_authorization_error_with_fields(self) -> None:
        policy = AuthorizationPolicy(CapabilityProfile.VIEWER)
        with pytest.raises(AuthorizationError) as exc_info:
            policy.enforce("tasks", "delete")
        err = exc_info.value
        assert err.code == "AUTHORIZATION_DENIED"
        assert err.capability == "tasks"
        assert err.method == "delete"
        assert err.profile == "viewer"

    def test_operator_can_create_but_not_delete(self) -> None:
        policy = AuthorizationPolicy(CapabilityProfile.OPERATOR)
        assert policy.check("tasks", "create") is True
        assert policy.check("tasks", "delete") is False

    def test_maintainer_is_unrestricted(self) -> None:
        policy = AuthorizationPolicy(CapabilityProfile.MAINTAINER)
        # Maintainer can access any capability.method, even made-up ones
        assert policy.check("tasks", "delete") is True
        assert policy.check("settings", "update") is True
        assert policy.check("made_up", "anything") is True


class TestSessionBinding:
    """get_binding resolves profile/origin/namespace from CoreRequest."""

    def _make_request(
        self,
        session_id: str = "default:test",
        origin: str = "kagan_admin",
        profile: str | None = "maintainer",
        capability: str = "tasks",
        method: str = "list",
        params: dict | None = None,
    ) -> CoreRequest:
        return CoreRequest(
            session_id=session_id,
            session_origin=origin,
            session_profile=profile,
            client_version="1.0",
            capability=capability,
            method=method,
            params=params or {},
        )

    def test_get_binding_creates_and_caches_binding(self) -> None:
        bindings: dict[str, SessionBinding] = {}
        req = self._make_request(session_id="ext:my-session", origin="kagan_admin")
        binding = get_binding(bindings, req)

        assert binding.origin == SessionOrigin.KAGAN_ADMIN
        assert binding.namespace == SessionNamespace.EXT
        assert binding.scope_id == "my-session"
        assert "ext:my-session" in bindings

        # Second call returns cached
        binding2 = get_binding(bindings, req)
        assert binding2 is binding

    def test_kagan_origin_ceiling_caps_profile(self) -> None:
        bindings: dict[str, SessionBinding] = {}
        # kagan origin has ceiling of pair_worker — requesting maintainer gets capped
        req = self._make_request(
            session_id="task:abc12345",
            origin="kagan",
            profile="maintainer",
        )
        binding = get_binding(bindings, req)
        assert binding.policy.profile == CapabilityProfile.PAIR_WORKER

    def test_invalid_origin_raises_session_binding_error(self) -> None:
        bindings: dict[str, SessionBinding] = {}
        req = self._make_request(origin="unknown_origin")
        with pytest.raises(SessionBindingError) as exc_info:
            get_binding(bindings, req)
        assert exc_info.value.code == "INVALID_ORIGIN"

    def test_namespace_denied_for_wrong_origin(self) -> None:
        bindings: dict[str, SessionBinding] = {}
        # kagan origin cannot use "ext" namespace
        req = self._make_request(
            session_id="ext:session1",
            origin="kagan",
            profile="pair_worker",
        )
        with pytest.raises(SessionBindingError) as exc_info:
            get_binding(bindings, req)
        assert exc_info.value.code == "SESSION_NAMESPACE_DENIED"


class TestEnforceTaskScope:
    """enforce_task_scope blocks task-scoped sessions from mutating other tasks."""

    def test_allows_mutation_of_scoped_task(self) -> None:
        binding = SessionBinding(
            policy=AuthorizationPolicy("pair_worker"),
            origin=SessionOrigin.KAGAN,
            namespace=SessionNamespace.TASK,
            scope_id="abc12345",
        )
        req = CoreRequest(
            session_id="task:abc12345",
            session_origin="kagan",
            client_version="1.0",
            capability="jobs",
            method="submit",
            params={"task_id": "abc12345"},
        )
        # Should not raise
        enforce_task_scope(req, binding)

    def test_blocks_mutation_of_different_task(self) -> None:
        binding = SessionBinding(
            policy=AuthorizationPolicy("pair_worker"),
            origin=SessionOrigin.KAGAN,
            namespace=SessionNamespace.TASK,
            scope_id="abc12345",
        )
        req = CoreRequest(
            session_id="task:abc12345",
            session_origin="kagan",
            client_version="1.0",
            capability="jobs",
            method="submit",
            params={"task_id": "OTHER_ID"},
        )
        with pytest.raises(SessionBindingError) as exc_info:
            enforce_task_scope(req, binding)
        assert exc_info.value.code == "SESSION_SCOPE_DENIED"

    def test_non_mutation_method_skips_check(self) -> None:
        binding = SessionBinding(
            policy=AuthorizationPolicy("pair_worker"),
            origin=SessionOrigin.KAGAN,
            namespace=SessionNamespace.TASK,
            scope_id="abc12345",
        )
        req = CoreRequest(
            session_id="task:abc12345",
            session_origin="kagan",
            client_version="1.0",
            capability="tasks",
            method="list",
            params={"task_id": "OTHER_ID"},
        )
        # tasks.list is not a mutation method, should not raise
        enforce_task_scope(req, binding)


class TestMcpToolPolicyHelpers:
    """Shared MCP tool-policy helpers are consistent with profile policy."""

    def test_protocol_calls_include_expected_pairs(self) -> None:
        from kagan.mcp._tool_policy import PROTOCOL_CALLS

        assert PROTOCOL_CALLS["tasks_create"] == ("tasks", "create")
        assert PROTOCOL_CALLS["settings_update"] == ("settings", "update")
        assert PROTOCOL_CALLS["review_reject"] == ("review", "reject")

    def test_is_allowed_rejects_unknown_profile(self) -> None:
        from kagan.mcp._tool_policy import is_allowed

        assert is_allowed("unknown_profile", "tasks", "list") is False

    def test_is_allowed_matches_viewer_permissions(self) -> None:
        from kagan.mcp._tool_policy import is_allowed

        assert is_allowed("viewer", "tasks", "list") is True
        assert is_allowed("viewer", "tasks", "create") is False


class TestResolveMcpCapability:
    """ACP MCP capability resolution follows task scope and readonly mode."""

    def test_readonly_unscoped_is_planner(self) -> None:
        assert resolve_mcp_capability(task_id="", read_only=True) == CapabilityProfile.PLANNER

    def test_readonly_task_scoped_is_viewer(self) -> None:
        assert (
            resolve_mcp_capability(task_id="task:abc123", read_only=True)
            == CapabilityProfile.VIEWER
        )

    def test_mutating_task_scoped_is_pair_worker(self) -> None:
        assert (
            resolve_mcp_capability(task_id="abc123", read_only=False)
            == CapabilityProfile.PAIR_WORKER
        )

    def test_mutating_unscoped_is_maintainer(self) -> None:
        assert resolve_mcp_capability(task_id="", read_only=False) == CapabilityProfile.MAINTAINER


class TestMcpServerEffectiveProfileResolution:
    """MCP server identity ceilings are applied to requested capability profiles."""

    def test_caps_profile_by_identity_ceiling(self) -> None:
        from kagan.mcp.server import MCPRuntimeConfig, _resolve_effective_profile

        effective = _resolve_effective_profile(
            CapabilityProfile.MAINTAINER,
            "kagan",
            runtime_config=MCPRuntimeConfig(
                capability_profile="maintainer",
                identity="kagan",
            ),
        )
        assert effective == "pair_worker"

    def test_invalid_requested_profile_falls_back_to_viewer(self) -> None:
        from kagan.mcp.server import MCPRuntimeConfig, _resolve_effective_profile

        effective = _resolve_effective_profile(
            CapabilityProfile.MAINTAINER,
            "kagan_admin",
            runtime_config=MCPRuntimeConfig(
                capability_profile="invalid-profile",
                identity="kagan_admin",
            ),
        )
        assert effective == "viewer"
