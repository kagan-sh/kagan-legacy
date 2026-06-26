from pathlib import Path

from kagan.core import Harness
from kagan.core.enums import TaskState


def test_core_creates_ledger_root(tmp_path: Path):
    core = Harness(data_dir=tmp_path)
    assert (tmp_path / "tasks").exists()
    core.close()


def test_core_accepts_repo_root(tmp_path: Path):
    # data_dir is the ledger root; repo_root is the git repo (separate concerns).
    repo = tmp_path / "repo"
    repo.mkdir()
    core = Harness(data_dir=tmp_path, repo_root=repo)
    assert core.repo_root == repo
    core.close()


def test_core_task_round_trip(tmp_path: Path):
    # TUI-LEDGER-02: a fresh core reads tasks back from disk, no in-memory state.
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    assert task.state == TaskState.INTAKE
    core.close()

    reopened = Harness(data_dir=tmp_path)
    loaded = reopened.get_task(task.id)
    assert loaded is not None
    assert loaded.title == "Add feature"
    assert reopened.list_tasks()[0].id == task.id
    reopened.close()


def test_core_report_round_trip(tmp_path: Path):
    # MCP-INTAKE-02 via the public Harness seam: a report recorded through the
    # engine is readable from a fresh engine (stateless TUI reads disk).
    core = Harness(data_dir=tmp_path)
    task = core.create_task("Add feature")
    core.record_intake_decisions(
        task.id,
        understanding="Add dark mode",
        decisions=[{"question": "Which file?", "severity": "blocking"}],
    )
    core.record_drift(task.id, message="touched api.py")
    core.record_done(task.id)
    core.close()

    loaded = Harness(data_dir=tmp_path).get_task(task.id)
    assert loaded is not None
    assert loaded.understanding == "Add dark mode"
    assert len(loaded.decisions) == 1
    assert len(loaded.drift_concerns) == 1
    assert loaded.done_reported is True
