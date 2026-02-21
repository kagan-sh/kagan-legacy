"""ACP roundtrip tests against a mock LLM proxy for each supported agent.

Agents covered:
  - goose      (OPENAI_HOST env var)
  - vtcode     (OPENAI_BASE_URL env var)
  - openhands  (LLM_BASE_URL + LLM_API_KEY env vars)
  - cagent     (agent.yml config file)
  - stakpak    (~/.stakpak/config.toml + --profile flag)
  - vibe       (~/.vibe/config.toml)

Agents intentionally excluded:
  - auggie     (locked to Augment's proprietary backend — no endpoint override)
  - amp        (locked to Sourcegraph's proprietary backend — no endpoint override)

Run with:
    KAGAN_INTEGRATION_TESTS=1 uv run pytest tests/integration/test_agent_acp_roundtrip.py -v

Skip in normal runs (auto-excluded via 'e2e' marker):
    uv run pytest -m "not e2e"
"""

from __future__ import annotations

import asyncio
import os
import shutil
import textwrap
from dataclasses import dataclass
from typing import TYPE_CHECKING

import pytest

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path

from tests.integration._acp_stub_client import StubAcpClient

_INTEGRATION_ENABLED = bool(os.getenv("KAGAN_INTEGRATION_TESTS"))

_SKIP_INTEGRATION = pytest.mark.skipif(
    not _INTEGRATION_ENABLED,
    reason="Set KAGAN_INTEGRATION_TESTS=1 to run ACP roundtrip tests",
)


# ---------------------------------------------------------------------------
# Config file helpers
# ---------------------------------------------------------------------------


def _write_cagent_config(config_dir: Path, proxy_url: str) -> Path:
    """Write an agent.yml for cagent pointing at the mock LLM proxy.

    Returns the path to the written file.
    """
    config_path = config_dir / "agent.yml"
    config_path.write_text(
        textwrap.dedent(f"""\
            models:
              mock:
                provider: openai
                base_url: {proxy_url}/v1
                model: gpt-4o-mini
                api_key: test-key
        """),
        encoding="utf-8",
    )
    return config_path


def _write_stakpak_config(config_dir: Path, proxy_url: str) -> Path:
    """Write a config.toml for stakpak with a ci-mock profile.

    Returns the directory containing the config file; callers must pass
    ``--profile ci-mock`` when invoking the agent.
    """
    stakpak_dir = config_dir / ".stakpak"
    stakpak_dir.mkdir(parents=True, exist_ok=True)
    config_path = stakpak_dir / "config.toml"
    config_path.write_text(
        textwrap.dedent(f"""\
            [profiles.ci-mock.providers.openai]
            type = "custom"
            api_endpoint = "{proxy_url}/v1"
            api_key = "test-key"
        """),
        encoding="utf-8",
    )
    return stakpak_dir


def _write_vibe_config(config_dir: Path, proxy_url: str) -> Path:
    """Write a config.toml for Mistral Vibe pointing at the mock LLM proxy.

    Returns the directory containing the config file.
    """
    vibe_dir = config_dir / ".vibe"
    vibe_dir.mkdir(parents=True, exist_ok=True)
    config_path = vibe_dir / "config.toml"
    config_path.write_text(
        textwrap.dedent(f"""\
            [[providers]]
            name = "mock"
            api_base = "{proxy_url}/v1"
            api_style = "openai"
            backend = "generic"
            api_key = "test-key"
            default_model = "gpt-4o-mini"
        """),
        encoding="utf-8",
    )
    return vibe_dir


# ---------------------------------------------------------------------------
# Shared roundtrip helper
# ---------------------------------------------------------------------------


