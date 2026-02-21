"""Tests for cross-platform command utility helpers."""

from __future__ import annotations

import pytest

from kagan.core.command_utils import (
    build_kagan_mcp_command_args,
    clear_which_cache,
    format_command_for_shell,
    resolve_kagan_cli_invocation,
    split_command_string,
)


def test_resolve_kagan_cli_invocation_prefers_path_binary(monkeypatch) -> None:
    clear_which_cache()
    monkeypatch.setattr(
        "kagan.core.command_utils.shutil.which",
        lambda name: "/tmp/bin/kagan" if name == "kagan" else None,
    )

    command, args = resolve_kagan_cli_invocation()

    assert command == "/tmp/bin/kagan"
    assert args == []


def test_resolve_kagan_cli_invocation_falls_back_to_python_module(monkeypatch) -> None:
    clear_which_cache()
    monkeypatch.setattr("kagan.core.command_utils.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "kagan.core.command_utils._resolve_current_python_executable",
        lambda: "/usr/bin/python3",
    )

    command, args = resolve_kagan_cli_invocation()

    assert command == "/usr/bin/python3"
    assert args == ["-m", "kagan"]


def test_build_kagan_mcp_command_args_appends_mcp_payload(monkeypatch) -> None:
    monkeypatch.setattr(
        "kagan.core.command_utils.resolve_kagan_cli_invocation",
        lambda: ("python", ["-m", "kagan"]),
    )

    command, args = build_kagan_mcp_command_args(["mcp", "--identity", "kagan"])

    assert command == "python"
    assert args == ["-m", "kagan", "mcp", "--identity", "kagan"]


@pytest.mark.windows_ci
def test_split_command_string_windows_uses_mslex(monkeypatch) -> None:
    monkeypatch.setattr("kagan.core.command_utils.is_windows", lambda: True)

    parsed = split_command_string(r'"C:\Program Files\Tool\tool.exe" "arg with spaces"')

    assert parsed == [r"C:\Program Files\Tool\tool.exe", "arg with spaces"]


@pytest.mark.windows_ci
def test_format_command_for_shell_windows_roundtrip(monkeypatch) -> None:
    monkeypatch.setattr("kagan.core.command_utils.is_windows", lambda: True)
    command = r"C:\Program Files\Tool\tool.exe"
    args = ["arg with spaces", r"C:\tmp\foo bar.txt", "--flag=%PATH%"]

    rendered = format_command_for_shell(command, args)
    parsed = split_command_string(rendered)

    assert parsed == [command, *args]
