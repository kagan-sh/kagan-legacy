"""Lever 6 — provenance receipt auto-write + multi-approver gate in approve_task."""

from datetime import datetime
from pathlib import Path

from kagan.core import Harness
from kagan.core.enums import TaskState
from kagan.core.models import CheckResult
from tests.helpers.gitrepo import make_repo


async def _review_task(core: Harness, *, risk: str) -> str:
    task = core.create_task("Migrate billing")
    core.update_task(task.id, branch="kagan/" + task.id, risk=risk)
    core.transition_task(task.id, TaskState.REVIEW)
    from kagan.core.comprehension import required_keys

    for key in required_keys(risk):
        core.record_comprehension(
            task.id, key, "Moves billing to usage-based; could break if the webhook retries twice."
        )
    return task.id


async def test_low_risk_reaches_ready_with_one_approver(tmp_path: Path):
    repo = await make_repo(tmp_path / "repo")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    tid = await _review_task(core, risk="low")
    task = core.approve_task(tid, approver="alice <a@x.io>")
    assert task.state is TaskState.READY


async def test_medium_risk_reaches_ready_with_one_approver(tmp_path: Path):
    repo = await make_repo(tmp_path / "repo")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    tid = await _review_task(core, risk="medium")
    task = core.approve_task(tid, approver="alice <a@x.io>")
    assert task.state is TaskState.READY


async def test_high_risk_one_approver_stays_review_recorded(tmp_path: Path):
    repo = await make_repo(tmp_path / "repo")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    tid = await _review_task(core, risk="high")
    task = core.approve_task(tid, approver="alice <a@x.io>")
    # Recorded but NOT approved — high risk needs a second distinct identity.
    assert task.state is TaskState.REVIEW
    assert task.approvers == ["alice <a@x.io>"]


async def test_high_risk_same_identity_twice_does_not_unlock(tmp_path: Path):
    # Distinctness is by identity: one human pressing twice never meets the bar.
    repo = await make_repo(tmp_path / "repo")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    tid = await _review_task(core, risk="high")
    core.approve_task(tid, approver="alice <a@x.io>")
    task = core.approve_task(tid, approver="alice <a@x.io>")
    assert task.state is TaskState.REVIEW
    assert task.approvers == ["alice <a@x.io>"]  # de-duped


async def test_high_risk_reaches_ready_after_second_distinct_approver(tmp_path: Path):
    repo = await make_repo(tmp_path / "repo")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    tid = await _review_task(core, risk="high")
    core.approve_task(tid, approver="alice <a@x.io>")
    task = core.approve_task(tid, approver="bob <b@x.io>")
    assert task.state is TaskState.READY
    assert set(task.approvers) == {"alice <a@x.io>", "bob <b@x.io>"}


async def test_approve_autowrites_receipt_into_repo_reviews(tmp_path: Path):
    repo = await make_repo(tmp_path / "repo")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    tid = await _review_task(core, risk="low")
    core.approve_task(tid, approver="alice <a@x.io>")
    reviews = repo / ".kagan" / "reviews"
    written = list(reviews.glob("*.md"))
    assert len(written) == 1
    name = written[0].name
    # B23: the receipt filename stamps the LOCAL date (the committed decision log is
    # human-facing; a dev east of UTC after midnight must not see yesterday).
    date = datetime.now().strftime("%Y-%m-%d")
    assert name == f"{date}-migrate-billing.md"
    body = written[0].read_text()
    assert "# Reviewed-before-push receipt: Migrate billing" in body
    # The committable artifact lives in the MAIN repo, NOT the external ledger.
    assert not (core.data_dir / "reviews").exists()


async def test_failed_required_check_keeps_task_in_review_without_receipt(tmp_path: Path):
    # A receipt with Status=Accepted must not be reachable while a declared check
    # failed; the approve chokepoint re-checks the machine gate.
    repo = await make_repo(tmp_path / "repo")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    tid = await _review_task(core, risk="low")
    core.update_task(tid, checks=[CheckResult(name="cargo clippy", passed=False, detail="rc=101")])
    task = core.approve_task(tid, approver="alice <a@x.io>")
    assert task.state is TaskState.REVIEW
    assert not list((repo / ".kagan" / "reviews").glob("*.md"))


async def test_high_risk_does_not_write_receipt_until_bar_met(tmp_path: Path):
    # The receipt is written only AFTER the READY transition (never while waiting).
    repo = await make_repo(tmp_path / "repo")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    tid = await _review_task(core, risk="high")
    core.approve_task(tid, approver="alice <a@x.io>")
    assert not list((repo / ".kagan" / "reviews").glob("*.md"))
    core.approve_task(tid, approver="bob <b@x.io>")
    assert len(list((repo / ".kagan" / "reviews").glob("*.md"))) == 1
