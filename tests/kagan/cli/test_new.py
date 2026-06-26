"""`kagan new` creates a task and runs intake up front (TUI-INTAKE-01/02)."""

import subprocess
from pathlib import Path

from click.testing import CliRunner

from kagan.cli.main import cli
from kagan.core import Harness
from kagan.core.enums import TaskState


def _git_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=path, check=True, capture_output=True)
    (path / ".kagan").mkdir()
    (path / ".kagan" / "repo.yaml").write_text("{}\n")


def test_new_writes_to_repo_scoped_ledger(tmp_path, monkeypatch):
    # Ledger scope: `kagan new` must write to the same <repo>/.kagan/state ledger the
    # TUI reads, not the global platformdirs folder — else a task created with `new`
    # is invisible to `kagan tui` in the same repo. Fails if new.py keeps the global
    # default. No KAGAN_DATA_DIR override here: we assert the repo-scoped default.
    monkeypatch.delenv("KAGAN_DATA_DIR", raising=False)  # assert the repo-scoped default
    repo = tmp_path / "repo"
    _git_repo(repo)
    monkeypatch.chdir(repo)

    async def _fake_intake(self, task_id):
        return self.update_task(task_id, understanding="x")

    monkeypatch.setattr(Harness, "run_intake", _fake_intake)

    result = CliRunner().invoke(cli, ["new", "Add dark mode"])
    assert result.exit_code == 0, result.output
    task_id = result.output.strip()

    ledger = repo / ".kagan" / "state"
    core = Harness(data_dir=ledger)
    task = core.get_task(task_id)
    core.close()
    assert task is not None and task.title == "Add dark mode"


def test_new_creates_task_and_runs_intake(tmp_path, monkeypatch):
    # TUI-INTAKE-01/02: `kagan new` persists a task in INTAKE with intake already
    # run, and prints its id. Fails if the command skips create_task or run_intake.
    monkeypatch.delenv("KAGAN_DATA_DIR", raising=False)  # assert the repo-scoped default
    repo = tmp_path / "repo"
    _git_repo(repo)
    monkeypatch.chdir(repo)

    ran: list[str] = []

    async def _fake_intake(self, task_id):
        # stand in for the plan-only agent pass: record the understanding the
        # surface reads, no subprocess.
        ran.append(task_id)
        return self.update_task(task_id, understanding="Add the thing.")

    monkeypatch.setattr(Harness, "run_intake", _fake_intake)

    result = CliRunner().invoke(cli, ["new", "Add dark mode"])
    assert result.exit_code == 0, result.output

    task_id = result.output.strip()
    assert ran == [task_id]  # intake ran for exactly this task

    core = Harness(data_dir=repo / ".kagan" / "state")
    task = core.get_task(task_id)
    core.close()
    assert task is not None
    assert task.state is TaskState.INTAKE
    assert task.understanding == "Add the thing."


def test_new_agent_and_scope_options_configure_the_task(tmp_path, monkeypatch):
    # F7: `kagan new --agent X --scope ...` must persist agent_cli + scope, mirroring
    # the interactive picker (which calls configure_task before intake). Without the
    # options the task keeps the empty defaults; this fails if new.py drops the flags.
    monkeypatch.delenv("KAGAN_DATA_DIR", raising=False)
    repo = tmp_path / "repo"
    _git_repo(repo)
    monkeypatch.chdir(repo)

    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude", "kimi"])

    async def _fake_intake(self, task_id):
        return self.update_task(task_id, understanding="x")

    monkeypatch.setattr(Harness, "run_intake", _fake_intake)

    result = CliRunner().invoke(
        cli,
        ["new", "Add dark mode", "--agent", "claude", "--scope", "src/**", "--scope", "tests/**"],
    )
    assert result.exit_code == 0, result.output
    task_id = result.output.strip()

    core = Harness(data_dir=repo / ".kagan" / "state")
    task = core.get_task(task_id)
    core.close()
    assert task is not None
    assert task.agent_cli == "claude"
    assert task.scope == ["src/**", "tests/**"]


def test_new_rejects_uninstalled_agent(tmp_path, monkeypatch):
    # F7: --agent is validated against the installed CLIs (PATH), not a static list,
    # so an unknown agent is rejected with a usage error rather than persisting a
    # non-launchable agent that only fails later at start_task.
    monkeypatch.delenv("KAGAN_DATA_DIR", raising=False)
    repo = tmp_path / "repo"
    _git_repo(repo)
    monkeypatch.chdir(repo)

    monkeypatch.setattr(Harness, "available_clis", lambda self: ["claude"])

    result = CliRunner().invoke(cli, ["new", "Add dark mode", "--agent", "bogus"])
    assert result.exit_code != 0
    assert "not available" in result.output.lower()
