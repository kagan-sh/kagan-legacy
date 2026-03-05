import subprocess

import pytest

from kagan.cli._bootstrap import _build_install_command, check_and_install_update

pytestmark = [pytest.mark.core, pytest.mark.unit]


def test_build_install_command_uv_prerelease_uses_uv_flags() -> None:
    command = _build_install_command("uv", prerelease=True)

    assert command == ["uv", "tool", "install", "--upgrade", "kagan", "--prerelease", "allow"]


def test_build_install_command_pip_prerelease_uses_pre_flag() -> None:
    command = _build_install_command("pip", prerelease=True)

    assert command[-1] == "--pre"


def test_check_and_install_update_uses_uv_for_prerelease(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, list[str]] = {}

    monkeypatch.setattr("kagan.cli._bootstrap._current_version", lambda: "0.7.0b1")
    monkeypatch.setattr(
        "kagan.cli._bootstrap._fetch_pypi_version", lambda timeout_seconds=6.0: "0.7.0b2"
    )
    monkeypatch.setattr("kagan.cli._bootstrap._detect_install_method", lambda: "uv")
    monkeypatch.setattr("kagan.cli._bootstrap.build_sanitized_subprocess_environment", lambda: {})
    monkeypatch.setattr("kagan.cli._bootstrap._write_cache", lambda _data: None)

    def _fake_run(
        command: list[str], *, capture_output: bool, text: bool, env: dict[str, str]
    ) -> subprocess.CompletedProcess[str]:
        del capture_output, text, env
        captured["command"] = command
        return subprocess.CompletedProcess(args=command, returncode=0, stdout="", stderr="")

    monkeypatch.setattr("kagan.cli._bootstrap.subprocess.run", _fake_run)

    ok, message = check_and_install_update(check_only=False, prerelease=True, force=True)

    assert ok is True
    assert message == "Updated via uv: 0.7.0b1 -> 0.7.0b2"
    assert captured["command"] == [
        "uv",
        "tool",
        "install",
        "--upgrade",
        "kagan",
        "--prerelease",
        "allow",
    ]
