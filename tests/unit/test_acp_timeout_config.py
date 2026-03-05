import pytest

from kagan.chat.acp import _acp_handshake_timeout_seconds
from kagan.chat.acp import _acp_process_exit_hint as _chat_exit_hint
from kagan.core import CODEX_BACKEND
from kagan.core._acp import _acp_process_exit_hint as _core_exit_hint
from kagan.core._acp import _acp_startup_timeout_seconds

pytestmark = [pytest.mark.unit]


def test_acp_timeout_defaults_are_backend_aware() -> None:
    assert _acp_handshake_timeout_seconds("claude-code") == 12.0
    assert _acp_handshake_timeout_seconds("codex") == 45.0
    assert _acp_handshake_timeout_seconds("gemini-cli") == 20.0

    assert _acp_startup_timeout_seconds("claude-code") == 12.0
    assert _acp_startup_timeout_seconds("codex") == 45.0
    assert _acp_startup_timeout_seconds("gemini-cli") == 20.0


def test_chat_timeout_reads_both_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAGAN_ACP_HANDSHAKE_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("KAGAN_ACP_STARTUP_TIMEOUT_SECONDS", "33")
    assert _acp_handshake_timeout_seconds("gemini-cli") == 33.0

    monkeypatch.setenv("KAGAN_ACP_HANDSHAKE_TIMEOUT_SECONDS", "27")
    assert _acp_handshake_timeout_seconds("gemini-cli") == 27.0


def test_core_timeout_reads_both_env_keys(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("KAGAN_ACP_STARTUP_TIMEOUT_SECONDS", raising=False)
    monkeypatch.setenv("KAGAN_ACP_HANDSHAKE_TIMEOUT_SECONDS", "31")
    assert _acp_startup_timeout_seconds("gemini-cli") == 31.0

    monkeypatch.setenv("KAGAN_ACP_STARTUP_TIMEOUT_SECONDS", "29")
    assert _acp_startup_timeout_seconds("gemini-cli") == 29.0


def test_acp_exit_hints_include_codex_eacces_recovery() -> None:
    details = "spawnSync ... codex-acp EACCES permission denied"
    chat_hint = _chat_exit_hint(agent_backend=CODEX_BACKEND, details=details)
    core_hint = _core_exit_hint(agent_backend=CODEX_BACKEND, details=details)
    assert chat_hint is not None and "npm npx cache permission issue" in chat_hint
    assert core_hint is not None and "npm npx cache permission issue" in core_hint


def test_acp_exit_hints_cover_generic_permission_denied() -> None:
    details = "permission denied while executing backend"
    assert _chat_exit_hint(agent_backend="gemini-cli", details=details) is not None
    assert _core_exit_hint(agent_backend="gemini-cli", details=details) is not None
