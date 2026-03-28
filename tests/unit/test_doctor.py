"""Unit tests for the doctor command."""

import pytest

from kagan.cli import doctor as doctor_module
from kagan.core import CheckStatus, PreflightCheckResult

pytestmark = [pytest.mark.unit]


class _FakeSettingsOps:
    def __init__(self, settings: dict[str, str]) -> None:
        self._settings = settings

    async def get(self) -> dict[str, str]:
        return dict(self._settings)


class _FakeClient:
    def __init__(self) -> None:
        self.settings = _FakeSettingsOps({"default_agent_backend": "codex"})
        self.preflight_calls: list[str] = []
        self.closed = False

    async def preflight(self, *, agent_backend: str):
        self.preflight_calls.append(agent_backend)
        return [
            PreflightCheckResult(
                name="agent_backend",
                status=CheckStatus.PASS,
                message=f"Agent backend '{agent_backend}' found at /usr/bin/{agent_backend}",
                fix_hint="",
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
