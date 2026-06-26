from pathlib import Path

import pytest

from kagan.core import Harness
from kagan.core.config import RepoConfig
from kagan.core.git import init_repo, worktree_add
from kagan.core.notifications import NotificationEvent


@pytest.fixture
async def core(tmp_path: Path):
    repo = tmp_path / "repo"
    await init_repo(repo, initial_branch="main")
    return Harness(data_dir=tmp_path / "db", repo_root=repo)


@pytest.mark.asyncio
async def test_run_local_mirror_persists_results(core, tmp_path: Path):
    # TUI-MIRROR-01: running the mirror records each declared check on the task.
    wt = tmp_path / "wt"
    await worktree_add(tmp_path / "repo", wt, branch="feature", base="main")
    core._repo_config = RepoConfig(checks={"echo": "echo ok"})

    task = core.create_task("Mirror test")
    core.update_task(task.id, worktree_path=wt)

    updated = await core.run_local_mirror(task.id)
    assert any(c.name == "echo" and c.passed for c in updated.checks)


@pytest.mark.asyncio
async def test_poll_remote_ci_sets_status(core, monkeypatch):
    # TUI-POSTPR-01: polling persists the normalized remote CI status on the task.
    task = core.create_task("CI test")
    core.update_task(task.id, remote_pr_url="https://github.com/o/r/pull/1")

    async def fake(_task):
        return "fail", []  # canonical token, already normalized by RemoteCi

    monkeypatch.setattr(core._remote_ci(), "fetch", fake)
    updated = await core.poll_remote_ci(task.id)
    assert updated.remote_ci_status == "fail"


@pytest.mark.asyncio
async def test_allow_scope_clears_drift_flag(core):
    # TUI-DRIFT-03: allow-scope clears the drift flag so the task leaves the inbox top.
    task = core.create_task("Drift test")
    core.update_task(task.id, drift=True)
    updated = await core.allow_scope(task.id)
    assert updated.drift is False


@pytest.mark.asyncio
async def test_send_back_clears_drift_appends_finding_and_reruns(core, monkeypatch):
    # TUI-DRIFT-03 / TUI-GATE-07: send-back clears drift, records a disagree Finding
    # carrying the human's comment, and re-runs the agent on the same task.
    task = core.create_task("Send-back test")
    core.update_task(task.id, drift=True)

    rerun_called = {}

    async def fake_start(task_id):
        rerun_called["id"] = task_id
        return core._require(task_id)

    monkeypatch.setattr(core, "start_task", fake_start)
    updated = await core.send_back(task.id, "out of scope: stay in src/")
    assert updated is not None
    reloaded = core._require(task.id)
    assert reloaded.drift is False
    assert reloaded.findings[-1].verdict == "disagree"
    assert reloaded.findings[-1].reply == "out of scope: stay in src/"
    assert rerun_called["id"] == task.id


@pytest.mark.asyncio
async def test_notify_runs(core, monkeypatch):
    # TUI-NOTIFY-01: the harness routes an attention event to the notifier.
    from unittest.mock import AsyncMock

    task = core.create_task("Notify test")
    monkeypatch.setattr(core._notifier(), "notify", AsyncMock())
    await core.notify(NotificationEvent.REVIEW, task.id)
    core._notifier().notify.assert_awaited_once()
