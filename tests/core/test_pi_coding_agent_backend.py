"""Smoke tests for the pi-coding-agent backend registration and (when available) RPC round-trip.

These tests cover:
1. BackendSpec registration — pi-coding-agent is in the registry with correct metadata.
2. Environment gate — check_node_version() behaves correctly.
3. Optional live smoke test — spawns a real pi RPC process when npx + Node >= 20.6 are
   available; skipped otherwise.

The live smoke test is gated on:
  - ``shutil.which("npx")`` returning a path.
  - Node.js >= 20.6 detected via ``check_node_version()``.

It does NOT require a real API key or network access; the test only verifies that the
subprocess starts and the client can be entered / exited without errors.  Full prompt
round-trips require actual credentials and are left to integration tests.
"""

from __future__ import annotations

import shutil

import pytest

from kagan.core._agent import (
    PI_CODING_AGENT_BACKEND,
    BackendCapability,
    get_backend_spec,
    list_backends,
)
from kagan.core._environment_checks import check_node_version
from kagan.core.adapters.pi_rpc import PiRpcClient

pytestmark = [pytest.mark.core]

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_npx_available = shutil.which("npx") is not None
_node_ok = check_node_version((20, 6, 0))
_pi_available = _npx_available and _node_ok

_skip_no_pi = pytest.mark.skipif(
    not _pi_available,
    reason="npx not on PATH or Node < 20.6 — pi smoke test skipped",
)


# ---------------------------------------------------------------------------
# BackendSpec registration
# ---------------------------------------------------------------------------


def test_pi_coding_agent_is_registered() -> None:
    """pi-coding-agent must be present in the backend registry."""
    backends = list_backends()
    assert PI_CODING_AGENT_BACKEND in backends, (
        f"pi-coding-agent not found in AGENT_BACKENDS; got: {backends}"
    )


def test_pi_coding_agent_spec_metadata() -> None:
    """Verify key BackendSpec fields for pi-coding-agent."""
    spec = get_backend_spec(PI_CODING_AGENT_BACKEND)
    assert spec.name == PI_CODING_AGENT_BACKEND
    assert spec.executable == "npx"
    assert spec.supports_acp is False
    assert spec.has_capability(BackendCapability.PI_RPC_STREAMING)
    assert not spec.has_capability(BackendCapability.ACP_STREAMING)
    assert spec.display_name == "pi coding-agent"


def test_pi_coding_agent_alias_resolves() -> None:
    """The 'pi' alias must resolve to 'pi-coding-agent'."""
    from kagan.core._agent import normalize_backend_name

    assert normalize_backend_name("pi") == PI_CODING_AGENT_BACKEND


def test_pi_coding_agent_install_hint_present() -> None:
    """pi-coding-agent must have an install hint."""
    spec = get_backend_spec(PI_CODING_AGENT_BACKEND)
    cmd = spec.resolve_command("install")
    assert cmd is not None
    assert "pi-coding-agent" in cmd.command or "mariozechner" in cmd.command


def test_pi_coding_agent_legacy_config_does_not_claim_acp() -> None:
    """to_legacy_config() must reflect supports_acp=False."""
    spec = get_backend_spec(PI_CODING_AGENT_BACKEND)
    cfg = spec.to_legacy_config()
    assert cfg["supports_acp"] is False


# ---------------------------------------------------------------------------
# Environment gate
# ---------------------------------------------------------------------------


def test_check_node_version_returns_bool() -> None:
    """check_node_version() must return a bool regardless of system state."""
    result = check_node_version((20, 6, 0))
    assert isinstance(result, bool)


def test_check_node_version_high_requirement_returns_false_or_true() -> None:
    """check_node_version() with a future version must return a bool."""
    result = check_node_version((9999, 0, 0))
    assert result is False


def test_check_node_version_zero_always_passes_if_node_exists() -> None:
    """check_node_version() with (0,0,0) passes whenever node is on PATH."""
    if shutil.which("node") is None:
        pytest.skip("node not on PATH")
    assert check_node_version((0, 0, 0)) is True


# ---------------------------------------------------------------------------
# Live smoke: subprocess start + immediate close
# ---------------------------------------------------------------------------


@_skip_no_pi
@pytest.mark.smoke
async def test_pi_rpc_client_context_manager_starts_and_closes(tmp_path: object) -> None:  # type: ignore[type-arg]
    """PiRpcClient.__aenter__/__aexit__ must not raise when npx + Node are available.

    This test only verifies the subprocess lifecycle; it does NOT send a prompt
    (which would require API credentials).
    """
    from pathlib import Path

    assert isinstance(tmp_path, Path)

    # We use a very short-lived context: enter, then immediately close.
    # The pi subprocess may print startup errors to stderr (missing API key, etc.)
    # but the process-lifecycle operations themselves must not raise.
    client = PiRpcClient(cwd=tmp_path)
    try:
        await client._start()
    except RuntimeError as exc:
        if "npx not found" in str(exc):
            pytest.skip(f"npx not executable: {exc}")
        raise
    finally:
        await client.aclose()

    # After aclose, _proc must be None
    assert client._proc is None
