"""End-to-end lifecycle wiring (5-shell-lifecycle-wiring).

Drives a task through the live path with a fake agent and asserts the wired
seams fire: the gate engine runs on harvest (checks populated, not just drift),
manifest services start on run, both human gates are reachable AND enforced.
"""

import os
from pathlib import Path

import pytest

from kagan.core import Harness, git
from kagan.core.enums import TaskState
from kagan.core.errors import ConfigurationError
from kagan.core.ledger import Ledger
from kagan.core.models import Task
from kagan.core.tasks import TaskService

# In-scope edit plus an out-of-scope edit so harvest produces BOTH the gate's
# checks (mirror ran) and drift findings.
AGENT = """#!/bin/sh
mkdir -p src .kagan
echo "edit" >> src/new.py
echo "x" >> README.md
"""


def _install(bin_dir: Path, name: str, body: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    s = bin_dir / name
    s.write_text(body)
    s.chmod(0o755)


async def _repo_with_checks(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    await git.init_repo(path, initial_branch="main", create_initial_commit=False)
    (path / "README.md").write_text("base\n", encoding="utf-8")
    (path / ".kagan").mkdir(exist_ok=True)
    # A declared check so the local mirror runs and Task.checks is populated.
    (path / ".kagan" / "repo.yaml").write_text("checks:\n  lint: 'true'\n", encoding="utf-8")
    await git.commit_all(path, "base")
    return path


@pytest.fixture
async def repo(tmp_path: Path):
    return await _repo_with_checks(tmp_path / "repo")


async def test_e2e_agreed_blocker_ships_only_with_a_note_and_surfaces_in_receipt(repo, tmp_path):
    # DESIGN §8 smoke for the headline (F20/F23): a VERIFIED blocking ai-review finding
    # cannot ship behind a green check. Approve is REFUSED until the human records a
    # resolution note; the conceded blocker then appears as a known issue in the receipt
    # and as "shipped unfixed" in the ship digest — never silently green.
    from kagan.core.comprehension import required_keys
    from kagan.format.receipt import render_receipt_digest
    from tests.kagan.format._render import to_str

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli="claude", scope=["src/**"])
    core.transition_task(task.id, TaskState.REVIEW)
    core.update_task(task.id, validator_outcome="ran", risk="medium")
    core.add_finding(
        task.id,
        severity="blocking",
        location="src/a.py:9",
        message="Ctrl-C leaves raw mode",
        source="ai-review",
        confidence=9,
        status="VERIFIED",
    )
    for key in required_keys("medium"):  # isolate the resolution-note gate
        core.record_comprehension(task.id, key, "Rounds half-up; could break on negative input.")
    fid = core.get_task(task.id).findings[0].id

    # Agree with NO note -> approve is refused; the task stays in REVIEW (not shipped).
    core.set_verdict(task.id, fid, verdict="agree")
    assert core.can_approve(task.id) is False
    assert core.approve_task(task.id).state is TaskState.REVIEW

    # Record how the conceded blocker ships -> approve clears to READY.
    core.set_verdict(task.id, fid, verdict="agree", resolution_note="deferred to #42, cosmetic")
    assert core.can_approve(task.id) is True
    assert core.approve_task(task.id).state is TaskState.READY

    receipt = core.render_receipt(task.id)
    assert "known issue · `src/a.py:9`: Ctrl-C leaves raw mode — deferred to #42" in receipt
    assert "_Nothing explicitly marked as not covered._" not in receipt

    digest = to_str(render_receipt_digest(core.get_task(task.id)))
    assert "shipped unfixed" in digest
    assert "✓ ai-review" not in digest
    core.close()


async def test_claim_running_transitions_synchronously_with_runner_pid(repo, tmp_path):
    # F12: the session claims RUNNING synchronously at spawn so the frame after `r`
    # re-probes a running task, not the stale pre-run intake frame. The detached child's
    # start_task then skips the now-redundant transition (idempotent).
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    assert task.state is TaskState.INTAKE

    claimed = core.claim_running(task.id, runner_pid=4242)
    assert claimed.state is TaskState.RUNNING
    assert claimed.runner_pid == 4242

    # Idempotent: claiming an already-running task is a no-op (no duplicate transition).
    transitions_before = sum(
        1 for e in core._ledger.read_events(task.id) if e.get("type") == "transition"
    )
    core.claim_running(task.id, runner_pid=9999)
    transitions_after = sum(
        1 for e in core._ledger.read_events(task.id) if e.get("type") == "transition"
    )
    assert transitions_after == transitions_before
    core.close()


async def test_harvest_runs_gate_so_review_carries_checks_and_drift(repo, tmp_path, monkeypatch):
    # TUI-GATE-01/02/03: harvest delegates to the gate engine, so REVIEW carries
    # the mirror's checks (not just drift). This fails if _harvest reverts to a
    # bare transition to REVIEW.
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli="fakeagent", scope=["src/**"])

    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state == TaskState.REVIEW
    assert any(c.name == "lint" for c in task.checks)  # mirror ran via run_gate
    assert any(f.location.startswith("README") for f in task.findings)  # drift kept


