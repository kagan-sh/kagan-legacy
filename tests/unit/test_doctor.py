"""Unit tests for the doctor command."""

import pytest

from kagan.cli import doctor as doctor_module
from kagan.core import CLAUDE_CODE_BACKEND, CODEX_BACKEND, CheckStatus, PreflightCheckResult

pytestmark = [pytest.mark.unit]


class _FakeSettingsOps:
    def __init__(self, settings: dict[str, str]) -> None:
        self._settings = settings

    async def get(self) -> dict[str, str]:
        return dict(self._settings)


class _FakeClient:
    def __init__(
        self,
        *,
        default_agent_backend: str = CODEX_BACKEND,
        status: CheckStatus = CheckStatus.PASS,
        fix_hint: str = "",
    ) -> None:
        self.settings = _FakeSettingsOps({"default_agent_backend": default_agent_backend})
        self._status = status
        self._fix_hint = fix_hint
        self.preflight_calls: list[str] = []
        self.closed = False

    async def preflight(self, *, agent_backend: str):
        self.preflight_calls.append(agent_backend)
        return [
            PreflightCheckResult(
                name="agent_backend",
                status=self._status,
                message=f"Agent backend '{agent_backend}' found at /usr/bin/{agent_backend}",
                fix_hint=self._fix_hint,
            )
        ]

    def close(self) -> None:
        self.closed = True


class _FakePluginManager:
    def __init__(self, client: _FakeClient) -> None:
        self.client = client

    async def load(self) -> None:
        return None

    def preflight(self) -> list[PreflightCheckResult]:
        return []


def test_run_doctor_checks_uses_configured_default_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient()
    monkeypatch.setattr(doctor_module, "make_client", lambda: client)
    monkeypatch.setattr(doctor_module, "PluginManager", _FakePluginManager)
    monkeypatch.setenv("KAGAN_AGENT_BACKEND", "opencode")
    monkeypatch.delenv("ZELLIJ", raising=False)

    checks = doctor_module.run_doctor_checks()

    agent_backend_check = next(check for check in checks if check.name == "agent backend")
    assert client.preflight_calls == ["codex"]
    assert "Default agent backend 'codex'" in agent_backend_check.message
    assert "codex" in agent_backend_check.verify_hint
    assert client.closed is True


@pytest.mark.parametrize(
    (
        "default_agent_backend",
        "expected_executable",
        "expected_install",
        "expected_auth",
        "expected_verify",
    ),
    [
        (
            CLAUDE_CODE_BACKEND,
            "claude",
            "curl -fsSL https://claude.ai/install.sh | bash",
            "run `claude`",
            "claude --version",
        ),
        (
            CODEX_BACKEND,
            "codex",
            "npm install -g @openai/codex",
            "OPENAI_API_KEY",
            "codex --version",
        ),
    ],
)
def test_run_doctor_checks_adds_reference_backend_guidance(
    monkeypatch: pytest.MonkeyPatch,
    default_agent_backend: str,
    expected_executable: str,
    expected_install: str,
    expected_auth: str,
    expected_verify: str,
) -> None:
    client = _FakeClient(
        default_agent_backend=default_agent_backend,
        status=CheckStatus.WARN,
        fix_hint="Install or configure a different agent backend",
    )
    monkeypatch.setattr(doctor_module, "make_client", lambda: client)
    monkeypatch.setattr(doctor_module, "PluginManager", _FakePluginManager)
    monkeypatch.delenv("ZELLIJ", raising=False)

    checks = doctor_module.run_doctor_checks()

    agent_backend_check = next(check for check in checks if check.name == "agent backend")
    assert client.preflight_calls == [expected_executable]
    assert expected_install in agent_backend_check.fix_hint
    assert expected_auth in agent_backend_check.fix_hint
    assert agent_backend_check.verify_hint == expected_verify
    assert f"Default agent backend '{default_agent_backend}'" in agent_backend_check.message
    assert client.closed is True
