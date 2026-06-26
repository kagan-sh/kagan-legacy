from pathlib import Path

import yaml

from kagan.core.doctor_checks import run_doctor_checks


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
