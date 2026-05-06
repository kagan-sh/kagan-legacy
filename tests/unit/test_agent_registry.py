"""Agent backend registry schema validation.

These tests validate the BackendSpec registry: every registered
backend must have the required attributes with the correct types.
Acceptance tests exercise ONE backend at a time; these tests validate ALL entries at once.
"""

import pytest

from kagan.core._agent import (
    REFERENCE_BACKENDS,
    AgentError,
    BackendCapability,
    get_backend_spec,
    list_backend_specs,
)

pytestmark = [pytest.mark.unit]


def test_each_backend_has_required_keys_and_nonempty_executable() -> None:
    specs = list_backend_specs()
    for name, spec in specs.items():
        assert isinstance(spec.executable, str), f"{name}: executable must be str"
        assert spec.executable, f"{name}: executable must not be empty"
        assert isinstance(spec.capabilities, frozenset), f"{name}: capabilities must be frozenset"
        assert spec.capabilities, f"{name}: capabilities must not be empty"


def test_backend_specs_expose_reference_backends() -> None:
    assert REFERENCE_BACKENDS == ("claude-code", "codex")

    claude = get_backend_spec("claude")
    codex = get_backend_spec("codex")

    assert claude.reference is True
    assert codex.reference is True
    assert claude.display_name == "Claude Code"
    assert codex.display_name == "Codex CLI"
    assert claude.install is not None
    assert codex.install is not None
    assert claude.auth is not None
    assert codex.auth is not None
    assert claude.resolve_command("install") is not None
    assert codex.resolve_command("install") is not None
    assert claude.resolve_command("auth") is not None
    assert codex.resolve_command("auth") is not None
    assert "claude-code" in claude.label().lower()
    assert "codex" in codex.label().lower()
    assert BackendCapability.ACP_STREAMING in claude.capabilities
    assert BackendCapability.ACP_STREAMING in codex.capabilities
    assert BackendCapability.TASK_SCOPED_MCP in claude.capabilities
    assert BackendCapability.TASK_SCOPED_MCP in codex.capabilities


def test_list_backend_specs_keys_consistent() -> None:
    specs = list_backend_specs()
    for name, spec in specs.items():
        assert spec.name == name


def test_kimi_cli_supports_acp_mode() -> None:
    spec = get_backend_spec("kimi-cli")
    assert BackendCapability.ACP_STREAMING in spec.capabilities


def test_acp_capable_backends_define_acp_command() -> None:
    for name, spec in list_backend_specs().items():
        if BackendCapability.ACP_STREAMING in spec.capabilities:
            assert isinstance(spec.acp_command, tuple), (
                f"{name}: ACP-capable backend must define tuple acp_command"
            )
            assert spec.acp_command, f"{name}: ACP-capable backend acp_command must not be empty"


def test_reference_aligned_executables_for_acp_backends() -> None:
    expected = {
        "github-copilot": "copilot",
        "docker-cagent": "cagent",
        "mistral-vibe": "vibe",
        "vt-code": "vtcode",
    }
    for name, executable in expected.items():
        assert get_backend_spec(name).executable == executable


def test_reference_aligned_acp_commands_for_shared_backends() -> None:
    expected = {
        "claude-code": ("npx", "claude-code-acp"),
        "codex": ("npx", "-y", "@zed-industries/codex-acp"),
        "gemini-cli": ("gemini", "--experimental-acp"),
        "kimi-cli": ("kimi", "acp"),
        "github-copilot": ("copilot", "--acp"),
        "goose": ("goose", "acp"),
        "openhands": ("openhands", "acp"),
        "opencode": ("opencode", "acp"),
        "auggie": ("auggie", "--acp"),
        "amp": ("npx", "-y", "amp-acp"),
        "docker-cagent": ("cagent", "acp"),
        "stakpak": ("stakpak", "acp"),
        "mistral-vibe": ("vibe-acp",),
        "vt-code": ("vtcode", "acp"),
    }
    for name, acp_command in expected.items():
        assert get_backend_spec(name).acp_command == acp_command


@pytest.mark.parametrize(
    "backend_name",
    [
        "claude-code",
        "codex",
        "gemini-cli",
        "kimi-cli",
        "github-copilot",
        "goose",
        "openhands",
        "opencode",
        "auggie",
        "amp",
        "docker-cagent",
        "stakpak",
        "mistral-vibe",
        "vt-code",
    ],
)
def test_every_backend_resolve_install_returns_non_none(backend_name: str) -> None:
    """AC #8 — every backend spec has a non-None install BackendCommand."""
    from kagan.core._agent import BackendCommand

    spec = get_backend_spec(backend_name)
    result = spec.resolve_command("install")
    assert result is not None, (
        f"Backend {backend_name!r}: resolve_command('install') returned None — "
        "install entry is missing or has no '*' wildcard"
    )
    assert isinstance(result, BackendCommand), (
        f"Backend {backend_name!r}: resolve_command('install') must return BackendCommand"
    )
    assert result.command, (
        f"Backend {backend_name!r}: install BackendCommand.command must not be empty"
    )
    assert result.description, (
        f"Backend {backend_name!r}: install BackendCommand.description must not be empty"
    )
    assert len(result.description) <= 60, (
        f"Backend {backend_name!r}: description {result.description!r} exceeds 60 chars "
        f"({len(result.description)} chars)"
    )
