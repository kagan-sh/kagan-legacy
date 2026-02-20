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
from typing import TYPE_CHECKING, Any

import pytest

if TYPE_CHECKING:
    from pathlib import Path

_INTEGRATION_ENABLED = bool(os.getenv("KAGAN_INTEGRATION_TESTS"))

_SKIP_INTEGRATION = pytest.mark.skipif(
    not _INTEGRATION_ENABLED,
    reason="Set KAGAN_INTEGRATION_TESTS=1 to run ACP roundtrip tests",
)


# ---------------------------------------------------------------------------
# ACP stub client
# ---------------------------------------------------------------------------


class _StubAcpClient:
    """Minimal ACP client stub sufficient for a single prompt roundtrip.

    All handler methods are no-ops or return the minimal value the ACP SDK
    expects.  The stub deliberately ignores all server-initiated calls so that
    the test can focus solely on whether the agent can process a prompt without
    erroring out.
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

    client = _StubAcpClient()
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


# ---------------------------------------------------------------------------
# goose (Block) — OPENAI_HOST env var
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
async def test_goose_acp_roundtrip_with_mock_llm(
    mock_llm_proxy: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Goose routes its LLM calls via OPENAI_HOST (not OPENAI_BASE_URL).

    The mock proxy satisfies the OpenAI-compatible endpoint so that the agent
    can complete a prompt without a real API key.
    """
    if not shutil.which("goose"):
        pytest.skip("goose binary not found in PATH — install to run this test")

    monkeypatch.setenv("OPENAI_HOST", mock_llm_proxy)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    await _run_acp_prompt_roundtrip(
        ["goose", "acp"],
        cwd=str(tmp_path),
        env={
            "OPENAI_HOST": mock_llm_proxy,
            "OPENAI_API_KEY": "test-key",
        },
    )


# ---------------------------------------------------------------------------
# vtcode (VT Code) — OPENAI_BASE_URL env var
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
async def test_vtcode_acp_roundtrip_with_mock_llm(
    mock_llm_proxy: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """VT Code honours the standard OPENAI_BASE_URL for endpoint override."""
    if not shutil.which("vtcode"):
        pytest.skip("vtcode binary not found in PATH — install to run this test")

    monkeypatch.setenv("OPENAI_BASE_URL", f"{mock_llm_proxy}/v1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    await _run_acp_prompt_roundtrip(
        ["vtcode", "acp"],
        cwd=str(tmp_path),
        env={
            "OPENAI_BASE_URL": f"{mock_llm_proxy}/v1",
            "OPENAI_API_KEY": "test-key",
        },
    )


# ---------------------------------------------------------------------------
# openhands — LLM_BASE_URL + LLM_API_KEY env vars (LiteLLM)
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
async def test_openhands_acp_roundtrip_with_mock_llm(
    mock_llm_proxy: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """OpenHands uses LiteLLM; endpoint override is via LLM_BASE_URL."""
    if not shutil.which("openhands"):
        pytest.skip("openhands binary not found in PATH — install to run this test")

    monkeypatch.setenv("LLM_BASE_URL", f"{mock_llm_proxy}/v1")
    monkeypatch.setenv("LLM_API_KEY", "test-key")

    await _run_acp_prompt_roundtrip(
        ["openhands", "acp"],
        cwd=str(tmp_path),
        env={
            "LLM_BASE_URL": f"{mock_llm_proxy}/v1",
            "LLM_API_KEY": "test-key",
        },
    )


# ---------------------------------------------------------------------------
# cagent (Docker) — agent.yml config file
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
async def test_cagent_acp_roundtrip_with_mock_llm(
    mock_llm_proxy: str,
    tmp_path: Path,
) -> None:
    """Docker cagent reads model config from agent.yml in the working directory."""
    if not shutil.which("cagent"):
        pytest.skip("cagent binary not found in PATH — install Docker Desktop 4.49+")

    _write_cagent_config(tmp_path, mock_llm_proxy)

    await _run_acp_prompt_roundtrip(
        ["cagent", "acp"],
        cwd=str(tmp_path),
    )


# ---------------------------------------------------------------------------
# stakpak — config.toml profile + --profile flag
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
async def test_stakpak_acp_roundtrip_with_mock_llm(
    mock_llm_proxy: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Stakpak uses a named profile in config.toml; we pass --profile ci-mock."""
    if not shutil.which("stakpak"):
        pytest.skip("stakpak binary not found in PATH — run: cargo install stakpak")

    stakpak_dir = _write_stakpak_config(tmp_path, mock_llm_proxy)
    # Point stakpak at the temporary config directory so it doesn't read the
    # real ~/.stakpak/config.toml from the developer's home directory.
    monkeypatch.setenv("STAKPAK_CONFIG_DIR", str(stakpak_dir))

    await _run_acp_prompt_roundtrip(
        ["stakpak", "acp", "--profile", "ci-mock"],
        cwd=str(tmp_path),
        env={"STAKPAK_CONFIG_DIR": str(stakpak_dir)},
    )


# ---------------------------------------------------------------------------
# vibe (Mistral Vibe) — ~/.vibe/config.toml
# ---------------------------------------------------------------------------


@_SKIP_INTEGRATION
async def test_vibe_acp_roundtrip_with_mock_llm(
    mock_llm_proxy: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mistral Vibe reads provider config from ~/.vibe/config.toml."""
    if not shutil.which("vibe-acp"):
        pytest.skip(
            "vibe-acp binary not found in PATH — "
            "run: curl -LsSf https://mistral.ai/vibe/install.sh | bash"
        )

    vibe_dir = _write_vibe_config(tmp_path, mock_llm_proxy)
    # Override HOME so vibe reads our temporary config instead of ~/.vibe/config.toml.
    monkeypatch.setenv("HOME", str(tmp_path))

    await _run_acp_prompt_roundtrip(
        ["vibe-acp"],
        cwd=str(tmp_path),
        env={"HOME": str(tmp_path), "VIBE_CONFIG_DIR": str(vibe_dir)},
    )
