"""Integration tests for all registered agent backends.

Tests are tiered by what they require:
  Tier 1 (KAGAN_INTEGRATION_TESTS=1): binary present in PATH
  Tier 2 (KAGAN_INTEGRATION_TESTS=1): actual ACP protocol handshake

Tier-0 (metadata-only, no binary needed) tests have been moved to:
  tests/core/unit/test_builtin_agents_metadata.py

Run everything:
    KAGAN_INTEGRATION_TESTS=1 uv run pytest tests/integration/ -v

Skip in normal runs (auto-excluded via 'e2e' marker):
    uv run pytest -m "not e2e"
"""

from __future__ import annotations

import asyncio
import os
import shutil
import subprocess
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

from kagan.core.builtin_agents import (
    AGENT_PRIORITY,
    BUILTIN_AGENTS,
    BuiltinAgent,
)
from kagan.core.config import get_os_value

_INTEGRATION_ENABLED = bool(os.getenv("KAGAN_INTEGRATION_TESTS"))

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_ALL_AGENT_NAMES = list(BUILTIN_AGENTS.keys())
_PRIORITY_ORDERED = [n for n in AGENT_PRIORITY if n in BUILTIN_AGENTS]


def _acp_binary_available(agent: BuiltinAgent) -> bool:
    """Return True if the ACP run_command binary resolves to an executable."""
    from kagan.core.preflight import resolve_acp_command

    run_cmd = get_os_value(agent.config.run_command)
    if not run_cmd:
        return False
    resolution = resolve_acp_command(run_cmd, agent.config.name)
    return resolution.resolved_command is not None


def _interactive_binary_available(agent: BuiltinAgent) -> bool:
    """Return True if the interactive CLI binary is on PATH."""
    cmd = get_os_value(agent.config.interactive_command)
    if not cmd:
        return False
    return shutil.which(cmd.split()[0]) is not None


# ---------------------------------------------------------------------------
# Tier 1 — binary availability (KAGAN_INTEGRATION_TESTS=1 required)
# ---------------------------------------------------------------------------


@pytest.mark.skipif(not _INTEGRATION_ENABLED, reason="Set KAGAN_INTEGRATION_TESTS=1")
@pytest.mark.parametrize("agent_name", _ALL_AGENT_NAMES)
def test_agent_binary_responds_to_version_flag(agent_name: str, tmp_path: Path) -> None:
    """Verify the interactive binary starts and exits cleanly with --version or --help.

    Does NOT require API keys — only checks that the binary is executable.
    Skips if the binary is not installed.
    """
    agent = BUILTIN_AGENTS[agent_name]
    if not _interactive_binary_available(agent):
        pytest.skip(f"{agent_name} binary not found in PATH")

    interactive_cmd = get_os_value(agent.config.interactive_command)
    assert interactive_cmd  # already validated above
    binary = interactive_cmd.split()[0]

    for flag in ("--version", "version", "--help", "-h"):
        try:
            subprocess.run(
                [binary, flag],
                capture_output=True,
                timeout=15,
                cwd=str(tmp_path),
            )
            # Binary exited — consider it a success regardless of exit code
            return
        except FileNotFoundError:
            continue
        except subprocess.TimeoutExpired:
            continue

    pytest.fail(
        f"{agent_name}: binary '{binary}' did not respond to any version/help flag "
        "within 15 seconds"
    )


# ---------------------------------------------------------------------------
# Tier 2 — ACP protocol handshake (KAGAN_INTEGRATION_TESTS=1 required)
# ---------------------------------------------------------------------------


class _StubAcpClient:
    """Minimal ACP client stub for handshake-only testing.

    Implements only the methods the ACP SDK may call before we terminate the
    connection.  All methods are stubs that return None / raise gracefully.
    """

    async def session_update(self, *_: Any, **__: Any) -> None:
        pass

    async def request_permission(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def read_text_file(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def write_text_file(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def create_terminal(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def terminal_output(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def kill_terminal(self, *_: Any, **__: Any) -> None:
        pass

    async def release_terminal(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]

    async def wait_for_terminal_exit(self, *_: Any, **__: Any) -> None:
        return None  # type: ignore[return-value]


@pytest.mark.skipif(not _INTEGRATION_ENABLED, reason="Set KAGAN_INTEGRATION_TESTS=1")
@pytest.mark.asyncio
@pytest.mark.parametrize("agent_name", _PRIORITY_ORDERED)
async def test_agent_acp_initialize_handshake(agent_name: str, tmp_path: Path) -> None:
    """Perform a real ACP initialize handshake with each installed agent.

    Protocol flow tested:
      1. Spawn agent subprocess with the configured ACP run_command
      2. Send acp/initialize — exchanges protocol version and capabilities
      3. Assert protocol_version matches the expected ACP version
      4. Terminate the process cleanly

    Does NOT call session/new or session/prompt, so no LLM API key is required.
    Skips automatically if the agent binary is not installed.
    """
    from acp import PROTOCOL_VERSION, spawn_agent_process
    from acp.schema import ClientCapabilities, FileSystemCapability, Implementation

    from kagan.core.preflight import resolve_acp_command

    agent = BUILTIN_AGENTS[agent_name]

    if not _acp_binary_available(agent):
        pytest.skip(f"{agent_name} ACP binary not available. Install hint: {agent.install_command}")

    run_cmd = get_os_value(agent.config.run_command)
    assert run_cmd

    resolution = resolve_acp_command(run_cmd, agent.config.name)
    assert resolution.resolved_command is not None  # guaranteed by _acp_binary_available

    command_parts = resolution.resolved_command
    client = _StubAcpClient()

    async with asyncio.timeout(30.0):
        async with (
            spawn_agent_process(
                client,  # type: ignore[arg-type]
                command_parts[0],
                *command_parts[1:],
                cwd=str(tmp_path),
            ) as (conn, process)
        ):
            result = await conn.initialize(
                protocol_version=PROTOCOL_VERSION,
                client_capabilities=ClientCapabilities(
                    fs=FileSystemCapability(
                        read_text_file=True,
                        write_text_file=False,
                    ),
                    terminal=False,
                ),
                client_info=Implementation(
                    name="kagan-integration-test",
                    title="Kagan Integration Test",
                    version="0.0.1",
                ),
            )

            assert result is not None, f"{agent_name}: initialize returned None"
            assert result.protocol_version == PROTOCOL_VERSION, (
                f"{agent_name}: protocol version mismatch — "
                f"expected {PROTOCOL_VERSION!r}, got {result.protocol_version!r}"
            )

            process.terminate()
