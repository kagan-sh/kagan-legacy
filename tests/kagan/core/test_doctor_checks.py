from pathlib import Path

import yaml
from click.testing import CliRunner

from kagan.cli.doctor import doctor
from kagan.core.doctor_checks import _check_manifest_models, run_doctor_checks


def _manifest_check(checks):
    return next(c for c in checks if c.name == "repo manifest")


def test_doctor_passes_with_valid_manifest(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text(
        yaml.safe_dump({"project_name": "demo", "services": {"api": {"command": "python -m api"}}})
    )
    check = _manifest_check(run_doctor_checks())
    assert check.status == "pass"
    assert "1 service" in check.message


def test_doctor_fails_when_manifest_missing(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    check = _manifest_check(run_doctor_checks())
    assert check.status == "fail"
    assert ".kagan/repo.yaml" in check.message
    assert "kagan init" in check.fix_hint
    assert "services" not in check.fix_hint


def test_doctor_command_exits_nonzero_on_hard_fail(tmp_path: Path, monkeypatch):
    # F2: `kg doctor` MUST exit non-zero on a hard fail so `kg doctor && kg ...` is safe.
    # A missing manifest is a hard fail (must be fixed), so the command exits non-zero.
    monkeypatch.chdir(tmp_path)
    result = CliRunner().invoke(doctor, [])
    assert result.exit_code != 0


def test_doctor_fails_when_manifest_invalid(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("services: not-a-mapping\n")
    check = _manifest_check(run_doctor_checks())
    assert check.status == "fail"
    assert "services" in check.message


def test_doctor_warns_when_a_models_configured_cli_is_not_on_path(tmp_path: Path, monkeypatch):
    # Models live under their CLI's key; if that CLI isn't installed, those tasks would
    # silently fall back to the CLI default — doctor warns (not fails: it's degradeable).
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text(
        yaml.safe_dump({"project_name": "demo", "agents": {"kimi": {"reviewer": "kimi-x"}}})
    )
    monkeypatch.setattr(
        "kagan.core.doctor_checks.shutil.which",
        lambda name: "/usr/bin/codex" if name == "codex" else None,
    )
    check = next(c for c in run_doctor_checks() if c.name == "manifest models")
    assert check.status == "warn"
    assert "kimi" in check.message


def test_doctor_models_ok_when_configured_cli_is_on_path(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text(
        yaml.safe_dump({"project_name": "demo", "agents": {"codex": {"reviewer": "o3"}}})
    )
    monkeypatch.setattr(
        "kagan.core.doctor_checks.shutil.which",
        lambda name: "/usr/bin/x" if name == "codex" else None,
    )
    assert _check_manifest_models() is None
