"""Unit tests for doctor CLI presentation."""

from __future__ import annotations

from io import StringIO

import pytest
from rich.console import Console

from kagan.cli._doctor_output import render_short
from kagan.cli.doctor import DoctorCheck

pytestmark = [pytest.mark.unit]


def _render(checks: list[DoctorCheck]) -> str:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, color_system=None, width=100)
    console.print(render_short(checks))
    return buffer.getvalue()


def test_short_output_collapses_optional_backend_warnings() -> None:
    checks = [
        DoctorCheck("git", "pass", "git found", "", "git --version"),
        DoctorCheck(
            "agent backends",
            "pass",
            "Default backend 'claude-code' ready - 1/3 backends installed",
            "",
            "claude --version",
            category="backend",
        ),
        DoctorCheck(
            "backend: claude-code (default)",
            "pass",
            "found",
            "",
            "claude --version",
            category="backend",
        ),
        DoctorCheck(
            "backend: codex",
            "warn",
            "missing",
            "Install 'codex' to enable the 'codex' backend",
            "codex --version",
            category="backend",
        ),
        DoctorCheck(
            "backend: gemini-cli",
            "warn",
            "missing",
            "Install 'gemini' to enable the 'gemini-cli' backend",
            "gemini --version",
            category="backend",
        ),
    ]

    output = _render(checks)

    assert "Agent backends" in output
    assert "Installed:" in output
    assert "Optional missing:" in output
    assert "codex, gemini-cli" in output
    assert "Install 'codex'" not in output
    assert "Install 'gemini'" not in output


def test_short_output_keeps_required_quick_fixes() -> None:
    checks = [
        DoctorCheck("git", "pass", "git found", "", "git --version"),
        DoctorCheck("tmux", "warn", "tmux missing", "Use an IDE launcher", "tmux -V"),
        DoctorCheck(
            "project config",
            "warn",
            "pyproject.toml not found",
            "Run this command from your project root",
            "test -f pyproject.toml",
        ),
    ]

    output = _render(checks)

    assert "Usable with warnings" in output
    assert "Required environment" in output
    assert "Actions" in output
    assert "Use an IDE launcher" in output
    assert "Run this command from your project root" in output
