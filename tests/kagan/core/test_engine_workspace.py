from pathlib import Path

from kagan.core import Harness, git


async def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    await git.init_repo(repo, initial_branch="main", create_initial_commit=True)
    (repo / ".kagan").mkdir(exist_ok=True)
    (repo / ".kagan" / "repo.yaml").write_text("{}\n")
    return repo


async def test_core_destroys_workspace(tmp_path: Path):
    # TUI-WS-06: destroy_workspace tears down the worktree the run created.
    repo = await _repo(tmp_path)
    core = Harness(data_dir=tmp_path / "data", repo_root=repo)
    task = core.create_task("Feature")

    task = await core._tasks.prepare_worktree(task, repo)
    assert task.worktree_path is not None and task.worktree_path.exists()

    task = await core.destroy_workspace(task.id)
    assert task.worktree_path is None
    core.close()


def test_workspace_map_lists_only_tasks_with_worktrees(tmp_path: Path):
    repo = tmp_path / "repo"
    (repo / ".kagan").mkdir(parents=True)
    (repo / ".kagan" / "repo.yaml").write_text("{}\n")
    core = Harness(data_dir=tmp_path / "data", repo_root=repo)
    core.create_task("No worktree")

    assert core.workspace_map() == []
    core.close()
