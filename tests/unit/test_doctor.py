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


def test_run_doctor_checks_uses_configured_default_backend(monkeypatch: pytest.MonkeyPatch) -> None:
    client = _FakeClient()
    monkeypatch.setattr(doctor_module, "make_client", lambda: client)
    # Stub out integration checks so no gh CLI calls fire
    monkeypatch.setattr(doctor_module, "all_enabled", lambda: [])
    monkeypatch.setenv("KAGAN_AGENT_BACKEND", "opencode")
    monkeypatch.delenv("ZELLIJ", raising=False)

    checks = doctor_module.run_doctor_checks()

    agent_backend_check = next(check for check in checks if check.name == "agent backend")
    assert client.preflight_calls == [CODEX_BACKEND]
    assert "Default agent backend 'codex'" in agent_backend_check.message
    assert "codex" in agent_backend_check.verify_hint
    assert client.closed is True


@pytest.mark.parametrize(
    (
        "default_agent_backend",
        "expected_install",
        "expected_auth",
        "expected_verify",
    ),
    [
        (
            CLAUDE_CODE_BACKEND,
            "curl -fsSL https://claude.ai/install.sh | bash",
            # Auth description shortened to ≤60 chars (AC #3).
            "Authenticate Claude Code",
            "claude --version",
        ),
        (
            CODEX_BACKEND,
            "npm install -g @openai/codex",
            "OPENAI_API_KEY",
            "codex --version",
        ),
    ],
)
def test_run_doctor_checks_adds_reference_backend_guidance(
    monkeypatch: pytest.MonkeyPatch,
    default_agent_backend: str,
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
    # Stub out integration checks so no gh CLI calls fire
    monkeypatch.setattr(doctor_module, "all_enabled", lambda: [])
    monkeypatch.delenv("ZELLIJ", raising=False)

    checks = doctor_module.run_doctor_checks()

    agent_backend_check = next(check for check in checks if check.name == "agent backend")
    # preflight receives the backend name directly — not the executable
    assert client.preflight_calls == [default_agent_backend]
    assert expected_install in agent_backend_check.fix_hint
    assert expected_auth in agent_backend_check.fix_hint
    assert agent_backend_check.verify_hint == expected_verify
    assert f"Default agent backend '{default_agent_backend}'" in agent_backend_check.message
    assert client.closed is True


# ── run_doctor_check_for_backend unit tests ──────────────────────────────────


def test_run_doctor_check_for_backend_returns_check_for_known_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Returns a DoctorCheck (pass) when the backend executable is on PATH."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _x: "/usr/local/bin/claude")

    result = doctor_module.run_doctor_check_for_backend(CLAUDE_CODE_BACKEND)

    assert result is not None
    assert result.status == "pass"
    assert result.category == "backend"
    assert CLAUDE_CODE_BACKEND in result.name or "claude" in result.name.lower()


def test_run_doctor_check_for_backend_returns_none_for_unknown_backend() -> None:
    """Returns None when the backend name is not registered."""
    result = doctor_module.run_doctor_check_for_backend("nonexistent-backend-xyz")
    assert result is None


def test_run_doctor_check_for_backend_fires_exactly_one_shutil_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exactly one shutil.which call fires — no full backend survey."""
    import shutil

    calls: list[str] = []
    monkeypatch.setattr(shutil, "which", lambda x: (calls.append(x), None)[1])

    result = doctor_module.run_doctor_check_for_backend(CODEX_BACKEND)

    assert len(calls) == 1, f"Expected exactly 1 shutil.which call, got {len(calls)}: {calls}"
    assert calls[0] == "codex"
    # Binary not found → hard FAIL in this recheck call path (deliberate)
    assert result is not None
    assert result.status == "fail"


def test_run_doctor_check_for_backend_does_not_call_environment_or_integration_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """run_doctor_check_for_backend must not invoke environment or integration checks."""
    import shutil

    monkeypatch.setattr(shutil, "which", lambda _x: None)

    env_called: list[bool] = []
    integration_called: list[bool] = []

    monkeypatch.setattr(
        doctor_module,
        "collect_environment_checks",
        lambda: (env_called.append(True), [])[1],
    )
    monkeypatch.setattr(
        doctor_module,
        "all_enabled",
        lambda *_a, **_kw: (integration_called.append(True), [])[1],
    )

    result = doctor_module.run_doctor_check_for_backend(CODEX_BACKEND)

    assert not env_called, "collect_environment_checks must not be called"
    assert not integration_called, "all_enabled must not be called"
    # Backend not installed → fail status (hard failure in recheck path)
    assert result is not None
    assert result.status == "fail"
