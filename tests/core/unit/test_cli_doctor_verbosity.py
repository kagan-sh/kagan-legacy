"""Tests for doctor output verbosity modes."""

from __future__ import annotations

from types import SimpleNamespace

from kagan.cli.commands.doctor import (
    DoctorCheckResult,
    DoctorReport,
    render_doctor_report,
    resolve_doctor_verbosity,
)


def _sample_hint() -> str:
    return "\n".join(
        (
            "Why: Sample reason",
            "1) Beginner: Do beginner setup",
            "2) Quick CLI (pick your OS):",
            "   macOS: brew install sample",
            "   Ubuntu: sudo apt install -y sample",
            "   Windows: winget install Sample.Tool -e",
            "3) Verify: sample --version",
            "Sources:",
            "- https://example.com/official",
            "- https://example.com/secondary",
        )
    )


def _sample_report() -> DoctorReport:
    return DoctorReport(
        checks=[
            DoctorCheckResult(name="Git", status="pass", detail="git found"),
            DoctorCheckResult(
                name="AI agent backend",
                status="fail",
                detail="no supported AI agent backend found in PATH",
                hint=_sample_hint(),
            ),
        ]
    )


def test_render_doctor_report_tldr_is_minimal(capsys) -> None:
    render_doctor_report(_sample_report(), verbosity="tldr")

    captured = capsys.readouterr()
    assert "Git: git found" not in captured.out
    assert "1) Beginner: Do beginner setup" in captured.out
    assert "2) Quick CLI" not in captured.out
    assert "Sources:" not in captured.out


def test_render_doctor_report_short_includes_source_pointer(capsys) -> None:
    render_doctor_report(_sample_report(), verbosity="short")

    captured = capsys.readouterr()
    assert "Git: git found" in captured.out
    assert "1) Beginner: Do beginner setup" in captured.out
    assert "3) Verify: sample --version" in captured.out
    assert "Source: https://example.com/official" in captured.out
    assert "2) Quick CLI" not in captured.out


def test_render_doctor_report_technical_shows_full_details(capsys) -> None:
    render_doctor_report(_sample_report(), verbosity="technical")

    captured = capsys.readouterr()
    assert "1) Beginner: Do beginner setup" in captured.out
    assert "2) Quick CLI (pick your OS):" in captured.out
    assert "macOS: brew install sample" in captured.out
    assert "Sources:" in captured.out
    assert "https://example.com/secondary" in captured.out


def test_resolve_doctor_verbosity_prefers_override() -> None:
    assert resolve_doctor_verbosity("tldr") == "tldr"


def test_resolve_doctor_verbosity_uses_config_default(monkeypatch) -> None:
    fake_config = SimpleNamespace(general=SimpleNamespace(doctor_verbosity="technical"))
    monkeypatch.setattr(
        "kagan.cli.commands.doctor.KaganConfig.load",
        lambda _path: fake_config,
    )
    assert resolve_doctor_verbosity() == "technical"
