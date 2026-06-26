from pathlib import Path

import yaml

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


def test_doctor_fails_when_manifest_invalid(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text("services: not-a-mapping\n")
    check = _manifest_check(run_doctor_checks())
    assert check.status == "fail"
    assert "services" in check.message


def test_doctor_fails_on_cross_vendor_reviewer_when_only_codex(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text(
        yaml.safe_dump({"project_name": "demo", "reviewer": "claude-opus"})
    )
    monkeypatch.setattr(
        "kagan.core.doctor_checks.shutil.which",
        lambda name: "/usr/bin/codex" if name == "codex" else None,
    )
    check = next(c for c in run_doctor_checks() if c.name == "manifest models")
    assert check.status == "fail"
    assert "claude-opus" in check.message
    assert "codex" in check.message


def test_doctor_models_ok_when_runnable_on_any_path_cli(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".kagan").mkdir()
    (tmp_path / ".kagan" / "repo.yaml").write_text(
        yaml.safe_dump({"project_name": "demo", "reviewer": "claude-opus"})
    )
    monkeypatch.setattr(
        "kagan.core.doctor_checks.shutil.which",
        lambda name: "/usr/bin/x" if name in ("claude", "codex") else None,
    )
    assert _check_manifest_models() is None
