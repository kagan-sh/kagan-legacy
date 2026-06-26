"""Bare-`kagan` auto-offer (Phase 14): a missing manifest is the one hard fail that
`kagan init` can fix in place, so the session offers setup instead of "continue anyway"
— but only when it's the SOLE fail and we're in a git repo."""

from kagan.cli import main as main_mod
from kagan.core.doctor_checks import DoctorCheck


def _wire(monkeypatch, tmp_path, checks, *, confirm: bool):
    calls: dict = {}

    async def fake_init(repo_root, **_kw):
        calls["init"] = repo_root
        return tmp_path / ".kagan" / "repo.yaml"  # truthy = setup completed

    async def fake_session(*, repo_root):
        calls["session"] = repo_root

    monkeypatch.setattr("kagan.cli.doctor.run_doctor_checks", lambda: checks)
    monkeypatch.setattr("kagan.core.git.repo_root", lambda _start: tmp_path)
    monkeypatch.setattr(main_mod.click, "confirm", lambda *_a, **_k: confirm)
    monkeypatch.setattr("kagan.cli.init.run_init", fake_init)
    monkeypatch.setattr("kagan.cli.session.run", fake_session)
    return calls


def test_offers_init_when_only_manifest_missing(tmp_path, monkeypatch):
    checks = [
        DoctorCheck(name="git", status="pass", message=""),
        DoctorCheck(name="python", status="pass", message=""),
        DoctorCheck(name="repo manifest", status="fail", message="missing"),
    ]
    calls = _wire(monkeypatch, tmp_path, checks, confirm=True)
    main_mod._launch_session()
    assert calls.get("init") == tmp_path
    assert calls.get("session") == tmp_path  # session still launches after setup


def test_declining_setup_does_not_launch_session(tmp_path, monkeypatch):
    # Declining the offer must exit, not drop into a session with no manifest
    # (matches the original "declined the fail → don't proceed" behaviour).
    checks = [
        DoctorCheck(name="git", status="pass", message=""),
        DoctorCheck(name="repo manifest", status="fail", message="missing"),
    ]
    calls = _wire(monkeypatch, tmp_path, checks, confirm=False)
    main_mod._launch_session()
    assert "init" not in calls
    assert "session" not in calls


def test_incomplete_setup_blocks_session(tmp_path, monkeypatch):
    # run_init returning None (e.g. user declined the git bootstrap) must block — the
    # session MUST NOT launch without a usable repo.
    checks = [DoctorCheck(name="repo manifest", status="fail", message="missing")]
    calls: dict = {}

    async def fake_init(repo_root, **_kw):
        calls["init"] = repo_root
        return None  # setup did not complete

    async def fake_session(*, repo_root):
        calls["session"] = repo_root

    monkeypatch.setattr("kagan.cli.doctor.run_doctor_checks", lambda: checks)
    monkeypatch.setattr("kagan.core.git.repo_root", lambda _start: None)
    monkeypatch.setattr(main_mod.click, "confirm", lambda *_a, **_k: True)
    monkeypatch.setattr("kagan.cli.init.run_init", fake_init)
    monkeypatch.setattr("kagan.cli.session.run", fake_session)
    main_mod._launch_session()
    assert "init" in calls  # setup was attempted
    assert "session" not in calls  # but the session was blocked


def test_no_offer_when_other_hard_fail(tmp_path, monkeypatch):
    # git also failing → more than the manifest is wrong; fall to "continue anyway",
    # which (declined here) returns WITHOUT launching the session or offering init.
    checks = [
        DoctorCheck(name="git", status="fail", message="missing"),
        DoctorCheck(name="repo manifest", status="fail", message="missing"),
    ]
    calls = _wire(monkeypatch, tmp_path, checks, confirm=False)
    main_mod._launch_session()
    assert "init" not in calls
    assert "session" not in calls
