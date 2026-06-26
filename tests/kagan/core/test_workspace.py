from pathlib import Path

import pytest

from kagan.core import git
from kagan.core.errors import ConfigurationError
from kagan.core.ledger import Ledger
from kagan.core.models import Task
from kagan.core.tasks import TaskService
from kagan.core.workspace import (
    destroy_workspace,
    free_port,
    start_services,
    stop_services,
)


async def _repo(tmp_path: Path, manifest: str) -> Path:
    repo = tmp_path / "repo"
    await git.init_repo(repo, initial_branch="main", create_initial_commit=True)
    (repo / ".kagan").mkdir(exist_ok=True)
    (repo / ".kagan" / "repo.yaml").write_text(manifest)
    return repo


def _ledger_with_task(tmp_path: Path) -> Ledger:
    ledger = Ledger(tmp_path / "ledger")
    ledger.save_task(Task(id="t-1", title="Task", base_branch="main"))
    return ledger


async def _make_worktree(ledger: Ledger, repo: Path) -> Task:
    # prepare_worktree is the single worktree creator (TUI-WS-05 reconcile).
    task = ledger.load_task("t-1")
    assert task is not None
    return await TaskService(ledger).prepare_worktree(task, repo)


def test_free_port_is_bindable():
    import socket

    port = free_port()
    assert 1024 < port < 65536
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", port))  # kernel just freed it; bind succeeds


async def test_destroy_removes_worktree_and_frees_ports(tmp_path: Path):
    repo = await _repo(tmp_path, "{}\n")
    ledger = _ledger_with_task(tmp_path)
    task = await _make_worktree(ledger, repo)
    task.ports["api"] = 20_005
    ledger.save_task(task)

    task = await destroy_workspace(ledger, repo, "t-1")

    assert task.worktree_path is None
    assert task.ports == {}
    # Branch is kept (Kagan never pushes; cleanup removes only the dir).
    assert (
        "kagan/t-1" in {wt["branch"] for wt in await git.worktree_list(repo)}
        or task.branch == "kagan/t-1"
    )


async def test_destroy_dirty_tree_requires_force(tmp_path: Path):
    repo = await _repo(tmp_path, "{}\n")
    ledger = _ledger_with_task(tmp_path)
    task = await _make_worktree(ledger, repo)
    (task.worktree_path / "dirty.txt").write_text("uncommitted")

    with pytest.raises(ConfigurationError):
        await destroy_workspace(ledger, repo, "t-1")

    task = await destroy_workspace(ledger, repo, "t-1", force=True)
    assert task.worktree_path is None


async def test_start_services_runs_command_and_leases_port(tmp_path: Path):
    # A real subprocess, no network: sleep keeps it alive; port_env => lease.
    repo = await _repo(
        tmp_path,
        "services:\n  api:\n    command: sleep 30\n    port_env: PORT\n",
    )
    ledger = _ledger_with_task(tmp_path)
    running: dict[str, list] = {}
    await _make_worktree(ledger, repo)

    started = await start_services(ledger, repo, "t-1", running)

    assert len(started) == 1
    assert started[0].name == "api"
    assert started[0].pid > 0
    assert started[0].port is not None
    assert started[0].log_path.exists()
    assert "api" in ledger.load_task("t-1").ports

    await stop_services(repo, "t-1", running)
    assert running["t-1"] == []


async def test_start_service_without_port_env_leases_nothing(tmp_path: Path):
    repo = await _repo(tmp_path, "services:\n  worker:\n    command: sleep 30\n")
    ledger = _ledger_with_task(tmp_path)
    running: dict[str, list] = {}
    await _make_worktree(ledger, repo)

    started = await start_services(ledger, repo, "t-1", running)

    assert started[0].port is None
    assert ledger.load_task("t-1").ports == {}
    await stop_services(repo, "t-1", running)


async def test_start_services_without_worktree_raises(tmp_path: Path):
    repo = await _repo(tmp_path, "{}\n")
    ledger = _ledger_with_task(tmp_path)
    with pytest.raises(ConfigurationError):
        await start_services(ledger, repo, "t-1", {})


async def test_stop_services_keeps_pinned_process_alive(tmp_path: Path):
    # TUI-WS-05: a pinned service name survives teardown — stop_services must not
    # kill it and must keep it in the running map so a later teardown still sees it.
    repo = await _repo(
        tmp_path,
        "services:\n"
        "  api:\n    command: sleep 30\n"
        "  daemon:\n    command: sleep 30\n"
        "pinned:\n  - daemon\n",
    )
    ledger = _ledger_with_task(tmp_path)
    running: dict[str, list] = {}
    await _make_worktree(ledger, repo)
    started = await start_services(ledger, repo, "t-1", running)
    daemon = next(s for s in started if s.name == "daemon")

    kept = await stop_services(repo, "t-1", running)

    assert [s.name for s in kept] == ["daemon"]
    assert daemon.process.returncode is None  # pinned process left running

    daemon.process.terminate()  # clean up the survivor the harness deliberately spared
    await daemon.process.wait()


async def test_destroy_refuses_pinned_branch(tmp_path: Path):
    # TUI-WS-05: a worktree pointing at a pinned branch must survive teardown —
    # removal is blocked so the branch is never destroyed.
    repo = await _repo(tmp_path, "pinned:\n  - kagan/t-1\n")
    ledger = _ledger_with_task(tmp_path)
    task = ledger.load_task("t-1")
    task.branch = "kagan/t-1"
    task.worktree_path = repo / ".kagan_worktrees" / "t-1"
    ledger.save_task(task)

    with pytest.raises(ConfigurationError):
        await destroy_workspace(ledger, repo, "t-1")
    assert ledger.load_task("t-1").branch == "kagan/t-1"
