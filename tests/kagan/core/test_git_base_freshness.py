from pathlib import Path

import pytest

from kagan.core import git


@pytest.mark.asyncio
async def test_base_has_moved_when_base_advanced(tmp_path: Path):
    # TUI-MIRROR-02: base advancing past the worktree must report moved + behind count.
    repo = tmp_path / "repo"
    await git.init_repo(repo, initial_branch="main")
    wt = tmp_path / "wt"
    await git.worktree_add(repo, wt, branch="feature", base="main")
    (repo / "upstream.txt").write_text("new\n")
    await git.commit_all(repo, "advance main")  # main moves ahead of the worktree

    moved, behind = await git.base_has_moved(wt, "main")
    assert moved is True
    assert behind == 1


@pytest.mark.asyncio
async def test_base_not_moved_when_in_sync(tmp_path: Path):
    # TUI-POSTPR-03: a worktree level with base must not raise a stale-base warning.
    repo = tmp_path / "repo"
    await git.init_repo(repo, initial_branch="main")
    wt = tmp_path / "wt"
    await git.worktree_add(repo, wt, branch="feature", base="main")

    moved, behind = await git.base_has_moved(wt, "main")
    assert moved is False
    assert behind == 0