async def test_rerun_resets_harvest_flags_done_and_smoke(repo, tmp_path, monkeypatch):
    # F19: a send-back re-run clears per-run harvest signals — done_reported and smoke —
    # so the re-run never starts already "done" (stale pass-1 signal) or carries pass-1
    # smoke onto a changed diff. The fresh run re-reports them via the MCP tools.
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli="fakeagent", scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    # Pass-1 harvest signals the agent reported.
    core.update_task(task.id, done_reported=True)
    core.add_smoke_test(task.id, behaviour="open /health")
    assert core.get_task(task.id).done_reported is True
    assert core.get_task(task.id).smoke_tests

    await core.send_back(task.id, "fix the thing")
    await core.await_agent(task.id)

    settled = core.get_task(task.id)
    # The fake agent does not re-report, so the reset is directly observable.
    assert settled.done_reported is False
    assert settled.smoke_tests == []
    core.close()


async def test_start_task_leases_port_and_starts_service(tmp_path, monkeypatch):
    # TUI-WS-02/07: start_task wires start_services — a port_env service gets a
    # leased port and a live RunningService. Fails if start_task skips services.
    repo = tmp_path / "repo"
    repo.mkdir()
    await git.init_repo(repo, initial_branch="main", create_initial_commit=False)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    (repo / ".kagan").mkdir()
    (repo / ".kagan" / "repo.yaml").write_text(
        "services:\n  api:\n    command: sleep 30\n    port_env: PORT\n", encoding="utf-8"
    )
    await git.commit_all(repo, "base")

    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", "#!/bin/sh\ntrue\n")
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("x")
    core.configure_task(task.id, agent_cli="fakeagent", scope=["src/**"])
    try:
        await core.start_task(task.id)
        assert "api" in core.get_task(task.id).ports
        assert [s.name for s in core._running[task.id]] == ["api"]
    finally:
        await core.stop_services(task.id)
        await core.await_agent(task.id)


async def test_prepare_worktree_refuses_pinned_branch(tmp_path):
    # TUI-WS-05: prepare_worktree (the one worktree creator) must never check out
    # a pinned branch. Pin the task's own kagan/<id> branch so the guard, not
    # luck, does the work.
    repo = tmp_path / "repo"
    repo.mkdir()
    await git.init_repo(repo, initial_branch="main", create_initial_commit=True)
    (repo / ".kagan").mkdir()
    (repo / ".kagan" / "repo.yaml").write_text("pinned:\n  - kagan/t-1\n", encoding="utf-8")

    ledger = Ledger(tmp_path / "ledger")
    task = Task(id="t-1", title="Task", base_branch="main")
    ledger.save_task(task)
    svc = TaskService(ledger)

    with pytest.raises(ConfigurationError, match="pinned"):
        await svc.prepare_worktree(task, repo)
    assert ledger.load_task("t-1").worktree_path is None


# Phased agent: intake (KAGAN_INTAKE) surfaces a blocking decision; run (KAGAN_RUN)
# edits in scope plus README (out of scope) so a blocking drift finding lands.
PHASED_AGENT = """#!/bin/sh
if [ -n "$KAGAN_INTAKE" ]; then
  printf '%s\\n' '{"type":"intake_decisions","payload":{"understanding":"build it","decisions":[{"question":"Which DB?","severity":"blocking"}]}}' >> .kagan/ask
else
  mkdir -p src
  echo "edit" >> src/new.py
  echo "x" >> README.md
fi
"""


