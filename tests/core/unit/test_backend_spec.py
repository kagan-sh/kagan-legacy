"""Unit tests for BackendCommand / BackendSpec.resolve_command — AC #7."""

import pytest

from kagan.core._agent import (
    BackendCapability,
    BackendCommand,
    BackendSpec,
)

pytestmark = [pytest.mark.core, pytest.mark.unit]

# ---------------------------------------------------------------------------
# BackendCommand construction
# ---------------------------------------------------------------------------


def test_backend_command_defaults() -> None:
    cmd = BackendCommand(description="Install foo", command="pip install foo")
    assert cmd.description == "Install foo"
    assert cmd.command == "pip install foo"
    assert cmd.bootstrap_uv is False


def test_backend_command_bootstrap_uv() -> None:
    cmd = BackendCommand(
        description="Install via uv",
        command="uv tool install foo",
        bootstrap_uv=True,
    )
    assert cmd.bootstrap_uv is True


def test_backend_command_is_frozen() -> None:
    cmd = BackendCommand(description="d", command="c")
    with pytest.raises((AttributeError, TypeError)):
        cmd.command = "other"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# BackendSpec.resolve_command — OS match
# ---------------------------------------------------------------------------


def _make_spec(**kwargs: object) -> BackendSpec:
    return BackendSpec(name="test-agent", executable="agent", **kwargs)  # type: ignore[arg-type]


_INSTALL_CMD = BackendCommand(description="Install on Linux", command="apt install agent")
_MACOS_CMD = BackendCommand(description="Install on macOS", command="brew install agent")
_WILDCARD_CMD = BackendCommand(description="Install anywhere", command="curl agent.sh | sh")


def test_resolve_command_exact_os_match() -> None:
    spec = _make_spec(
        install={
            "linux": _INSTALL_CMD,
            "macos": _MACOS_CMD,
        }
    )
    result = spec.resolve_command("install", platform="linux")
    assert result is _INSTALL_CMD


def test_resolve_command_exact_os_macos() -> None:
    spec = _make_spec(
        install={
            "linux": _INSTALL_CMD,
            "macos": _MACOS_CMD,
        }
    )
    result = spec.resolve_command("install", platform="macos")
    assert result is _MACOS_CMD


def test_resolve_command_wildcard_fallback() -> None:
    """When no exact-OS entry exists, '*' should be returned."""
    spec = _make_spec(
        install={
            "*": _WILDCARD_CMD,
        }
    )
    result = spec.resolve_command("install", platform="windows")
    assert result is _WILDCARD_CMD


def test_resolve_command_exact_takes_priority_over_wildcard() -> None:
    spec = _make_spec(
        install={
            "linux": _INSTALL_CMD,
            "*": _WILDCARD_CMD,
        }
    )
    result = spec.resolve_command("install", platform="linux")
    assert result is _INSTALL_CMD


def test_resolve_command_missing_action_returns_none() -> None:
    """When a spec has no mapping for the requested action, return None."""
    spec = _make_spec(install=None, auth=None)
    assert spec.resolve_command("install", platform="macos") is None
    assert spec.resolve_command("auth", platform="linux") is None


def test_resolve_command_missing_platform_with_wildcard() -> None:
    """Missing exact-OS but wildcard present — wildcard is returned."""
    spec = _make_spec(
        auth={
            "*": _WILDCARD_CMD,
        }
    )
    result = spec.resolve_command("auth", platform="windows")
    assert result is _WILDCARD_CMD


def test_resolve_command_missing_platform_no_wildcard_returns_none() -> None:
    """No exact OS match and no wildcard — return None."""
    spec = _make_spec(
        install={
            "macos": _MACOS_CMD,
        }
    )
    result = spec.resolve_command("install", platform="linux")
    assert result is None


# ---------------------------------------------------------------------------
# BackendSpec.guidance_hints — legacy shim
# ---------------------------------------------------------------------------


def test_guidance_hints_derives_from_install_and_auth() -> None:
    spec = _make_spec(
        install={"*": BackendCommand(description="Install hint text", command="cmd-install")},
        auth={"*": BackendCommand(description="Auth hint text", command="cmd-auth")},
    )
    hints = spec.guidance_hints()
    assert len(hints) == 2
    # Each hint contains both the description and the command.
    assert any("Install hint text" in h and "cmd-install" in h for h in hints)
    assert any("Auth hint text" in h and "cmd-auth" in h for h in hints)


def test_guidance_hints_empty_when_no_mappings() -> None:
    spec = _make_spec(install=None, auth=None)
    assert spec.guidance_hints() == ()


def test_guidance_hints_partial_mappings() -> None:
    spec = _make_spec(
        install={"*": BackendCommand(description="Just install", command="cmd")},
        auth=None,
    )
    hints = spec.guidance_hints()
    assert len(hints) == 1
    assert "Just install" in hints[0]
    assert "cmd" in hints[0]


# ---------------------------------------------------------------------------
# to_legacy_config round-trip — BackendCommand does not appear in legacy config
# ---------------------------------------------------------------------------


def test_to_legacy_config_excludes_install_auth() -> None:
    """The legacy config dict must not contain 'install' or 'auth' keys."""
    spec = BackendSpec(
        name="test",
        executable="test-exe",
        capabilities=frozenset({BackendCapability.ACP_STREAMING}),
        install={"*": BackendCommand(description="d", command="c")},
        auth={"*": BackendCommand(description="d2", command="c2")},
    )
    config = spec.to_legacy_config()
    assert "install" not in config
    assert "auth" not in config
    assert "install_hint" not in config
    assert "auth_hint" not in config
    assert config["supports_acp"] is True
