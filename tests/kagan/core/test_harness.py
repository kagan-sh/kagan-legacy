import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from kagan.core import Harness
from kagan.core.enums import TaskState
from kagan.core.errors import AgentCapError
from tests.helpers.gitrepo import make_repo

# Untracked file inside scope -> harvested, no drift, advances to review.
FAKE_AGENT = """#!/bin/sh
mkdir -p src .kagan
echo "edit" >> src/new.py
echo '{"type":"smoke_tests","payload":{"items":[{"text":"open /health"}]}}' >> .kagan/ask
echo '{"type":"done","payload":{}}' >> .kagan/ask
"""

# Untracked file OUTSIDE scope -> drift finding.
DRIFTER = """#!/bin/sh
echo x >> README.md
"""


@pytest.fixture
async def repo(tmp_path: Path):
    return await make_repo(tmp_path / "repo")


def _install(bin_dir, name, body):
    bin_dir.mkdir(parents=True, exist_ok=True)
    s = bin_dir / name
    s.write_text(body)
    s.chmod(0o755)


async def test_run_lifecycle_harvests_and_reviews(repo, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", FAKE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("add feature")
    task = core.configure_task(task.id, agent_cli="fakeagent", scope=["src/**"])
    assert task.agent_cli == "fakeagent"

    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.state == TaskState.REVIEW
    assert [s.behaviour for s in task.smoke_tests] == ["open /health"]
    assert task.drift is False


async def test_out_of_scope_edit_is_drift(repo, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "drifter", DRIFTER)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("x")
    core.configure_task(task.id, agent_cli="drifter", scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.drift is True
    assert any(f.severity == "blocking" and "README" in f.location for f in task.findings)


async def test_start_task_writes_mcp_config_pointing_at_kagan_mcp(repo, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", FAKE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("x")
    core.configure_task(task.id, agent_cli="fakeagent", scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    wt = Path(core.get_task(task.id).worktree_path)
    cfg = json.loads((wt / ".mcp.json").read_text())
    server = cfg["mcpServers"]["kagan"]
    assert server["command"] == "kagan"
    # B-1: --data-dir is required so the server reads the harness's ledger, not a
    # divergent global default derived from the worktree's own git root.
    assert server["args"] == ["mcp", "--task-id", task.id, "--data-dir", str(core.data_dir)]


async def test_mcp_less_recipe_writes_no_config_and_uses_ask(repo, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "kimi", FAKE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("x")
    core.configure_task(task.id, agent_cli="kimi", scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)

    wt = Path(core.get_task(task.id).worktree_path)
    assert not (wt / ".mcp.json").exists()
    assert [s.behaviour for s in core.get_task(task.id).smoke_tests] == ["open /health"]


async def test_start_task_reuses_worktree_on_send_back(repo, tmp_path, monkeypatch):
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", FAKE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")

    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("x")
    core.configure_task(task.id, agent_cli="fakeagent", scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)
    first = core.get_task(task.id).worktree_path

    await core.start_task(task.id)
    await core.await_agent(task.id)
    assert core.get_task(task.id).worktree_path == first


async def test_agent_cap_refuses_third_concurrent_run(repo, tmp_path):
    # Lever 5: the parallel-agent cliff after 3 (DESIGN L181). With the cap at the
    # unconfigured default of 2 and two tasks RUNNING/VALIDATING, a 3rd start is
    # refused BEFORE any worktree/launch side effect — and allowed once one leaves.
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    a = core.create_task("a")
    b = core.create_task("b")
    c = core.create_task("c")
    core.transition_task(a.id, TaskState.RUNNING)
    core.transition_task(b.id, TaskState.VALIDATING)  # both in-flight states count

    assert core.running_count() == 2
    assert not core.can_start_agent()
    with pytest.raises(AgentCapError):
        await core.start_task(c.id)
    # The refusal had no side effect: the would-be 3rd task never got a worktree.
    assert core.get_task(c.id).worktree_path is None

    # One agent leaves the in-flight set -> the cap clears and a start is allowed.
    core.transition_task(a.id, TaskState.REVIEW)
    assert core.running_count() == 1
    assert core.can_start_agent()


async def test_agent_cap_excludes_the_task_being_started(repo, tmp_path):
    # A send-back re-runs an in-flight task in place; it must not count against
    # itself, so a single running task can always re-run even at a cap of 1.
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    only = core.create_task("only")
    core.transition_task(only.id, TaskState.RUNNING)
    assert core.running_count() == 1
    assert core.running_count(exclude=only.id) == 0
    assert core.can_start_agent(exclude=only.id)


def _dead_pid() -> int:
    # A pid that is guaranteed dead right now: spawn a no-op child, reap it, reuse its
    # pid. The narrow pid-reuse window is the documented residual; for the test the pid
    # is dead the instant after wait() returns.
    import subprocess
    import sys

    proc = subprocess.Popen([sys.executable, "-c", ""])
    proc.wait()
    return proc.pid


async def test_reconcile_frees_cap_slot_for_dead_runner(repo, tmp_path):
    # Rule 12 / fix D: a RUNNING task whose detached runner was hard-killed (dead pid)
    # must, after reconcile, be flagged interrupted, stop counting toward the cap, and
    # surface in the inbox as re-runnable. Fails if a stranded RUNNING task keeps eating
    # a slot forever with no liveness check.
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("stranded")
    core.transition_task(task.id, TaskState.RUNNING)
    core.update_task(task.id, runner_pid=_dead_pid())
    assert core.running_count() == 1  # still counted before reconcile

    reaped = core.reconcile_in_flight()

    assert reaped == [task.id]
    assert core.get_task(task.id).interrupted is True
    assert core.running_count() == 0  # the dead runner no longer occupies a slot
    assert core.can_start_agent()
    # It surfaces in the inbox as the top-precedence re-runnable signal.
    item = next(i for i in core.inbox_tasks() if i.task_id == task.id)
    assert item.signal == "interrupted"


async def test_reconcile_leaves_live_runner_untouched(repo, tmp_path):
    # A RUNNING task with a LIVE runner_pid (this process) must be left alone — only a
    # dead pid is reaped. Fails if reconcile mis-flags a healthy in-flight run.
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("healthy")
    core.transition_task(task.id, TaskState.RUNNING)
    core.update_task(task.id, runner_pid=os.getpid())

    reaped = core.reconcile_in_flight()

    assert reaped == []
    assert core.get_task(task.id).interrupted is False
    assert core.running_count() == 1  # still a live in-flight run


async def test_reconcile_never_recovers_a_settled_task(repo, tmp_path):
    # A task that legitimately reached REVIEW (or READY) is never reaped, even with a
    # dead runner_pid lingering on it — the run finished, the slot is already free.
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("settled")
    core.transition_task(task.id, TaskState.RUNNING)
    core.transition_task(task.id, TaskState.REVIEW)
    core.update_task(task.id, runner_pid=_dead_pid())

    assert core.reconcile_in_flight() == []
    assert core.get_task(task.id).interrupted is False


async def test_rerun_clears_interrupted_and_finishes(repo, tmp_path, monkeypatch):
    # The acceptance loop (rule 12): an interrupted task, re-run via start_task, clears
    # the flag, restamps a live pid, and finishes cleanly in the same worktree.
    bin_dir = tmp_path / "bin"
    _install(bin_dir, "fakeagent", FAKE_AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    core = Harness(data_dir=tmp_path / "ledger", repo_root=repo)
    task = core.create_task("redo")
    core.configure_task(task.id, agent_cli="fakeagent", scope=["src/**"])
    core.transition_task(task.id, TaskState.RUNNING)
    core.update_task(task.id, runner_pid=_dead_pid())
    core.reconcile_in_flight()
    assert core.get_task(task.id).interrupted is True

    await core.start_task(task.id)
    await core.await_agent(task.id)

    task = core.get_task(task.id)
    assert task.interrupted is False  # the fresh run cleared the flag
    assert task.runner_pid == os.getpid()  # re-stamped by the new owner
    assert task.state == TaskState.REVIEW  # finished cleanly


def test_approve_cooldown_runs_from_the_review_transition(tmp_path):
    # Lever 5: the gen->approve cooldown forces a real read. It is derived (never
    # stored) from the RUNNING/VALIDATING -> REVIEW event timestamp + the configured
    # window; `now` is injected so the elapsed window is deterministic. Defaults to
    # 60s for an unconfigured repo.
    core = Harness(data_dir=tmp_path / "ledger")
    task = core.create_task("t")
    core.transition_task(task.id, TaskState.RUNNING)
    core.transition_task(task.id, TaskState.REVIEW)

    landed = _review_landed_at(core, task.id)
    # Immediately after landing: the full window remains, approve must wait.
    assert core.approve_cooldown_remaining(task.id, now=landed) > 0
    # Just inside the window still blocks; past it returns 0 (unlocked).
    assert core.approve_cooldown_remaining(task.id, now=landed + timedelta(seconds=59)) > 0
    assert core.approve_cooldown_remaining(task.id, now=landed + timedelta(seconds=61)) == 0


def test_approve_cooldown_is_zero_before_any_review_transition(tmp_path):
    # No REVIEW transition yet -> nothing to cool down on, so it never blocks.
    core = Harness(data_dir=tmp_path / "ledger")
    task = core.create_task("t")
    assert core.approve_cooldown_remaining(task.id) == 0


def _review_landed_at(core, task_id):
    for event in reversed(core.read_events(task_id)):
        if event.get("type") == "transition" and event.get("to") == "review":
            return datetime.fromisoformat(event["ts"])
    raise AssertionError("no review transition recorded")


class _StubRemoteCi:
    def __init__(self, url):
        self._url = url
        self.seen_branch = None

    async def pr_url(self, branch):
        self.seen_branch = branch
        return self._url


async def test_mark_task_pushed_captures_remote_pr_url(tmp_path):
    # Lever 7 prereq: at mark-pushed kagan reads the PR URL (read-only gh) and
    # persists it so remote_ci.fetch + the CFR metric stop being inert.
    core = Harness(data_dir=tmp_path / "ledger")
    task = core.create_task("t")
    core.update_task(task.id, branch="kagan/" + task.id)
    core.transition_task(task.id, TaskState.READY)
    core._remote_ci_obj = _StubRemoteCi("https://github.com/o/r/pull/9")

    pushed = await core.mark_task_pushed(task.id)
    assert pushed.state is TaskState.PR_OPEN
    assert pushed.remote_pr_url == "https://github.com/o/r/pull/9"
    assert core._remote_ci_obj.seen_branch == "kagan/" + task.id


async def test_mark_task_pushed_flips_even_when_gh_yields_no_url(tmp_path):
    # gh absent / no PR yet must NOT block the READY->PR_OPEN flip: the URL stays
    # None and the tripwire just stays inert until a later poll.
    core = Harness(data_dir=tmp_path / "ledger")
    task = core.create_task("t")
    core.update_task(task.id, branch="kagan/" + task.id)
    core.transition_task(task.id, TaskState.READY)
    core._remote_ci_obj = _StubRemoteCi(None)

    pushed = await core.mark_task_pushed(task.id)
    assert pushed.state is TaskState.PR_OPEN
    assert pushed.remote_pr_url is None
