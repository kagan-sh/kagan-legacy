from pathlib import Path

import pytest

from kagan.core import git
from kagan.core.config import RepoConfig
from kagan.core.mirror import base_drift_warning, run_mirror


@pytest.fixture
async def worktree(tmp_path: Path):
    repo = tmp_path / "repo"
    await git.init_repo(repo, initial_branch="main")
    wt = tmp_path / "wt"
    await git.worktree_add(repo, wt, branch="feature", base="main")
    return repo, wt


@pytest.mark.asyncio
async def test_run_mirror_runs_declared_checks(worktree):
    # TUI-MIRROR-01: a passing declared check lands as a passed CheckResult with its output.
    _, wt = worktree
    config = RepoConfig(checks={"echo": "echo hello-mirror"})

    results = await run_mirror(wt, config)
    assert len(results) == 1
    assert results[0].name == "echo"
    assert results[0].passed is True
    assert "hello-mirror" in results[0].detail


@pytest.mark.asyncio
async def test_run_mirror_records_failure(worktree):
    # TUI-MIRROR-01: a non-zero check is recorded as failed with its exit code in detail.
    _, wt = worktree
    config = RepoConfig(checks={"fail": "exit 3"})

    results = await run_mirror(wt, config)
    assert results[0].passed is False
    assert "rc=3" in results[0].detail


@pytest.mark.asyncio
async def test_base_drift_warning_when_base_moved(worktree):
    # TUI-MIRROR-02: when base moved, codegen-drift warning names the base branch.
    repo, wt = worktree
    (repo / "upstream.txt").write_text("new\n")
    await git.commit_all(repo, "advance main")
    warning = await base_drift_warning(wt, "main")
    assert warning is not None
    assert "main" in warning


@pytest.mark.asyncio
async def test_no_base_drift_warning_when_in_sync(worktree):
    # TUI-MIRROR-02: an in-sync worktree raises no warning (None, not empty string).
    _, wt = worktree
    assert await base_drift_warning(wt, "main") is None
