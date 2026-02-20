"""Tests for startup doctor gating and agent-backend diagnostics."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from kagan.cli.commands import doctor as doctor_command
from kagan.cli.commands import tui as tui_command


def test_check_agent_backend_suggests_installs_when_no_agents_available(monkeypatch) -> None:
    availability = [
        SimpleNamespace(
            is_available=False,
            agent=SimpleNamespace(
                config=SimpleNamespace(name="Codex"),
                install_command="npm install -g @openai/codex",
                docs_url="https://github.com/openai/codex",
            ),
        ),
        SimpleNamespace(
            is_available=False,
            agent=SimpleNamespace(
                config=SimpleNamespace(name="Gemini CLI"),
                install_command="npm install -g @google/gemini-cli",
                docs_url="https://github.com/google-gemini/gemini-cli",
            ),
        ),
    ]
    monkeypatch.setattr(
        "kagan.core.builtin_agents.get_all_agent_availability",
        lambda: availability,
    )

    result = doctor_command._check_agent_backend()

    assert result.status == "fail"
    assert "no supported AI agent backend found in PATH" in result.detail
    assert "1) Beginner: Pick one AI CLI and follow its docs:" in result.hint
    assert "2) Quick CLI (pick one install command):" in result.hint
    assert "3) Verify:" in result.hint
    assert "Codex" in result.hint
    assert "https://github.com/openai/codex" in result.hint


def test_startup_doctor_gate_is_silent_when_checks_pass(monkeypatch, capsys) -> None:
    monkeypatch.setattr(tui_command, "_auto_cleanup_done_workspaces", lambda db_path: None)
    monkeypatch.setattr(
        doctor_command,
        "run_doctor_checks",
        lambda: doctor_command.DoctorReport(
            checks=[doctor_command.DoctorCheckResult(name="Git", status="pass", detail="git found")]
        ),
    )

    def _unexpected_render(*args: object, **kwargs: object) -> None:
        raise AssertionError("Doctor output should not render when startup checks pass")

    monkeypatch.setattr(doctor_command, "render_doctor_report", _unexpected_render)

    tui_command._run_startup_doctor_gate(db_path=":memory:", skip_preflight=False)

    captured = capsys.readouterr()
    assert captured.out == ""


def test_startup_doctor_gate_renders_report_and_exits_on_failure(monkeypatch, capsys) -> None:
    monkeypatch.setattr(tui_command, "_auto_cleanup_done_workspaces", lambda db_path: None)
    monkeypatch.setattr(doctor_command, "resolve_doctor_verbosity", lambda: "short")

    failing_report = doctor_command.DoctorReport(
        checks=[
            doctor_command.DoctorCheckResult(
                name="AI agent backend",
                status="fail",
                detail="no supported AI agent backend found in PATH",
                hint="Install one of the supported AI CLIs:",
            )
        ]
    )
    monkeypatch.setattr(doctor_command, "run_doctor_checks", lambda: failing_report)

    def _fake_render(
        report: doctor_command.DoctorReport,
        *,
        title: str = "Kagan Doctor",
        verbosity: str = "short",
    ) -> None:
        assert report is failing_report
        assert title == "Kagan Doctor (startup)"
        assert verbosity == "short"
        print("DOCTOR REPORT RENDERED")

    monkeypatch.setattr(doctor_command, "render_doctor_report", _fake_render)

    with pytest.raises(SystemExit) as exc:
        tui_command._run_startup_doctor_gate(db_path=":memory:", skip_preflight=False)

    assert exc.value.code == 1
    captured = capsys.readouterr()
    assert "DOCTOR REPORT RENDERED" in captured.out
    assert "Blocking issues prevent TUI startup" in captured.out
