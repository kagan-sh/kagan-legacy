"""Harness gate wiring (TUI-GATE-01/10).

run_gate runs the mirror then the engine, writes findings, and transitions to
review; gate_is_stale reflects whether the base advanced. Both assert through
the ledger round-trip so they fail when the wiring breaks.
"""

from pathlib import Path

import pytest

from kagan.core import Harness, git
from kagan.core.enums import TaskState


@pytest.fixture
async def repo(tmp_path: Path):
    r = tmp_path / "repo"
    await git.init_repo(r, initial_branch="main")
    (r / "README.md").write_text("base\n", encoding="utf-8")
    await git.commit_all(r, "base")
    return r


@pytest.mark.asyncio
async def test_run_gate_collects_findings_and_transitions(repo, tmp_path):
    # TUI-GATE-01: a leaked secret surfaces as a blocking finding and the task
    # lands in review after the gate runs.
    wt = tmp_path / "wt"
    await git.worktree_add(repo, wt, branch="feature", base="main")
    (wt / ".env").write_text("TOKEN=x\n", encoding="utf-8")
    await git.commit_all(wt, "leak a secret")

    core = Harness(data_dir=tmp_path / "db", repo_root=repo)
    task = core.create_task("Add feature")
    core.transition_task(task.id, TaskState.RUNNING)
    task.worktree_path = wt
    task.scope = ["src/"]
    core._ledger.save_task(task)

    task = await core.run_gate(task.id)

    assert task.state == TaskState.REVIEW
    assert any(f.severity == "blocking" and ".env" in f.location for f in task.findings)
    await core.aclose()


@pytest.mark.asyncio
async def test_gate_is_stale_when_base_moved(repo, tmp_path):
    # TUI-GATE-10: results go stale once the base branch advances past the worktree.
    wt = tmp_path / "wt"
    await git.worktree_add(repo, wt, branch="feature", base="main")
    core = Harness(data_dir=tmp_path / "db", repo_root=repo)
    task = core.create_task("Add feature")
    task.worktree_path = wt
    core._ledger.save_task(task)

    assert await core.gate_is_stale(task.id) is False
    (repo / "moved.txt").write_text("more\n", encoding="utf-8")
    await git.commit_all(repo, "upstream moves on")
    assert await core.gate_is_stale(task.id) is True
    await core.aclose()
