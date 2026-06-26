"""B-1: the MCP server must read the SAME ledger the harness wrote the task into.

The harness writes the agent's MCP client config (`.mcp.json`) into the worktree;
the agent's client then launches `kagan mcp` as a subprocess. That subprocess's
cwd is the worktree, whose git root is the worktree itself — so it cannot
re-derive the main repo's ledger. If the config omits `--data-dir`, the server
defaults to a different ledger and every report hits a task that isn't there.
"""

import json
import os
from pathlib import Path

import pytest

from kagan.core import Harness, git

AGENT = """#!/bin/sh
echo "edit" >> src/new.py
"""


def _install(bin_dir: Path, name: str, body: str) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    s = bin_dir / name
    s.write_text(body)
    s.chmod(0o755)


@pytest.fixture
async def repo(tmp_path: Path) -> Path:
    path = tmp_path / "repo"
    path.mkdir(parents=True, exist_ok=True)
    await git.init_repo(path, initial_branch="main", create_initial_commit=False)
    (path / ".kagan").mkdir(exist_ok=True)
    (path / ".kagan" / "repo.yaml").write_text("{}\n", encoding="utf-8")
    (path / "README.md").write_text("base\n", encoding="utf-8")
    await git.commit_all(path, "base")
    return path


async def _run_to_review(
    repo: Path, ledger: Path, bin_dir: Path, monkeypatch
) -> tuple[Harness, str]:
    _install(bin_dir, "fakeagent", AGENT)
    monkeypatch.setenv("PATH", f"{bin_dir}:{os.environ.get('PATH', '')}")
    core = Harness(data_dir=ledger, repo_root=repo)
    task = core.create_task("add feature")
    core.configure_task(task.id, agent_cli="fakeagent", scope=["src/**"])
    await core.start_task(task.id)
    await core.await_agent(task.id)
    return core, task.id


async def test_mcp_config_pins_the_harness_ledger(repo, tmp_path, monkeypatch):
    # B-1: the .mcp.json the agent launches must carry --data-dir == the harness's
    # ledger. Fails if _write_mcp_config drops it (the pre-fix bug).
    core, task_id = await _run_to_review(repo, tmp_path / "ledger", tmp_path / "bin", monkeypatch)
    wt = core.get_task(task_id).worktree_path
    args = json.loads((wt / ".mcp.json").read_text())["mcpServers"]["kagan"]["args"]

    assert "--data-dir" in args, f"MCP config must pin a ledger, got {args}"
    assert args[args.index("--data-dir") + 1] == str(core.data_dir)


async def test_report_through_mcp_config_reaches_the_task(repo, tmp_path, monkeypatch):
    # B-1 end-to-end: a server booted exactly as the agent would (from the config's
    # --data-dir) mutates the SAME task the TUI sees — no divergent global ledger.
    core, task_id = await _run_to_review(repo, tmp_path / "ledger", tmp_path / "bin", monkeypatch)
    wt = core.get_task(task_id).worktree_path
    args = json.loads((wt / ".mcp.json").read_text())["mcpServers"]["kagan"]["args"]
    server_data_dir = args[args.index("--data-dir") + 1]
    server_task_id = args[args.index("--task-id") + 1]

    # This is exactly what the report_done tool does: Harness(data_dir=opts.data_dir)
    # then client.record_done(task_id).
    server_core = Harness(data_dir=server_data_dir)
    server_core.record_done(server_task_id)
    server_core.close()

    assert core.get_task(task_id).done_reported is True
