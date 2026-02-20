from __future__ import annotations

from kagan.core.host import CoreHost
from kagan.core.ipc.contracts import CoreRequest
from kagan.core.policy import AuthorizationPolicy, SessionBinding, SessionNamespace, SessionOrigin


def _binding_for(origin: SessionOrigin) -> SessionBinding:
    namespace = SessionNamespace.DEFAULT
    if origin is SessionOrigin.TUI:
        namespace = SessionNamespace.TUI
    if origin is SessionOrigin.KAGAN_ADMIN:
        namespace = SessionNamespace.EXT
    return SessionBinding(
        policy=AuthorizationPolicy("maintainer"),
        origin=origin,
        namespace=namespace,
        scope_id="scope",
    )


def _request_for(
    origin: SessionOrigin,
    *,
    version: str,
    build_hash: str | None,
) -> CoreRequest:
    return CoreRequest(
        session_id=f"{origin.value}:session",
        session_origin=origin.value,
        client_version=version,
        client_build_hash=build_hash,
        capability="tasks",
        method="list",
        params={},
    )


def test_runtime_guard_requires_client_version_for_tui() -> None:
    host = CoreHost()
    request = _request_for(SessionOrigin.TUI, version="", build_hash="abcd1234")

    response = host._validate_client_runtime_compatibility(
        request,
        binding=_binding_for(SessionOrigin.TUI),
    )

    assert response is not None
    assert response.error is not None
    assert response.error.code == "CLIENT_VERSION_REQUIRED"
    assert "Restart the TUI session" in response.error.message


def test_runtime_guard_requires_build_hash_for_mcp() -> None:
    host = CoreHost()
    request = _request_for(
        SessionOrigin.KAGAN_ADMIN,
        version=host._runtime_version,
        build_hash=None,
    )

    response = host._validate_client_runtime_compatibility(
        request,
        binding=_binding_for(SessionOrigin.KAGAN_ADMIN),
    )

    assert response is not None
    assert response.error is not None
    assert response.error.code == "CLIENT_BUILD_HASH_REQUIRED"
    assert "Restart the MCP session" in response.error.message


def test_runtime_guard_rejects_hash_mismatch_for_tui() -> None:
    host = CoreHost()
    request = _request_for(
        SessionOrigin.TUI,
        version=host._runtime_version,
        build_hash="deadbeefdeadbeef",
    )

    response = host._validate_client_runtime_compatibility(
        request,
        binding=_binding_for(SessionOrigin.TUI),
    )

    assert response is not None
    assert response.error is not None
    assert response.error.code == "CLIENT_OUTDATED"
    assert "does not match core build hash" in response.error.message
    assert "Restart the TUI session" in response.error.message


def test_runtime_guard_allows_matching_version_and_hash() -> None:
    host = CoreHost()
    request = _request_for(
        SessionOrigin.KAGAN,
        version=host._runtime_version,
        build_hash=host._runtime_build_hash,
    )

    response = host._validate_client_runtime_compatibility(
        request,
        binding=_binding_for(SessionOrigin.KAGAN),
    )

    assert response is None