async def test_lifecycle_through_both_gates(tmp_path, monkeypatch):
    # TUI-INTAKE-06 + TUI-GATE-06: walk the full lifecycle and prove BOTH human
    # gates are reachable AND enforced — the run-lock blocks until the blocking
    # decision is answered, and the approve-lock blocks while a finding is open.
    repo = tmp_path / "repo"
    repo.mkdir()
    await git.init_repo(repo, initial_branch="main", create_initial_commit=False)
    (repo / "README.md").write_text("base\n", encoding="utf-8")
    (repo / ".kagan").mkdir()
    (repo / ".kagan" / "repo.yaml").write_text(
        "checks:\n  lint: 'true'\nservices:\n  api:\n    command: sleep 30\n    port_env: PORT\n",
        encoding="utf-8",
    )
    await git.commit_all(repo, "base")

    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", PHASED_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli="fakeagent", scope=["src/**"])

    # Intake surfaces a blocking decision; the RUN GATE is locked until answered.
    await core.run_intake(task.id)
    decisions = core.get_task(task.id).decisions
    assert any(d.severity == "blocking" for d in decisions)
    assert core.can_run(task.id) is False  # gate 1 enforced: run blocked
    dec_id = decisions[0].id
    core.answer_decision(task.id, dec_id, answer="postgres")
    assert core.can_run(task.id) is True  # answering the decision unlocks the run

    # Run -> worktree + services + agent -> harvest runs the gate -> REVIEW.
    try:
        await core.start_task(task.id)
        assert "api" in core.get_task(task.id).ports  # services started on run
        await core.await_agent(task.id)
    finally:
        await core.stop_services(task.id)

    task = core.get_task(task.id)
    assert task.state is TaskState.REVIEW
    assert any(c.name == "lint" for c in task.checks)  # gate engine ran
    blocking = [f for f in task.findings if f.severity == "blocking"]
    assert blocking  # drift produced an open blocking finding

    # APPROVE GATE is locked while a blocking finding is open.
    assert core.can_approve(task.id) is False  # gate 2 enforced: approve blocked
    core.set_verdict(task.id, blocking[0].id, verdict="disagree", reply="intentional")
    for f in blocking[1:]:
        core.set_verdict(task.id, f.id, verdict="agree")
    # Findings cleared, but the comprehension gate (lever 1) still holds approve.
    assert core.can_approve(task.id) is False
    note = "Adds postgres pool; could break if the connection string is unset at boot."
    core.record_comprehension(task.id, "postcondition", note)
    assert core.can_approve(task.id) is False  # one of two medium prompts answered
    core.record_comprehension(task.id, "what_breaks", note)
    assert core.can_approve(task.id) is True  # both gates satisfied -> approve unlocks

    # Approve -> READY -> manual push receipt -> PR_OPEN (never an auto-push).
    # Lever 6: approve_task records the approver; medium risk needs one.
    core.approve_task(task.id, approver="dev <dev@x.io>")
    assert core.get_task(task.id).state is TaskState.READY
    await core.mark_task_pushed(task.id)
    assert core.get_task(task.id).state is TaskState.PR_OPEN


async def test_run_intake_records_no_unknowns_when_fully_specified(tmp_path, monkeypatch):
    # TUI-INTAKE-07: when intake RAN and reported but surfaced zero decisions, the
    # harness records "no unknowns" (audit trail). The discriminator is "did the agent
    # report / exit clean", not "are decisions empty" — so the stub returns a report
    # (understanding) with ok=True but no decisions.
    from kagan.core.models import ReportMessage

    async def _understanding_no_decisions(task, repo_root, *, timeout=None):
        return [ReportMessage(type="intake_decisions", payload={"decisions": []})], True

    monkeypatch.setattr("kagan.core.harness.launch_intake", _understanding_no_decisions)
    core = Harness(data_dir=tmp_path / "ledger", repo_root=tmp_path)
    task = core.create_task("fully specified")
    await core.run_intake(task.id)
    assert not core.get_task(task.id).decisions
    events = core._ledger.read_events(task.id)
    assert any(e.get("type") == "intake_no_unknowns" for e in events)
    assert not any(e.get("type") == "intake_no_output" for e in events)


async def test_run_intake_records_no_output_when_agent_produces_nothing(tmp_path, monkeypatch):
    # F6: a crashed/silent intake (no reports OR non-zero exit) must be LOUD —
    # recorded as intake_no_output, NEVER as the calm intake_no_unknowns. Otherwise
    # "the agent produced nothing" is indistinguishable from "a fully-specified ticket
    # with zero unknowns". Covers both the empty-reports and the non-zero-exit cases.
    async def _crashed(task, repo_root, *, timeout=None):
        return [], False  # no reports AND non-zero exit

    monkeypatch.setattr("kagan.core.harness.launch_intake", _crashed)
    warnings: list[tuple] = []
    monkeypatch.setattr("kagan.core.harness.logger.warning", lambda *args: warnings.append(args))
    core = Harness(data_dir=tmp_path / "ledger", repo_root=tmp_path)
    task = core.create_task("crashed intake")
    await core.run_intake(task.id)
    task = core.get_task(task.id)
    events = core._ledger.read_events(task.id)
    assert any(e.get("type") == "intake_no_output" for e in events)
    assert not any(e.get("type") == "intake_no_unknowns" for e in events)
    assert warnings
    assert any(d.id == "intake-no-output" for d in task.decisions)
    assert not core.can_run(task.id)
