"""Branch-protection doctor probe (Phase 14): warn-not-fail, resilient to gh/remote gaps."""

from types import SimpleNamespace

import pytest

from kagan.core import doctor_checks
from kagan.core.doctor_checks import _check_branch_protection


@pytest.fixture
def _in_remoteless_repo(tmp_path, monkeypatch):
    # No manifest above tmp_path → base branch defaults to "main"; tests set remote/gh.
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _fake_gh(returncode: int, stdout: str = "", stderr: str = ""):
    def _run(cmd, **kwargs):
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return _run


def test_skipped_when_gh_absent(_in_remoteless_repo, monkeypatch):
    monkeypatch.setattr(doctor_checks.shutil, "which", lambda _name: None)
    monkeypatch.setattr(doctor_checks, "_has_remote", lambda: True)
    assert _check_branch_protection() is None


def test_skipped_when_no_remote(_in_remoteless_repo, monkeypatch):
    monkeypatch.setattr(doctor_checks.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(doctor_checks, "_has_remote", lambda: False)
    assert _check_branch_protection() is None


def test_pass_when_reviews_required(_in_remoteless_repo, monkeypatch):
    monkeypatch.setattr(doctor_checks.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(doctor_checks, "_has_remote", lambda: True)
    monkeypatch.setattr(
        doctor_checks.subprocess,
        "run",
        _fake_gh(0, stdout='{"required_pull_request_reviews": {"x": 1}}'),
    )
    check = _check_branch_protection()
    assert check is not None and check.status == "pass"


def test_warn_when_protected_without_reviews(_in_remoteless_repo, monkeypatch):
    monkeypatch.setattr(doctor_checks.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(doctor_checks, "_has_remote", lambda: True)
    monkeypatch.setattr(doctor_checks.subprocess, "run", _fake_gh(0, stdout="{}"))
    check = _check_branch_protection()
    assert check is not None and check.status == "warn"
    assert "does not require reviews" in check.message


def test_warn_when_not_protected(_in_remoteless_repo, monkeypatch):
    monkeypatch.setattr(doctor_checks.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(doctor_checks, "_has_remote", lambda: True)
    monkeypatch.setattr(
        doctor_checks.subprocess, "run", _fake_gh(1, stderr="gh: Branch not protected (HTTP 404)")
    )
    check = _check_branch_protection()
    assert check is not None and check.status == "warn"
    assert "NOT branch-protected" in check.message


def test_warn_when_not_authenticated(_in_remoteless_repo, monkeypatch):
    monkeypatch.setattr(doctor_checks.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(doctor_checks, "_has_remote", lambda: True)
    monkeypatch.setattr(
        doctor_checks.subprocess, "run", _fake_gh(1, stderr="gh auth login required")
    )
    check = _check_branch_protection()
    assert check is not None and check.status == "warn"
    assert "not authenticated" in check.message


def test_never_fails_on_subprocess_error(_in_remoteless_repo, monkeypatch):
    monkeypatch.setattr(doctor_checks.shutil, "which", lambda _name: "/usr/bin/gh")
    monkeypatch.setattr(doctor_checks, "_has_remote", lambda: True)

    def _boom(cmd, **kwargs):
        raise OSError("exec failed")

    monkeypatch.setattr(doctor_checks.subprocess, "run", _boom)
    check = _check_branch_protection()
    # The wall is the remote's, not kagan's — kagan can't fix it, so it never hard-fails.
    assert check is not None and check.status == "warn"