async def _run_acp_prompt_roundtrip(
    command_parts: list[str],
    *,
    cwd: str,
    env: dict[str, str] | None = None,
) -> None:
    """Spawn an ACP agent, initialize, open a session, send one prompt, then terminate.

    Args:
        command_parts: The fully-resolved ACP run command split into tokens.
        cwd: Working directory for the subprocess.
        env: Additional environment variables to inject (merged with os.environ).
    """
    from acp import PROTOCOL_VERSION, spawn_agent_process
    from acp.schema import ClientCapabilities, FileSystemCapability, Implementation

    client = StubAcpClient()
    merged_env = {**os.environ, **(env or {})}

    async with asyncio.timeout(30.0):
        async with (
            spawn_agent_process(
                client,  # type: ignore[arg-type]
                command_parts[0],
                *command_parts[1:],
                cwd=cwd,
                env=merged_env,
            ) as (conn, process)
        ):
            init_result = await conn.initialize(
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

            assert init_result is not None, "ACP initialize returned None"
            assert init_result.protocol_version == PROTOCOL_VERSION, (
                f"Protocol version mismatch: expected {PROTOCOL_VERSION!r}, "
                f"got {init_result.protocol_version!r}"
            )

            # Open a session and send a minimal prompt.  We do not assert on
            # the response content — just that the round trip completes without
            # raising an exception.
            session = await conn.session_new(
                model="gpt-4o-mini",
                system_prompt="You are a helpful assistant.",
            )
            await conn.session_prompt(
                session_id=session.session_id,
                messages=[{"role": "user", "content": "Say ok."}],
            )

            process.terminate()


@dataclass(frozen=True, slots=True)
class _RoundtripCase:
    binary: str
    command_parts: tuple[str, ...]
    missing_binary_message: str
    prepare_env: Callable[[str, Path, pytest.MonkeyPatch], dict[str, str] | None]


def _prepare_goose_env(
    proxy_url: str,
    _tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    monkeypatch.setenv("OPENAI_HOST", proxy_url)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return {
        "OPENAI_HOST": proxy_url,
        "OPENAI_API_KEY": "test-key",
    }


def _prepare_vtcode_env(
    proxy_url: str,
    _tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    endpoint = f"{proxy_url}/v1"
    monkeypatch.setenv("OPENAI_BASE_URL", endpoint)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    return {
        "OPENAI_BASE_URL": endpoint,
        "OPENAI_API_KEY": "test-key",
    }


def _prepare_openhands_env(
    proxy_url: str,
    _tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    endpoint = f"{proxy_url}/v1"
    monkeypatch.setenv("LLM_BASE_URL", endpoint)
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    return {
        "LLM_BASE_URL": endpoint,
        "LLM_API_KEY": "test-key",
    }


def _prepare_cagent_env(
    proxy_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    del monkeypatch
    _write_cagent_config(tmp_path, proxy_url)
    return None


def _prepare_stakpak_env(
    proxy_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    stakpak_dir = _write_stakpak_config(tmp_path, proxy_url)
    # Point stakpak at the temporary config directory so it doesn't read the
    # real ~/.stakpak/config.toml from the developer's home directory.
    monkeypatch.setenv("STAKPAK_CONFIG_DIR", str(stakpak_dir))
    return {"STAKPAK_CONFIG_DIR": str(stakpak_dir)}


def _prepare_vibe_env(
    proxy_url: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> dict[str, str]:
    vibe_dir = _write_vibe_config(tmp_path, proxy_url)
    # Override HOME so vibe reads our temporary config instead of ~/.vibe/config.toml.
    monkeypatch.setenv("HOME", str(tmp_path))
    return {"HOME": str(tmp_path), "VIBE_CONFIG_DIR": str(vibe_dir)}


_ROUNDTRIP_CASES = (
    pytest.param(
        _RoundtripCase(
            binary="goose",
            command_parts=("goose", "acp"),
            missing_binary_message="goose binary not found in PATH — install to run this test",
            prepare_env=_prepare_goose_env,
        ),
        id="goose",
    ),
    pytest.param(
        _RoundtripCase(
            binary="vtcode",
            command_parts=("vtcode", "acp"),
            missing_binary_message="vtcode binary not found in PATH — install to run this test",
            prepare_env=_prepare_vtcode_env,
        ),
        id="vtcode",
    ),
    pytest.param(
        _RoundtripCase(
            binary="openhands",
            command_parts=("openhands", "acp"),
            missing_binary_message="openhands binary not found in PATH — install to run this test",
            prepare_env=_prepare_openhands_env,
        ),
        id="openhands",
    ),
    pytest.param(
        _RoundtripCase(
            binary="cagent",
            command_parts=("cagent", "acp"),
            missing_binary_message="cagent binary not found in PATH — install Docker Desktop 4.49+",
            prepare_env=_prepare_cagent_env,
        ),
        id="cagent",
    ),
    pytest.param(
        _RoundtripCase(
            binary="stakpak",
            command_parts=("stakpak", "acp", "--profile", "ci-mock"),
            missing_binary_message="stakpak binary not found in PATH — run: cargo install stakpak",
            prepare_env=_prepare_stakpak_env,
        ),
        id="stakpak",
    ),
    pytest.param(
        _RoundtripCase(
            binary="vibe-acp",
            command_parts=("vibe-acp",),
            missing_binary_message=(
                "vibe-acp binary not found in PATH — "
                "run: curl -LsSf https://mistral.ai/vibe/install.sh | bash"
            ),
            prepare_env=_prepare_vibe_env,
        ),
        id="vibe",
    ),
)


@_SKIP_INTEGRATION
@pytest.mark.parametrize("case", _ROUNDTRIP_CASES)
async def test_agent_acp_roundtrip_with_mock_llm(
    case: _RoundtripCase,
    mock_llm_proxy: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Run ACP roundtrip smoke checks across supported agents."""
    if not shutil.which(case.binary):
        pytest.skip(case.missing_binary_message)

    env = case.prepare_env(mock_llm_proxy, tmp_path, monkeypatch)
    await _run_acp_prompt_roundtrip(list(case.command_parts), cwd=str(tmp_path), env=env)
