"""Unit tests for kagan.core._subprocess.resolve_spawn_command."""

import sys
from unittest.mock import patch

import pytest

from kagan.core._subprocess import resolve_spawn_command

pytestmark = [pytest.mark.core, pytest.mark.unit, pytest.mark.windows_ci]


# ---------------------------------------------------------------------------
# POSIX behaviour
# ---------------------------------------------------------------------------


def test_posix_bare_name_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with patch("kagan.core._subprocess.shutil.which", return_value="/usr/bin/npx"):
        result = resolve_spawn_command("npx", "claude-code-acp")
    assert result == ["/usr/bin/npx", "claude-code-acp"]


def test_posix_which_none_falls_back_to_original(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with patch("kagan.core._subprocess.shutil.which", return_value=None):
        result = resolve_spawn_command("missing-tool", "--flag")
    assert result == ["missing-tool", "--flag"]


def test_posix_no_extra_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "linux")
    with patch("kagan.core._subprocess.shutil.which", return_value="/usr/local/bin/gh"):
        result = resolve_spawn_command("gh")
    assert result == ["/usr/local/bin/gh"]


# ---------------------------------------------------------------------------
# Windows .cmd / .bat wrapping
# ---------------------------------------------------------------------------


def test_windows_cmd_shim_wrapped_with_cmd_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    resolved = r"C:\Users\user\AppData\Roaming\npm\claude.cmd"
    with patch("kagan.core._subprocess.shutil.which", return_value=resolved):
        result = resolve_spawn_command("claude", "-p", "hello")
    assert result == ["cmd.exe", "/c", resolved, "-p", "hello"]


def test_windows_bat_shim_wrapped_with_cmd_exe(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    resolved = r"C:\tools\run.bat"
    with patch("kagan.core._subprocess.shutil.which", return_value=resolved):
        result = resolve_spawn_command("run", "--flag")
    assert result == ["cmd.exe", "/c", resolved, "--flag"]


def test_windows_ps1_wrapped_with_powershell(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    resolved = r"C:\tools\deploy.ps1"
    with patch("kagan.core._subprocess.shutil.which", return_value=resolved):
        result = resolve_spawn_command("deploy", "--env", "prod")
    assert result == [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        resolved,
        "--env",
        "prod",
    ]


def test_windows_exe_passes_through(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    resolved = r"C:\Program Files\GitHub CLI\gh.exe"
    with patch("kagan.core._subprocess.shutil.which", return_value=resolved):
        result = resolve_spawn_command("gh", "auth", "token")
    assert result == [resolved, "auth", "token"]


def test_windows_which_none_falls_back_to_original(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    with patch("kagan.core._subprocess.shutil.which", return_value=None):
        result = resolve_spawn_command("missing-tool", "--flag")
    assert result == ["missing-tool", "--flag"]


# ---------------------------------------------------------------------------
# Explicit Windows paths — skip which(), inspect suffix
# ---------------------------------------------------------------------------
# Root-relative paths ("\...") are explicit Windows paths even though they do
# not carry a drive letter. They must not be treated as bare command names.


def test_absolute_cmd_path_wraps_without_calling_which(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    abs_path = "\\tools\\claude.cmd"
    with patch("kagan.core._subprocess.shutil.which") as mock_which:
        result = resolve_spawn_command(abs_path, "--flag")
    mock_which.assert_not_called()
    assert result == ["cmd.exe", "/c", abs_path, "--flag"]


def test_absolute_exe_path_passes_through_without_calling_which(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    abs_path = "\\usr\\local\\bin\\git.exe"
    with patch("kagan.core._subprocess.shutil.which") as mock_which:
        result = resolve_spawn_command(abs_path, "status")
    mock_which.assert_not_called()
    assert result == [abs_path, "status"]


# ---------------------------------------------------------------------------
# Mixed-case suffix (.CMD / .BAT)
# ---------------------------------------------------------------------------


def test_windows_mixed_case_cmd_suffix_triggers_wrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    resolved = "/tools/claude.CMD"
    with patch("kagan.core._subprocess.shutil.which", return_value=resolved):
        result = resolve_spawn_command("claude")
    assert result == ["cmd.exe", "/c", resolved]


def test_windows_mixed_case_bat_suffix_triggers_wrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    resolved = "/tools/run.BAT"
    with patch("kagan.core._subprocess.shutil.which", return_value=resolved):
        result = resolve_spawn_command("run")
    assert result == ["cmd.exe", "/c", resolved]


def test_windows_mixed_case_ps1_suffix_triggers_wrap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    resolved = "/tools/script.PS1"
    with patch("kagan.core._subprocess.shutil.which", return_value=resolved):
        result = resolve_spawn_command("script")
    assert result == [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        resolved,
    ]


# ---------------------------------------------------------------------------
# Absolute .cmd path — no args edge case
# ---------------------------------------------------------------------------


def test_absolute_cmd_no_extra_args(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(sys, "platform", "win32")
    abs_path = "\\tools\\cursor.cmd"
    # absolute path: which() must not be called
    with patch("kagan.core._subprocess.shutil.which") as mock_which:
        result = resolve_spawn_command(abs_path)
    mock_which.assert_not_called()
    assert result == ["cmd.exe", "/c", abs_path]
